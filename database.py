import sqlite3
import os

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
    finally:
        conn.close()

def save_usage(db_path, records):
    """
    Save or aggregate window usage records.
    records is a list of tuples: (date, exe_name, window_title, duration_seconds)
    """
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
    """Return a list of dicts for app usage breakdown: [{'exe_name': '...', 'duration': 123}] (excluding Untracked apps)"""
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
    """Return the daily average usage in seconds across all logged days (excluding Untracked apps)."""
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
    """
    Return platform-specific highlights for browser usage.
    Looks for major platforms (YouTube, GitHub, etc.) inside browser window titles.
    """
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
        
        result = {
            'Productivity': 0,
            'Entertainment': 0,
            'Distraction': 0,
            'Uncategorized': 0
        }
        for row in rows:
            cat = row['category']
            # If the category is not one of the pre-defined ones, lump it under Uncategorized
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
