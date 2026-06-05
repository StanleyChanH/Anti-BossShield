import threading
import cv2
import time
import logging
import numpy as np
from typing import List, Optional, Callable, Dict, Tuple, Any
from .detector import FaceDetector
from .recognizer import FaceRecognizer
from .notifier import EmailNotifier, create_detection_notification
from .locker import WindowsLocker
from .logger import SentinelLogger
from .config import SentinelConfig, ConfigWatcher
from .tracker import FaceTracker

# Optional feature modules — gracefully degrade if not available
try:
    from .shoulder_surfing import ShoulderSurfingDetector
except ImportError:
    ShoulderSurfingDetector = None  # type: ignore[assignment,misc]

try:
    from .intruder_capture import IntruderCapture
except ImportError:
    IntruderCapture = None  # type: ignore[assignment,misc]

try:
    from .pomodoro import PomodoroTimer
except ImportError:
    PomodoroTimer = None  # type: ignore[assignment,misc]

try:
    from .mqtt_bridge import MQTTBridge
except ImportError:
    MQTTBridge = None  # type: ignore[assignment,misc]

try:
    from .drowsiness_detector import DrowsinessDetector
except ImportError:
    DrowsinessDetector = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# 检测框颜色常量 (BGR)
COLOR_TARGET = (0, 0, 255)     # 红色 - 已识别的目标人物
COLOR_UNKNOWN = (0, 255, 0)    # 绿色 - 未知人脸
COLOR_LABEL_BG = None          # 标签背景色跟随边框
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX

# 自适应帧跳过上限倍率
_MAX_ADAPTIVE_SKIP_MULTIPLIER = 10
# 冷却字典清理间隔帧数
_COOLDOWN_CLEANUP_INTERVAL = 100


