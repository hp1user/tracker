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
import re

def get_db_connection(db_path):
    """Establish and return a connection to the SQLite database."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """Initialize the database and create tables if they do not exist."""
    # Ensure parent directories exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    conn = get_db_connection(db_path)
    try:
        with conn:
            # Main app usage table
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
            # Index for fast date queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_date ON app_usage(date)")
            
            # Persistent settings table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # App category mapping table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_categories (
                    exe_name TEXT PRIMARY KEY,
                    category TEXT NOT NULL
                )
            """)
            
            # Check if track_details column exists in app_categories, and add if missing
            cursor = conn.execute("PRAGMA table_info(app_categories)")
            columns = [info[1] for info in cursor.fetchall()]
            if "track_details" not in columns:
                conn.execute("ALTER TABLE app_categories ADD COLUMN track_details INTEGER DEFAULT 0")
                
            # Migrate any existing "Unsaved" window titles to ""
            migrate_unsaved_records(conn)
    finally:
        conn.close()

def save_usage(db_path, records):
    """
    Save or aggregate window usage records.
    records is a list of tuples: (date, exe_name, window_title, duration_seconds)
    """
    if not records:
        return
        
    # Clean records: if the project name extracts to "Unsaved", save with empty window_title
    cleaned_records = []
    for date, exe, title, dur in records:
        project = extract_project_name(exe, title)
        if project == "Unsaved":
            cleaned_records.append((date, exe, "", dur))
        else:
            cleaned_records.append((date, exe, title, dur))
            
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.executemany("""
                INSERT INTO app_usage (date, exe_name, window_title, duration_seconds)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date, exe_name, window_title)
                DO UPDATE SET duration_seconds = duration_seconds + excluded.duration_seconds
            """, cleaned_records)
    finally:
        conn.close()

def get_today_total_time(db_path, date_str):
    """Return total time spent today in seconds (only manually added/categorized apps)."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT SUM(u.duration_seconds) as total 
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE u.date = ? AND c.category IN ('Productivity', 'Entertainment', 'Distraction')
        """, (date_str,)).fetchone()
        return row['total'] if row and row['total'] is not None else 0
    finally:
        conn.close()

def get_today_app_breakdown(db_path, date_str):
    """Return a list of dicts for app usage breakdown (only manually added/categorized apps)"""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT u.exe_name, SUM(u.duration_seconds) as duration
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE u.date = ? AND c.category IN ('Productivity', 'Entertainment', 'Distraction')
            GROUP BY u.exe_name
            ORDER BY duration DESC
        """, (date_str,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_daily_average(db_path):
    """Return the daily average usage in seconds across all logged days (only manually added/categorized apps)."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT AVG(daily_sum) as avg_duration FROM (
                SELECT u.date, SUM(u.duration_seconds) as daily_sum
                FROM app_usage u
                JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
                WHERE c.category IN ('Productivity', 'Entertainment', 'Distraction')
                GROUP BY u.date
            )
        """).fetchone()
        return round(row['avg_duration']) if row and row['avg_duration'] is not None else 0
    finally:
        conn.close()

def get_browser_highlights(db_path, date_str):
    """
    Return platform-specific highlights for browser usage.
    Looks for major platforms (YouTube, GitHub, etc.) inside browser window titles.
    """
    browser_exes = ('chrome.exe', 'msedge.exe', 'firefox.exe', 'brave.exe', 'opera.exe', 'operagx.exe', 'vivaldi.exe', 'arc.exe')
    conn = get_db_connection(db_path)
    try:
        query = f"""
            SELECT u.window_title, u.duration_seconds
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE u.date = ? 
              AND c.category IN ('Productivity', 'Entertainment', 'Distraction')
              AND LOWER(u.exe_name) IN ({','.join(['?']*len(browser_exes))})
        """
        rows = conn.execute(query, (date_str, *browser_exes)).fetchall()
        
        platforms = {
            'YouTube': 0,
            'GitHub': 0,
            'Stack Overflow': 0,
            'Reddit': 0,
            'ChatGPT': 0,
            'Google Search': 0,
            'Gmail': 0
        }
        
        for row in rows:
            title = row['window_title']
            dur = row['duration_seconds']
            title_lower = title.lower()
            
            matched = False
            for platform in platforms:
                keyword = platform.lower()
                if keyword in title_lower:
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

# --- Settings & App Categories Persistence Functions ---

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
    """Assign or update a category for a specific executable name. If 'Uncategorized', deletes it."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            if category == "Uncategorized":
                conn.execute("DELETE FROM app_categories WHERE LOWER(exe_name) = LOWER(?)", (exe_name,))
            else:
                conn.execute("""
                    INSERT INTO app_categories (exe_name, category) 
                    VALUES (?, ?) 
                    ON CONFLICT(exe_name) 
                    DO UPDATE SET category = excluded.category
                """, (exe_name.lower(), category))
    finally:
        conn.close()

def get_category_durations(db_path, date_str):
    """Get the total tracking duration spent today per category."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT c.category, SUM(u.duration_seconds) as duration
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE u.date = ? AND c.category IN ('Productivity', 'Entertainment', 'Distraction')
            GROUP BY c.category
        """, (date_str,)).fetchall()
        
        result = {
            'Productivity': 0,
            'Entertainment': 0,
            'Distraction': 0,
            'Uncategorized': 0
        }
        for row in rows:
            cat = row['category']
            if cat in result:
                result[cat] += row['duration']
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
    """Return the average daily screen time (only manually added/categorized apps) over the last 7 days."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT AVG(daily_sum) as avg_duration FROM (
                SELECT u.date, SUM(u.duration_seconds) as daily_sum
                FROM app_usage u
                JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
                WHERE c.category IN ('Productivity', 'Entertainment', 'Distraction')
                  AND u.date >= date('now', 'localtime', '-7 days')
                GROUP BY u.date
            )
        """).fetchone()
        return round(row['avg_duration']) if row and row['avg_duration'] is not None else 0
    finally:
        conn.close()

def get_monthly_total(db_path):
    """Return the total screen time in seconds spent in the current month (only manually added/categorized apps)."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("""
            SELECT SUM(u.duration_seconds) as total
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE c.category IN ('Productivity', 'Entertainment', 'Distraction')
              AND u.date >= date('now', 'localtime', 'start of month')
        """).fetchone()
        return row['total'] if row and row['total'] is not None else 0
    finally:
        conn.close()

def get_monthly_breakdown(db_path):
    """Return the top 5 applications spent in the current month (only manually added/categorized apps)."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT u.exe_name, SUM(u.duration_seconds) as duration
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE c.category IN ('Productivity', 'Entertainment', 'Distraction')
              AND u.date >= date('now', 'localtime', 'start of month')
            GROUP BY u.exe_name
            ORDER BY duration DESC
            LIMIT 5
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_daily_totals_for_month(db_path, year, month):
    """Retrieve daily screen time sums (only manually added/categorized apps) for a given calendar month."""
    conn = get_db_connection(db_path)
    prefix = f"{year:04d}-{month:02d}-%"
    try:
        rows = conn.execute("""
            SELECT u.date, SUM(u.duration_seconds) as duration
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE c.category IN ('Productivity', 'Entertainment', 'Distraction')
              AND u.date LIKE ?
            GROUP BY u.date
        """, (prefix,)).fetchall()
        return {row['date']: row['duration'] for row in rows}
    finally:
        conn.close()

def get_last_7_days_totals(db_path):
    """Retrieve daily screen time sums (only manually added/categorized apps) for the last 7 calendar days."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT u.date, SUM(u.duration_seconds) as duration
            FROM app_usage u
            JOIN app_categories c ON LOWER(u.exe_name) = LOWER(c.exe_name)
            WHERE c.category IN ('Productivity', 'Entertainment', 'Distraction')
              AND u.date >= date('now', 'localtime', '-7 days')
            GROUP BY u.date
            ORDER BY u.date ASC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_category_goal(db_path, category):
    """Retrieve the daily goal limit for a category in seconds. Returns 0 if no goal is set."""
    val = get_setting(db_path, f"goal_{category}", "0")
    try:
        return int(val)
    except ValueError:
        return 0

def set_category_goal(db_path, category, seconds):
    """Save the daily goal limit for a category in seconds."""
    set_setting(db_path, f"goal_{category}", str(seconds))

def clear_all_data(db_path):
    """Truncate/clear all records from app_usage, settings, and app_categories tables."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM app_usage")
            conn.execute("DELETE FROM settings")
            conn.execute("DELETE FROM app_categories")
            conn.execute("VACUUM")
    finally:
        conn.close()

