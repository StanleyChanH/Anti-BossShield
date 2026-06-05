# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Boss Sentinel (Anti-BossShield) is a Windows-based face recognition monitoring system that automatically locks the screen when specific individuals are detected. It uses YOLOv8 for face detection and FaceNet for face recognition, with a Web UI (Apple-style, browser-based) and CLI interfaces. The system also includes optional creative features: shoulder surfing detection, intruder photo capture, pomodoro timer, MQTT smart home bridge, and drowsiness detection.

## Common Development Commands

### Installation
```bash
uv sync
```

### Running the System

**Web UI mode (recommended) — auto-opens browser:**
```bash
python -m boss_sentinel
```

**Command-line mode (no UI):**
```bash
python -m boss_sentinel.main
```

**Web UI via CLI flag:**
```bash
python -m boss_sentinel.main --web
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
| `main.py` | `main()` | CLI entry point with `--web` flag for Web UI mode |

### Web UI (boss_sentinel/web/)

| File | Description |
|------|-------------|
| `web/server.py` | FastAPI backend — REST API, MJPEG video stream, SSE log/alert push, monitoring thread management, stats tracking |
| `web/static/index.html` | Single-page application — Apple-style dark theme, Hero, video preview, feature dashboard, data dashboard, config panel, log viewer |
| `web/static/style.css` | Apple-inspired CSS — glassmorphism cards, gradient text, toggle switches, responsive layout, dashboard charts |
| `web/static/app.js` | Frontend logic — API calls, SSE streams, MJPEG feed, Web Notification API, audio alerts, dashboard polling |

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI main page |
| GET | `/api/status` | Monitoring status + feature data (JSON) |
| POST | `/api/start` | Start monitoring (config JSON body) |
| POST | `/api/stop` | Stop monitoring |
| GET | `/api/config` | Read config.json |
| PUT | `/api/config` | Update config.json |
| GET | `/api/video` | MJPEG live video stream |
| GET | `/api/logs` | Real-time log push (SSE) |
| GET | `/api/alerts` | Real-time alert push (SSE) |
| GET | `/api/faces` | List known faces |
| GET | `/api/stats` | Dashboard statistics (detections, alerts, timeline, hourly distribution, pomodoro report, attention samples) |

### Optional Feature Modules

| File | Class | Description |
|------|-------|-------------|
| `role_manager.py` | `RoleManager` | Maps recognized person names to roles (owner/boss/colleague/unknown) |
| `head_pose.py` | `HeadPoseEstimator` | Estimates head orientation (yaw/pitch/roll) using solvePnP with 5 keypoints, tracks attention/focus |
| `shoulder_surfing.py` | `ShoulderSurfingDetector` | Detects unauthorized people looking over the user's shoulder |
| `intruder_capture.py` | `IntruderCapture` | Captures photos of unknown faces during user absence with timestamp watermark |
| `pomodoro.py` | `PomodoroTimer` | Pomodoro timer that auto-starts/pauses based on owner presence |
| `mqtt_bridge.py` | `MQTTBridge` | Publishes presence status to MQTT broker for Home Assistant integration |
| `drowsiness_detector.py` | `DrowsinessDetector` | Detects drowsiness using EAR (legacy, limited accuracy with YOLOv8 5-keypoint) |

### Role System (Identity-Based Feature Separation)

The system uses a role-based identity model to differentiate behavior for different people:

**Roles:**
- **owner** — The computer user. Drives pomodoro timer, attention tracking, focus score.
- **boss** — Target persons who trigger defensive actions: lock screen, email notification, pomodoro pause.
- **colleague** — Known persons with no special actions. Authorized for shoulder surfing.
- **unknown** — Unrecognized faces. Triggers intruder capture, shoulder surfing alerts.

**Configuration** (`roles` field in config.json):
```json
{"roles": {"owner": ["stanley"], "boss": ["boss_name"], "colleague": ["coworker"]}}
```

**Feature behavior by role:**

| Feature | Owner Present | Boss Detected | Unknown Detected | Owner Absent |
|---------|--------------|---------------|------------------|--------------|
| Lock Screen | — | ✅ Lock | — | — |
| Pomodoro | Start/resume | Pause (meeting) | — | Pause |
| Shoulder Surfing | Monitor | Suppressed | ⚠️ Alert | Off |
| Intruder Capture | — | — | ✅ Photo | ✅ Photo |
| Head Pose | Attention tracking | Approach detection | Behavior tracking | Off |
| MQTT | owner_present | boss_detected | unknown_present | all_away |

**Backward compatibility:** If `roles.boss` is empty, the system falls back to `target_names`. If both are empty, all recognized faces trigger lock (legacy behavior). If `roles.owner` is empty, any recognized face drives pomodoro (legacy).

### Data Flow

```
Camera Frame → FaceDetector → FaceTracker → FaceRecognizer → RoleManager → Match? → WindowsLocker
                  ↓                              ↓               ↓
              (YOLOv8)                     (FaceNet)     (owner/boss/
              + keypoints                   + alignment    colleague/
              + FP16 GPU                    + batch inf.   unknown)
                                               ↓
                                    Compare with known_faces/
                                               ↓
                              ┌─────────────────┼──────────────────┐
                              ↓                 ↓                  ↓
                     Shoulder Surfing    Intruder Capture    Pomodoro Timer
                     Head Pose Est.      MQTT Bridge         Drowsiness (legacy)
