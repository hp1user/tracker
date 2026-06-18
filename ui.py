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

# Configure customtkinter colors and themes
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Category Colors & Emoticons for UI headers
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

class AppRow(tk.Frame):
    """Custom compact row displaying application usage. Inherits from tk.Frame for maximum resize performance."""
    def __init__(self, master, exe_name, duration, total_duration, max_duration, category, bg_color="#1e293b"):
        super().__init__(master, bg=bg_color)
        
        # Calculate percentage relative to total day/period screen time
        percentage_total = (duration / total_duration) * 100 if total_duration > 0 else 0
        # Progress bar fill relative to the highest overall app for visual balance
        bar_value = duration / max_duration if max_duration > 0 else 0
        
        bar_color = CATEGORY_COLORS.get(category, '#64748b')
        
        # Name label - takes remaining space, allows resizing
        self.name_label = ctk.CTkLabel(
            self, 
            text=exe_name, 
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            anchor="w",
            fg_color=bg_color
        )
        self.name_label.pack(side="left", padx=(5, 5), fill="x", expand=True)
        
        # Progress Bar - Set to fixed width to avoid Tkinter canvas redrawing lag during window resizes!
        self.progress_bar = ctk.CTkProgressBar(
            self, 
            orientation="horizontal", 
            width=110, # Fixed width prevents dynamic redraw events
            height=8, 
            fg_color="#020617", # Dark background for contrast
            progress_color=bar_color
        )
        self.progress_bar.set(bar_value)
        self.progress_bar.pack(side="left", padx=5)
        
        # Info Label (compact percentage + duration)
        info_text = f"{percentage_total:.0f}% ({format_duration(duration)})"
        self.info_label = ctk.CTkLabel(
            self, 
            text=info_text, 
            font=ctk.CTkFont(family="Segoe UI", size=10),
            anchor="e",
            width=70,
            fg_color=bg_color
        )
        self.info_label.pack(side="right", padx=(5, 5))

class CategorySettingsRow(tk.Frame):
    """Compact card in Settings for mapping an executable name to a category. Uses tk.Frame for speed."""
    def __init__(self, master, exe_name, current_category, on_change_callback):
        super().__init__(master, bg="#1e293b")
        
        self.exe_name = exe_name
        self.on_change_callback = on_change_callback
        
        # Application name
        self.name_label = ctk.CTkLabel(
            self, 
            text=exe_name, 
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            anchor="w",
            fg_color="#1e293b"
        )
        self.name_label.pack(side="left", padx=10, fill="x", expand=True)
        
        # Category Selector Dropdown (includes Untracked option)
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
        self.after(10, self.lift) # Make sure it focuses on Windows
        
        # Header
        header_lbl = ctk.CTkLabel(
            self,
            text="📅 Weekly Screen Time History",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#10b981",
            anchor="w"
        )
        header_lbl.pack(fill="x", padx=20, pady=(20, 5))
        
        desc_lbl = ctk.CTkLabel(
            self,
            text="Total active time logged for each of the last 7 days.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8",
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
                text_color="#f8fafc",
                anchor="w"
            )
            summary_lbl.pack(fill="x", padx=10, pady=(0, 10))
            
            for item in data:
                date_str = item['date']
                dur = item['duration']
                
                dt = datetime.date.fromisoformat(date_str)
                formatted_date = dt.strftime("%A, %b %d")
                
                # Row Container using standard Frame
                row = tk.Frame(scroll, bg="#1e293b")
                row.pack(fill="x", pady=4, padx=5)
                
                # Date label
                lbl = ctk.CTkLabel(
                    row,
                    text=formatted_date,
                    font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                    anchor="w",
                    width=150,
                    fg_color="#1e293b"
                )
                lbl.pack(side="left", padx=10, pady=8)
                
                # Simple relative progress bar
                bar_value = dur / max_duration if max_duration > 0 else 0
                bar = ctk.CTkProgressBar(
                    row,
                    orientation="horizontal",
                    height=8,
                    fg_color="#020617",
                    progress_color="#10b981"
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
                    fg_color="#1e293b"
                )
                val.pack(side="right", padx=10)
        else:
            no_data = ctk.CTkLabel(
                scroll,
                text="No active tracking records found for the past 7 days.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color="#64748b"
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
        self.configure(fg_color="#020617")
        self.after(10, self.lift)
        
        # Header Controls Frame
        self.header_frame = tk.Frame(self, bg="#020617")
        self.header_frame.pack(fill="x", padx=20, pady=(20, 5))
        
        # Month Navigation Title
        self.month_title_label = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#3b82f6",
            anchor="w"
        )
        self.month_title_label.pack(side="left", fill="x", expand=True)
        
        # Back month button
        btn_prev = ctk.CTkButton(
            self.header_frame,
            text="<",
            command=self._prev_month,
            width=32,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155"
        )
        btn_prev.pack(side="right", padx=3)
        
        # Next month button
        btn_next = ctk.CTkButton(
            self.header_frame,
            text=">",
            command=self._next_month,
            width=32,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155"
        )
        btn_next.pack(side="right", padx=3)
        
        desc_lbl = ctk.CTkLabel(
            self,
            text="Color highlights represent daily active time (Dark Blue for light, Bright Blue for heavy usage).",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8",
            anchor="w"
        )
        desc_lbl.pack(fill="x", padx=20, pady=(0, 15))
        
        # Main Calendar Grid Container Frame
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
                text_color="#94a3b8"
            )
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

