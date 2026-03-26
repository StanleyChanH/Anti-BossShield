import cv2
import time
import numpy as np
from typing import List, Optional, Callable
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
        self.notifier = EmailNotifier(config.notification_email) if config.notification_email else None
        self.running = False
        self.frame_count = 0
        self.tracker = FaceTracker(max_disappeared=30)
        self._callback: Optional[Callable[[str], None]] = None

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

    def _on_config_changed(self, new_config: SentinelConfig) -> None:
        """配置变化回调"""
        self.logger.log("Config changed, reloading...")
        old_faces_dir = self.config.known_faces_dir
        self.config = new_config

        # 更新通知器
        if new_config.notification_email:
            self.notifier = EmailNotifier(new_config.notification_email)
        else:
            self.notifier = None

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

    def process_frame(self, frame: np.ndarray, camera_idx: int) -> bool:
        """
        处理摄像头帧（带帧跳过优化和人脸跟踪）

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
            x1, y1, x2, y2 = track.bbox
            face_img = frame[int(y1):int(y2), int(x1):int(x2)]

            if face_img.size == 0:
                continue

            try:
                embedding = self.recognizer.get_embedding(face_img)
                person_name, similarity = self.recognizer.compare_faces(embedding, self.config.threshold)

                if person_name:
                    self.logger.log(f"Camera {camera_idx}: Detected {person_name} ({similarity:.2%})")
                    detected = True

                    if self._callback:
                        self._callback(person_name)

                    if self.notifier:
                        notification = create_detection_notification(person_name, similarity, camera_idx)
                        self.notifier.send(notification['subject'], notification['body'])

            except Exception as e:
                self.logger.log(f"Face processing error: {e}")

        return detected

    def run(self, callback: Optional[Callable[[str], None]] = None):
        """
        运监控系统

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
                        self.locker.lock()
                        self.running = False
                        break

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
