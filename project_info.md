# Windows Time Tracker (Local-Only) - Full Project Documentation & Code

This document provides a comprehensive overview of the **Windows Time Tracker** project, detailing its architecture, file structure, configuration, compilation processes, key technical solutions, and a full repository copy of all un-truncated source code files. Use this file as your reference to set up, run, and continue developing the tracker in your new Git repository (`D:\Extra\tracker`).

---

## 📂 Repository File Structure
The project consists of the following key files:
1. **`requirements.txt`**: Pip dependency manifest.
2. **`database.py`**: Local SQLite database schema, aggregation queries, and settings storage.
3. **`tracker.py`**: Background thread that handles active window process polling and idle time detection.
4. **`tray.py`**: Threaded system tray icon implementation with an options menu.
5. **`ui.py`**: A lag-free CustomTkinter dark-mode dashboard with custom grid views and pop-up calendars.
6. **`main.py`**: The central coordinator and application entry point.
7. **`TimeTracker.spec`**: PyInstaller spec file for standalone executable compilation.

---

## 🛠️ Setup & Execution Guide

### 1. Install Dependencies
Ensure you have Python installed, open your shell in the project folder, and run:
```powershell
python -m pip install -r requirements.txt
```

### 2. Running the Application
To run the python script directly:
```powershell
python main.py
```
*(To run it without showing a terminal window in the background during script execution, use `pythonw main.py` instead).*

### 3. Application Behaviors
* **Quiet Startup**: The app boots silently directly into the system tray. Look for the blue clock icon in your Windows notification tray (click the `^` arrow next to the clock if hidden).
* **Opening the Dashboard**: Right-click the system tray icon and click **Open Dashboard** (or double-click the tray icon).
* **Closing the Window**: Clicking the **"X"** close button on the dashboard will hide the window back to the tray rather than terminating the process.
* **Quitting the Application**: Right-click the system tray icon and click **Quit** to save pending logs and shut down the background threads cleanly.

---

## 📦 Bundling into a Standalone `.exe`
To compile the application into a single, windowless executable that boots quietly:
1. Ensure PyInstaller is installed:
   ```powershell
   python -m pip install pyinstaller
   ```
2. Build the project using the PyInstaller configuration:
   ```powershell
   python -m PyInstaller --noconsole --onefile --collect-all customtkinter main.py -n "TimeTracker"
   ```
   Or run PyInstaller on the existing spec file:
   ```powershell
   python -m PyInstaller TimeTracker.spec
   ```
3. Your standalone executable will be generated inside:
   📁 **`dist/TimeTracker.exe`**

---

## 💡 Resolved Engineering Challenges

### 1. Smooth, Lag-Free Resizing
* **Problem**: Initially, resizing the CustomTkinter window was extremely laggy due to canvas-heavy redraw operations inside CustomTkinter frames.
* **Solution**: Bypassed canvas elements by using native `tkinter.Frame` containers for layouts and repeating item rows (such as `AppRow` and `CategorySettingsRow`). Kept progress bar widths static (`width=110`) and configured the sidebar width to weight 0 with `grid_propagate(False)` to isolate redraw calls.

### 2. Auto-Start on Windows Boot (Registry Hooks)
* **Problem**: Setting up start-on-boot required a robust mechanism that doesn't trigger admin prompts.
* **Solution**: Implemented a settings toggle that updates the local user registry (`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`) using Python's native `winreg` package.
* **Path Resolution**: Dynamically resolves the running path:
  - If frozen (`.exe`), it uses `sys.executable`.
  - If running as a script, it maps pythonw executable + script path: `"{pythonw}" "{script}"`.

### 3. Dynamic Database Relocation & Migration
* **Problem**: Allowing users to move their database location at runtime without losing active state or corrupting files.
* **Solution**: Written a folder selection handler in `ui.py`. It stops the tracker background thread to release file locks, copies the database using `shutil.copy2` to preserve transaction histories, updates `AppData\LocalTimeTracker\config.json`, triggers database re-initialization on the new path, and restarts the background tracker.

---

## 📝 Complete Un-Truncated Code Files

### 1. `requirements.txt`
```text
pystray>=0.19.5
Pillow>=10.3.0
pywin32>=306
psutil>=5.9.8
customtkinter>=5.2.2
```

