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