def get_track_details_map(db_path):
    """Retrieve a dictionary mapping lowercase exe name to track_details (0 or 1)."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("SELECT exe_name, track_details FROM app_categories").fetchall()
        return {row['exe_name'].lower(): bool(row['track_details']) for row in rows}
    except Exception as e:
        print(f"[Database] Error in get_track_details_map: {e}")
        return {}
    finally:
        conn.close()

def set_app_track_details(db_path, exe_name, track_details):
    """Enable or disable detailed project tracking for an executable."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                UPDATE app_categories
                SET track_details = ?
                WHERE LOWER(exe_name) = LOWER(?)
            """, (int(track_details), exe_name))
    finally:
        conn.close()

def extract_unity_project(title):
    if not title or title.strip() == "System/Background Process":
        return "Unknown Project"
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    if len(parts) >= 2:
        if "unity" in parts[0].lower():
            return parts[1]
        for part in parts:
            if "unity" in part.lower():
                return parts[0]
        return parts[0]
    return "Unknown Project"

def extract_blender_project(title):
    if not title or title.strip() == "System/Background Process":
        return "New Project"
    match = re.search(r'\[([^\]]+)\]', title)
    if match:
        path = match.group(1).strip()
        filename = os.path.basename(path)
        filename = filename.rstrip('*').strip()
        if filename:
            return filename
    if " - Blender" in title:
        parts = title.split(" - Blender")
        if parts[0]:
            return parts[0].rstrip('*').strip()
    if title.strip().startswith("Blender"):
        return "New Project"
    return title.strip()

def extract_maya_project(title):
    if not title or title.strip() == "System/Background Process":
        return "Untitled Scene"
    
    # 1. Check for suffix pattern: E.g., "C:\path\to\scene.mb* - Autodesk Maya 2024"
    if " - Autodesk Maya" in title:
        path_part = title.split(" - Autodesk Maya")[0].strip()
        filename = os.path.basename(path_part)
        filename = filename.rstrip('*').strip()
        if filename:
            return filename
            
    # 2. Check for prefix pattern: E.g., "Autodesk Maya 2024: C:\path\to\scene.mb"
    if "autodesk maya" in title.lower():
        parts = title.split(":")
        if len(parts) >= 2:
            path_part = ":".join(parts[1:]).strip()
            if path_part.lower() == "untitled":
                return "Untitled Scene"
            filename = os.path.basename(path_part)
            filename = filename.rstrip('*').strip()
            if filename:
                return filename
                
    return "Untitled Scene"

def extract_substance_project(title):
    if not title or title.strip() == "System/Background Process":
        return "Untitled Project"
    parts = title.split(" - ")
    if len(parts) >= 2:
        for part in parts:
            p = part.strip()
            if p.lower().endswith(".spp") or p.lower().endswith(".sbs") or p.lower().endswith(".sbsar") or p.lower().endswith(".spp*") or p.lower().endswith(".sbs*") or p.startswith("*"):
                project = p.lstrip('*').strip()
                if project:
                    return project
        project = parts[0].lstrip('*').strip()
        if project:
            return project
    return "Untitled Project"

def extract_general_project(title):
    if not title or title.strip() == "System/Background Process":
        return "General/Idle"
    match = re.search(r'([a-zA-Z]:[\\/][^:*?"<>|\r\n]+)', title)
    if match:
        path = match.group(1).strip()
        filename = os.path.basename(path)
        filename = filename.split(" - ")[0].split(" : ")[0].strip()
        filename = filename.rstrip('*').strip()
        if filename:
            return filename
    parts = title.split(" - ")
    if len(parts) >= 2:
        return parts[0].strip()
    return title.strip()

def extract_project_name(exe_name, window_title):
    exe_lower = exe_name.lower()
    if 'unity.exe' in exe_lower:
        project = extract_unity_project(window_title)
    elif 'blender.exe' in exe_lower:
        project = extract_blender_project(window_title)
    elif 'maya.exe' in exe_lower:
        project = extract_maya_project(window_title)
    elif 'substance' in exe_lower:
        project = project_name = extract_substance_project(window_title)
    else:
        project = extract_general_project(window_title)
        
    # Clean up project name (strip leading/trailing asterisks, brackets, and whitespace)
    project = project.strip('* \t\r\n[]()')
    
    # Consolidate unsaved/untitled documents into a single unified label
    proj_lower = project.lower()
    if not project or any(word in proj_lower for word in ("unsaved", "untitled", "new project", "unknown project", "general/idle")):
        return "Unsaved"
        
    return project

def migrate_unsaved_records(conn):
    """Migrate any existing database records where the project name parses to 'Unsaved' to have an empty window_title."""
    cursor = conn.execute("SELECT id, date, exe_name, window_title, duration_seconds FROM app_usage")
    rows = cursor.fetchall()
    
    needs_migration = False
    for row in rows:
        exe = row['exe_name']
        title = row['window_title']
        if title != "":
            if extract_project_name(exe, title) == "Unsaved":
                needs_migration = True
                break
                
    if not needs_migration:
        return
        
    print("[Database] Migrating existing 'Unsaved' window titles to empty strings...")
    aggregated = {}
    for row in rows:
        date = row['date']
        exe = row['exe_name']
        title = row['window_title']
        dur = row['duration_seconds']
        
        if extract_project_name(exe, title) == "Unsaved":
            new_title = ""
        else:
            new_title = title
            
        key = (date, exe.lower(), new_title)
        if key in aggregated:
            aggregated[key]['duration'] += dur
        else:
            aggregated[key] = {
                'date': date,
                'exe_name': exe,
                'window_title': new_title,
                'duration': dur
            }
            
    conn.execute("DELETE FROM app_usage")
    conn.executemany("""
        INSERT INTO app_usage (date, exe_name, window_title, duration_seconds)
        VALUES (?, ?, ?, ?)
    """, [(item['date'], item['exe_name'], item['window_title'], item['duration']) for item in aggregated.values()])
    print(f"[Database] Migration complete. Consolidated into {len(aggregated)} rows.")

def get_project_breakdown_for_app(db_path, date_str, exe_name):
    """Retrieve durations grouped by parsed project/file names for a specific app on a given date."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT window_title, duration_seconds
            FROM app_usage
            WHERE date = ? AND LOWER(exe_name) = LOWER(?)
        """, (date_str, exe_name)).fetchall()
        
        project_durations = {}
        for row in rows:
            title = row['window_title']
            dur = row['duration_seconds']
            project = extract_project_name(exe_name, title)
            if project == "Unsaved":
                continue
            project_durations[project] = project_durations.get(project, 0) + dur
            
        result = [{'project_name': p, 'duration': d} for p, d in project_durations.items()]
        result.sort(key=lambda x: x['duration'], reverse=True)
        return result
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
        
        # Load initial interval from settings database, default to 30
        try:
            saved_interval = int(get_setting(db_path, "poll_interval", 30))
        except Exception:
            saved_interval = 30
        self.poll_interval = saved_interval
        
        self.stop_event = threading.Event()
        self.tracker_thread = None
        
        # Dictionary of apps marked for manual tracking: {exe_name: category} (lowercase keys)
        self.tracked_apps_categories = {}
        self.load_tracked_apps()
        
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

    def load_tracked_apps(self):
        """Load the list of executables and categories manually assigned from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT exe_name, category FROM app_categories 
                WHERE category IN ('Productivity', 'Entertainment', 'Distraction')
            """).fetchall()
            self.tracked_apps_categories = {row['exe_name'].lower(): row['category'] for row in rows}
            conn.close()
            print(f"[Tracker] Loaded {len(self.tracked_apps_categories)} manually tracked applications.")
        except Exception as e:
            print(f"[Tracker] Error loading tracked apps: {e}")
            self.tracked_apps_categories = {}

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
            
        exe_lower = exe_name.lower()
        if exe_lower not in self.tracked_apps_categories:
            default_excluded = {"explorer.exe", "timetracker.exe", "python.exe", "pythonw.exe"}
            if exe_lower in default_excluded:
                return None, None
                
            ancestor_name = self.find_tracked_ancestor(pid)
            if ancestor_name:
                category = self.tracked_apps_categories[ancestor_name]
                try:
                    import database
                    database.set_app_category(self.db_path, exe_lower, category)
                    self.tracked_apps_categories[exe_lower] = category
                    print(f"[Tracker] Automatically added child app: {exe_name} -> {category} (launched by {ancestor_name})")
                except Exception as e:
                    print(f"[Tracker] Error auto-categorizing child app {exe_name}: {e}")
            else:
                return None, None
            
        return exe_name, title

    def find_tracked_ancestor(self, pid):
        """Walk up the process tree to find if any ancestor is in the manually tracked list."""
        try:
            current_pid = pid
            for _ in range(3): # Walk up at most 3 levels
                proc = psutil.Process(current_pid)
                ppid = proc.ppid()
                if ppid <= 0:
                    break
                parent = psutil.Process(ppid)
                parent_name = parent.name().lower()
                
                # Ignore common system/host shells as launcher ancestors
                if parent_name in {"explorer.exe", "services.exe", "svchost.exe", "cmd.exe", "powershell.exe"}:
                    break
                    
                if parent_name in self.tracked_apps_categories:
                    return parent_name
                current_pid = ppid
        except Exception:
            pass
        return None

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
        self.load_tracked_apps() # Reload list on startup
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

```

### 4. `tray.py`
```python
import threading
import os
from PIL import Image, ImageDraw
import pystray

def create_tray_icon_image(width=64, height=64):
    """Load the user-provided Assets/icon.png or fall back to programmatic generation."""
    # Resolve absolute path to Assets/icon.png relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(script_dir, "Assets", "icon.png")
    
    try:
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            return img.resize((width, height), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"[Tray] Error loading user icon.png: {e}")
    """Programmatically generate the new logo with horizontal cyan-to-purple gradient."""
    render_size = 512
    image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    
    # 1. Background: rounded square with smooth dark color matching Zinc theme
    bg_color = (24, 24, 27, 255) # #18181b
    border_color = (39, 39, 42, 255) # #27272a
    dc.rounded_rectangle([16, 16, 496, 496], radius=110, fill=bg_color, outline=border_color, width=12)
    
    # Create mask for the gradient shapes (arch, arrow, bucket)
    mask = Image.new("L", (render_size, render_size), 0)
    dc_mask = ImageDraw.Draw(mask)
    
    # A. Dashed arch on top
    for start_angle in range(195, 346, 15):
        dc_mask.arc([96, 96, 416, 416], start=start_angle, end=start_angle + 8, fill=255, width=16)
        
    # B. Downward arrow
    dc_mask.rectangle([256 - 14, 140, 256 + 14, 280], fill=255)
    dc_mask.polygon([(256 - 45, 290), (256 + 45, 290), (256, 350)], fill=255)
    
    # C. Bottom curved bucket
    dc_mask.arc([96, 200, 416, 420], start=0, end=180, fill=255, width=44)
    
    # Create horizontal cyan-to-purple gradient
    gradient_1d = Image.new("RGB", (render_size, 1))
    r1, g1, b1 = 34, 211, 238  # Softer Cyan (#22d3ee)
    r2, g2, b2 = 121, 99, 210  # Faded Purple (#7963d2)
    pixels = []
    for x in range(render_size):
        t = x / (render_size - 1)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        pixels.append((r, g, b))
    gradient_1d.putdata(pixels)
    gradient = gradient_1d.resize((render_size, render_size))
    
    # Paste gradient onto the background image using the mask
    image.paste(gradient, (0, 0), mask=mask)
    
    # Downscale to the desired size using LANCZOS for super smooth anti-aliased output
    output_image = image.resize((width, height), Image.Resampling.LANCZOS)
    return output_image

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
import win32gui
import win32process
import psutil
from PIL import ImageTk
from tray import create_tray_icon_image

# Configure customtkinter colors and themes
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Modern Premium Theme Color Palette (Zinc & Violet Theme)
THEME = {
    'bg_main': '#121214',        # Dark neutral grey (Zinc-950)
    'bg_sidebar': '#18181b',     # Slightly lighter dark grey (Zinc-900)
    'bg_card': '#1c1c1e',        # Card/Panel background (Zinc-850)
    'border_subtle': '#27272a',  # Zinc-800 borders
    'accent': '#7963d2',         # Softer desaturated Violet accent
    'accent_hover': '#634eb7',   # Softer desaturated Violet hover
    'text_primary': '#f4f4f5',   # Zinc-100 high-contrast text
    'text_secondary': '#a1a1aa', # Zinc-400 muted text
    'text_muted': '#71717a',     # Zinc-500 dark muted text
    
    # Dropdown / OptionMenu / Button colors
    'btn_bg': '#27272a',
    'btn_hover': '#3f3f46',
    'btn_border': '#3f3f46'
}

# Category Colors & Emoticons for UI headers (Modern flat shades)
CATEGORY_COLORS = {
    'Productivity': '#10b981',    # Emerald Green
    'Entertainment': '#3b82f6',   # Sky Blue
    'Distraction': '#f43f5e',     # Rose/Red
    'Untracked': '#52525b',       # Muted Zinc-600
    'Uncategorized': '#71717a'    # Zinc-500
}

CATEGORY_ICONS = {
    'Productivity': '🟢',
    'Entertainment': '🔵',
    'Distraction': '🔴',
    'Untracked': '🚫',
    'Uncategorized': '⚫'
}

def format_duration(seconds):
    """Format duration in seconds to a human-readable string (e.g., 2h 15m or 45s)."""
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

def get_open_window_exes():
    """Scan top-level visible windows to extract currently open user-visible executables."""
    exes = set()
    def enum_cb(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and title != "System/Background Process":
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid > 0:
                    try:
                        proc = psutil.Process(pid)
                        name = proc.name()
                        if name:
                            exes.add(name.lower())
                    except Exception:
                        pass
        return True
    
    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception as e:
        print(f"[UI] Error enumerating windows: {e}")
        
    # Exclude typical system shells / tracker itself from the list to avoid cluttering
    excluded_defaults = {"explorer.exe", "timetracker.exe", "python.exe", "pythonw.exe"}
    filtered_exes = [name for name in exes if name not in excluded_defaults]
    return sorted(list(filtered_exes))

class ProjectSubRow(tk.Frame):
    """Custom compact row displaying a nested project's duration. Inherits from tk.Frame for speed."""
    def __init__(self, master, project_name, duration, parent_duration, category, is_last=False, bg_color=None):
        bg_color = bg_color or THEME['bg_card']
        super().__init__(master, bg=bg_color)
        
        percentage_parent = (duration / parent_duration) * 100 if parent_duration > 0 else 0
        bar_value = duration / parent_duration if parent_duration > 0 else 0
        
        # Indent icon or symbol
        indent_char = " └─" if is_last else " ├─"
        self.arrow_label = ctk.CTkLabel(
            self,
            text=indent_char,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=bg_color,
            text_color=THEME['text_muted'],
            width=20
        )
        self.arrow_label.pack(side="left", padx=(5, 2))
        
        self.name_label = ctk.CTkLabel(
            self, 
            text=project_name, 
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w",
            fg_color=bg_color,
            text_color=THEME['text_primary']
        )
        self.name_label.pack(side="left", padx=2, fill="x", expand=True)
        
        bar_color = CATEGORY_COLORS.get(category, '#71717a')
        self.progress_bar = ctk.CTkProgressBar(
            self, 
            orientation="horizontal", 
            width=80, 
            height=4, 
            fg_color=THEME['bg_main'], 
            progress_color=bar_color
        )
        self.progress_bar.set(bar_value)
        self.progress_bar.pack(side="left", padx=5)
        
        info_text = f"{percentage_parent:.0f}% ({format_duration(duration)})"
        self.info_label = ctk.CTkLabel(
            self, 
            text=info_text, 
            font=ctk.CTkFont(family="Segoe UI", size=10),
            anchor="e",
            width=80,
            fg_color=bg_color,
            text_color=THEME['text_secondary']
        )
        self.info_label.pack(side="right", padx=(5, 5))