### 2. `database.py`
```python
import sqlite3
import os

def get_db_connection(db_path):
    """Establish and return a connection to the SQLite database."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """Initialize the database and create tables if they do not exist."""
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    exe_name TEXT NOT NULL,
                    window_title TEXT NOT NULL,
                    duration_seconds INTEGER NOT NULL,
                    UNIQUE(date, exe_name, window_title)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_date ON app_usage(date)")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_categories (
                    exe_name TEXT PRIMARY KEY,
                    category TEXT NOT NULL
                )
            """)
    finally:
        conn.close()

def save_usage(db_path, records):
    """Save or aggregate window usage records."""
    if not records:
        return
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.executemany("""
                INSERT INTO app_usage (date, exe_name, window_title, duration_seconds)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date, exe_name, window_title)
                DO UPDATE SET duration_seconds = duration_seconds + excluded.duration_seconds
            """, records)
    finally:
        conn.close()

def get_today_total_time(db_path, date_str):
    """Return total time spent today in seconds (excluding Untracked apps)."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT SUM(u.duration_seconds) as total 
            FROM app_usage u
            LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE u.date = ? AND (c.category IS NULL OR c.category != 'Untracked')
        """, (date_str,)).fetchone()
        return row['total'] if row and row['total'] is not None else 0
    finally:
        conn.close()

def get_today_app_breakdown(db_path, date_str):
    """Return a list of dicts for app usage breakdown (excluding Untracked apps)."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT u.exe_name, SUM(u.duration_seconds) as duration
            FROM app_usage u
            LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE u.date = ? AND (c.category IS NULL OR c.category != 'Untracked')
            GROUP BY u.exe_name
            ORDER BY duration DESC
        """, (date_str,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_daily_average(db_path):
    """Return the daily average usage in seconds (excluding Untracked apps)."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT AVG(daily_sum) as avg_duration FROM (
                SELECT u.date, SUM(u.duration_seconds) as daily_sum
                FROM app_usage u
                LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
                WHERE c.category IS NULL OR c.category != 'Untracked'
                GROUP BY u.date
            )
        """).fetchone()
        return round(row['avg_duration']) if row and row['avg_duration'] is not None else 0
    finally:
        conn.close()

def get_browser_highlights(db_path, date_str):
    """Return platform-specific highlights for browser usage."""
    browser_exes = ('chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe')
    conn = get_db_connection(db_path)
    try:
        query = f"""
            SELECT window_title, duration_seconds
            FROM app_usage
            WHERE date = ? AND LOWER(exe_name) IN ({','.join(['?']*len(browser_exes))})
        """
        rows = conn.execute(query, (date_str, *browser_exes)).fetchall()
        
        platforms = {
            'YouTube': 0, 'GitHub': 0, 'Stack Overflow': 0, 'Reddit': 0,
            'ChatGPT': 0, 'Google Search': 0, 'Gmail': 0
        }
        for row in rows:
            title = row['window_title']
            dur = row['duration_seconds']
            title_lower = title.lower()
            matched = False
            for platform in platforms:
                if platform.lower() in title_lower:
                    platforms[platform] += dur
                    matched = True
                    break
            if not matched and 'google' in title_lower and 'search' in title_lower:
                platforms['Google Search'] += dur
                
        highlights = [{'platform': p, 'duration': d} for p, d in platforms.items() if d > 0]
        highlights.sort(key=lambda x: x['duration'], reverse=True)
        return highlights
    finally:
        conn.close()

def get_setting(db_path, key, default):
    """Retrieve a setting value from the database."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else default
    finally:
        conn.close()

def set_setting(db_path, key, value):
    """Save or update a setting value in the database."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO settings (key, value) 
                VALUES (?, ?) 
                ON CONFLICT(key) 
                DO UPDATE SET value = excluded.value
            """, (key, str(value)))
    finally:
        conn.close()

def get_app_categories(db_path):
    """Retrieve all categorized apps as a dictionary: {exe_name: category}."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("SELECT exe_name, category FROM app_categories").fetchall()
        return {row['exe_name']: row['category'] for row in rows}
    finally:
        conn.close()

def set_app_category(db_path, exe_name, category):
    """Assign or update a category for a specific executable name."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO app_categories (exe_name, category) 
                VALUES (?, ?) 
                ON CONFLICT(exe_name) 
                DO UPDATE SET category = excluded.category
            """, (exe_name.lower(), category))
    finally:
        conn.close()

def get_category_durations(db_path, date_str):
    """Get the total tracking duration spent today per category (excluding Untracked)."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT COALESCE(c.category, 'Uncategorized') as category, SUM(u.duration_seconds) as duration
            FROM app_usage u
            LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE u.date = ?
            GROUP BY category
        """, (date_str,)).fetchall()
        
        result = {'Productivity': 0, 'Entertainment': 0, 'Distraction': 0, 'Uncategorized': 0}
        for row in rows:
            cat = row['category']
            if cat in result:
                result[cat] += row['duration']
            elif cat != 'Untracked':
                result['Uncategorized'] += row['duration']
        return result
    finally:
        conn.close()

def get_all_tracked_apps(db_path):
    """Retrieve all unique executable names recorded in the database."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("SELECT DISTINCT exe_name FROM app_usage ORDER BY exe_name ASC").fetchall()
        return [row['exe_name'] for row in rows]
    finally:
        conn.close()

def get_weekly_average(db_path):
    """Return the average daily screen time (excluding Untracked) over the last 7 days."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT AVG(daily_sum) as avg_duration FROM (
                SELECT u.date, SUM(u.duration_seconds) as daily_sum
                FROM app_usage u
                LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
                WHERE (c.category IS NULL OR c.category != 'Untracked')
                  AND u.date >= date('now', 'localtime', '-7 days')
                GROUP BY u.date
            )
        """).fetchone()
        return round(row['avg_duration']) if row and row['avg_duration'] is not None else 0
    finally:
        conn.close()

def get_monthly_total(db_path):
    """Return the total screen time in seconds spent in the current month (excluding Untracked)."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT SUM(u.duration_seconds) as total
            FROM app_usage u
            LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE (c.category IS NULL OR c.category != 'Untracked')
              AND u.date >= date('now', 'localtime', 'start of month')
        """).fetchone()
        return row['total'] if row and row['total'] is not None else 0
    finally:
        conn.close()

def get_monthly_breakdown(db_path):
    """Return the top 5 applications spent in the current month (excluding Untracked)."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT u.exe_name, SUM(u.duration_seconds) as duration
            FROM app_usage u
            LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE (c.category IS NULL OR c.category != 'Untracked')
              AND u.date >= date('now', 'localtime', 'start of month')
            GROUP BY u.exe_name
            ORDER BY duration DESC
            LIMIT 5
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_daily_totals_for_month(db_path, year, month):
    """Retrieve daily screen time sums (excluding Untracked) for a given calendar month."""
    conn = get_db_connection(db_path)
    prefix = f"{year:04d}-{month:02d}-%"
    try:
        rows = conn.execute("""
            SELECT u.date, SUM(u.duration_seconds) as duration
            FROM app_usage u
            LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE (c.category IS NULL OR c.category != 'Untracked')
              AND u.date LIKE ?
            GROUP BY u.date
        """, (prefix,)).fetchall()
        return {row['date']: row['duration'] for row in rows}
    finally:
        conn.close()

def get_last_7_days_totals(db_path):
    """Retrieve daily screen time sums (excluding Untracked) for the last 7 calendar days."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT u.date, SUM(u.duration_seconds) as duration
            FROM app_usage u
            LEFT JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE (c.category IS NULL OR c.category != 'Untracked')
              AND u.date >= date('now', 'localtime', '-7 days')
            GROUP BY u.date
            ORDER BY u.date ASC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
```