class SentinelMonitor:
    """哨兵监控系统 - 统一入口"""

    def __init__(self, config: SentinelConfig, lazy_load: bool = False, config_path: Optional[str] = None):
        """
        初始化监控系统

        参数:
            config: 系统配置
            lazy_load: 是否延迟加载模型
            config_path: 配置文件路径（启用热重载）
        """
        self.config = config
        self.logger = SentinelLogger(config.log_file)
        self.locker = WindowsLocker()
        self.notifier = self._create_notifier(config.notification_email)
        self.running = False
        self.frame_count = 0
        # Issue 3: per-camera trackers
        self.trackers: Dict[int, FaceTracker] = {}
        self._callback: Optional[Callable[[str], None]] = None

        # 冷却计时器
        self._last_lock_time: float = 0.0
        self._last_notify_time: Dict[str, float] = {}
        self._last_log_time: Dict[str, float] = {}

        # 模型占位符（懒加载）
        self._models_loaded = False
        self.detector: Optional[FaceDetector] = None
        self.recognizer: Optional[FaceRecognizer] = None
        self.cameras: List[cv2.VideoCapture] = []

        # Issue 6: adaptive frame skip — per-camera counters
        self._no_face_count: Dict[int, int] = {}
        # Issue 8: overlay cache per camera
        self._overlay_cache: Dict[int, np.ndarray] = {}

        # --- Optional feature modules ---
        self._shoulder_surfing: Optional[Any] = None
        self._intruder_capture: Optional[Any] = None
        self._pomodoro: Optional[Any] = None
        self._mqtt: Optional[Any] = None
        self._drowsiness: Optional[Any] = None

        # Latest feature status snapshot (for frame_callback)
        self._feature_status: Dict[str, Any] = {}

        self._init_optional_features()

        # 配置热重载
        self._config_watcher: Optional[ConfigWatcher] = None
        if config_path:
            self._config_watcher = ConfigWatcher(config_path, on_change=self._on_config_changed)

        if not lazy_load:
            self.initialize_models()

    # ------------------------------------------------------------------
    # Issue 1: Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.shutdown()

    def __del__(self):
        """Safety net — best-effort cleanup if someone forgot to call shutdown."""
        try:
            self.shutdown()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Static / private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_notifier(email_config) -> Optional[EmailNotifier]:
        """创建通知器，跳过无效的占位符配置"""
        if not email_config:
            return None
        if 'example.com' in email_config.smtp_server:
            return None
        return EmailNotifier(email_config)

    # ------------------------------------------------------------------
    # Optional feature module initialization
    # ------------------------------------------------------------------

    def _init_optional_features(self) -> None:
        """Initialize optional feature modules based on config flags.

        Each module is guarded by both the config flag and the availability
        of its Python class (import may have failed at module load time).
        """
        cfg = self.config

        if cfg.enable_shoulder_surfing and ShoulderSurfingDetector is not None:
            self._shoulder_surfing = ShoulderSurfingDetector()
            logger.info("Shoulder surfing detector enabled")

        if cfg.enable_intruder_capture and IntruderCapture is not None:
            self._intruder_capture = IntruderCapture(save_dir=cfg.intruder_save_dir)
            logger.info("Intruder capture enabled (dir=%s)", cfg.intruder_save_dir)

        if cfg.enable_pomodoro and PomodoroTimer is not None:
            self._pomodoro = PomodoroTimer(
                focus_minutes=cfg.pomodoro_focus_minutes,
                break_minutes=cfg.pomodoro_break_minutes,
            )
            logger.info("Pomodoro timer enabled")

        if cfg.enable_mqtt and MQTTBridge is not None:
            self._mqtt = MQTTBridge(
                broker=cfg.mqtt_broker,
                port=cfg.mqtt_port,
                topic_prefix=cfg.mqtt_topic_prefix,
            )
            self._mqtt.connect()
            logger.info("MQTT bridge enabled (broker=%s:%d)", cfg.mqtt_broker, cfg.mqtt_port)

        if cfg.enable_drowsiness and DrowsinessDetector is not None:
            self._drowsiness = DrowsinessDetector(
                ear_threshold=cfg.drowsiness_ear_threshold,
            )
            logger.info("Drowsiness detector enabled")

    # Issue 3: get or create per-camera tracker
    def _get_tracker(self, camera_idx: int) -> FaceTracker:
        """获取指定摄像头的跟踪器（不存在则创建）"""
        if camera_idx not in self.trackers:
            self.trackers[camera_idx] = FaceTracker(
                max_disappeared=self.config.tracker_max_disappeared
            )
        return self.trackers[camera_idx]

    # Issue 6: adaptive frame skip helpers
    def _effective_frame_skip(self, camera_idx: int) -> int:
        """根据连续无脸帧数计算有效帧跳过率"""
        no_face = self._no_face_count.get(camera_idx, 0)
        multiplier = min(1 << (no_face // 30), _MAX_ADAPTIVE_SKIP_MULTIPLIER)
        return self.config.frame_skip * multiplier

    def _reset_adaptive_skip(self, camera_idx: int) -> None:
        """检测到人脸后重置自适应帧跳过"""
        self._no_face_count[camera_idx] = 0

    def _increment_no_face(self, camera_idx: int) -> None:
        """未检测到人脸时递增计数"""
        self._no_face_count[camera_idx] = self._no_face_count.get(camera_idx, 0) + 1

    # Issue 11: periodic cooldown dict cleanup
    def _cleanup_cooldown_dicts(self) -> None:
        """清理冷却字典中过旧的条目"""
        max_cooldown = max(self.config.lock_cooldown, self.config.notify_cooldown) * 2
        threshold = time.time() - max_cooldown

        for person_name in list(self._last_notify_time.keys()):
            if self._last_notify_time[person_name] < threshold:
                del self._last_notify_time[person_name]

        for person_name in list(self._last_log_time.keys()):
            if self._last_log_time[person_name] < threshold:
                del self._last_log_time[person_name]

    # ------------------------------------------------------------------
    # Issue 9: Config resilience
    # ------------------------------------------------------------------

    def _on_config_changed(self, new_config: SentinelConfig) -> None:
        """配置变化回调（包裹异常保护）"""
        try:
            self.logger.log("Config changed, reloading...")
            old_faces_dir = self.config.known_faces_dir
            self.config = new_config

            # 更新通知器
            self.notifier = self._create_notifier(new_config.notification_email)

            # 重新加载人脸特征（如果目录变化）
            if self.recognizer and old_faces_dir != new_config.known_faces_dir:
                self.recognizer.reload_faces(new_config.known_faces_dir)
                count = len(self.recognizer.known_embeddings)
                self.logger.log(f"Reloaded {count} face features")

            self.logger.log("Config hot-reload complete")
        except Exception as e:
            self.logger.log(f"Config reload error, keeping old config: {e}")

    # ------------------------------------------------------------------
    # Model & camera initialization
    # ------------------------------------------------------------------

    def initialize_models(self):
        """初始化模型（支持延迟加载）"""
        if self._models_loaded:
            return

        self.logger.log("Loading models...")
        self.detector = FaceDetector(self.config.model_path, self.config.use_gpu)
        device = 'cuda' if self.config.use_gpu else 'cpu'
        self.recognizer = FaceRecognizer(self.config.known_faces_dir, device=device)
        self.cameras = self._init_cameras(self.config.cameras)
        self._models_loaded = True
        self.logger.log("Models loaded")

    def ensure_models_loaded(self):
        """确保模型已加载"""
        if not self._models_loaded:
            self.initialize_models()

    def _init_cameras(self, camera_indices: List[int]) -> List[cv2.VideoCapture]:
        """初始化摄像头"""
        cameras = []
        for idx in camera_indices:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cameras.append(cap)
                self.logger.log(f"Camera {idx} initialized")
            else:
                self.logger.log(f"Warning: Cannot open camera {idx}", print_console=True)
        return cameras

    # ------------------------------------------------------------------
    # Cooldown checks
    # ------------------------------------------------------------------

    def _should_lock(self) -> bool:
        """检查是否在锁屏冷却期内"""
        return (time.time() - self._last_lock_time) >= self.config.lock_cooldown

    def _should_notify(self, person_name: str) -> bool:
        """检查是否在通知冷却期内"""
        last_time = self._last_notify_time.get(person_name, 0.0)
        return (time.time() - last_time) >= self.config.notify_cooldown

    # ------------------------------------------------------------------
    # Overlay drawing
    # ------------------------------------------------------------------

    def _draw_overlay(self, frame: np.ndarray, tracks: dict,
                      inplace: bool = False) -> np.ndarray:
        """在帧上绘制检测框和人名标注

        参数:
            frame: 原始帧
            tracks: 跟踪对象字典
            inplace: 是否直接在原帧上绘制（CLI 模式可省去复制开销）

        返回:
            标注后的帧
        """
        display = frame if inplace else frame.copy()

        for track_id, track in tracks.items():
            if track.disappeared > 0:
                continue

            x1, y1, x2, y2 = [int(v) for v in track.bbox]

            if track.person_name:
                color = COLOR_TARGET
                label = f"{track.person_name} ({track.similarity:.0%})"
            else:
                color = COLOR_UNKNOWN
                label = "unknown"

            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)

            (tw, th), _ = cv2.getTextSize(label, LABEL_FONT, 0.6, 1)
            cv2.rectangle(display, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(display, label, (x1 + 2, y1 - 4),
                        LABEL_FONT, 0.6, (255, 255, 255), 1)

        return display

    # ------------------------------------------------------------------
    # Issue 5: Extracted helper methods
    # ------------------------------------------------------------------

    def _recognize_tracks(self, frame: np.ndarray, tracks: dict,
                          camera_idx: int) -> List[Tuple]:
        """对跟踪对象进行人脸识别

        参数:
            frame: 摄像头帧
            tracks: 跟踪对象字典
            camera_idx: 摄像头索引

        返回:
            list of (track, person_name, similarity) 对已识别的人脸
        """
        recognized_tracks: List[Tuple] = []

        for track_id, track in tracks.items():
            if track.disappeared > 0:
                continue

            # 利用识别缓存：已识别过的跟踪对象直接使用缓存结果
            if track.recognized:
                if not track.person_name:
                    continue
                recognized_tracks.append((track, track.person_name, track.similarity))
                continue

            x1, y1, x2, y2 = track.bbox
            fh, fw = frame.shape[:2]
            x1c, y1c = max(0, int(x1)), max(0, int(y1))
            x2c, y2c = min(fw, int(x2)), min(fh, int(y2))
            face_img = frame[y1c:y2c, x1c:x2c]

            if face_img.size == 0:
                continue

            try:
                embedding = self.recognizer.get_embedding(face_img)
                if embedding is None:
                    continue
                person_name, similarity = self.recognizer.compare_faces(embedding, self.config.threshold)
            except Exception as e:
                self.logger.log(f"Face processing error: {e}")
                continue

            # 缓存识别结果到跟踪对象
            if person_name:
                track.person_name = person_name
                track.similarity = similarity
                track.recognized = True
                recognized_tracks.append((track, person_name, similarity))

        return recognized_tracks

    def _handle_detection(self, person_name: str, similarity: float,
                          camera_idx: int) -> Tuple[bool, bool]:
        """处理检测到的人脸：日志、回调、通知

        参数:
            person_name: 识别到的人名
            similarity: 相似度
            camera_idx: 摄像头索引

        返回:
            (should_lock, should_notify) 元组
        """
        now = time.time()

        # 日志冷却：同一人 5 秒内不重复记录
        elapsed = now - self._last_log_time.get(person_name, 0.0)
        if elapsed >= 5.0:
            self.logger.log(f"Camera {camera_idx}: Detected {person_name} ({similarity:.2%})")
            self._last_log_time[person_name] = now

        # 回调
        if self._callback:
            self._callback(person_name)

        # Issue 10: target names check
        should_lock = False
        should_notify = False

        target_names = self.config.target_names
        is_target = (not target_names) or (person_name in target_names)

        if is_target:
            should_lock = self._should_lock()
            if self.notifier and self._should_notify(person_name):
                should_notify = True

        return should_lock, should_notify

    def _send_notification(self, person_name: str, similarity: float,
                           camera_idx: int) -> bool:
        """异步发送邮件通知（Issue 7: 使用 daemon 线程）

        参数:
            person_name: 识别到的人名
            similarity: 相似度
            camera_idx: 摄像头索引

        返回:
            True（线程已启动），并非发送结果
        """
        notifier = self.notifier
        if notifier is None:
            return False

        notification = create_detection_notification(person_name, similarity, camera_idx)
        subject = notification['subject']
        body = notification['body']

        # Only update _last_notify_time if send returns True (done inside thread)
        notify_time_key = person_name

        def _do_send():
            success = notifier.send(subject, body)
            if success:
                self._last_notify_time[notify_time_key] = time.time()

        thread = threading.Thread(target=_do_send, daemon=True)
        thread.start()
        return True

    # ------------------------------------------------------------------
    # Feature hook helpers
    # ------------------------------------------------------------------

    def _check_shoulder_surfing(self, face_names: List[Optional[str]]) -> None:
        """Shoulder surfing: check if unauthorized faces are present."""
        if self._shoulder_surfing is None:
            return
        try:
            if len(face_names) > 1:
                result = self._shoulder_surfing.check_frame(face_names)
                self._feature_status['shoulder_surfing'] = {
                    'is_vulnerable': result.is_vulnerable,
                    'total_faces': result.total_faces,
                    'unauthorized_count': result.unauthorized_count,
                    'privacy_level': result.privacy_level,
                }
            else:
                self._feature_status['shoulder_surfing'] = {
                    'is_vulnerable': False,
                    'total_faces': len(face_names),
                    'unauthorized_count': 0,
                    'privacy_level': 0.0,
                }
        except Exception as exc:
            logger.debug("Shoulder surfing check failed: %s", exc)

    def _on_user_recognized(self, person_name: str) -> None:
        """Handle a recognized user appearing."""
        # Pomodoro: user is present
        if self._pomodoro is not None:
            try:
                self._pomodoro.on_user_present()
                status = self._pomodoro.get_status()
                self._feature_status['pomodoro'] = {
                    'state': status.state.value,
                    'remaining_seconds': status.remaining_seconds,
                    'completed_pomodoros': status.completed_pomodoros,
                    'focus_ratio': status.focus_ratio,
                }
            except Exception as exc:
                logger.debug("Pomodoro update failed: %s", exc)

        # MQTT: publish presence
        if self._mqtt is not None:
            try:
                self._mqtt.publish_presence(person_name, is_present=True)
            except Exception as exc:
                logger.debug("MQTT publish presence failed: %s", exc)

    def _on_no_faces_detected(self, frame: np.ndarray, camera_idx: int) -> None:
        """Handle the case when no faces are detected (user absent)."""
        # Pomodoro: user is absent
        if self._pomodoro is not None:
            try:
                self._pomodoro.on_user_absent()
                status = self._pomodoro.get_status()
                self._feature_status['pomodoro'] = {
                    'state': status.state.value,
                    'remaining_seconds': status.remaining_seconds,
                    'completed_pomodoros': status.completed_pomodoros,
                    'focus_ratio': status.focus_ratio,
                }
            except Exception as exc:
                logger.debug("Pomodoro absent update failed: %s", exc)

        # MQTT: publish away
        if self._mqtt is not None:
            try:
                self._mqtt.publish_away()
            except Exception as exc:
                logger.debug("MQTT publish away failed: %s", exc)

        # Intruder capture: check overlay cache for intruder frames
        if self._intruder_capture is not None:
            cached = self._overlay_cache.get(camera_idx)
            if cached is not None:
                try:
                    self._intruder_capture.capture(cached)
                except Exception as exc:
                    logger.debug("Intruder capture failed: %s", exc)

    def _on_unknown_faces(self, frame: np.ndarray) -> None:
        """Handle unknown faces detected with no recognized user present."""
        if self._intruder_capture is not None:
            try:
                self._intruder_capture.capture(frame)
            except Exception as exc:
                logger.debug("Intruder capture (unknown) failed: %s", exc)

    def _update_drowsiness(self, detections: list) -> None:
        """Run drowsiness detection on face landmarks from detections."""
        if self._drowsiness is None:
            return
        try:
            for det in detections:
                result = self._drowsiness.update(face_landmarks=det)
                self._feature_status['drowsiness'] = {
                    'is_drowsy': result.is_drowsy,
                    'ear_value': result.ear_value,
                    'blink_rate': result.blink_rate,
                    'alert_level': result.alert_level,
                }
                # Only process the first face with valid data
                if result.ear_value >= 0.0:
                    break
        except Exception as exc:
            logger.debug("Drowsiness update failed: %s", exc)

    def get_feature_status(self) -> Dict[str, Any]:
        """Return the latest feature status snapshot.

        This is a thread-safe read of the status dict assembled by
        feature hooks during frame processing.
        """
        return dict(self._feature_status)

    # ------------------------------------------------------------------
    # Main frame processing (refactored orchestrator)
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray, camera_idx: int) -> bool:
        """
        处理摄像头帧（带帧跳过优化、人脸跟踪和识别缓存）

        参数:
            frame: 摄像头帧
            camera_idx: 摄像头索引

        返回:
            是否检测到目标人物
        """
        self.ensure_models_loaded()
        self.frame_count += 1

        # Issue 11: periodic cooldown cleanup
        if self.frame_count % _COOLDOWN_CLEANUP_INTERVAL == 0:
            self._cleanup_cooldown_dicts()

        # Issue 6: adaptive frame skip
        effective_skip = self._effective_frame_skip(camera_idx)

        # Time-based gating: only process every effective_skip-th frame
        if self.frame_count % effective_skip != 0:
            return False

        detections = self.detector.detect(frame, self.config.confidence_threshold)
        tracker = self._get_tracker(camera_idx)

        if not detections:
            tracker.update([])
            self._increment_no_face(camera_idx)

            # --- Feature hook: user absent ---
            self._on_no_faces_detected(frame, camera_idx)

            return False

        # Faces detected — reset adaptive skip
        self._reset_adaptive_skip(camera_idx)

        # 将字典格式的检测结果转换为 tracker 所需的扁平列表格式
        boxes = [
            d['bbox'] + [d['confidence']]
            for d in detections
        ]

        # 更新跟踪器
        tracks = tracker.update(boxes)
        detected = False

        # Issue 5: use extracted helper for recognition
        recognized_tracks = self._recognize_tracks(frame, tracks, camera_idx)

        # Collect all face names for shoulder-surfing check
        all_face_names: List[Optional[str]] = []

        any_should_lock = False

        for track, person_name, similarity in recognized_tracks:
            all_face_names.append(person_name)

            should_lock, should_notify = self._handle_detection(person_name, similarity, camera_idx)

            if should_lock:
                any_should_lock = True

            if should_notify:
                # Issue 7: async email via thread
                self._send_notification(person_name, similarity, camera_idx)

            detected = True

            # --- Feature hook: recognized user present ---
            self._on_user_recognized(person_name)

        # Also count unrecognized tracked faces
        for track_id, track in tracks.items():
            if track.disappeared > 0:
                continue
            if not track.recognized:
                all_face_names.append(None)

        # --- Feature hook: shoulder surfing (multiple faces) ---
        self._check_shoulder_surfing(all_face_names)

        # --- Feature hook: drowsiness (after face detection) ---
        self._update_drowsiness(detections)

        # --- Feature hook: intruder capture (unknown face + no recognized user) ---
        if not detected and len(detections) > 0:
            self._on_unknown_faces(frame)

        # Issue 10: lock only for target names (checked inside _handle_detection)
        if any_should_lock and self._should_lock():
            self.locker.lock()
            self._last_lock_time = time.time()
            self.logger.log(f"Screen locked, cooldown {self.config.lock_cooldown}s")

        return detected

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    def run(self, callback: Optional[Callable[[str], None]] = None,
            frame_callback: Optional[Callable[[np.ndarray], None]] = None):
        """
        运行监控系统

        参数:
            callback: 检测到目标人物时的回调函数
            frame_callback: 每帧回调，传递带标注的画面（用于 GUI 内嵌预览）
        """
        self._callback = callback
        self.ensure_models_loaded()

        # Issue 2: camera init guard
        if not self.cameras:
            raise RuntimeError('No cameras available')

        self.running = True
        self.logger.log("Sentinel started, monitoring...")

        try:
            while self.running:
                # Issue 9: wrap check_for_changes in try/except
                if self._config_watcher:
                    try:
                        self._config_watcher.check_for_changes()
                    except Exception as e:
                        self.logger.log(f"Config check error: {e}")

                # CLI 模式可原地绘制，GUI 模式需复制帧避免污染原始数据
                is_cli_mode = self.config.show_feed and not frame_callback

                for idx, cap in enumerate(self.cameras):
                    ret, frame = cap.read()
                    if not ret:
                        continue

                    tracker = self._get_tracker(idx)
                    detected = self.process_frame(frame, idx)

                    overlay_frame = self._draw_overlay(
                        frame, tracker.tracks, inplace=is_cli_mode
                    )

                    # Issue 8: cache overlay per camera
                    self._overlay_cache[idx] = overlay_frame

                    # 传递帧给调用方（GUI 模式）— include feature status
                    if frame_callback:
                        feature_data = self.get_feature_status()
                        frame_callback(overlay_frame, feature_data)

                    # CLI 模式：用 cv2.imshow 显示
                    if is_cli_mode:
                        cv2.imshow(f'Camera {idx} - Press Q to quit', overlay_frame)

                if is_cli_mode:
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

        except KeyboardInterrupt:
            self.logger.log("User interrupted")
        finally:
            self.shutdown()

    def stop(self):
        """停止监控系统"""
        self.running = False
        self.logger.log("Stopping...")

    # ------------------------------------------------------------------
    # Issue 4: Shutdown cleanup
    # ------------------------------------------------------------------

    def shutdown(self):
        """关闭监控系统"""
        for cap in self.cameras:
            cap.release()
        cv2.destroyAllWindows()

        # Issue 4: full cleanup
        self.cameras = []
        self._models_loaded = False
        self.trackers.clear()
        self._overlay_cache.clear()
        self._no_face_count.clear()

        if self.detector and hasattr(self.detector, 'cleanup'):
            self.detector.cleanup()
            self.detector = None

        if self.recognizer and hasattr(self.recognizer, 'cleanup'):
            self.recognizer.cleanup()
            self.recognizer = None

        # Cleanup optional feature modules
        if self._mqtt is not None:
            try:
                self._mqtt.disconnect()
            except Exception:
                pass
            self._mqtt = None

        if self._pomodoro is not None:
            try:
                self._pomodoro.reset()
            except Exception:
                pass
            self._pomodoro = None

        if self._drowsiness is not None:
            try:
                self._drowsiness.reset()
            except Exception:
                pass
            self._drowsiness = None

        self._shoulder_surfing = None
        self._intruder_capture = None
        self._feature_status.clear()

        self.running = False
        self.logger.log("Sentinel shutdown")
