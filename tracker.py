import time
import datetime
import threading
import ctypes
import os
import sqlite3
import win32gui
import win32process
import psutil

from database import save_usage, get_setting

class WindowTracker:
    def __init__(self, db_path, idle_threshold_seconds=300):
        self.db_path = db_path
        self.idle_threshold = idle_threshold_seconds
        
        # Load initial interval from settings database, default to 30
        try:
            saved_interval = int(get_setting(db_path, "poll_interval", 30))
        except Exception:
            saved_interval = 30
        self.poll_interval = saved_interval
        
        self.stop_event = threading.Event()
        self.tracker_thread = None
        
        # Set of apps marked as Untracked (lowercase)
        self.untracked_apps = set()
        self.load_untracked_apps()
        
        # State variables
        self.current_exe = None
        self.current_title = None
        self.current_start_time = None
        
        # Buffer for database commits: {(date, exe_name, window_title): duration_seconds}
        self.buffer = {}
        self.buffer_lock = threading.Lock()
        self.last_db_commit = time.time()
        self.is_idle = False
        
        # Process name cache to minimize psutil lookups
        self.process_cache = {}

    def load_untracked_apps(self):
        """Load the list of executables marked as 'Untracked' from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT exe_name FROM app_categories WHERE category = 'Untracked'").fetchall()
            self.untracked_apps = {row['exe_name'].lower() for row in rows}
            conn.close()
            print(f"[Tracker] Loaded {len(self.untracked_apps)} untracked applications.")
        except Exception as e:
            print(f"[Tracker] Error loading untracked apps: {e}")
            self.untracked_apps = set()

    def get_idle_duration(self):
        """Return the idle duration in seconds since last user input."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            # GetTickCount returns milliseconds since system startup
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        return 0.0

    def get_active_window_info(self):
        """Get the executable name and window title of the foreground window."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None
            
        # If the window is minimized (iconic), do not track it
        if win32gui.IsIconic(hwnd):
            return None, None
            
        # Extract title
        title = win32gui.GetWindowText(hwnd)
        if not title:
            title = "System/Background Process"
            
        # Get process ID
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == 0:
            return None, None
            
        # Get exe name from cache or look it up
        exe_name = "Unknown"
        if pid in self.process_cache:
            exe_name = self.process_cache[pid]
        else:
            try:
                proc = psutil.Process(pid)
                exe_name = proc.name()
                self.process_cache[pid] = exe_name
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                exe_name = "System Process"
                
        # Clean process cache occasionally to avoid memory leaks
        if len(self.process_cache) > 200:
            self.process_cache.clear()
            
        # Check if the process is marked as Untracked (ignored) or is a default excluded process
        default_excluded = {"explorer.exe", "timetracker.exe", "python.exe", "pythonw.exe"}
        if exe_name.lower() in self.untracked_apps or exe_name.lower() in default_excluded:
            return None, None
            
        return exe_name, title

    def flush_to_buffer(self, date_str, exe_name, window_title, duration):
        """Add duration to the in-memory buffer."""
        if duration <= 0 or not exe_name:
            return
            
        key = (date_str, exe_name, window_title)
        with self.buffer_lock:
            self.buffer[key] = self.buffer.get(key, 0) + duration

    def commit_buffer_to_db(self):
        """Flush all aggregated buffer data to the SQLite database."""
        with self.buffer_lock:
            if not self.buffer:
                return
            records = [(k[0], k[1], k[2], v) for k, v in self.buffer.items()]
            self.buffer.clear()
            self.last_db_commit = time.time()
            
        try:
            save_usage(self.db_path, records)
        except Exception as e:
            print(f"[Tracker] Error committing to database: {e}")
            with self.buffer_lock:
                for date, exe, title, dur in records:
                    key = (date, exe, title)
                    self.buffer[key] = self.buffer.get(key, 0) + dur

    def start(self):
        """Start the background tracking thread."""
        self.load_untracked_apps() # Reload list on startup
        self.stop_event.clear()
        self.tracker_thread = threading.Thread(target=self._run_loop, name="TrackerThread", daemon=True)
        self.tracker_thread.start()
        print("[Tracker] Background engine started.")

    def stop(self):
        """Stop the background tracking thread and commit any remaining usage."""
        self.stop_event.set()
        if self.tracker_thread:
            self.tracker_thread.join(timeout=3)
            
        # Final flush
        if self.current_exe and self.current_start_time:
            dur = int(time.time() - self.current_start_time)
            today = datetime.date.today().isoformat()
            self.flush_to_buffer(today, self.current_exe, self.current_title, dur)
            
        self.commit_buffer_to_db()
        print("[Tracker] Background engine stopped cleanly.")

    def _run_loop(self):
        """Main tracking loop running on background thread."""
        self.current_start_time = time.time()
        self.current_exe, self.current_title = self.get_active_window_info()
        
        while not self.stop_event.is_set():
            time.sleep(self.poll_interval)
            
            # Check idle state
            idle_sec = self.get_idle_duration()
            if idle_sec >= self.idle_threshold:
                if not self.is_idle:
                    # Just transitioned to idle: flush current activity
                    if self.current_exe and self.current_start_time:
                        dur = int(time.time() - self.current_start_time)
                        today = datetime.date.today().isoformat()
                        self.flush_to_buffer(today, self.current_exe, self.current_title, dur)
                    self.commit_buffer_to_db()
                    self.is_idle = True
                    self.current_exe = None
                    self.current_title = None
                    self.current_start_time = None
                    print("[Tracker] Idle detected. Tracking paused.")
                continue
            
            # User is active
            if self.is_idle:
                self.is_idle = False
                self.current_start_time = time.time()
                self.current_exe, self.current_title = self.get_active_window_info()
                print("[Tracker] User active. Tracking resumed.")
                continue

            # Poll active window
            exe, title = self.get_active_window_info()
            
            # If active window/title changed
            if exe != self.current_exe or title != self.current_title:
                # Log duration of the previous app
                if self.current_exe and self.current_start_time:
                    dur = int(time.time() - self.current_start_time)
                    today = datetime.date.today().isoformat()
                    self.flush_to_buffer(today, self.current_exe, self.current_title, dur)
                    
                    # Force commit immediately upon app/window switch for fast UI updates
                    self.commit_buffer_to_db()
                
                # Switch to new app
                self.current_exe = exe
                self.current_title = title
                self.current_start_time = time.time()
            else:
                # Periodic database commits if same app remains open
                now = time.time()
                commit_interval = max(30.0, self.poll_interval)
                if now - self.last_db_commit >= commit_interval:
                    if self.current_exe and self.current_start_time:
                        dur = int(now - self.current_start_time)
                        today = datetime.date.today().isoformat()
                        self.flush_to_buffer(today, self.current_exe, self.current_title, dur)
                        self.current_start_time = now
                        
                    self.commit_buffer_to_db()