### 3. `tracker.py`
```python
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
        
        try:
            saved_interval = int(get_setting(db_path, "poll_interval", 30))
        except Exception:
            saved_interval = 30
        self.poll_interval = saved_interval
        
        self.stop_event = threading.Event()
        self.tracker_thread = None
        self.untracked_apps = set()
        self.load_untracked_apps()
        
        self.current_exe = None
        self.current_title = None
        self.current_start_time = None
        
        self.buffer = {}
        self.buffer_lock = threading.Lock()
        self.last_db_commit = time.time()
        self.is_idle = False
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
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        return 0.0

    def get_active_window_info(self):
        """Get the executable name and window title of the foreground window."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None
            
        if win32gui.IsIconic(hwnd):
            return None, None
            
        title = win32gui.GetWindowText(hwnd)
        if not title:
            title = "System/Background Process"
            
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == 0:
            return None, None
            
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
                
        if len(self.process_cache) > 200:
            self.process_cache.clear()
            
        if exe_name.lower() in self.untracked_apps:
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
        self.load_untracked_apps()
        self.stop_event.clear()
        self.tracker_thread = threading.Thread(target=self._run_loop, name="TrackerThread", daemon=True)
        self.tracker_thread.start()
        print("[Tracker] Background engine started.")

    def stop(self):
        """Stop the background tracking thread and commit any remaining usage."""
        self.stop_event.set()
        if self.tracker_thread:
            self.tracker_thread.join(timeout=3)
            
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
            
            idle_sec = self.get_idle_duration()
            if idle_sec >= self.idle_threshold:
                if not self.is_idle:
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
            
            if self.is_idle:
                self.is_idle = False
                self.current_start_time = time.time()
                self.current_exe, self.current_title = self.get_active_window_info()
                print("[Tracker] User active. Tracking resumed.")
                continue

            exe, title = self.get_active_window_info()
            
            if exe != self.current_exe or title != self.current_title:
                if self.current_exe and self.current_start_time:
                    dur = int(time.time() - self.current_start_time)
                    today = datetime.date.today().isoformat()
                    self.flush_to_buffer(today, self.current_exe, self.current_title, dur)
                    self.commit_buffer_to_db()
                
                self.current_exe = exe
                self.current_title = title
                self.current_start_time = time.time()
            else:
                now = time.time()
                commit_interval = max(30.0, self.poll_interval)
                if now - self.last_db_commit >= commit_interval:
                    if self.current_exe and self.current_start_time:
                        dur = int(now - self.current_start_time)
                        today = datetime.date.today().isoformat()
                        self.flush_to_buffer(today, self.current_exe, self.current_title, dur)
                        self.current_start_time = now
                    self.commit_buffer_to_db()
```

### 4. `tray.py`
```python
import threading
from PIL import Image, ImageDraw
import pystray

def create_tray_icon_image():
    """Programmatically generate a clean, modern clock icon for the system tray."""
    width, height = 64, 64
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    
    # Outer dark blue-grey rounded container
    dc.rounded_rectangle([4, 4, 60, 60], radius=16, fill=(30, 41, 59, 255), outline=(71, 85, 105, 255), width=3)
    
    # Inner clock face (dodger blue / teal gradient style color)
    dc.ellipse([16, 16, 48, 48], fill=(59, 130, 246, 255))
    
    # Clock hands (white)
    dc.line([32, 32, 32, 22], fill=(255, 255, 255, 255), width=3)
    dc.line([32, 32, 42, 32], fill=(255, 255, 255, 255), width=3)
    
    return image

class SystemTrayApp:
    def __init__(self, on_open_dashboard, on_quit):
        self.on_open_dashboard = on_open_dashboard
        self.on_quit = on_quit
        self.icon = None
        self.tray_thread = None

    def start(self):
        """Start the system tray icon loop in a background thread."""
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", self._handle_open, default=True),
            pystray.MenuItem("Quit", self._handle_quit)
        )
        
        self.icon = pystray.Icon(
            "TimeTrackerIcon",
            create_tray_icon_image(),
            "Time Tracker",
            menu=menu
        )
        
        # Run pystray run loop on a dedicated thread
        self.tray_thread = threading.Thread(target=self.icon.run, name="TrayIconThread", daemon=True)
        self.tray_thread.start()
        print("[Tray] System tray icon thread started.")

    def stop(self):
        """Stop the system tray icon."""
        if self.icon:
            self.icon.stop()
            print("[Tray] System tray icon stopped.")

    def _handle_open(self, icon, item):
        """Trigger open dashboard callback."""
        if self.on_open_dashboard:
            self.on_open_dashboard()

    def _handle_quit(self, icon, item):
        """Trigger quit callback."""
        if self.on_quit:
            self.on_quit()
```