class TrackerDashboard(ctk.CTk):
    def __init__(self, db_path, tracker=None):
        super().__init__()
        self.db_path = db_path
        self.tracker = tracker
        
        # Window setup
        self.title("Windows Time Tracker")
        self.geometry("950x650")
        self.minsize(850, 550)
        
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

    def _setup_sidebar(self):
        """Create left side panel with stats cards."""
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#0f172a")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False) # Prevent grid geometry resizing from collapsing the sidebar
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Spacer
        
        # Logo / Title
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="⏱️ Tracker", 
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color="#3b82f6"
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="w")
        
        # Card 1: Today's Time
        self.today_card = ctk.CTkFrame(self.sidebar_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.today_card.grid(row=1, column=0, padx=15, pady=10, sticky="ew")
        
        self.today_card_title = ctk.CTkLabel(
            self.today_card, 
            text="SCREEN TIME TODAY", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94a3b8"
        )
        self.today_card_title.pack(padx=15, pady=(10, 2))
        
        self.today_time_label = ctk.CTkLabel(
            self.today_card, 
            text="0h 0m", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#f8fafc"
        )
        self.today_time_label.pack(padx=15, pady=(2, 10))
        
        # Card 2: Daily Average
        self.avg_card = ctk.CTkFrame(self.sidebar_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.avg_card.grid(row=2, column=0, padx=15, pady=10, sticky="ew")
        
        self.avg_card_title = ctk.CTkLabel(
            self.avg_card, 
            text="DAILY AVERAGE", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#94a3b8"
        )
        self.avg_card_title.pack(padx=15, pady=(10, 2))
        
        self.avg_time_label = ctk.CTkLabel(
            self.avg_card, 
            text="0h 0m", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#f8fafc"
        )
        self.avg_time_label.pack(padx=15, pady=(2, 10))

        # Manual Refresh Button
        self.refresh_btn = ctk.CTkButton(
            self.sidebar_frame,
            text="Sync & Refresh",
            command=self.refresh_data,
            fg_color="#3b82f6",
            hover_color="#2563eb",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=32
        )
        self.refresh_btn.grid(row=3, column=0, padx=15, pady=15, sticky="ew")
        
        # Footer
        self.footer_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Local Time Tracker v0.1", 
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#64748b"
        )
        self.footer_label.grid(row=5, column=0, padx=20, pady=20, sticky="s")

    def _setup_main_panel(self):
        """Create right side panel with tabs and data lists. Uses tk.Frame for maximum resize performance."""
        self.main_frame = tk.Frame(self, bg="#020617")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        # View switcher
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
        
        # Scrollable container for Apps Breakdown
        self.apps_scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.apps_scroll.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        
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
        """Construct settings menu and app category grids."""
        # Clear previous settings widgets
        for widget in self.settings_scroll.winfo_children():
            widget.destroy()
            
        # Section 1: Tracker Settings Header
        title_settings = ctk.CTkLabel(
            self.settings_scroll,
            text="⚙️ Tracker Settings",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            anchor="w",
            text_color="#3b82f6"
        )
        title_settings.pack(fill="x", padx=10, pady=(15, 10))
        
        # Polling Interval Setting Card
        interval_card = ctk.CTkFrame(self.settings_scroll, fg_color="#1e293b", corner_radius=8)
        interval_card.pack(fill="x", padx=10, pady=5)
        
        interval_label = ctk.CTkLabel(
            interval_card,
            text="Polling Interval",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
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
        
        # Startup Settings Card (Registry Toggle)
        startup_card = ctk.CTkFrame(self.settings_scroll, fg_color="#1e293b", corner_radius=8)
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
            progress_color="#3b82f6",
            fg_color="#334155"
        )
        if is_startup_enabled:
            self.startup_switch.select()
        else:
            self.startup_switch.deselect()
        self.startup_switch.pack(side="left", padx=15, pady=15)
        
        # Database Folder Path Settings Card
        db_card = ctk.CTkFrame(self.settings_scroll, fg_color="#1e293b", corner_radius=8)
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
            text_color="#94a3b8",
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
            fg_color="#334155",
            hover_color="#475569"
        )
        browse_btn.pack(side="right", padx=15, pady=15)
        
        # Section: Quick-Add Application Category Card
        quick_add_card = ctk.CTkFrame(self.settings_scroll, fg_color="#1e293b", corner_radius=8)
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
            text_color="#94a3b8",
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
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.add_app_combo.set("Select or type app name...")
        self.add_app_combo.pack(side="left", padx=(0, 10))
        
        self.add_cat_menu = ctk.CTkOptionMenu(
            controls_frame,
            values=["Productivity", "Entertainment", "Distraction", "Untracked", "Uncategorized"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            width=130,
            fg_color="#334155",
            button_color="#475569",
            button_hover_color="#64748b"
        )
        self.add_cat_menu.set("Untracked") # Default to Untracked as that's the primary use-case
        self.add_cat_menu.pack(side="left", padx=(0, 10))
        
        add_btn = ctk.CTkButton(
            controls_frame,
            text="Assign Category",
            command=self._quick_add_app,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            width=130,
            fg_color="#3b82f6",
            hover_color="#2563eb"
        )
        add_btn.pack(side="left")
        
        # Section 2: App Categories Header
        title_categories = ctk.CTkLabel(
            self.settings_scroll,
            text="🏷️ App Categories Settings",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            anchor="w",
            text_color="#3b82f6"
        )
        title_categories.pack(fill="x", padx=10, pady=(25, 5))
        
        desc_label = ctk.CTkLabel(
            self.settings_scroll,
            text="Group and configure categories. Mark applications as 'Untracked' to exclude them entirely.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8",
            anchor="w"
        )
        desc_label.pack(fill="x", padx=10, pady=(0, 15))
        
        # Fetch and group unique apps by category
        tracked_apps = database.get_all_tracked_apps(self.db_path)
        categories = database.get_app_categories(self.db_path)
        
        grouped_settings = {
            'Productivity': [],
            'Entertainment': [],
            'Distraction': [],
            'Untracked': [],
            'Uncategorized': []
        }
        
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
            
            # Category Section Label
            cat_header = ctk.CTkLabel(
                self.settings_scroll,
                text=f"{icon} {cat_name.upper()} APPS ({len(apps_list)})",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=color,
                anchor="w"
            )
            cat_header.pack(fill="x", padx=10, pady=(15, 5))
            
            # 2-Column Grid Container Frame (Uses tk.Frame for zero resize-redraw lag)
            grid_frame = tk.Frame(self.settings_scroll, bg="#020617")
            grid_frame.pack(fill="x", padx=5, pady=5)
            grid_frame.grid_columnconfigure(0, weight=1)
            grid_frame.grid_columnconfigure(1, weight=1)
            
            for idx, app in enumerate(apps_list):
                r = idx // 2
                c = idx % 2
                card = CategorySettingsRow(
                    grid_frame, 
                    exe_name=app, 
                    current_category=cat_name, 
                    on_change_callback=self._update_app_category
                )
                card.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
                
        if not has_apps:
            no_apps_lbl = ctk.CTkLabel(
                self.settings_scroll,
                text="No tracked applications found to categorize yet. Start using apps to populate this list.",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color="#64748b"
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
            self.tracker.load_untracked_apps()
            
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

    def open_weekly_popup(self):
        """Open weekly daily breakdown pop-up modal."""
        print("[UI] Opening weekly daily breakdown pop-up modal...")
        WeeklyCalendarWindow(self, self.db_path)

    def open_monthly_popup(self):
        """Open interactive monthly calendar pop-up modal."""
        print("[UI] Opening interactive monthly calendar pop-up modal...")
        MonthlyCalendarWindow(self, self.db_path)

    def build_history_tab(self):
        """Construct the History and Reports layout including weekly averages and monthly top apps."""
        # Clear previous history widgets
        for widget in self.history_scroll.winfo_children():
            widget.destroy()
            
        # Section Header
        title_history = ctk.CTkLabel(
            self.history_scroll,
            text="📈 History & Reports",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            anchor="w",
            text_color="#3b82f6"
        )
        title_history.pack(fill="x", padx=10, pady=(15, 10))
        
        # Grid frame for stats cards (Uses tk.Frame for fast resizing)
        stats_grid_frame = tk.Frame(self.history_scroll, bg="#020617")
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
        card1 = ctk.CTkFrame(stats_grid_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
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
            text_color="#f8fafc"
        )
        val1.pack(padx=15, pady=(2, 12))
        
        # Make Card 1 clickable
        bind_card(card1, self.open_weekly_popup)
        bind_card(lbl1, self.open_weekly_popup)
        bind_card(val1, self.open_weekly_popup)
        
        # Card 2: This Month's Total Screen Time
        card2 = ctk.CTkFrame(stats_grid_frame, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        card2.grid(row=0, column=1, padx=10, pady=5, sticky="nsew")
        
        lbl2 = ctk.CTkLabel(
            card2, 
            text="THIS MONTH'S TOTAL TIME (CLICK TO VIEW)", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), 
            text_color="#3b82f6"
        )
        lbl2.pack(padx=15, pady=(12, 2))
        
        val2 = ctk.CTkLabel(
            card2, 
            text=format_duration(monthly_total), 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"), 
            text_color="#f8fafc"
        )
        val2.pack(padx=15, pady=(2, 12))
        
        # Make Card 2 clickable
        bind_card(card2, self.open_monthly_popup)
        bind_card(lbl2, self.open_monthly_popup)
        bind_card(val2, self.open_monthly_popup)
        
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
                
            self.rendered_grid_container = tk.Frame(self.apps_scroll, bg="#020617")
            self.rendered_grid_container.pack(fill="both", expand=True, padx=5, pady=5)
            self.rendered_grid_container.grid_columnconfigure(0, weight=1)
            self.rendered_grid_container.grid_columnconfigure(1, weight=1)
            
            app_breakdown = database.get_today_app_breakdown(self.db_path, today)
            app_categories = database.get_app_categories(self.db_path)
            cat_durations = database.get_category_durations(self.db_path, today)
            
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
                    fg_color="#1e293b", 
                    corner_radius=10, 
                    border_width=1, 
                    border_color="#334155"
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
                        app_row = AppRow(
                            panel,
                            exe_name=app['exe_name'],
                            duration=app['duration'],
                            total_duration=today_total_sec,
                            max_duration=overall_max_sec,
                            category=cat_name
                        )
                        app_row.pack(fill="x", padx=10, pady=4)
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
            self.tracker.load_untracked_apps()
            
        # Re-render Settings tab to show the new app in its list
        self.build_settings_tab()
