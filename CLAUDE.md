# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Boss Sentinel (Anti-BossShield) is a Windows-based face recognition monitoring system that automatically locks the screen when specific individuals are detected. It uses YOLOv8 for face detection and FaceNet for face recognition, with both CLI and GUI interfaces.

## Common Development Commands

### Installation
```bash
uv sync
```

### Running the System

**GUI mode (recommended):**
```bash
python -m boss_sentinel
```

**Command-line mode:**
```bash
python -m boss_sentinel.main
```

### Testing
```bash
uv run pytest tests/ -v
```

### Building Executable
```bash
uv run pyinstaller BossSentinel.spec
```

### Configuration Setup
```bash
cp config.json.example config.json
# Edit config.json with your settings
```

## Architecture

### Core Components (boss_sentinel/ package)

| File | Class | Description |
|------|-------|-------------|
| `config.py` | `SentinelConfig`, `ConfigWatcher` | Configuration management with hot-reload support |
| `detector.py` | `FaceDetector` | YOLOv8-based face detection |
| `recognizer.py` | `FaceRecognizer` | FaceNet-based face recognition with multi-person support |
| `tracker.py` | `FaceTracker`, `Track` | Lightweight face tracking with recognition caching |
| `monitor.py` | `SentinelMonitor` | **Main orchestration layer (unified entry point)** |
| `locker.py` | `WindowsLocker` | Windows screen locking via LockWorkStation API |
| `notifier.py` | `EmailNotifier` | Email alert notifications |
| `logger.py` | `SentinelLogger` | File-based logging |
| `gui.py` | `MainWindow` | PyQt5 GUI with system tray support |
| `main.py` | `main()` | CLI entry point, directly uses SentinelMonitor |

### Data Flow

```
Camera Frame → FaceDetector → FaceTracker → FaceRecognizer → Match? → WindowsLocker
                  ↓                              ↓
              (YOLOv8)                     (FaceNet)
                                               ↓
                                    Compare with known_faces/
```

### Cooldown & Caching System

- **Lock cooldown** (`lock_cooldown`): After locking screen, wait N seconds before locking again
- **Notify cooldown** (`notify_cooldown`): Same person only triggers one email per N seconds
- **Recognition cache**: Tracked faces cache recognition results, skip re-running FaceNet
- **Log cooldown**: Same person logged at most once per 5 seconds
- **Invalid email skip**: Placeholder email config silently ignored

### Configuration System

**SentinelConfig fields:**
- `known_faces_dir`: Directory with person subdirectories
- `model_path`: YOLOv8 face model path
- `threshold`: Face recognition similarity threshold (0.0-1.0)
- `confidence_threshold`: YOLO detection confidence threshold
- `frame_skip`: Process every Nth frame for performance
- `use_gpu`: Enable GPU acceleration
- `cameras`: List of camera indices to monitor
- `log_file`: Log file path
- `lock_cooldown`: Seconds between consecutive screen locks (default: 30)
- `notify_cooldown`: Seconds between notifications for same person (default: 60)
- `notification_email`: Optional EmailConfig for alerts

**Hot Reload:**
- `ConfigWatcher` monitors config.json for changes
- Changes automatically reload without restart
- Face features reload if `known_faces_dir` changes

### Known Faces Directory Structure

```
known_faces/
├── boss/           # One folder per person
│   ├── photo1.jpg
│   ├── photo2.jpg
│   └── photo3.jpg
└── other_person/
    └── photo1.jpg
```

The system supports both:
1. Multi-person subdirectory structure (recommended)
2. Flat structure with filename as person name

## Key Implementation Notes

1. **Face detection vs recognition:**
   - YOLOv8 detects face bounding boxes (detector.py)
   - FaceNet computes 512D embeddings for recognition (recognizer.py)
   - Recognition uses cosine similarity to match embeddings

2. **Windows-only:** The system uses `ctypes.windll.user32.LockWorkStation()` for screen locking.

3. **Chinese path support:** `__main__.py` pre-loads PyTorch DLLs and sets Qt plugin path to handle non-ASCII paths.

4. **System Tray:** GUI minimizes to system tray, runs in background.

5. **Model files:** YOLOv8 face model (`yolov8n-face.pt`) auto-downloads on first run.

## Development Guidelines

- Extend modular components (monitor.py, detector.py, recognizer.py)
- Keep GUI ConfigGroup in sync with SentinelConfig fields
- Use `SentinelMonitor` as the entry point for new features
- Camera IDs are 0-based integers (0 = default webcam)