class AppRow(tk.Frame):
    """Custom compact row displaying application usage. Inherits from tk.Frame for maximum resize performance."""
    def __init__(self, master, exe_name, duration, total_duration, max_duration, category, db_path=None, date_str=None, bg_color=None, dashboard=None, is_expandable=False):
        bg_color = bg_color or THEME['bg_card']
        super().__init__(master, bg=bg_color)
        
        self.exe_name = exe_name
        self.duration = duration
        self.category = category
        self.db_path = db_path
        self.date_str = date_str
        self.bg_color = bg_color
        self.dashboard = dashboard
        self.is_expandable = is_expandable
        self.is_expanded = False
        
        percentage_total = (duration / total_duration) * 100 if total_duration > 0 else 0
        bar_value = duration / max_duration if max_duration > 0 else 0
        bar_color = CATEGORY_COLORS.get(category, '#71717a')
        
        # Display name prepended with chevron arrow if expandable
        display_name = f"▶  {exe_name}" if self.is_expandable else exe_name
        
        # Create a container frame for header to separate it from the sub-frame grid
        self.main_row = tk.Frame(self, bg=bg_color)
        self.main_row.pack(fill="x", expand=True)
        
        # Name label - takes remaining space, allows resizing
        self.name_label = ctk.CTkLabel(
            self.main_row, 
            text=display_name, 
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            anchor="w",
            fg_color=bg_color,
            text_color=THEME['text_primary']
        )
        self.name_label.pack(side="left", padx=(5, 5), fill="x", expand=True)
        
        # Progress Bar - Set to fixed width to avoid Tkinter canvas redrawing lag during window resizes
        self.progress_bar = ctk.CTkProgressBar(
            self.main_row, 
            orientation="horizontal", 
            width=110, 
            height=8, 
            fg_color=THEME['bg_main'], 
            progress_color=bar_color
        )
        self.progress_bar.set(bar_value)
        self.progress_bar.pack(side="left", padx=5)
        
        # Info Label (compact percentage + duration)
        info_text = f"{percentage_total:.0f}% ({format_duration(duration)})"
        self.info_label = ctk.CTkLabel(
            self.main_row, 
            text=info_text, 
            font=ctk.CTkFont(family="Segoe UI", size=10),
            anchor="e",
            width=70,
            fg_color=bg_color,
            text_color=THEME['text_secondary']
        )
        self.info_label.pack(side="right", padx=(5, 5))
        
        # Sub-frame container for project details list
        self.sub_frame = tk.Frame(self, bg=bg_color)
        
        if self.is_expandable:
            # Bind hover and click events
            self.main_row.configure(cursor="hand2")
            self.name_label.configure(cursor="hand2")
            
            self.main_row.bind("<Button-1>", lambda e: self.toggle_expand())
            self.name_label.bind("<Button-1>", lambda e: self.toggle_expand())
            
            def on_enter(e):
                self.main_row.configure(bg=THEME['btn_hover'])
                self.name_label.configure(fg_color=THEME['btn_hover'])
                self.info_label.configure(fg_color=THEME['btn_hover'])
            def on_leave(e):
                self.main_row.configure(bg=bg_color)
                self.name_label.configure(fg_color=bg_color)
                self.info_label.configure(fg_color=bg_color)
                
            self.main_row.bind("<Enter>", on_enter)
            self.main_row.bind("<Leave>", on_leave)
            self.name_label.bind("<Enter>", on_enter)
            self.name_label.bind("<Leave>", on_leave)

    def toggle_expand(self):
        """Toggle project details expansion and update arrow indicator."""
        self.is_expanded = not self.is_expanded
        
        if self.dashboard:
            if self.is_expanded:
                self.dashboard.expanded_apps.add(self.exe_name.lower())
            else:
                self.dashboard.expanded_apps.discard(self.exe_name.lower())
                
        if self.is_expanded:
            self.name_label.configure(text=f"▼  {self.exe_name}")
            self.load_sub_projects()
        else:
            self.name_label.configure(text=f"▶  {self.exe_name}")
            self.sub_frame.pack_forget()

    def load_sub_projects(self):
        """Query and populate sub-project rows dynamically."""
        for widget in self.sub_frame.winfo_children():
            widget.destroy()
            
        projects = database.get_project_breakdown_for_app(self.db_path, self.date_str, self.exe_name)
        if projects:
            for idx, proj in enumerate(projects):
                is_last = (idx == len(projects) - 1)
                sub_row = ProjectSubRow(
                    self.sub_frame,
                    project_name=proj['project_name'],
                    duration=proj['duration'],
                    parent_duration=self.duration,
                    category=self.category,
                    is_last=is_last,
                    bg_color=self.bg_color
                )
                sub_row.pack(fill="x", padx=(15, 0), pady=2)
                
            self.sub_frame.pack(fill="x", padx=0, pady=(2, 4))
        else:
            lbl = ctk.CTkLabel(
                self.sub_frame,
                text="   No project details found",
                font=ctk.CTkFont(family="Segoe UI", size=10, italic=True),
                text_color=THEME['text_muted'],
                anchor="w"
            )
            lbl.pack(fill="x", padx=20, pady=2)
            self.sub_frame.pack(fill="x", padx=0, pady=(2, 4))

class CategorySettingsRow(tk.Frame):
    """Compact card in Settings for mapping an executable name to a category and toggling details tracking. Uses tk.Frame for speed."""
    def __init__(self, master, exe_name, current_category, track_details_enabled, on_change_callback, on_toggle_details_callback):
        super().__init__(master, bg=THEME['bg_card'])
        
        self.exe_name = exe_name
        self.on_change_callback = on_change_callback
        self.on_toggle_details_callback = on_toggle_details_callback
        
        # Application name
        self.name_label = ctk.CTkLabel(
            self, 
            text=exe_name, 
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            anchor="w",
            fg_color=THEME['bg_card'],
            text_color=THEME['text_primary']
        )
        self.name_label.pack(side="left", padx=10, fill="x", expand=True)
        
        # Remove button
        self.remove_btn = ctk.CTkButton(
            self,
            text="Remove",
            command=self._on_remove_click,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            width=65,
            height=28,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            text_color="#fca5a5"
        )
        self.remove_btn.pack(side="right", padx=10, pady=8)
        
        # Category Selector Dropdown (excludes Uncategorized option as we have dedicated Remove button)
        self.cat_menu = ctk.CTkOptionMenu(
            self,
            values=["Productivity", "Entertainment", "Distraction", "Untracked"],
            command=self._on_changed,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            width=110,
            fg_color=THEME['btn_bg'],
            button_color=THEME['btn_hover'],
            button_hover_color=THEME['text_muted'],
            text_color=THEME['text_primary'],
            dropdown_fg_color=THEME['bg_sidebar'],
            dropdown_text_color=THEME['text_primary'],
            dropdown_hover_color=THEME['btn_hover']
        )
        self.cat_menu.set(current_category)
        self.cat_menu.pack(side="right", padx=5, pady=8)

        # Track Details Checkbox
        self.details_check = ctk.CTkCheckBox(
            self,
            text="Track Details",
            command=self._on_details_toggled,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            checkbox_width=18,
            checkbox_height=18,
            border_width=1,
            fg_color=THEME['accent'],
            hover_color=THEME['accent_hover'],
            text_color=THEME['text_primary']
        )
        if track_details_enabled:
            self.details_check.select()
        else:
            self.details_check.deselect()
        self.details_check.pack(side="right", padx=10, pady=8)

    def _on_changed(self, choice):
        self.on_change_callback(self.exe_name, choice)

    def _on_details_toggled(self):
        enabled = self.details_check.get() == 1
        self.on_toggle_details_callback(self.exe_name, enabled)

    def _on_remove_click(self):
        from tkinter import messagebox
        confirm = messagebox.askyesno(
            "Remove Application",
            f"Are you sure you want to remove '{self.exe_name}' from the tracked applications list?\n\n"
            "This will stop tracking the application and remove it from the dashboard, but all past recorded time will remain in the database.",
            icon="warning"
        )
        if confirm:
            self.on_change_callback(self.exe_name, "Uncategorized")

