import cv2
import time
import numpy as np
from typing import List, Optional, Callable, Dict
from .detector import FaceDetector
from .recognizer import FaceRecognizer
from .notifier import EmailNotifier, create_detection_notification
from .locker import WindowsLocker
from .logger import SentinelLogger
from .config import SentinelConfig, ConfigWatcher
from .tracker import FaceTracker


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
        self.tracker = FaceTracker(max_disappeared=30)
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

        # 配置热重载
        self._config_watcher: Optional[ConfigWatcher] = None
        if config_path:
            self._config_watcher = ConfigWatcher(config_path, on_change=self._on_config_changed)

        if not lazy_load:
            self.initialize_models()

    @staticmethod
    def _create_notifier(email_config) -> Optional[EmailNotifier]:
        """创建通知器，跳过无效的占位符配置"""
        if not email_config:
            return None
        if 'example.com' in email_config.smtp_server:
            return None
        return EmailNotifier(email_config)

    def _on_config_changed(self, new_config: SentinelConfig) -> None:
        """配置变化回调"""
        self.logger.log("Config changed, reloading...")
        old_faces_dir = self.config.known_faces_dir
        self.config = new_config

        # 更新通知器
        self.notifier = self._create_notifier(new_config.notification_email)

        # 重新加载人脸特征（如果目录变化）
        if self.recognizer and old_faces_dir != new_config.known_faces_dir:
            self.recognizer = FaceRecognizer(new_config.known_faces_dir)
            count = len(self.recognizer.known_embeddings)
            self.logger.log(f"Reloaded {count} face features")

        self.logger.log("Config hot-reload complete")

    def initialize_models(self):
        """初始化模型（支持延迟加载）"""
        if self._models_loaded:
            return

        self.logger.log("Loading models...")
        self.detector = FaceDetector(self.config.model_path, self.config.use_gpu)
        self.recognizer = FaceRecognizer(self.config.known_faces_dir)
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

    def _should_lock(self) -> bool:
        """检查是否在锁屏冷却期内"""
        return (time.time() - self._last_lock_time) >= self.config.lock_cooldown

    def _should_notify(self, person_name: str) -> bool:
        """检查是否在通知冷却期内"""
        last_time = self._last_notify_time.get(person_name, 0.0)
        return (time.time() - last_time) >= self.config.notify_cooldown

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

        # 帧跳过逻辑：只处理每N帧
        if self.frame_count % self.config.frame_skip != 0:
            return False

        boxes = self.detector.detect(frame, self.config.confidence_threshold)
        if not boxes:
            self.tracker.update([])
            return False

        # 更新跟踪器
        tracks = self.tracker.update(boxes)
        detected = False

        # 对每个跟踪对象进行人脸识别
        for track_id, track in tracks.items():
            person_name = None
            # 跳过已消失的跟踪对象
            if track.disappeared > 0:
                continue

            # 利用识别缓存：已识别过的跟踪对象直接使用缓存结果，不再重复推理和日志
            if track.recognized:
                if not track.person_name:
                    continue
                person_name = track.person_name
                similarity = track.similarity
                detected = True
                continue
            else:
                x1, y1, x2, y2 = track.bbox
                face_img = frame[int(y1):int(y2), int(x1):int(x2)]

                if face_img.size == 0:
                    continue

                try:
                    embedding = self.recognizer.get_embedding(face_img)
                    person_name, similarity = self.recognizer.compare_faces(embedding, self.config.threshold)
                except Exception as e:
                    self.logger.log(f"Face processing error: {e}")
                    continue

                # 缓存识别结果到跟踪对象
                if person_name:
                    track.person_name = person_name
                    track.similarity = similarity
                    track.recognized = True

            if person_name:
                now = time.time()
                elapsed = now - self._last_log_time.get(person_name, 0.0)
                if elapsed >= 5.0:
                    self.logger.log(f"Camera {camera_idx}: Detected {person_name} ({similarity:.2%})")
                    self._last_log_time[person_name] = now
                detected = True

                if self._callback:
                    self._callback(person_name)

                # 带冷却的通知
                if self.notifier and self._should_notify(person_name):
                    notification = create_detection_notification(person_name, similarity, camera_idx)
                    self.notifier.send(notification['subject'], notification['body'])
                    self._last_notify_time[person_name] = time.time()

        return detected

    def run(self, callback: Optional[Callable[[str], None]] = None):
        """
        运行监控系统

        检测到目标后锁屏，冷却期过后继续监控，不会退出。

        参数:
            callback: 检测到目标人物时的回调函数
        """
        self._callback = callback
        self.ensure_models_loaded()
        self.running = True
        self.logger.log("Sentinel started, monitoring...")

        try:
            while self.running:
                # 检查配置热重载
                if self._config_watcher:
                    self._config_watcher.check_for_changes()

                for idx, cap in enumerate(self.cameras):
                    ret, frame = cap.read()
                    if not ret:
                        continue

                    if self.process_frame(frame, idx):
                        if self._should_lock():
                            self.locker.lock()
                            self._last_lock_time = time.time()
                            self.logger.log(f"Screen locked, cooldown {self.config.lock_cooldown}s")

                    if self.config.show_feed:
                        cv2.imshow(f'Camera {idx} - Press Q to quit', frame)

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

    def shutdown(self):
        """关闭监控系统"""
        for cap in self.cameras:
            cap.release()
        cv2.destroyAllWindows()
        self.running = False
        self.logger.log("Sentinel shutdown")