### 5. `ui.py`
```python
import datetime
import os
import shutil
import json
import tkinter as tk
import calendar
import winreg
import sys
import customtkinter as ctk
import database

# Configure customtkinter colors and themes
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CATEGORY_COLORS = {
    'Productivity': '#10b981',    # Emerald Green
    'Entertainment': '#3b82f6',   # Blue
    'Distraction': '#ef4444',     # Coral Red
    'Untracked': '#475569',       # Slate/Dark Grey
    'Uncategorized': '#64748b'    # Slate Grey
}

CATEGORY_ICONS = {
    'Productivity': '🟢',
    'Entertainment': '🔵',
    'Distraction': '🔴',
    'Untracked': '🚫',
    'Uncategorized': '⚫'
}

def format_duration(seconds):
    """Format duration in seconds to a human-readable string."""
    if seconds <= 0:
        return "0s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)

class AppRow(tk.Frame):
    """Custom compact row displaying application usage. Inherits from tk.Frame for maximum resize performance."""
    def __init__(self, master, exe_name, duration, total_duration, max_duration, category, bg_color="#1e293b"):
        super().__init__(master, bg=bg_color)
        percentage_total = (duration / total_duration) * 100 if total_duration > 0 else 0
        bar_value = duration / max_duration if max_duration > 0 else 0
        bar_color = CATEGORY_COLORS.get(category, '#64748b')
        
        self.name_label = ctk.CTkLabel(self, text=exe_name, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), anchor="w", fg_color=bg_color)
        self.name_label.pack(side="left", padx=(5, 5), fill="x", expand=True)
        
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", width=110, height=8, fg_color="#020617", progress_color=bar_color)
        self.progress_bar.set(bar_value)
        self.progress_bar.pack(side="left", padx=5)
        
        info_text = f"{percentage_total:.0f}% ({format_duration(duration)})"
        self.info_label = ctk.CTkLabel(self, text=info_text, font=ctk.CTkFont(family="Segoe UI", size=10), anchor="e", width=70, fg_color=bg_color)
        self.info_label.pack(side="right", padx=(5, 5))

class CategorySettingsRow(tk.Frame):
    """Compact card in Settings for mapping an executable name to a category."""
    def __init__(self, master, exe_name, current_category, on_change_callback):
        super().__init__(master, bg="#1e293b")
        self.exe_name = exe_name
        self.on_change_callback = on_change_callback
        
        self.name_label = ctk.CTkLabel(self, text=exe_name, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), anchor="w", fg_color="#1e293b")
        self.name_label.pack(side="left", padx=10, fill="x", expand=True)
        
        self.cat_menu = ctk.CTkOptionMenu(
            self,
            values=["Productivity", "Entertainment", "Distraction", "Untracked", "Uncategorized"],
            command=self._on_changed,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            width=120,
            fg_color="#334155",
            button_color="#475569",
            button_hover_color="#64748b"
        )
        self.cat_menu.set(current_category)
        self.cat_menu.pack(side="right", padx=10, pady=8)

    def _on_changed(self, choice):
        self.on_change_callback(self.exe_name, choice)

class WeeklyCalendarWindow(ctk.CTkToplevel):
    """Popup window showing daily totals for the last 7 calendar days."""
    def __init__(self, parent, db_path):
        super().__init__(parent)
        self.db_path = db_path
        self.title("Weekly Screen Time Breakdown")
        self.geometry("520x420")
        self.minsize(450, 350)
        self.configure(fg_color="#020617")
        self.after(10, self.lift)
        
        header_lbl = ctk.CTkLabel(self, text="📅 Weekly Screen Time History", font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), text_color="#10b981", anchor="w")
        header_lbl.pack(fill="x", padx=20, pady=(20, 5))
        
        desc_lbl = ctk.CTkLabel(self, text="Total active time logged for each of the last 7 days.", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#94a3b8", anchor="w")
        desc_lbl.pack(fill="x", padx=20, pady=(0, 15))
        
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        data = database.get_last_7_days_totals(self.db_path)
        if data:
            max_duration = max(day['duration'] for day in data)
            total_duration = sum(day['duration'] for day in data)
            
            summary_lbl = ctk.CTkLabel(scroll, text=f"Total Screen Time (Past 7 Days): {format_duration(total_duration)}", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color="#f8fafc", anchor="w")
            summary_lbl.pack(fill="x", padx=10, pady=(0, 10))
            
            for item in data:
                date_str = item['date']
                dur = item['duration']
                dt = datetime.date.fromisoformat(date_str)
                formatted_date = dt.strftime("%A, %b %d")
                
                row = tk.Frame(scroll, bg="#1e293b")
                row.pack(fill="x", pady=4, padx=5)
                
                lbl = ctk.CTkLabel(row, text=formatted_date, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), anchor="w", width=150, fg_color="#1e293b")
                lbl.pack(side="left", padx=10, pady=8)
                
                bar_value = dur / max_duration if max_duration > 0 else 0
                bar = ctk.CTkProgressBar(row, orientation="horizontal", height=8, fg_color="#020617", progress_color="#10b981")
                bar.set(bar_value)
                bar.pack(side="left", fill="x", expand=True, padx=10)
                
                val = ctk.CTkLabel(row, text=format_duration(dur), font=ctk.CTkFont(family="Segoe UI", size=12), anchor="e", width=80, fg_color="#1e293b")
                val.pack(side="right", padx=10)
        else:
            no_data = ctk.CTkLabel(scroll, text="No active tracking records found for the past 7 days.", font=ctk.CTkFont(family="Segoe UI", size=13), text_color="#64748b")
            no_data.pack(pady=40)

class MonthlyCalendarWindow(ctk.CTkToplevel):
    """Popup window showing an interactive monthly grid of logged screen times."""
    def __init__(self, parent, db_path):
        super().__init__(parent)
        self.db_path = db_path
        today = datetime.date.today()
        self.year = today.year
        self.month = today.month
        
        self.title("Monthly Screen Time Calendar")
        self.geometry("680x560")
        self.minsize(600, 480)
        self.configure(fg_color="#020617")
        self.after(10, self.lift)
        
        self.header_frame = tk.Frame(self, bg="#020617")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 5))
        
        self.month_title_label = ctk.CTkLabel(self.header_frame, text="", font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), text_color="#3b82f6", anchor="w")
        self.month_title_label.pack(side="left", fill="x", expand=True)
        
        btn_prev = ctk.CTkButton(self.header_frame, text="<", command=self._prev_month, width=32, height=32, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), fg_color="#1e293b", hover_color="#334155")
        btn_prev.pack(side="right", padx=3)
        
        btn_next = ctk.CTkButton(self.header_frame, text=">", command=self._next_month, width=32, height=32, font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), fg_color="#1e293b", hover_color="#334155")
        btn_next.pack(side="right", padx=3)
        
        desc_lbl = ctk.CTkLabel(self, text="Color highlights represent daily active time (Dark Blue for light, Bright Blue for heavy usage).", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#94a3b8", anchor="w")
        desc_lbl.pack(fill="x", padx=20, pady=(0, 15))
        
        self.grid_container = tk.Frame(self, bg="#020617")
        self.grid_container.pack(fill="both", expand=True, padx=15, pady=5)
        self.draw_calendar()

    def _prev_month(self):
        self.month -= 1
        if self.month < 1:
            self.month = 12
            self.year -= 1
        self.draw_calendar()

    def _next_month(self):
        self.month += 1
        if self.month > 12:
            self.month = 1
            self.year += 1
        self.draw_calendar()

    def draw_calendar(self):
        month_name = calendar.month_name[self.month]
        self.month_title_label.configure(text=f"📅 {month_name} {self.year}")
        for widget in self.grid_container.winfo_children():
            widget.destroy()
        for col in range(7):
            self.grid_container.grid_columnconfigure(col, weight=1)
            
        days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for col, day_name in enumerate(days_of_week):
            lbl = ctk.CTkLabel(self.grid_container, text=day_name, font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color="#94a3b8")
            lbl.grid(row=0, column=col, padx=4, pady=6, sticky="ew")
            
        totals = database.get_daily_totals_for_month(self.db_path, self.year, self.month)
        cal_matrix = calendar.monthcalendar(self.year, self.month)
        for r in range(len(cal_matrix) + 1):
            self.grid_container.grid_rowconfigure(r, weight=1)
            
        for r_idx, week in enumerate(cal_matrix):
            for c_idx, day in enumerate(week):
                if day == 0:
                    cell = tk.Frame(self.grid_container, bg="#020617")
                    cell.grid(row=r_idx+1, column=c_idx, padx=4, pady=4, sticky="nsew")
                    continue
                date_str = f"{self.year:04d}-{self.month:02d}-{day:02d}"
                duration = totals.get(date_str, 0)
                if duration == 0:
                    bg_color = "#1e293b"
                    text_color = "#64748b"
                elif duration < 7200:
                    bg_color = "#1e3a8a"
                    text_color = "#93c5fd"
                elif duration < 18000:
                    bg_color = "#3b82f6"
                    text_color = "#eff6ff"
                else:
                    bg_color = "#2563eb"
                    text_color = "#f8fafc"
                cell = tk.Frame(self.grid_container, bg=bg_color, borderwidth=1, relief="ridge")
                cell.grid(row=r_idx+1, column=c_idx, padx=4, pady=4, sticky="nsew")
                
                day_lbl = ctk.CTkLabel(cell, text=str(day), font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=text_color, fg_color=bg_color)
                day_lbl.pack(anchor="nw", padx=6, pady=4)
                if duration > 0:
                    dur_lbl = ctk.CTkLabel(cell, text=format_duration(duration), font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=text_color, fg_color=bg_color)
                    dur_lbl.pack(anchor="se", padx=6, pady=(5, 4))

class TrackerDashboard(ctk.CTk):
    def __init__(self, db_path, tracker=None):
        super().__init__()
        self.db_path = db_path
        self.tracker = tracker
        self.title("Windows Time Tracker")
        self.geometry("950x650")
        self.minsize(850, 550)
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._setup_sidebar()
        self._setup_main_panel()
        self.refresh_data()
        self.schedule_refresh()

    def _setup_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#0f172a")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="⏱️ Tracker", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"), text_color="#3b82f6")
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="w")
        
        self.today_card = ctk.CTkFrame(self.sidebar_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.today_card.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        
        self.today_card_title = ctk.CTkLabel(self.today_card, text="SCREEN TIME TODAY", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94a3b8")
        self.today_card_title.pack(padx=15, pady=(10, 2))
        self.today_time_label = ctk.CTkLabel(self.today_card, text="0h 0m", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color="#f8fafc")
        self.today_time_label.pack(padx=15, pady=(2, 10))
        
        self.avg_card = ctk.CTkFrame(self.sidebar_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.avg_card.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        
        self.avg_card_title = ctk.CTkLabel(self.avg_card, text="DAILY AVERAGE", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#94a3b8")
        self.avg_card_title.pack(padx=15, pady=(10, 2))
        self.avg_time_label = ctk.CTkLabel(self.avg_card, text="0h 0m", font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color="#f8fafc")
        self.avg_time_label.pack(padx=15, pady=(2, 10))

        self.refresh_btn = ctk.CTkButton(self.sidebar_frame, text="Sync & Refresh", command=self.refresh_data, fg_color="#3b82f6", hover_color="#2563eb", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), height=32)
        self.refresh_btn.grid(row=3, column=0, padx=15, pady=15, sticky="ew")
        
        self.footer_label = ctk.CTkLabel(self.sidebar_frame, text="Local Time Tracker v1.8", font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#64748b")
        self.footer_label.grid(row=5, column=0, padx=20, pady=20, sticky="s")

    def _setup_main_panel(self):
        self.main_frame = tk.Frame(self, bg="#020617")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        self.view_selector = ctk.CTkSegmentedButton(
            self.main_frame,
            values=["App Breakdown", "Browser Highlights", "History & Reports", "Settings"],
            command=self._switch_view,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            selected_color="#3b82f6",
            unselected_color="#1e293b",
            selected_hover_color="#2563eb"
        )
        self.view_selector.set("App Breakdown")
        self.view_selector.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        self.apps_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.apps_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        
        self.browser_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.history_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.settings_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        
        self.rendered_grid_container = None
        self.rendered_browser_rows = []

    def _switch_view(self, value):
        self.apps_scroll.grid_forget()
        self.browser_scroll.grid_forget()
        self.history_scroll.grid_forget()
        self.settings_scroll.grid_forget()
        
        if value == "App Breakdown":
            self.apps_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.refresh_data()
        elif value == "Browser Highlights":
            self.browser_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.refresh_data()
        elif value == "History & Reports":
            self.history_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.refresh_data()
        elif value == "Settings":
            self.settings_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.build_settings_tab()

    def build_settings_tab(self):
        for widget in self.settings_scroll.winfo_children():
            widget.destroy()
            
        title_settings = ctk.CTkLabel(self.settings_scroll, text="⚙️ Tracker Settings", font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), anchor="w", text_color="#3b82f6")
        title_settings.pack(fill="x", padx=10, pady=(15, 10))
        
        interval_card = ctk.CTkFrame(self.settings_scroll, fg_color="#1e293b", corner_radius=8)
        interval_card.pack(fill="x", padx=10, pady=5)
        
        interval_label = ctk.CTkLabel(interval_card, text="Polling Interval", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"))
        interval_label.pack(side="left", padx=15, pady=15)
        
        current_val = database.get_setting(self.db_path, "poll_interval", "30")
        current_option = f"{current_val} seconds"
        
        self.interval_menu = ctk.CTkOptionMenu(
            interval_card,
            values=["10 seconds", "30 seconds", "60 seconds"],
            command=self._change_poll_interval,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=140,
            fg_color="#334155",
            button_color="#475569",
            button_hover_color="#64748b"
        )
        self.interval_menu.set(current_option)
        self.interval_menu.pack(side="right", padx=15, pady=15)
        
        startup_card = ctk.CTkFrame(self.settings_scroll, fg_color="#1e293b", corner_radius=8)
        startup_card.pack(fill="x", padx=10, pady=5)
        
        is_startup_enabled = False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, "LocalTimeTracker")
                is_startup_enabled = True
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass
            
        self.startup_switch = ctk.CTkSwitch(
            startup_card,
            text="Run at Windows Startup",
            command=self._toggle_startup,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            progress_color="#3b82f6",
            fg_color="#334155"
        )
        if is_startup_enabled:
            self.startup_switch.select()
        else:
            self.startup_switch.deselect()
        self.startup_switch.pack(side="left", padx=15, pady=15)
        
        db_card = ctk.CTkFrame(self.settings_scroll, fg_color="#1e293b", corner_radius=8)
        db_card.pack(fill="x", padx=10, pady=5)
        
        db_info_frame = ctk.CTkFrame(db_card, fg_color="transparent")
        db_info_frame.pack(side="left", padx=15, pady=10, fill="x", expand=True)
        
        db_label = ctk.CTkLabel(db_info_frame, text="Database Directory", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), anchor="w")
        db_label.pack(fill="x")
        
        self.db_path_label = ctk.CTkLabel(db_info_frame, text=os.path.dirname(self.db_path), font=ctk.CTkFont(family="Segoe UI", size=10), text_color="#94a3b8", anchor="w")
        self.db_path_label.pack(fill="x")
        
        self.db_status_label = ctk.CTkLabel(db_info_frame, text="", font=ctk.CTkFont(family="Segoe UI", size=10), anchor="w")
        self.db_status_label.pack(fill="x")
        
        browse_btn = ctk.CTkButton(db_card, text="Change Folder", command=self._change_db_folder, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), width=120, fg_color="#334155", hover_color="#475569")
        browse_btn.pack(side="right", padx=15, pady=15)
        
        title_categories = ctk.CTkLabel(self.settings_scroll, text="🏷️ App Categories Settings", font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), anchor="w", text_color="#3b82f6")
        title_categories.pack(fill="x", padx=10, pady=(25, 5))
        
        desc_label = ctk.CTkLabel(self.settings_scroll, text="Group and configure categories. Mark applications as 'Untracked' to exclude them entirely.", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#94a3b8", anchor="w")
        desc_label.pack(fill="x", padx=10, pady=(0, 15))
        
        tracked_apps = database.get_all_tracked_apps(self.db_path)
        categories = database.get_app_categories(self.db_path)
        grouped_settings = {'Productivity': [], 'Entertainment': [], 'Distraction': [], 'Untracked': [], 'Uncategorized': []}
        
        for app in tracked_apps:
            cat = categories.get(app.lower(), "Uncategorized")
            if cat in grouped_settings:
                grouped_settings[cat].append(app)
            else:
                grouped_settings['Uncategorized'].append(app)
                
        has_apps = False
        for cat_name in ['Productivity', 'Entertainment', 'Distraction', 'Untracked', 'Uncategorized']:
            apps_list = grouped_settings[cat_name]
            if not apps_list:
                continue
            has_apps = True
            color = CATEGORY_COLORS[cat_name]
            icon = CATEGORY_ICONS[cat_name]
            
            cat_header = ctk.CTkLabel(self.settings_scroll, text=f"{icon} {cat_name.upper()} APPS ({len(apps_list)})", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=color, anchor="w")
            cat_header.pack(fill="x", padx=10, pady=(15, 5))
            
            grid_frame = tk.Frame(self.settings_scroll, bg="#020617")
            grid_frame.pack(fill="x", padx=5, pady=5)
            grid_frame.grid_columnconfigure(0, weight=1)
            grid_frame.grid_columnconfigure(1, weight=1)
            
            for idx, app in enumerate(apps_list):
                r = idx // 2
                c = idx % 2
                card = CategorySettingsRow(grid_frame, exe_name=app, current_category=cat_name, on_change_callback=self._update_app_category)
                card.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
                
        if not has_apps:
            no_apps_lbl = ctk.CTkLabel(self.settings_scroll, text="No tracked applications found to categorize yet.", font=ctk.CTkFont(family="Segoe UI", size=13), text_color="#64748b")
            no_apps_lbl.pack(pady=30)

    def _change_poll_interval(self, choice):
        seconds = int(choice.split()[0])
        database.set_setting(self.db_path, "poll_interval", seconds)
        if self.tracker:
            self.tracker.poll_interval = seconds
            print(f"[UI] Tracker polling interval changed to: {seconds}s")
            
    def _update_app_category(self, exe_name, category):
        database.set_app_category(self.db_path, exe_name, category)
        if self.tracker:
            self.tracker.load_untracked_apps()
        self.build_settings_tab()

    def _toggle_startup(self):
        enabled = self.startup_switch.get() == 1
        REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
        REG_NAME = "LocalTimeTracker"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_WRITE)
            if enabled:
                if getattr(sys, 'frozen', False):
                    exe_path = sys.executable
                else:
                    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                    script_path = os.path.abspath(sys.argv[0])
                    exe_path = f'"{python_exe}" "{script_path}"'
                winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, exe_path)
                print(f"[UI] Enabled run at startup in registry: {exe_path}")
            else:
                try:
                    winreg.DeleteValue(key, REG_NAME)
                    print("[UI] Disabled run at startup in registry.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[UI] Error toggling startup registry key: {e}")

    def _change_db_folder(self):
        from tkinter import filedialog
        current_folder = os.path.dirname(self.db_path)
        new_folder = filedialog.askdirectory(initialdir=current_folder, title="Select Database Directory")
        if not new_folder:
            return
            
        new_folder = os.path.normpath(new_folder)
        new_db_dir = os.path.join(new_folder, "LocalTimeTracker")
        if new_db_dir == current_folder:
            return
            
        try:
            os.makedirs(new_db_dir, exist_ok=True)
            new_db_path = os.path.join(new_db_dir, "tracker.db")
            self.db_status_label.configure(text="Migrating database...", text_color="#3b82f6")
            self.update_idletasks()
            
            was_tracking = False
            if self.tracker and self.tracker.tracker_thread and self.tracker.tracker_thread.is_alive():
                was_tracking = True
                self.tracker.stop()
                
            if os.path.exists(self.db_path):
                shutil.copy2(self.db_path, new_db_path)
                
            self.db_path = new_db_path
            if self.tracker:
                self.tracker.db_path = new_db_path
                
            config_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LocalTimeTracker")
            config_path = os.path.join(config_dir, "config.json")
            os.makedirs(config_dir, exist_ok=True)
            with open(config_path, "w") as f:
                json.dump({"db_folder": new_db_dir}, f)
                
            database.init_db(new_db_path)
            if was_tracking:
                self.tracker.start()
                
            self.db_path_label.configure(text=new_db_dir)
            self.refresh_data()
            self.db_status_label.configure(text="✅ Database directory updated and migrated successfully!", text_color="#10b981")
        except Exception as e:
            self.db_status_label.configure(text=f"❌ Error moving database: {e}", text_color="#ef4444")

    def open_weekly_popup(self):
        WeeklyCalendarWindow(self, self.db_path)

    def open_monthly_popup(self):
        MonthlyCalendarWindow(self, self.db_path)

    def build_history_tab(self):
        for widget in self.history_scroll.winfo_children():
            widget.destroy()
            
        title_history = ctk.CTkLabel(self.history_scroll, text="📈 History & Reports", font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"), anchor="w", text_color="#3b82f6")
        title_history.pack(fill="x", padx=10, pady=(15, 10))
        
        stats_grid_frame = tk.Frame(self.history_scroll, bg="#020617")
        stats_grid_frame.pack(fill="x", padx=5, pady=5)
        stats_grid_frame.grid_columnconfigure(0, weight=1)
        stats_grid_frame.grid_columnconfigure(1, weight=1)
        
        weekly_avg = database.get_weekly_average(self.db_path)
        monthly_total = database.get_monthly_total(self.db_path)
        
        def bind_card(widget, callback):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda e: callback())
        
        card1 = ctk.CTkFrame(stats_grid_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        card1.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        lbl1 = ctk.CTkLabel(card1, text="PAST 7 DAYS DAILY AVERAGE (CLICK TO VIEW)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#10b981")
        lbl1.pack(padx=15, pady=(12, 2))
        val1 = ctk.CTkLabel(card1, text=format_duration(weekly_avg), font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color="#f8fafc")
        val1.pack(padx=15, pady=(2, 12))
        
        bind_card(card1, self.open_weekly_popup)
        bind_card(lbl1, self.open_weekly_popup)
        bind_card(val1, self.open_weekly_popup)
        
        card2 = ctk.CTkFrame(stats_grid_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        card2.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")
        lbl2 = ctk.CTkLabel(card2, text="THIS MONTH'S TOTAL TIME (CLICK TO VIEW)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color="#3b82f6")
        lbl2.pack(padx=15, pady=(12, 2))
        val2 = ctk.CTkLabel(card2, text=format_duration(monthly_total), font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), text_color="#f8fafc")
        val2.pack(padx=15, pady=(2, 12))
        
        bind_card(card2, self.open_monthly_popup)
        bind_card(lbl2, self.open_monthly_popup)
        bind_card(val2, self.open_monthly_popup)
        
        top_title = ctk.CTkLabel(self.history_scroll, text="🏆 Top Apps This Month", font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), anchor="w", text_color="#3b82f6")
        top_title.pack(fill="x", padx=10, pady=(25, 5))
        
        desc_top = ctk.CTkLabel(self.history_scroll, text="Most used applications in the current calendar month.", font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#94a3b8", anchor="w")
        desc_top.pack(fill="x", padx=10, pady=(0, 10))
        
        monthly_apps = database.get_monthly_breakdown(self.db_path)
        app_categories = database.get_app_categories(self.db_path)
        if monthly_apps:
            max_monthly_sec = monthly_apps[0]['duration']
            for app in monthly_apps:
                exe = app['exe_name']
                cat = app_categories.get(exe.lower(), "Uncategorized")
                row = AppRow(self.history_scroll, exe_name=exe, duration=app['duration'], total_duration=monthly_total, max_duration=max_monthly_sec, category=cat)
                row.pack(fill="x", padx=10, pady=4)
        else:
            no_monthly_lbl = ctk.CTkLabel(self.history_scroll, text="No monthly application tracking history recorded yet.", font=ctk.CTkFont(family="Segoe UI", size=13), text_color="#64748b")
            no_monthly_lbl.pack(pady=30)

    def refresh_data(self):
        today = datetime.date.today().isoformat()
        today_total_sec = database.get_today_total_time(self.db_path, today)
        daily_avg_sec = database.get_daily_average(self.db_path)
        self.today_time_label.configure(text=format_duration(today_total_sec))
        self.avg_time_label.configure(text=format_duration(daily_avg_sec))
        
        active_tab = self.view_selector.get()
        if active_tab == "App Breakdown":
            if self.rendered_grid_container:
                self.rendered_grid_container.destroy()
                self.rendered_grid_container = None
                
            self.rendered_grid_container = tk.Frame(self.apps_scroll, bg="#020617")
            self.rendered_grid_container.pack(fill="both", expand=True, padx=5, pady=5)
            self.rendered_grid_container.grid_columnconfigure(0, weight=1)
            self.rendered_grid_container.grid_columnconfigure(1, weight=1)
            
            app_breakdown = database.get_today_app_breakdown(self.db_path, today)
            app_categories = database.get_app_categories(self.db_path)
            cat_durations = database.get_category_durations(self.db_path, today)
            
            grouped_apps = {'Productivity': [], 'Entertainment': [], 'Distraction': [], 'Uncategorized': []}
            for app in app_breakdown:
                exe = app['exe_name']
                cat = app_categories.get(exe.lower(), "Uncategorized")
                if cat == 'Untracked':
                    continue
                if cat in grouped_apps:
                    grouped_apps[cat].append(app)
                else:
                    grouped_apps['Uncategorized'].append(app)
                    
            coords = {'Productivity': (0, 0), 'Entertainment': (0, 1), 'Distraction': (1, 0), 'Uncategorized': (1, 1)}
            overall_max_sec = app_breakdown[0]['duration'] if app_breakdown else 0
            
            for cat_name in ['Productivity', 'Entertainment', 'Distraction', 'Uncategorized']:
                color = CATEGORY_COLORS[cat_name]
                icon = CATEGORY_ICONS[cat_name]
                row_val, col_val = coords[cat_name]
                
                panel = ctk.CTkFrame(self.rendered_grid_container, fg_color="#1e293b", corner_radius=10, border_width=1, border_color="#334155")
                panel.grid(row=row_val, column=col_val, padx=10, pady=10, sticky="nsew")
                
                cat_sec_time = cat_durations.get(cat_name, 0)
                header_text = f"{icon} {cat_name.upper()} — {format_duration(cat_sec_time)}"
                header_lbl = ctk.CTkLabel(panel, text=header_text, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=color, anchor="w")
                header_lbl.pack(fill="x", padx=15, pady=(12, 8))
                
                apps_in_cat = grouped_apps[cat_name]
                if apps_in_cat:
                    for app in apps_in_cat:
                        app_row = AppRow(panel, exe_name=app['exe_name'], duration=app['duration'], total_duration=today_total_sec, max_duration=overall_max_sec, category=cat_name)
                        app_row.pack(fill="x", padx=10, pady=4)
                else:
                    empty_lbl = ctk.CTkLabel(panel, text="No activity tracked today", font=ctk.CTkFont(family="Segoe UI", size=11), text_color="#64748b", anchor="w")
                    empty_lbl.pack(fill="x", padx=15, pady=10)

        elif active_tab == "Browser Highlights":
            for row in self.rendered_browser_rows:
                row.destroy()
            self.rendered_browser_rows.clear()
            
            browser_highlights = database.get_browser_highlights(self.db_path, today)
            if browser_highlights:
                total_browser_sec = sum(b['duration'] for b in browser_highlights)
                max_browser_sec = browser_highlights[0]['duration']
                
                for item in browser_highlights:
                    title_lower = item['platform'].lower()
                    cat = "Uncategorized"
                    if title_lower in ("youtube", "reddit"):
                        cat = "Distraction"
                    elif title_lower in ("github", "stack overflow", "chatgpt"):
                        cat = "Productivity"
                    elif title_lower in ("google search", "gmail"):
                        cat = "Entertainment"
                        
                    row = AppRow(self.browser_scroll, exe_name=item['platform'], duration=item['duration'], total_duration=total_browser_sec, max_duration=max_browser_sec, category=cat)
                    row.pack(fill="x", pady=4)
                    self.rendered_browser_rows.append(row)
            else:
                lbl = ctk.CTkLabel(self.browser_scroll, text="No active browser highlights recorded today.", font=ctk.CTkFont(family="Segoe UI", size=13), text_color="#64748b")
                lbl.pack(pady=40)
                self.rendered_browser_rows.append(lbl)

        elif active_tab == "History & Reports":
            self.build_history_tab()

    def schedule_refresh(self):
        self.refresh_data()
        self.after(5000, self.schedule_refresh)

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide_window(self):
        self.withdraw()
```

