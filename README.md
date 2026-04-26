# 🎯 QA Proof Capture

A lightweight Windows desktop app for QA engineers to capture screenshots, record screencasts, annotate bugs, and export proof reports — all in one place.

---

## 🚀 Quick Start

### Requirements
- Windows 10 / 11
- Python 3.10 or newer → https://python.org (check "Add to PATH")

### Run (first time)
Double-click **`install.bat`** — it installs dependencies and launches the app.

### Run (after install)
Double-click **`run.bat`**

---

## ✨ Features

### 📷 Screenshot Capture
- Full-screen screenshot of any monitor
- Region capture (click and drag to select area)
- Hotkey: **F9** (full screen), **F11** (region)

### 🎬 Screencast Recording
- Records screen as MP4 video at 15fps
- Timestamp overlay burned into every frame
- Multi-monitor support
- Hotkey: **F10** to start/stop

### ✏️ Annotation Tools
After taking a screenshot, click **Annotate** to:
- Draw freehand with pen
- Draw rectangles to highlight areas
- Add arrows pointing to bugs
- Add text labels (e.g. "BUG:", "Expected:")
- Blur/censor sensitive data
- Undo last action
- Choose color and brush size

### 📋 Session Management
- Organize captures by test session / bug ID
- Each session gets its own timestamped folder
- Browse all past sessions in the Sessions tab

### 📄 HTML Report Export
- Exports all session captures to a self-contained HTML file
- Includes embedded screenshots (base64), timestamps, and notes
- Open in any browser — no internet needed
- Perfect for attaching to Jira/Confluence tickets

### 📁 Gallery View
- Thumbnail grid of all captures in current session
- Click to preview full-size
- Add notes before each capture
- Delete unwanted items

---

## ⌨️ Hotkeys

| Key | Action |
|-----|--------|
| F9  | Full screenshot |
| F10 | Start / Stop recording |
| F11 | Region capture |
| Esc | Cancel region selection |

---

## 📁 File Locations

All captures are saved to:
```
C:\Users\<YourName>\QAProofCapture\sessions\<timestamp>_<session-name>\
```

Each session folder contains:
- `screenshot_*.png` — screenshots
- `recording_*.mp4` — screen recordings
- `session.json` — metadata (timestamps, notes, file list)

---

## 🛠 Troubleshooting

**App won't start?**
→ Make sure Python is installed and run `install.bat` first

**Black screen in recording?**
→ Run as Administrator (right-click → Run as administrator)

**Region capture not working?**
→ Press Esc and try again; make sure you click and drag

**Videos won't play?**
→ Install VLC media player — Windows Media Player may not support MP4/mp4v

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| pillow | Image capture, annotation, thumbnails |
| mss | Fast cross-monitor screen capture |
| opencv-python | MP4 video writing |
| numpy | Frame conversion |

All installed automatically by `install.bat`.