class WeeklyCalendarWindow(ctk.CTkToplevel):
    """Popup window showing daily totals for the last 7 calendar days."""
    def __init__(self, parent, db_path):
        super().__init__(parent)
        self.db_path = db_path
        
        self.title("Weekly Screen Time Breakdown")
        self.geometry("520x420")
        self.minsize(450, 350)
        self.configure(fg_color=THEME['bg_main'])
        self.after(10, self.lift) # Make sure it focuses on Windows
        
        # Header
        header_lbl = ctk.CTkLabel(
            self,
            text="📅 Weekly Screen Time History",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=THEME['accent'],
            anchor="w"
        )
        header_lbl.pack(fill="x", padx=20, pady=(20, 5))
        
        desc_lbl = ctk.CTkLabel(
            self,
            text="Total active time logged for each of the last 7 days.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        desc_lbl.pack(fill="x", padx=20, pady=(0, 15))
        
        # Scrollable area
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        data = database.get_last_7_days_totals(self.db_path)
        
        if data:
            max_duration = max(day['duration'] for day in data)
            total_duration = sum(day['duration'] for day in data)
            
            summary_lbl = ctk.CTkLabel(
                scroll,
                text=f"Total Screen Time (Past 7 Days): {format_duration(total_duration)}",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=THEME['text_primary'],
                anchor="w"
            )
            summary_lbl.pack(fill="x", padx=10, pady=(0, 10))
            
            for item in data:
                date_str = item['date']
                dur = item['duration']
                
                dt = datetime.date.fromisoformat(date_str)
                formatted_date = dt.strftime("%A, %b %d")
                
                # Row Container using standard Frame
                row = tk.Frame(scroll, bg=THEME['bg_card'])
                row.pack(fill="x", pady=4, padx=5)
                
                # Date label
                lbl = ctk.CTkLabel(
                    row,
                    text=formatted_date,
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                    anchor="w",
                    width=150,
                    fg_color=THEME['bg_card'],
                    text_color=THEME['text_primary']
                )
                lbl.pack(side="left", padx=10, pady=8)
                
                # Simple relative progress bar
                bar_value = dur / max_duration if max_duration > 0 else 0
                bar = ctk.CTkProgressBar(
                    row,
                    orientation="horizontal",
                    height=8,
                    fg_color=THEME['bg_main'],
                    progress_color=THEME['accent']
                )
                bar.set(bar_value)
                bar.pack(side="left", fill="x", expand=True, padx=10)
                
                # Duration text
                val = ctk.CTkLabel(
                    row,
                    text=format_duration(dur),
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    anchor="e",
                    width=80,
                    fg_color=THEME['bg_card'],
                    text_color=THEME['text_primary']
                )
                val.pack(side="right", padx=10)
        else:
            no_data = ctk.CTkLabel(
                scroll,
                text="No active tracking records found for the past 7 days.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=THEME['text_muted']
            )
            no_data.pack(pady=40)

class MonthlyCalendarWindow(ctk.CTkToplevel):
    """Popup window showing an interactive monthly grid of logged screen times."""
    def __init__(self, parent, db_path):
        super().__init__(parent)
        self.db_path = db_path
        
        # Load current month
        today = datetime.date.today()
        self.year = today.year
        self.month = today.month
        
        self.title("Monthly Screen Time Calendar")
        self.geometry("680x560")
        self.minsize(600, 480)
        self.configure(fg_color=THEME['bg_main'])
        self.after(10, self.lift)
        
        # Header Controls Frame
        self.header_frame = tk.Frame(self, bg=THEME['bg_main'])
        self.header_frame.pack(fill="x", padx=20, pady=(20, 5))
        
        # Month Navigation Title
        self.month_title_label = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=THEME['accent'],
            anchor="w"
        )
        self.month_title_label.pack(side="left", fill="x", expand=True)
        
        # Next month button
        btn_next = ctk.CTkButton(
            self.header_frame,
            text=">",
            command=self._next_month,
            width=32,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=THEME['btn_bg'],
            hover_color=THEME['btn_hover'],
            text_color=THEME['text_primary']
        )
        btn_next.pack(side="right", padx=3)
        
        # Back month button
        btn_prev = ctk.CTkButton(
            self.header_frame,
            text="<",
            command=self._prev_month,
            width=32,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=THEME['btn_bg'],
            hover_color=THEME['btn_hover'],
            text_color=THEME['text_primary']
        )
        btn_prev.pack(side="right", padx=3)
        
        desc_lbl = ctk.CTkLabel(
            self,
            text="Color highlights represent daily active time (Dark Purple for light, Bright Violet for heavy usage).",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        desc_lbl.pack(fill="x", padx=20, pady=(0, 15))
        
        # Main Calendar Grid Container Frame
        self.grid_container = tk.Frame(self, bg=THEME['bg_main'])
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
        """Draw the actual monthly grid cells and query screen times."""
        month_name = calendar.month_name[self.month]
        self.month_title_label.configure(text=f"📅 {month_name} {self.year}")
        
        for widget in self.grid_container.winfo_children():
            widget.destroy()
            
        for col in range(7):
            self.grid_container.grid_columnconfigure(col, weight=1)
            
        days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for col, day_name in enumerate(days_of_week):
            lbl = ctk.CTkLabel(
                self.grid_container, 
                text=day_name, 
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), 
                text_color=THEME['text_secondary']
            )
            lbl.grid(row=0, column=col, padx=4, pady=6, sticky="ew")
            
        totals = database.get_daily_totals_for_month(self.db_path, self.year, self.month)
        cal_matrix = calendar.monthcalendar(self.year, self.month)
        
        for r in range(len(cal_matrix) + 1):
            self.grid_container.grid_rowconfigure(r, weight=1)
            
        for r_idx, week in enumerate(cal_matrix):
            for c_idx, day in enumerate(week):
                if day == 0:
                    cell = tk.Frame(self.grid_container, bg=THEME['bg_main'])
                    cell.grid(row=r_idx+1, column=c_idx, padx=4, pady=4, sticky="nsew")
                    continue
                    
                date_str = f"{self.year:04d}-{self.month:02d}-{day:02d}"
                duration = totals.get(date_str, 0)
                
                if duration == 0:
                    bg_color = THEME['bg_card']
                    text_color = THEME['text_muted']
                elif duration < 7200:
                    bg_color = "#2c1c5c"   # Dark desaturated purple
                    text_color = "#ddd6fe"  # Violet-200
                elif duration < 18000:
                    bg_color = "#5b49b0"   # Medium desaturated purple
                    text_color = "#f5f3ff"  # Violet-50
                else:
                    bg_color = THEME['accent']   # Softer desaturated Violet accent (#7963d2)
                    text_color = "#ffffff"  # Pure white
                    
                cell = tk.Frame(self.grid_container, bg=bg_color, borderwidth=1, relief="flat", highlightbackground=THEME['border_subtle'], highlightthickness=1)
                cell.grid(row=r_idx+1, column=c_idx, padx=4, pady=4, sticky="nsew")
                
                day_lbl = ctk.CTkLabel(
                    cell, 
                    text=str(day), 
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), 
                    text_color=text_color, 
                    fg_color=bg_color
                )
                day_lbl.pack(anchor="nw", padx=6, pady=4)
                
                if duration > 0:
                    dur_lbl = ctk.CTkLabel(
                        cell, 
                        text=format_duration(duration), 
                        font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), 
                        text_color=text_color, 
                        fg_color=bg_color
                    )
                    dur_lbl.pack(anchor="se", padx=6, pady=(5, 4))

class DonutChart(tk.Canvas):
    """A native Tkinter Canvas widget that draws a premium, beautiful donut chart for categories."""
    def __init__(self, master, data, colors, **kwargs):
        # Default canvas settings to match the dark aesthetic
        kwargs.setdefault('bg', THEME['bg_card'])
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(master, **kwargs)
        self.data = data # Dictionary: {category: seconds}
        self.colors = colors # Dictionary: {category: hex_color}
        self.bind("<Configure>", self.on_resize)
        
    def on_resize(self, event):
        self.draw()
        
    def draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
            
        cx = w / 2
        cy = h / 2
        radius = min(w, h) * 0.4
        inner_radius = radius * 0.6
        
        # Calculate total duration
        total = sum(self.data.values())
        
        if total == 0:
            # Draw an empty slate grey ring if no data is tracked
            self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=THEME['border_subtle'], outline="")
            self.create_oval(cx - inner_radius, cy - inner_radius, cx + inner_radius, cy + inner_radius, fill=THEME['bg_card'], outline="")
            self.create_text(cx, cy, text="No Tracking\nData", font=("Segoe UI", 12, "bold"), fill=THEME['text_secondary'], justify="center")
            return
            
        start_angle = 90
        # Draw arcs for each category
        for cat, value in self.data.items():
            if value <= 0:
                continue
            extent = (value / total) * 360
            color = self.colors.get(cat, THEME['text_muted'])
            # create_arc draws slice
            self.create_arc(cx - radius, cy - radius, cx + radius, cy + radius,
                             start=start_angle, extent=extent, fill=color, outline="", style="pieslice")
            start_angle += extent
            
        # Draw center circle to hollow out the pie chart into a donut
        self.create_oval(cx - inner_radius, cy - inner_radius, cx + inner_radius, cy + inner_radius, fill=THEME['bg_card'], outline="")
        
        # Draw center text (Total screen time)
        total_str = format_duration(total)
        self.create_text(cx, cy - 8, text="TOTAL TIME", font=("Segoe UI", 8, "bold"), fill=THEME['text_secondary'])
        self.create_text(cx, cy + 10, text=total_str, font=("Segoe UI", 14, "bold"), fill=THEME['text_primary'])

class BarChart(tk.Canvas):
    """A native Tkinter Canvas widget that draws a clean weekly bar chart."""
    def __init__(self, master, data, bar_color=None, **kwargs):
        bar_color = bar_color or THEME['accent']
        kwargs.setdefault('bg', THEME['bg_card'])
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(master, **kwargs)
        self.data = data # List of dicts: [{'date': 'YYYY-MM-DD', 'duration': seconds}]
        self.bar_color = bar_color
        self.bind("<Configure>", self.on_resize)
        
    def on_resize(self, event):
        self.draw()
        
    def draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 20 or h < 20:
            return
            
        padding_top = 40
        padding_bottom = 30
        padding_left = 30
        padding_right = 30
        
        plot_w = w - padding_left - padding_right
        plot_h = h - padding_top - padding_bottom
        
        if not self.data:
            self.create_text(w / 2, h / 2, text="No weekly data available yet.", font=("Segoe UI", 12, "bold"), fill=THEME['text_muted'])
            return
            
        max_duration = max(day['duration'] for day in self.data)
        if max_duration <= 0:
            max_duration = 3600 # Fallback 1 hour limit to avoid divide by zero
            
        num_bars = len(self.data)
        bar_gap = 16
        total_gaps_w = bar_gap * (num_bars - 1)
        bar_w = (plot_w - total_gaps_w) / num_bars
        if bar_w < 5:
            bar_w = 5
            
        for i, item in enumerate(self.data):
            date_str = item['date']
            dur = item['duration']
            
            # Format label: day name
            try:
                dt = datetime.date.fromisoformat(date_str)
                day_label = dt.strftime("%a") # e.g. "Mon"
            except Exception:
                day_label = date_str[-5:] # fallback to MM-DD
                
            # Calculate coordinates
            bx1 = padding_left + i * (bar_w + bar_gap)
            bx2 = bx1 + bar_w
            
            # Calculate height scale
            bar_h = (dur / max_duration) * plot_h
            by1 = h - padding_bottom - bar_h
            by2 = h - padding_bottom
            
            # Draw bar
            self.create_rectangle(bx1, by1, bx2, by2, fill=self.bar_color, outline="", width=0)
            
            # Top duration label
            dur_str = format_duration(dur)
            self.create_text((bx1 + bx2) / 2, by1 - 12, text=dur_str, font=("Segoe UI", 9, "bold"), fill=THEME['text_primary'])
            
            # Bottom day label
            self.create_text((bx1 + bx2) / 2, h - 15, text=day_label, font=("Segoe UI", 10, "bold"), fill=THEME['text_secondary'])
            
        # Draw bottom baseline
        self.create_line(padding_left, h - padding_bottom, w - padding_right, h - padding_bottom, fill=THEME['border_subtle'], width=2)

