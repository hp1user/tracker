# ⏱️ Windows Time Tracker (v1.0.3)

A premium, local-only, and privacy-first time tracking application for Windows. It runs quietly in the system tray, monitors active applications, filters out system idle time, and presents detailed productivity metrics in a sleek, lag-free dark mode dashboard.

---

## ✨ Key Features

* **🤫 Quiet System Tray Startup**: Launches directly to the system tray on boot, running silently in the background without stealing window focus.
* **⚡ Lag-Free CustomTkinter UI**: Uses hybrid native `tkinter` components to ensure buttery-smooth window resizing without layout lag.
* **📁 Detail Project Tracking**: Deep window-title parsing for creative/dev software (**Unity**, **Blender**, **Maya**, **Substance Painter/Designer**). Click to expand apps in the dashboard to see your exact file/project name breakdowns in a nested tree view.
* **📊 Integrated Analytics & Trends**: Includes a category donut chart (Productivity, Entertainment, Distraction, and Uncategorized) and a weekly screen time bar chart directly in the merged History dashboard.
* **🌐 Browser Highlights**: Automatically parses browser tabs to extract active durations on key platforms like **GitHub**, **YouTube**, **Stack Overflow**, **Reddit**, **ChatGPT**, **Google Search**, and **Gmail**.
* **🚀 Run on Windows Startup**: Toggle automatic startup on boot directly in settings. Programmed using native Windows user registry hooks (`winreg`) so **no Administrator privileges** are required.
* **📦 Database Relocation & Migration**: Change your tracking database location at any time. The app safely pauses background tracking, copies the SQLite file to preservation, updates app settings, and resumes automatically.
* **🔒 100% Offline & Private**: Zero external connections. All metrics, window logs, and goals are stored locally in an encrypted-on-request SQLite database.

---

## 📂 Project Structure

```text
tracker/
├── requirements.txt   # Pip package dependencies
├── main.py           # Application coordinator & system tray launcher
├── ui.py             # CTk Dashboard & Pop-up Calendar Modals
├── tracker.py        # Active foreground window and idle monitoring engine
├── tray.py           # Threaded system tray icon implementation
├── database.py       # SQLite schema, migrations, and aggregation queries
└── TimeTracker.spec  # PyInstaller spec file for standalone compilation
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
Ensure you have [Python 3.10+](https://www.python.org/downloads/) installed on your Windows machine.

### 2. Install Dependencies
Clone this repository, open your terminal/PowerShell in the project folder, and run:
```powershell
python -m pip install -r requirements.txt
```

### 3. Run the Application
Start the tracking script:
```powershell
python main.py
```
*(To run it silently without leaving a command prompt open, run `pythonw main.py` instead).*

---

## 💻 Standalone Compilation

You can compile the entire application into a single, standalone `.exe` file that runs natively on Windows:

1. Install PyInstaller:
   ```powershell
   python -m pip install pyinstaller
   ```
2. Build the executable:
   ```powershell
   python -m PyInstaller TimeTracker.spec
   ```
3. Locate the output file in:
   📁 `dist/TimeTracker.exe`

---

## 📖 Developer Documentation

For the complete technical manual, including full code architecture details and code copies for each file, check out:
📄 **[project_info.md](file:///d:/Work/tracker/project_info.md)**

---

## 🛡️ License

This project is open-source and free to use. Built by **WofstudioZ**.
