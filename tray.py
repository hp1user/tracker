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