class TrackerDashboard(ctk.CTk):
    def __init__(self, db_path, tracker=None, on_notify=None):
        super().__init__()
        self.db_path = db_path
        self.tracker = tracker
        self.on_notify = on_notify
        
        # Goals tracking state
        self.fired_alerts = set()
        self.last_alert_date = datetime.date.today().isoformat()
        
        # Expanded apps state for dropdown memory
        self.expanded_apps = set()
        
        # Window setup
        self.title("WofstudioZ Time Tracker")
        self.geometry("950x650")
        self.minsize(850, 550)
        self.configure(fg_color=THEME['bg_main'])
        
        # Set window icon - use the user's Assets/icon.png at high resolution
        try:
            self.logo_pil = create_tray_icon_image(256, 256)
            self.logo_tk = ImageTk.PhotoImage(self.logo_pil)
            self.iconphoto(True, self.logo_tk)
        except Exception as e:
            print(f"[UI] Error setting window icon: {e}")
        
        # Intercept closing
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        # Grid layout config - sidebar is fixed width (weight=0) to optimize redraw loops!
        self.grid_columnconfigure(0, weight=0)  # Sidebar: Static width
        self.grid_columnconfigure(1, weight=1)  # Main panel: Expands to fill window
        self.grid_rowconfigure(0, weight=1)
        
        self._setup_sidebar()
        self._setup_main_panel()
        
        # Run first refresh and schedule updates
        self.refresh_data()
        self.schedule_refresh()
        self.after(3000, lambda: self.run_update_check(quiet=True))

    def _setup_sidebar(self):
        """Create left side panel with stats cards."""
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=THEME['bg_sidebar'])
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False) # Prevent grid geometry resizing from collapsing the sidebar
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Spacer row
        
        # Logo / Title
        try:
            self.sidebar_logo_pil = create_tray_icon_image(32, 32)
            self.sidebar_logo_image = ctk.CTkImage(
                light_image=self.sidebar_logo_pil,
                dark_image=self.sidebar_logo_pil,
                size=(28, 28)
            )
            self.logo_label = ctk.CTkLabel(
                self.sidebar_frame,
                text=" Tracker",
                image=self.sidebar_logo_image,
                compound="left",
                font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                text_color=THEME['text_primary']
            )
        except Exception as e:
            print(f"[UI] Error creating sidebar logo: {e}")
            self.logo_label = ctk.CTkLabel(
                self.sidebar_frame, 
                text="⏱️ Tracker", 
                font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
                text_color=THEME['accent']
            )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="w")
        
        # Card 1: Today's Time
        self.today_card = ctk.CTkFrame(self.sidebar_frame, fg_color=THEME['bg_card'], corner_radius=8, border_width=1, border_color=THEME['border_subtle'])
        self.today_card.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        
        self.today_card_title = ctk.CTkLabel(
            self.today_card, 
            text="SCREEN TIME TODAY", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=THEME['text_secondary']
        )
        self.today_card_title.pack(padx=15, pady=(10, 2))
        
        self.today_time_label = ctk.CTkLabel(
            self.today_card, 
            text="0h 0m", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=THEME['text_primary']
        )
        self.today_time_label.pack(padx=15, pady=(2, 10))
        
        # Card 2: Daily Average
        self.avg_card = ctk.CTkFrame(self.sidebar_frame, fg_color=THEME['bg_card'], corner_radius=8, border_width=1, border_color=THEME['border_subtle'])
        self.avg_card.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        
        self.avg_card_title = ctk.CTkLabel(
            self.avg_card, 
            text="DAILY AVERAGE", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=THEME['text_secondary']
        )
        self.avg_card_title.pack(padx=15, pady=(10, 2))
        
        self.avg_time_label = ctk.CTkLabel(
            self.avg_card, 
            text="0h 0m", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=THEME['text_primary']
        )
        self.avg_time_label.pack(padx=15, pady=(2, 10))
 
        # Manual Refresh Button
        self.refresh_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="Sync & Refresh",
            command=self.refresh_data,
            fg_color=THEME['accent'],
            hover_color=THEME['accent_hover'],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=32
        )
        self.refresh_btn.grid(row=3, column=0, padx=15, pady=15, sticky="ew")
        
        # Footer
        self.footer_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="WofstudioZ Time Tracker v1.0.2", 
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=THEME['text_muted']
        )
        self.footer_label.grid(row=5, column=0, padx=20, pady=20, sticky="s")
 
    def _setup_main_panel(self):
        """Create right side panel with tabs and data lists. Uses tk.Frame for maximum resize performance."""
        self.main_frame = tk.Frame(self, bg=THEME['bg_main'])
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        # View switcher
        self.view_selector = ctk.CTkSegmentedButton(
            self.main_frame,
            values=["App Breakdown", "Browser Highlights", "Add Apps", "History & Reports", "Settings"],
            command=self._switch_view,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            selected_color=THEME['accent'],
            unselected_color=THEME['bg_card'],
            selected_hover_color=THEME['accent_hover'],
            text_color=THEME['text_primary']
        )
        self.view_selector.set("App Breakdown")
        self.view_selector.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        # Scrollable container for Apps Breakdown
        self.apps_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.apps_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        
        # Scrollable container for Add Apps
        self.add_apps_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        
        # Scrollable container for Browser Highlights
        self.browser_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        
        # Scrollable container for History & Reports
        self.history_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        
        # Scrollable container for Settings panel
        self.settings_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        
        # Lists for clean widget recreation
        self.rendered_grid_container = None
        self.rendered_browser_rows = []

    def _switch_view(self, value):
        """Toggle frame visibility based on selected tab."""
        self.apps_scroll.grid_forget()
        self.add_apps_scroll.grid_forget()
        self.browser_scroll.grid_forget()
        self.history_scroll.grid_forget()
        self.settings_scroll.grid_forget()
        
        if value == "App Breakdown":
            self.apps_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.refresh_data()
        elif value == "Browser Highlights":
            self.browser_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.refresh_data()
        elif value == "Add Apps":
            self.add_apps_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.build_add_apps_tab()
        elif value == "History & Reports":
            self.history_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.refresh_data()
        elif value == "Settings":
            self.settings_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
            self.build_settings_tab()

    def build_settings_tab(self):
        """Construct settings menu showing configs, daily goals, and operations."""
        # Clear previous settings widgets
        for widget in self.settings_scroll.winfo_children():
            widget.destroy()
            
        # Section 1: Tracker Settings Header
        title_settings = ctk.CTkLabel(
            self.settings_scroll,
            text="⚙️ Tracker Settings",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            anchor="w",
            text_color=THEME['accent']
        )
        title_settings.pack(fill="x", padx=10, pady=(15, 10))
        
        # Refresh Rate Setting Card
        interval_card = ctk.CTkFrame(self.settings_scroll, fg_color=THEME['bg_card'], corner_radius=8)
        interval_card.pack(fill="x", padx=10, pady=5)
        
        interval_info_frame = ctk.CTkFrame(interval_card, fg_color="transparent")
        interval_info_frame.pack(side="left", padx=15, pady=10, fill="x", expand=True)
        
        interval_label = ctk.CTkLabel(
            interval_info_frame,
            text="Refresh Rate",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        interval_label.pack(fill="x")
        
        interval_desc = ctk.CTkLabel(
            interval_info_frame,
            text="How often the tracker polls the active window.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        interval_desc.pack(fill="x")
        
        current_val = database.get_setting(self.db_path, "poll_interval", "30")
        current_option = f"{current_val} seconds"
        
        self.interval_menu = ctk.CTkOptionMenu(
            interval_card,
            values=["10 seconds", "30 seconds", "60 seconds"],
            command=self._change_poll_interval,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            width=140,
            fg_color=THEME['btn_bg'],
            button_color=THEME['btn_hover'],
            button_hover_color=THEME['text_muted'],
            text_color=THEME['text_primary'],
            dropdown_fg_color=THEME['bg_sidebar'],
            dropdown_text_color=THEME['text_primary'],
            dropdown_hover_color=THEME['btn_hover']
        )
        self.interval_menu.set(current_option)
        self.interval_menu.pack(side="right", padx=15, pady=15)
        
        # Startup Settings Card (Registry Toggle)
        startup_card = ctk.CTkFrame(self.settings_scroll, fg_color=THEME['bg_card'], corner_radius=8)
        startup_card.pack(fill="x", padx=10, pady=5)
        
        # Check current Windows Startup registry status
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
            progress_color=THEME['accent'],
            fg_color=THEME['btn_bg']
        )
        if is_startup_enabled:
            self.startup_switch.select()
        else:
            self.startup_switch.deselect()
        self.startup_switch.pack(side="left", padx=15, pady=15)
        
        # Database Folder Path Settings Card
        db_card = ctk.CTkFrame(self.settings_scroll, fg_color=THEME['bg_card'], corner_radius=8)
        db_card.pack(fill="x", padx=10, pady=5)
        
        db_info_frame = ctk.CTkFrame(db_card, fg_color="transparent")
        db_info_frame.pack(side="left", padx=15, pady=10, fill="x", expand=True)
        
        db_label = ctk.CTkLabel(
            db_info_frame,
            text="Database Directory",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        db_label.pack(fill="x")
        
        self.db_path_label = ctk.CTkLabel(
            db_info_frame,
            text=os.path.dirname(self.db_path),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        self.db_path_label.pack(fill="x")
        
        self.db_status_label = ctk.CTkLabel(
            db_info_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            anchor="w"
        )
        self.db_status_label.pack(fill="x")
        
        browse_btn = ctk.CTkButton(
            db_card,
            text="Change Folder",
            command=self._change_db_folder,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=120,
            fg_color=THEME['btn_bg'],
            hover_color=THEME['btn_hover'],
            text_color=THEME['text_primary']
        )
        browse_btn.pack(side="right", padx=15, pady=15)
        
        # Check for Updates Settings Card
        update_card = ctk.CTkFrame(self.settings_scroll, fg_color=THEME['bg_card'], corner_radius=8)
        update_card.pack(fill="x", padx=10, pady=5)
        
        update_info_frame = ctk.CTkFrame(update_card, fg_color="transparent")
        update_info_frame.pack(side="left", padx=15, pady=10, fill="x", expand=True)
        
        update_label = ctk.CTkLabel(
            update_info_frame,
            text="Application Version & Updates",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        update_label.pack(fill="x")
        
        update_desc = ctk.CTkLabel(
            update_info_frame,
            text="Current version: v1.0.2. Check for new updates on GitHub.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        update_desc.pack(fill="x")
        
        check_update_btn = ctk.CTkButton(
            update_card,
            text="Check for Updates",
            command=lambda: self.run_update_check(quiet=False),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=140,
            fg_color=THEME['btn_bg'],
            hover_color=THEME['btn_hover'],
            text_color=THEME['text_primary']
        )
        check_update_btn.pack(side="right", padx=15, pady=15)
        
        # Section 2: Daily Goals Card
        goals_card = ctk.CTkFrame(self.settings_scroll, fg_color=THEME['bg_card'], corner_radius=8)
        goals_card.pack(fill="x", padx=10, pady=10)
        
        goals_info_frame = ctk.CTkFrame(goals_card, fg_color="transparent")
        goals_info_frame.pack(fill="x", padx=15, pady=10)
        
        goals_title = ctk.CTkLabel(
            goals_info_frame,
            text="🎯 Daily Screen Time Targets & Limits",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        goals_title.pack(fill="x", pady=(5, 2))
        
        goals_desc = ctk.CTkLabel(
            goals_info_frame,
            text="Set minimum targets (Productivity) or maximum limits (Entertainment, Distraction). Set to 0h 0m to disable.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        goals_desc.pack(fill="x", pady=(0, 15))
        
        # Grid for options
        grid_goals = tk.Frame(goals_info_frame, bg=THEME['bg_card'])
        grid_goals.pack(fill="x", pady=5)
        
        hours_values = [str(x) for x in range(13)]
        minutes_values = [str(x) for x in range(0, 60, 5)]
        
        # Helper to render a goal row
        def create_goal_row(master, row_idx, cat_name, color, label_text):
            lbl = ctk.CTkLabel(master, text=label_text, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=color, anchor="w", fg_color=THEME['bg_card'])
            lbl.grid(row=row_idx, column=0, padx=10, pady=6, sticky="w")
            
            goal_sec = database.get_category_goal(self.db_path, cat_name)
            curr_h = str(goal_sec // 3600)
            curr_m = str((goal_sec % 3600) // 60)
            # Ensure minutes matches the 5-min steps (round to nearest)
            curr_m_int = int(curr_m)
            curr_m_int = 5 * round(curr_m_int / 5)
            if curr_m_int >= 60:
                curr_m_int = 55
            curr_m = str(curr_m_int)
            
            h_menu = ctk.CTkOptionMenu(
                master, values=hours_values, width=80, font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color=THEME['btn_bg'], button_color=THEME['btn_hover'], button_hover_color=THEME['text_muted'],
                text_color=THEME['text_primary'], dropdown_fg_color=THEME['bg_sidebar'], dropdown_text_color=THEME['text_primary'],
                dropdown_hover_color=THEME['btn_hover']
            )
            h_menu.set(curr_h)
            h_menu.grid(row=row_idx, column=1, padx=5, pady=6)
            
            lbl_h = ctk.CTkLabel(master, text="h", font=ctk.CTkFont(family="Segoe UI", size=12), fg_color=THEME['bg_card'], text_color=THEME['text_primary'])
            lbl_h.grid(row=row_idx, column=2, padx=(0, 15), pady=6)
            
            m_menu = ctk.CTkOptionMenu(
                master, values=minutes_values, width=80, font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color=THEME['btn_bg'], button_color=THEME['btn_hover'], button_hover_color=THEME['text_muted'],
                text_color=THEME['text_primary'], dropdown_fg_color=THEME['bg_sidebar'], dropdown_text_color=THEME['text_primary'],
                dropdown_hover_color=THEME['btn_hover']
            )
            m_menu.set(curr_m)
            m_menu.grid(row=row_idx, column=3, padx=5, pady=6)
            
            lbl_m = ctk.CTkLabel(master, text="m", font=ctk.CTkFont(family="Segoe UI", size=12), fg_color=THEME['bg_card'], text_color=THEME['text_primary'])
            lbl_m.grid(row=row_idx, column=4, padx=0, pady=6)
            
            return h_menu, m_menu

        self.p_h, self.p_m = create_goal_row(grid_goals, 0, "Productivity", CATEGORY_COLORS["Productivity"], "🟢 Productivity Target:")
        self.e_h, self.e_m = create_goal_row(grid_goals, 1, "Entertainment", CATEGORY_COLORS["Entertainment"], "🔵 Entertainment Limit:")
        self.d_h, self.d_m = create_goal_row(grid_goals, 2, "Distraction", CATEGORY_COLORS["Distraction"], "🔴 Distraction Limit:")
        
        # Save Goals Button & Status
        btn_frame = ctk.CTkFrame(goals_info_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15, 5))
        
        save_goals_btn = ctk.CTkButton(
            btn_frame,
            text="Save Daily Goals",
            command=self._save_goals,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=140,
            fg_color=THEME['accent'],
            hover_color=THEME['accent_hover']
        )
        save_goals_btn.pack(side="left")
        
        self.goals_status_lbl = ctk.CTkLabel(
            btn_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w",
            fg_color=THEME['bg_card']
        )
        self.goals_status_lbl.pack(side="left", padx=15)

        # Section 3: Operations & Danger Zone Header
        title_ops = ctk.CTkLabel(
            self.settings_scroll,
            text="⚠️ Operations & Danger Zone",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            anchor="w",
            text_color="#ef4444"
        )
        title_ops.pack(fill="x", padx=10, pady=(25, 10))
        
        # Danger Zone / Clear Data Card
        reset_card = ctk.CTkFrame(self.settings_scroll, fg_color=THEME['bg_card'], corner_radius=8, border_width=1, border_color="#7f1d1d")
        reset_card.pack(fill="x", padx=10, pady=5)
        
        reset_info_frame = ctk.CTkFrame(reset_card, fg_color="transparent")
        reset_info_frame.pack(side="left", padx=15, pady=10, fill="x", expand=True)
        
        reset_label = ctk.CTkLabel(
            reset_info_frame,
            text="Clear All Tracker Data",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#f87171",
            anchor="w"
        )
        reset_label.pack(fill="x")
        
        reset_desc = ctk.CTkLabel(
            reset_info_frame,
            text="Permanently delete all logged screen times, category mappings, and goals.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        reset_desc.pack(fill="x")
        
        clear_btn = ctk.CTkButton(
            reset_card,
            text="Clear All Data",
            command=self._clear_database_data,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=120,
            fg_color="#991b1b",
            hover_color="#b91c1c"
        )
        clear_btn.pack(side="right", padx=15, pady=15)
        
        # Force Quit / Kill App Card
        kill_card = ctk.CTkFrame(self.settings_scroll, fg_color=THEME['bg_card'], corner_radius=8)
        kill_card.pack(fill="x", padx=10, pady=5)
        
        kill_info_frame = ctk.CTkFrame(kill_card, fg_color="transparent")
        kill_info_frame.pack(side="left", padx=15, pady=10, fill="x", expand=True)
        
        kill_label = ctk.CTkLabel(
            kill_info_frame,
            text="Force Quit Application",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        kill_label.pack(fill="x")
        
        kill_desc = ctk.CTkLabel(
            kill_info_frame,
            text="Immediately terminate the tracker and all background threads.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        kill_desc.pack(fill="x")
        
        kill_btn = ctk.CTkButton(
            kill_card,
            text="Kill App",
            command=self._force_quit_app,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=120,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            text_color="#fca5a5"
        )
        kill_btn.pack(side="right", padx=15, pady=15)

    def build_add_apps_tab(self):
        """Construct the Add & Categorize Applications layout."""
        # Clear previous add apps widgets
        for widget in self.add_apps_scroll.winfo_children():
            widget.destroy()
            
        # Section Header
        title_add_apps = ctk.CTkLabel(
            self.add_apps_scroll,
            text="➕ Add & Categorize Applications",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            anchor="w",
            text_color=THEME['accent']
        )
        title_add_apps.pack(fill="x", padx=10, pady=(15, 10))
        
        # Section: Quick-Add Application Category Card
        quick_add_card = ctk.CTkFrame(self.add_apps_scroll, fg_color=THEME['bg_card'], corner_radius=8)
        quick_add_card.pack(fill="x", padx=10, pady=5)
        
        quick_add_info_frame = ctk.CTkFrame(quick_add_card, fg_color="transparent")
        quick_add_info_frame.pack(fill="x", padx=15, pady=10)
        
        quick_add_title = ctk.CTkLabel(
            quick_add_info_frame,
            text="➕ Quick-Add / Categorize Application",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            anchor="w"
        )
        quick_add_title.pack(fill="x", pady=(5, 2))
        
        quick_add_desc = ctk.CTkLabel(
            quick_add_info_frame,
            text="Select from currently open windows or type a custom executable name (e.g. notepad.exe) to assign it to a category.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        quick_add_desc.pack(fill="x", pady=(0, 10))
        
        # Controls row
        controls_frame = ctk.CTkFrame(quick_add_info_frame, fg_color="transparent")
        controls_frame.pack(fill="x", pady=5)
        
        open_exes = get_open_window_exes()
        self.add_app_combo = ctk.CTkComboBox(
            controls_frame,
            values=open_exes,
            width=250,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=THEME['btn_bg'],
            text_color=THEME['text_primary'],
            border_color=THEME['btn_bg'],
            button_color=THEME['btn_hover'],
            button_hover_color=THEME['text_muted'],
            dropdown_fg_color=THEME['bg_sidebar'],
            dropdown_text_color=THEME['text_primary'],
            dropdown_hover_color=THEME['btn_hover']
        )
        self.add_app_combo.set("Select or type app name...")
        self.add_app_combo.pack(side="left", padx=(0, 10))
        
        self.add_cat_menu = ctk.CTkOptionMenu(
            controls_frame,
            values=["Productivity", "Entertainment", "Distraction", "Untracked"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            width=130,
            fg_color=THEME['btn_bg'],
            button_color=THEME['btn_hover'],
            button_hover_color=THEME['text_muted'],
            text_color=THEME['text_primary'],
            dropdown_fg_color=THEME['bg_sidebar'],
            dropdown_text_color=THEME['text_primary'],
            dropdown_hover_color=THEME['btn_hover']
        )
        self.add_cat_menu.set("Untracked")
        self.add_cat_menu.pack(side="left", padx=(0, 10))
        
        add_btn = ctk.CTkButton(
            controls_frame,
            text="Assign Category",
            command=self._quick_add_app,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=130,
            fg_color=THEME['accent'],
            hover_color=THEME['accent_hover']
        )
        add_btn.pack(side="left")
        
        # Section 2: App Categories Header
        title_categories = ctk.CTkLabel(
            self.add_apps_scroll,
            text="🏷️ App Categories Settings",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            anchor="w",
            text_color=THEME['accent']
        )
        title_categories.pack(fill="x", padx=10, pady=(25, 5))
        
        desc_label = ctk.CTkLabel(
            self.add_apps_scroll,
            text="Group and configure categories. Mark applications as 'Untracked' to exclude them entirely. Check 'Track Details' to log project names.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=THEME['text_secondary'],
            anchor="w"
        )
        desc_label.pack(fill="x", padx=10, pady=(0, 15))
        
        # Fetch categories and track details maps
        categories = database.get_app_categories(self.db_path)
        track_details_map = database.get_track_details_map(self.db_path)
        
        grouped_settings = {
            'Productivity': [],
            'Entertainment': [],
            'Distraction': [],
            'Untracked': [],
            'Uncategorized': []
        }
        
        for app, cat in categories.items():
            if cat in grouped_settings:
                grouped_settings[cat].append(app)
                
        has_apps = False
        for cat_name in ['Productivity', 'Entertainment', 'Distraction', 'Untracked', 'Uncategorized']:
            apps_list = grouped_settings[cat_name]
            if not apps_list:
                continue
                
            has_apps = True
            color = CATEGORY_COLORS[cat_name]
            icon = CATEGORY_ICONS[cat_name]
            
            # Category Section Label
            cat_header = ctk.CTkLabel(
                self.add_apps_scroll,
                text=f"{icon} {cat_name.upper()} APPS ({len(apps_list)})",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=color,
                anchor="w"
            )
            cat_header.pack(fill="x", padx=10, pady=(15, 5))
            
            # 2-Column Grid Container Frame (Uses tk.Frame for zero lag)
            grid_frame = tk.Frame(self.add_apps_scroll, bg=THEME['bg_main'])
            grid_frame.pack(fill="x", padx=5, pady=5)
            grid_frame.grid_columnconfigure(0, weight=1)
            grid_frame.grid_columnconfigure(1, weight=1)
            
            for idx, app in enumerate(apps_list):
                r = idx // 2
                c = idx % 2
                det_enabled = track_details_map.get(app.lower(), False)
                card = CategorySettingsRow(
                    grid_frame, 
                    exe_name=app, 
                    current_category=cat_name, 
                    track_details_enabled=det_enabled,
                    on_change_callback=self._update_app_category,
                    on_toggle_details_callback=self._toggle_app_track_details
                )
                card.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
                
        if not has_apps:
            no_apps_lbl = ctk.CTkLabel(
                self.add_apps_scroll,
                text="No tracked applications found to categorize yet. Start using apps to populate this list.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=THEME['text_muted']
            )
            no_apps_lbl.pack(pady=30)

    def _change_poll_interval(self, choice):
        """Update polling rate setting dynamically in the DB and running tracker thread."""
        seconds = int(choice.split()[0])
        database.set_setting(self.db_path, "poll_interval", seconds)
        if self.tracker:
            self.tracker.poll_interval = seconds
            print(f"[UI] Tracker polling interval changed to: {seconds}s")
            
    def _update_app_category(self, exe_name, category):
        """Update app category mapping in SQLite database and refresh UI."""
        database.set_app_category(self.db_path, exe_name, category)
        print(f"[UI] Set category for {exe_name} to {category}")
        
        # If the app was set to Untracked or moved out of it, update tracker cached set dynamically
        if self.tracker:
            self.tracker.load_tracked_apps()
            
        # Redraw settings panel immediately to show them in their new section grid
        self.build_settings_tab()

    def _toggle_startup(self):
        """Enable or disable registry key to start the app automatically when Windows boots."""
        enabled = self.startup_switch.get() == 1
        REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
        REG_NAME = "LocalTimeTracker"
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_WRITE)
            if enabled:
                # Find executable path dynamically (handles script mode and compiled EXE)
                if getattr(sys, 'frozen', False):
                    exe_path = sys.executable
                else:
                    # Point to script file with pythonw.exe
                    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                    script_path = os.path.abspath(sys.argv[0])
                    exe_path = f'"{python_exe}" "{script_path}"'
                
                winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, exe_path)
                print(f"[UI] Enabled run at startup in registry pointing to: {exe_path}")
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
        """Open a directory picker, copy the current database, and update configuration paths."""
        from tkinter import filedialog
        
        current_folder = os.path.dirname(self.db_path)
        new_folder = filedialog.askdirectory(
            initialdir=current_folder, 
            title="Select Database Directory"
        )
        
        if not new_folder:
            return # Dialog cancelled
            
        new_folder = os.path.normpath(new_folder)
        new_db_dir = os.path.join(new_folder, "LocalTimeTracker")
        
        if new_db_dir == current_folder:
            return
            
        try:
            os.makedirs(new_db_dir, exist_ok=True)
            new_db_path = os.path.join(new_db_dir, "tracker.db")
            
            print(f"[UI] Migrating database from {self.db_path} to {new_db_path}")
            self.db_status_label.configure(text="Migrating database...", text_color="#3b82f6")
            self.update_idletasks()
            
            was_tracking = False
            if self.tracker and self.tracker.tracker_thread and self.tracker.tracker_thread.is_alive():
                was_tracking = True
                self.tracker.stop()
                
            if os.path.exists(self.db_path):
                shutil.copy2(self.db_path, new_db_path)
                print("[UI] Database copied successfully.")
                
            self.db_path = new_db_path
            if self.tracker:
                self.tracker.db_path = new_db_path
                
            config_dir = os.path.join(
                os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), 
                "LocalTimeTracker"
            )
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
            print(f"[UI] Error moving database: {e}")
            self.db_status_label.configure(text=f"❌ Error moving database: {e}", text_color="#ef4444")

    def _clear_database_data(self):
        """Prompt user for confirmation, stop tracker, clear SQLite tables, restart tracker, and refresh UI."""
        from tkinter import messagebox
        
        confirm = messagebox.askyesno(
            "Clear All Data",
            "Are you absolutely sure you want to permanently delete all logged active times, category mappings, and settings?\n\nThis action cannot be undone.",
            icon="warning"
        )
        
        if not confirm:
            return
            
        try:
            # 1. Stop background tracker to avoid DB locks
            was_tracking = False
            if self.tracker:
                was_tracking = True
                self.tracker.stop()
                
            # 2. Clear all tables in SQLite
            database.clear_all_data(self.db_path)
            database.init_db(self.db_path)
            
            # 3. Reset internal UI states
            self.fired_alerts.clear()
            
            # 4. Restart tracker if it was active
            if was_tracking:
                self.tracker.start()
                
            # 5. Rebuild and refresh all tabs to update UI metrics back to zero
            self.refresh_data()
            self.build_settings_tab()
            
            messagebox.showinfo("Success", "All tracker data has been successfully cleared and reset.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while clearing data: {e}")

    def open_weekly_popup(self):
        """Open weekly daily breakdown pop-up modal."""
        print("[UI] Opening weekly daily breakdown pop-up modal...")
        WeeklyCalendarWindow(self, self.db_path)

    def open_monthly_popup(self):
        """Open interactive monthly calendar pop-up modal."""
        print("[UI] Opening interactive monthly calendar pop-up modal...")
        MonthlyCalendarWindow(self, self.db_path)

    def build_history_tab(self):
        """Construct the merged History, Reports & Analytics layout."""
        # Clear previous history widgets
        for widget in self.history_scroll.winfo_children():
            widget.destroy()
            
        # Section Header
        title_history = ctk.CTkLabel(
            self.history_scroll,
            text="📈 History, Reports & Analytics",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            anchor="w",
            text_color=THEME['accent']
        )
        title_history.pack(fill="x", padx=10, pady=(15, 10))
        
        # Grid frame for stats cards (Uses tk.Frame for fast resizing)
        stats_grid_frame = tk.Frame(self.history_scroll, bg=THEME['bg_main'])
        stats_grid_frame.pack(fill="x", padx=5, pady=5)
        stats_grid_frame.grid_columnconfigure(0, weight=1)
        stats_grid_frame.grid_columnconfigure(1, weight=1)
        
        # Fetch statistics
        weekly_avg = database.get_weekly_average(self.db_path)
        monthly_total = database.get_monthly_total(self.db_path)
        
        # Helper to bind click commands to widgets and show a hand cursor
        def bind_card(widget, callback):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda e: callback())
        
        # Card 1: Past 7 Days Average
        card1 = ctk.CTkFrame(stats_grid_frame, fg_color=THEME['bg_card'], corner_radius=8, border_width=1, border_color=THEME['border_subtle'])
        card1.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
        
        lbl1 = ctk.CTkLabel(
            card1, 
            text="PAST 7 DAYS DAILY AVERAGE (CLICK TO VIEW)", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), 
            text_color="#10b981"
        )
        lbl1.pack(padx=15, pady=(12, 2))
        
        val1 = ctk.CTkLabel(
            card1, 
            text=format_duration(weekly_avg), 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), 
            text_color=THEME['text_primary']
        )
        val1.pack(padx=15, pady=(2, 12))
        
        # Make Card 1 clickable
        bind_card(card1, self.open_weekly_popup)
        bind_card(lbl1, self.open_weekly_popup)
        bind_card(val1, self.open_weekly_popup)
        
        # Card 2: This Month's Total Screen Time
        card2 = ctk.CTkFrame(stats_grid_frame, fg_color=THEME['bg_card'], corner_radius=8, border_width=1, border_color=THEME['border_subtle'])
        card2.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")
        
        lbl2 = ctk.CTkLabel(
            card2, 
            text="THIS MONTH'S TOTAL TIME (CLICK TO VIEW)", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), 
            text_color=THEME['accent']
        )
        lbl2.pack(padx=15, pady=(12, 2))
        
        val2 = ctk.CTkLabel(
            card2, 
            text=format_duration(monthly_total), 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), 
            text_color=THEME['text_primary']
        )
        val2.pack(padx=15, pady=(2, 12))
        
        # Make Card 2 clickable
        bind_card(card2, self.open_monthly_popup)
        bind_card(lbl2, self.open_monthly_popup)
        bind_card(val2, self.open_monthly_popup)
        
        # --- Analytics Charts Split Panel (Horizontal Split) ---
        charts_split_frame = tk.Frame(self.history_scroll, bg=THEME['bg_main'])
        charts_split_frame.pack(fill="x", padx=5, pady=10)
        
        # Left Panel (Donut Chart)
        left_card = ctk.CTkFrame(charts_split_frame, fg_color=THEME['bg_card'], corner_radius=10, border_width=1, border_color=THEME['border_subtle'])
        left_card.pack(side="left", fill="both", expand=True, padx=10, pady=5)
        
        lbl_donut = ctk.CTkLabel(
            left_card,
            text="Today's Category Breakdown",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=THEME['text_primary']
        )
        lbl_donut.pack(pady=(12, 5))
        
        today = datetime.date.today().isoformat()
        cat_durations = database.get_category_durations(self.db_path, today)
        donut = DonutChart(left_card, cat_durations, CATEGORY_COLORS, width=280, height=220)
        donut.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Right Panel (Weekly Bar Chart)
        right_card = ctk.CTkFrame(charts_split_frame, fg_color=THEME['bg_card'], corner_radius=10, border_width=1, border_color=THEME['border_subtle'])
        right_card.pack(side="right", fill="both", expand=True, padx=10, pady=5)
        
        lbl_bar = ctk.CTkLabel(
            right_card,
            text="Weekly Screen Time Trend",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=THEME['text_primary']
        )
        lbl_bar.pack(pady=(12, 5))
        
        # Fetch weekly history totals
        weekly_totals = database.get_last_7_days_totals(self.db_path)
        barchart = BarChart(right_card, weekly_totals, bar_color=THEME['accent'], width=380, height=220)
        barchart.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Monthly Top Apps Header
        top_title = ctk.CTkLabel(
            self.history_scroll,
            text="🏆 Top Apps This Month",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            anchor="w",
            text_color="#3b82f6"
        )
        top_title.pack(fill="x", padx=10, pady=(25, 5))
        
        desc_top = ctk.CTkLabel(
            self.history_scroll,
            text="Most used applications in the current calendar month.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8",
            anchor="w"
        )
        desc_top.pack(fill="x", padx=10, pady=(0, 10))
        
        # Fetch and list top monthly apps
        monthly_apps = database.get_monthly_breakdown(self.db_path)
        app_categories = database.get_app_categories(self.db_path)
        
        if monthly_apps:
            max_monthly_sec = monthly_apps[0]['duration']
            for app in monthly_apps:
                exe = app['exe_name']
                cat = app_categories.get(exe.lower(), "Uncategorized")
                
                row = AppRow(
                    self.history_scroll,
                    exe_name=exe,
                    duration=app['duration'],
                    total_duration=monthly_total,
                    max_duration=max_monthly_sec,
                    category=cat
                )
                row.pack(fill="x", padx=10, pady=4)
        else:
            no_monthly_lbl = ctk.CTkLabel(
                self.history_scroll,
                text="No monthly application tracking history recorded yet.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color="#64748b"
            )
            no_monthly_lbl.pack(pady=30)

    def refresh_data(self):
        """Fetch latest database stats and rebuild the UI list views."""
        today = datetime.date.today().isoformat()
        
        # 1. Update Sidebar Stats Cards
        today_total_sec = database.get_today_total_time(self.db_path, today)
        daily_avg_sec = database.get_daily_average(self.db_path)
        
        self.today_time_label.configure(text=format_duration(today_total_sec))
        self.avg_time_label.configure(text=format_duration(daily_avg_sec))
        
        active_tab = self.view_selector.get()
        
        # 2. Rebuild the Active Tab
        if active_tab == "App Breakdown":
            if self.rendered_grid_container:
                self.rendered_grid_container.destroy()
                self.rendered_grid_container = None
                
            self.rendered_grid_container = tk.Frame(self.apps_scroll, bg=THEME['bg_main'])
            self.rendered_grid_container.pack(fill="both", expand=True, padx=5, pady=5)
            self.rendered_grid_container.grid_columnconfigure(0, weight=1)
            self.rendered_grid_container.grid_columnconfigure(1, weight=1)
            
            app_breakdown = database.get_today_app_breakdown(self.db_path, today)
            app_categories = database.get_app_categories(self.db_path)
            cat_durations = database.get_category_durations(self.db_path, today)
            track_details_map = database.get_track_details_map(self.db_path)
            
            grouped_apps = {
                'Productivity': [],
                'Entertainment': [],
                'Distraction': [],
                'Uncategorized': []
            }
            
            for app in app_breakdown:
                exe = app['exe_name']
                cat = app_categories.get(exe.lower(), "Uncategorized")
                
                if cat == 'Untracked':
                    continue
                    
                if cat in grouped_apps:
                    grouped_apps[cat].append(app)
                else:
                    grouped_apps['Uncategorized'].append(app)
                    
            coords = {
                'Productivity': (0, 0),
                'Entertainment': (0, 1),
                'Distraction': (1, 0),
                'Uncategorized': (1, 1)
            }
            
            overall_max_sec = app_breakdown[0]['duration'] if app_breakdown else 0
            
            for cat_name in ['Productivity', 'Entertainment', 'Distraction', 'Uncategorized']:
                color = CATEGORY_COLORS[cat_name]
                icon = CATEGORY_ICONS[cat_name]
                row_val, col_val = coords[cat_name]
                
                panel = ctk.CTkFrame(
                    self.rendered_grid_container, 
                    fg_color=THEME['bg_card'], 
                    corner_radius=10, 
                    border_width=1, 
                    border_color=THEME['border_subtle']
                )
                panel.grid(row=row_val, column=col_val, padx=10, pady=10, sticky="nsew")
                
                cat_sec_time = cat_durations.get(cat_name, 0)
                header_text = f"{icon} {cat_name.upper()} — {format_duration(cat_sec_time)}"
                header_lbl = ctk.CTkLabel(
                    panel, 
                    text=header_text, 
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                    text_color=color,
                    anchor="w"
                )
                header_lbl.pack(fill="x", padx=15, pady=(12, 8))
                
                apps_in_cat = grouped_apps[cat_name]
                if apps_in_cat:
                    for app in apps_in_cat:
                        exe_lower = app['exe_name'].lower()
                        is_expandable = track_details_map.get(exe_lower, False)
                        app_row = AppRow(
                            panel,
                            exe_name=app['exe_name'],
                            duration=app['duration'],
                            total_duration=today_total_sec,
                            max_duration=overall_max_sec,
                            category=cat_name,
                            db_path=self.db_path,
                            date_str=today,
                            dashboard=self,
                            is_expandable=is_expandable
                        )
                        app_row.pack(fill="x", padx=10, pady=4)
                        
                        # Re-expand if it was previously expanded
                        if exe_lower in self.expanded_apps:
                            app_row.is_expanded = True
                            app_row.name_label.configure(text=f"▼  {app['exe_name']}")
                            app_row.load_sub_projects()
                else:
                    empty_lbl = ctk.CTkLabel(
                        panel, 
                        text="No activity tracked today", 
                        font=ctk.CTkFont(family="Segoe UI", size=11),
                        text_color="#64748b",
                        anchor="w"
                    )
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
                        
                    row = AppRow(
                        self.browser_scroll,
                        exe_name=item['platform'],
                        duration=item['duration'],
                        total_duration=total_browser_sec,
                        max_duration=max_browser_sec,
                        category=cat
                    )
                    row.pack(fill="x", pady=4)
                    self.rendered_browser_rows.append(row)
            else:
                lbl = ctk.CTkLabel(
                    self.browser_scroll, 
                    text="No active browser highlights recorded today.", 
                    font=ctk.CTkFont(family="Segoe UI", size=13),
                    text_color="#64748b"
                )
                lbl.pack(pady=40)
                self.rendered_browser_rows.append(lbl)

        elif active_tab == "History & Reports":
            self.build_history_tab()

        # 3. Check Screen Time Goals / Alerts
        current_date = datetime.date.today().isoformat()
        if current_date != self.last_alert_date:
            self.fired_alerts.clear()
            self.last_alert_date = current_date
            
        for category in ['Productivity', 'Entertainment', 'Distraction']:
            goal_sec = database.get_category_goal(self.db_path, category)
            if goal_sec > 0 and category not in self.fired_alerts:
                cat_durations = database.get_category_durations(self.db_path, current_date)
                actual_sec = cat_durations.get(category, 0)
                
                if category in ('Entertainment', 'Distraction'):
                    if actual_sec >= goal_sec:
                        self.fired_alerts.add(category)
                        msg = f"You have reached your daily limit of {format_duration(goal_sec)} for {category}!"
                        title = "Limit Exceeded!"
                        if self.on_notify:
                            self.on_notify(msg, title)
                elif category == 'Productivity':
                    if actual_sec >= goal_sec:
                        self.fired_alerts.add(category)
                        msg = f"Congratulations! You reached your daily productivity target of {format_duration(goal_sec)}!"
                        title = "Target Reached!"
                        if self.on_notify:
                            self.on_notify(msg, title)

    # def _send_feedback(self):
    #     """Send feedback directly via Web3Forms API in a background thread."""
    #     import threading
    #     
    #     name = self.feedback_name.get().strip() if self.feedback_name.get().strip() else "Anonymous"
    #     body = self.feedback_textbox.get("0.0", "end").strip()
    #     
    #     if not body or body == "Type your feedback here...":
    #         self.feedback_status_lbl.configure(text="Please type some feedback first.", text_color="#f87171")
    #         return
    #     
    #     # Disable button state while sending
    #     self.feedback_status_lbl.configure(text="Sending...", text_color=THEME['text_secondary'])
    #     self.update_idletasks()
    #     
    #     def _do_send():
    #         import urllib.request
    #         import urllib.error
    #         import json as _json
    #         
    #         payload = _json.dumps({
    #             "access_key": "b5a3b32f-ab89-46bb-85e6-a20ae11bc230",
    #             "subject": "Time Tracker Feedback",
    #             "from_name": name,
    #             "name": name,
    #             "message": body
    #         }).encode("utf-8")
    #         
    #         req = urllib.request.Request(
    #             "https://api.web3forms.com/submit",
    #             data=payload,
    #             headers={
    #                 "Content-Type": "application/json",
    #                 "Accept": "application/json"
    #             },
    #             method="POST"
    #         )
    #         
    #         try:
    #             with urllib.request.urlopen(req, timeout=10) as resp:
    #                 result = _json.loads(resp.read().decode())
    #                 if result.get("success"):
    #                     self.after(0, lambda: self.feedback_status_lbl.configure(
    #                         text="Feedback sent! Thank you.", text_color="#10b981"))
    #                     self.after(0, lambda: self.feedback_textbox.delete("0.0", "end"))
    #                     self.after(0, lambda: self.feedback_name.delete(0, "end"))
    #                 else:
    #                     msg = result.get("message", "Unknown error")
    #                     err_text = f"Failed: {msg}"
    #                     self.after(0, lambda t=err_text: self.feedback_status_lbl.configure(
    #                         text=t, text_color="#f87171"))
    #         except urllib.error.HTTPError as e:
    #             # Read the error body for more detail
    #             try:
    #                 err_body = _json.loads(e.read().decode())
    #                 err_msg = err_body.get("message", str(e.code))
    #             except Exception:
    #                 err_msg = f"HTTP {e.code}"
    #             err_text = f"Error: {err_msg}"
    #             self.after(0, lambda t=err_text: self.feedback_status_lbl.configure(
    #                 text=t, text_color="#f87171"))
    #         except Exception as e:
    #             err_text = f"Network error: {type(e).__name__}"
    #             self.after(0, lambda t=err_text: self.feedback_status_lbl.configure(
    #                 text=t, text_color="#f87171"))
    #     
    #     threading.Thread(target=_do_send, daemon=True).start()

    def _force_quit_app(self):
        """Immediately force-terminate the application and all threads."""
        import os
        try:
            # Flush tracker data first if available
            if self.tracker:
                self.tracker.stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    def schedule_refresh(self):
        """Schedule the refresh method to execute every 5 seconds."""
        self.refresh_data()
        self.after(5000, self.schedule_refresh)

    def show_window(self):
        """Show and focus the window."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide_window(self):
        """Hide the window instead of destroying/quitting."""
        self.withdraw()

    def run_update_check(self, quiet=True):
        """Start the update check in a background thread to prevent UI freezing."""
        import threading
        threading.Thread(target=self.check_for_updates, args=(quiet,), daemon=True).start()

    def check_for_updates(self, quiet=True):
        """Query GitHub Releases API to see if a newer version tag exists."""
        import urllib.request
        import json
        import webbrowser
        import tkinter.messagebox as messagebox
        
        current_version = "v1.0.2"
        url = "https://api.github.com/repos/hp1user/tracker/releases/latest"
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        
        def parse_version(v):
            """Parse 'v1.0.2' into comparable tuple (1, 0, 2)."""
            try:
                return tuple(int(x) for x in v.lstrip("v").split("."))
            except Exception:
                return (0,)
        
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get("tag_name")
                release_url = data.get("html_url")
                assets = data.get("assets", [])
                
                if latest_version and parse_version(latest_version) > parse_version(current_version):
                    ans = messagebox.askyesno(
                        "Update Available", 
                        f"A new version ({latest_version}) is available!\n\n"
                        f"Current version: {current_version}\n\n"
                        "Download and install the update now?"
                    )
                    if ans:
                        # Find the .exe asset download URL
                        download_url = None
                        for asset in assets:
                            if asset.get("name", "").lower().endswith(".exe"):
                                download_url = asset.get("browser_download_url")
                                break
                        
                        if download_url and getattr(sys, 'frozen', False):
                            # Running as compiled EXE - do auto-update
                            import threading
                            threading.Thread(
                                target=self._download_and_apply_update,
                                args=(download_url, latest_version),
                                daemon=True
                            ).start()
                        else:
                            # Running as script or no asset found - open browser
                            webbrowser.open(release_url)
                elif not quiet:
                    messagebox.showinfo("Up to Date", f"You are running the latest version ({current_version}).")
        except Exception as e:
            if not quiet:
                messagebox.showerror("Update Error", f"Failed to check for updates:\n{e}")

    def _download_and_apply_update(self, download_url, new_version):
        """Download the new EXE and swap it in via a batch script after exit."""
        import urllib.request
        import tempfile
        import subprocess
        import tkinter.messagebox as messagebox

        try:
            # Show downloading status on main thread
            self.after(0, lambda: messagebox.showinfo(
                "Downloading Update",
                f"Downloading {new_version}...\n\nThe app will restart automatically when done."
            ))

            # Download new EXE to a temp file
            temp_dir = tempfile.gettempdir()
            new_exe_path = os.path.join(temp_dir, "TimeTracker_new.exe")
            current_exe_path = sys.executable

            with urllib.request.urlopen(download_url, timeout=60) as resp:
                with open(new_exe_path, "wb") as f:
                    f.write(resp.read())

            # Write a batch script that:
            # 1. Waits for this process to exit
            # 2. Copies new EXE over old EXE
            # 3. Restarts the app
            # 4. Deletes itself
            bat_path = os.path.join(temp_dir, "timetracker_updater.bat")
            bat_content = (
                "@echo off\n"
                "timeout /t 2 /nobreak > NUL\n"
                f"copy /y \"{new_exe_path}\" \"{current_exe_path}\"\n"
                f"start \"\" \"{current_exe_path}\"\n"
                f"del \"{new_exe_path}\"\n"
                "del \"%~f0\"\n"
            )
            with open(bat_path, "w") as f:
                f.write(bat_content)

            # Launch the updater script in background and quit
            subprocess.Popen(
                ["cmd", "/c", bat_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True
            )

            # Quit app so the batch can replace the EXE
            self.after(0, lambda: os._exit(0))

        except Exception as e:
            err = str(e)
            self.after(0, lambda: messagebox.showerror(
                "Update Failed", f"Could not download update:\n{err}\n\nPlease download manually from GitHub."
            ))

    def _quick_add_app(self):
        """Read the combobox selection, normalize the app name, save to DB, update tracker, and refresh UI."""
        app_name = self.add_app_combo.get().strip()
        
        # Check if the user hasn't selected/typed anything or left the placeholder text
        if not app_name or app_name == "Select or type app name...":
            return
            
        # Normalize: strip, lowercase, ensure it has a .exe suffix if it has no extension
        app_name = app_name.lower()
        if not app_name.endswith(".exe") and "." not in app_name:
            app_name += ".exe"
            
        category = self.add_cat_menu.get()
        
        # Save to database
        database.set_app_category(self.db_path, app_name, category)
        print(f"[UI] Quick-added mapping: {app_name} -> {category}")
        
        # Update background tracker's cache if active
        if self.tracker:
            self.tracker.load_tracked_apps()
            
        # Re-render Add Apps tab to show the new app in its list
        self.build_add_apps_tab()

    def _toggle_app_track_details(self, exe_name, enabled):
        """Update the database with the tracking details preference for this app."""
        database.set_app_track_details(self.db_path, exe_name, enabled)
        print(f"[UI] Toggled detail tracking for {exe_name} to {enabled}")

    def _save_goals(self):
        """Save the hours and minutes settings for categories back to database."""
        try:
            p_sec = int(self.p_h.get()) * 3600 + int(self.p_m.get()) * 60
            e_sec = int(self.e_h.get()) * 3600 + int(self.e_m.get()) * 60
            d_sec = int(self.d_h.get()) * 3600 + int(self.d_m.get()) * 60
            
            # Write to DB
            database.set_category_goal(self.db_path, "Productivity", p_sec)
            database.set_category_goal(self.db_path, "Entertainment", e_sec)
            database.set_category_goal(self.db_path, "Distraction", d_sec)
            
            # Clear alerts for updated goals so they can trigger if they are now exceeded
            self.fired_alerts.discard("Productivity")
            self.fired_alerts.discard("Entertainment")
            self.fired_alerts.discard("Distraction")
            
            self.goals_status_lbl.configure(text="✅ Daily goals updated successfully!", text_color="#10b981")
            # Clear status message after 3 seconds
            self.after(3000, lambda: self.goals_status_lbl.configure(text=""))
        except Exception as e:
            self.goals_status_lbl.configure(text=f"❌ Error updating goals: {e}", text_color="#ef4444")
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