```

### Web UI Data Flow

```
SentinelMonitor (background thread)
    │
    ├── frame_callback(frame, feature_data)
    │       ├── MJPEG queue → /api/video (multipart/x-mixed-replace)
    │       ├── feature_status dict → /api/status (polling)
    │       └── attention samples → _stats (session-level tracking)
    │
    ├── detection_callback(person_name)
    │       ├── log buffer → /api/logs (SSE)
    │       ├── alert event → /api/alerts (SSE)
    │       └── stats tracking → /api/stats (detection count, timeline, hourly distribution)
    │
    └── Browser Frontend
            ├── <img src="/api/video"> → live video feed
            ├── EventSource("/api/logs") → real-time log display
            ├── EventSource("/api/alerts") → alert toast + notification
            ├── fetch("/api/...") → config CRUD, start/stop control
            └── fetch("/api/stats") → data dashboard (3s polling: stat cards, hourly chart, timeline, pomodoro report, attention overview)
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
- `enable_drowsiness`: Enable drowsiness detection (default: false, legacy)
- `enable_head_pose`: Enable head pose estimation / attention tracking (default: false)

**Feature configuration fields:**
- `mqtt_broker`, `mqtt_port`, `mqtt_topic_prefix`: MQTT connection settings
- `pomodoro_focus_minutes`, `pomodoro_break_minutes`: Pomodoro timing
- `intruder_save_dir`: Directory for intruder photos
- `drowsiness_ear_threshold`: Eye Aspect Ratio threshold for drowsiness (legacy)
- `head_pose_alert_threshold`: Yaw angle threshold (degrees) for "looking away" detection
- `roles`: Dict mapping role names to person name lists (e.g., `{"owner": ["alice"], "boss": ["bob"]}`)

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

4. **Chinese path support:** `__main__.py` pre-loads PyTorch DLLs to handle non-ASCII paths.

5. **Web UI:** Browser-based interface at `http://localhost:8970`, auto-opens on startup. Uses FastAPI + MJPEG + SSE for real-time communication.

6. **Model files:** YOLOv8 face model (`yolov8n-face.pt`) auto-downloads on first run.

7. **Resource management:** SentinelMonitor implements context manager (`__enter__/__exit__`) and `__del__` for guaranteed cleanup of cameras and GPU models.

8. **Optional dependencies:** Feature modules (paho-mqtt, mediapipe) are imported conditionally with try/except. Missing deps disable features gracefully with log warnings.

## Development Guidelines

- Extend modular components (monitor.py, detector.py, recognizer.py)
- Keep Web UI config form fields in sync with SentinelConfig fields
- Use `SentinelMonitor` as the entry point for new features
- Camera IDs are 0-based integers (0 = default webcam)
- New features should be optional (disabled by default, enabled via config toggle)
- All modules should use `logging.getLogger(__name__)` instead of `print()`
- Web UI static files are in `boss_sentinel/web/static/`
- Test changes with `uv run pytest tests/ -v`