### 6. `main.py`
```python
import os
import sys
import json
import database
from tracker import WindowTracker
from tray import SystemTrayApp
from ui import TrackerDashboard

def get_config_path():
    """Resolve the configuration file path inside Local AppData."""
    app_data_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), 
        "LocalTimeTracker"
    )
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "config.json")

def load_db_folder():
    """Load the saved database folder or default to Documents/LocalTimeTracker."""
    config_path = get_config_path()
    default_folder = os.path.join(os.path.expanduser("~"), "Documents", "LocalTimeTracker")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                folder = data.get("db_folder", default_folder)
                if folder:
                    return folder
        except Exception:
            pass
            
    return default_folder

def main():
    db_folder = load_db_folder()
    os.makedirs(db_folder, exist_ok=True)
    db_path = os.path.join(db_folder, "tracker.db")
    
    print(f"[Main] Initializing database at: {db_path}")
    database.init_db(db_path)
    
    # Initialize components
    tracker = WindowTracker(db_path)
    
    # Initialize the dashboard UI (running on the main thread)
    app = TrackerDashboard(db_path, tracker=tracker)
    
    # Withdraw the window immediately so that the app starts quietly in the system tray
    app.withdraw()

    # Define thread-safe tray callbacks
    def show_dashboard():
        print("[Main] Showing dashboard window.")
        app.after(0, app.show_window)

    def quit_application():
        print("[Main] Initiating application shutdown...")
        # 1. Stop the tracker (flushes remaining data and joins thread)
        tracker.stop()
        # 2. Stop the tray icon
        tray.stop()
        # 3. Destroy Tkinter window to terminate mainloop
        app.after(0, app.destroy)

    # Initialize and start system tray
    tray = SystemTrayApp(on_open_dashboard=show_dashboard, on_quit=quit_application)
    tray.start()
    
    # Start background tracker
    tracker.start()
    
    # Start the Tkinter main loop (blocking main thread)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        # Handle ctrl+c in terminal during testing
        print("[Main] Ctrl+C detected. Cleaning up...")
        quit_application()
        sys.exit(0)

if __name__ == "__main__":
    main()
```

### 7. `TimeTracker.spec`
```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TimeTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

---

## 📈 Git Integration & Workspace Transition
Now that all source code files have been copied to `D:\Extra\tracker`:
1. **Initialize Git**:
   Open a terminal in `D:\Extra\tracker` and initialize your repository:
   ```powershell
   git init
   ```
2. **Create `.gitignore`**:
   Create a `.gitignore` file to avoid checking in virtual environments, caches, and build folders:
   ```text
   __pycache__/
   *.pyc
   build/
   dist/
   *.db
   *.json
   ```
3. **Commit Your Code**:
   Add and commit all tracker files:
   ```powershell
   git add .
   git commit -m "Initial commit of Windows Time Tracker application"
   ```
4. **Transition Safely**:
   You can now open `D:\Extra\tracker` as your active workspace in your IDE without losing any source code or progress files!
