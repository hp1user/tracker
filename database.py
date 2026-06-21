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
