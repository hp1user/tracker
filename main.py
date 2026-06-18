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
    
    # Define notification callback (resolves tray dynamically from outer scope)
    def notify_user(message, title="Time Tracker"):
        try:
            if 'tray' in locals() and tray and tray.icon:
                tray.icon.notify(message, title)
            else:
                print(f"[Notification] {title}: {message}")
        except Exception as e:
            print(f"[Main] Notification error: {e}")

    # Initialize the dashboard UI (running on the main thread)
    app = TrackerDashboard(db_path, tracker=tracker, on_notify=notify_user)
    
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
