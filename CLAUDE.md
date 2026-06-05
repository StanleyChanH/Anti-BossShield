# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Boss Sentinel (Anti-BossShield) is a Windows-based face recognition monitoring system that automatically locks the screen when specific individuals are detected. It uses YOLOv8 for face detection and FaceNet for face recognition, with both CLI and GUI interfaces. The system also includes optional creative features: shoulder surfing detection, intruder photo capture, pomodoro timer, MQTT smart home bridge, and drowsiness detection.

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
| `config.py` | `SentinelConfig`, `ConfigWatcher`, `EmailConfig` | Configuration management with hot-reload, validation, and None-safe loading |
| `detector.py` | `FaceDetector` | YOLOv8-based face detection with GPU/FP16 support, returns bounding boxes + keypoints |
| `recognizer.py` | `FaceRecognizer` | FaceNet-based face recognition with batch inference, GPU acceleration, face alignment, and vectorized comparison |
| `tracker.py` | `FaceTracker`, `Track` | Lightweight face tracking with recognition caching (per-camera instances) |
| `monitor.py` | `SentinelMonitor` | **Main orchestration layer (unified entry point)**, context manager, adaptive frame skip |
| `locker.py` | `WindowsLocker` | Windows screen locking via LockWorkStation API |
| `notifier.py` | `EmailNotifier` | Email alert notifications with SMTP_SSL support |
| `logger.py` | `SentinelLogger` | Rotating file-based logging (RotatingFileHandler) |
| `gui.py` | `MainWindow` | PyQt5 GUI with system tray, email config UI, feature status indicators |
| `main.py` | `main()` | CLI entry point, directly uses SentinelMonitor |

### Optional Feature Modules

| File | Class | Description |
|------|-------|-------------|
| `shoulder_surfing.py` | `ShoulderSurfingDetector` | Detects unauthorized people looking over the user's shoulder |
| `intruder_capture.py` | `IntruderCapture` | Captures photos of unknown faces during user absence with timestamp watermark |
| `pomodoro.py` | `PomodoroTimer` | Pomodoro timer that auto-starts/pauses based on user presence |
| `mqtt_bridge.py` | `MQTTBridge` | Publishes presence status to MQTT broker for Home Assistant integration |
| `drowsiness_detector.py` | `DrowsinessDetector` | Detects drowsiness using Eye Aspect Ratio (EAR) |

### Data Flow

```
Camera Frame → FaceDetector → FaceTracker → FaceRecognizer → Match? → WindowsLocker
                  ↓                              ↓
              (YOLOv8)                     (FaceNet)
              + keypoints                   + alignment
              + FP16 GPU                    + batch inference
                                               ↓
                                    Compare with known_faces/
                                               ↓
                              ┌─────────────────┼──────────────────┐
                              ↓                 ↓                  ↓
                     Shoulder Surfing    Intruder Capture    Pomodoro Timer
                     Drowsiness Detect   MQTT Bridge         Target Names
```

### Cooldown & Caching System

- **Lock cooldown** (`lock_cooldown`): After locking screen, wait N seconds before locking again
- **Notify cooldown** (`notify_cooldown`): Same person only triggers one email per N seconds
- **Recognition cache**: Tracked faces cache recognition results, skip re-running FaceNet
- **Log cooldown**: Same person logged at most once per 5 seconds
- **Invalid email skip**: Placeholder email config silently ignored
- **Cooldown dict cleanup**: `_last_notify_time` and `_last_log_time` periodically pruned

### Configuration System

**SentinelConfig core fields:**
- `known_faces_dir`: Directory with person subdirectories
- `model_path`: YOLOv8 face model path
- `threshold`: Face recognition similarity threshold (0.0-1.0, validated)
- `confidence_threshold`: YOLO detection confidence threshold (0.0-1.0, validated)
- `frame_skip`: Process every Nth frame for performance (>= 1, validated)
- `use_gpu`: Enable GPU acceleration
- `cameras`: List of camera indices to monitor
- `log_file`: Log file path
- `lock_cooldown`: Seconds between consecutive screen locks (default: 30)
- `notify_cooldown`: Seconds between notifications for same person (default: 60)
- `notification_email`: Optional EmailConfig for alerts
- `target_names`: List of names that trigger lock (empty = all detected persons)
- `tracker_max_disappeared`: Frames before a track is considered lost (default: 30)
- `away_timeout`: Seconds before user is considered absent (default: 30)

**Feature toggle fields:**
- `enable_shoulder_surfing`: Enable shoulder surfing detection (default: false)
- `enable_intruder_capture`: Enable intruder photo capture (default: false)
- `enable_pomodoro`: Enable pomodoro timer (default: false)
- `enable_mqtt`: Enable MQTT bridge (default: false)
- `enable_drowsiness`: Enable drowsiness detection (default: false)

**Feature configuration fields:**
- `mqtt_broker`, `mqtt_port`, `mqtt_topic_prefix`: MQTT connection settings
- `pomodoro_focus_minutes`, `pomodoro_break_minutes`: Pomodoro timing
- `intruder_save_dir`: Directory for intruder photos
- `drowsiness_ear_threshold`: Eye Aspect Ratio threshold for drowsiness

**Validation:**
- `__post_init__` validates types and ranges (threshold 0-1, frame_skip >= 1, etc.)
- `load_config()` accepts both dict and file path string
- None values and unknown keys are silently filtered
- ConfigWatcher preserves last valid config on load failure

**Hot Reload:**
- `ConfigWatcher` monitors config.json for changes
- Changes automatically reload without restart
- Face features reload via `recognizer.reload_faces()` (no model re-initialization)

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
   - YOLOv8 detects face bounding boxes + 5 keypoints (detector.py)
   - FaceNet computes 512D embeddings for recognition (recognizer.py)
   - Recognition uses cosine similarity (vectorized via np.dot) to match embeddings
   - Input tensors are normalized (/ 255.0) before FaceNet inference
   - Face alignment via affine transform using eye keypoints

2. **Performance features:**
   - GPU acceleration for both detection (FP16) and recognition
   - Batch face embedding extraction (single forward pass for multiple faces)
   - Adaptive frame skipping (increases skip rate when no faces detected)
   - Per-camera independent FaceTracker instances
   - Cached overlay frames for skipped frames
   - Async email notification (non-blocking)

3. **Windows-only:** The system uses `ctypes.windll.user32.LockWorkStation()` for screen locking.

4. **Chinese path support:** `__main__.py` pre-loads PyTorch DLLs and sets Qt plugin path to handle non-ASCII paths.

5. **System Tray:** GUI minimizes to system tray, runs in background.

6. **Model files:** YOLOv8 face model (`yolov8n-face.pt`) auto-downloads on first run.

7. **Resource management:** SentinelMonitor implements context manager (`__enter__/__exit__`) and `__del__` for guaranteed cleanup of cameras and GPU models.

8. **Optional dependencies:** Feature modules (paho-mqtt, mediapipe) are imported conditionally with try/except. Missing deps disable features gracefully with log warnings.

## Development Guidelines

- Extend modular components (monitor.py, detector.py, recognizer.py)
- Keep GUI ConfigGroup in sync with SentinelConfig fields
- Use `SentinelMonitor` as the entry point for new features
- Camera IDs are 0-based integers (0 = default webcam)
- New features should be optional (disabled by default, enabled via config toggle)
- All modules should use `logging.getLogger(__name__)` instead of `print()`
- Test changes with `uv run pytest tests/ -v`
