import cv2
import time
import numpy as np
from typing import List, Optional
from .detector import FaceDetector
from .recognizer import FaceRecognizer
from .notifier import EmailNotifier, create_detection_notification
from .locker import WindowsLocker
from .logger import SentinelLogger
from .config import SentinelConfig

class SentinelMonitor:
    """哨兵监控系统"""
    
    def __init__(self, config: SentinelConfig):
        """
        初始化监控系统
        
        参数:
            config: 系统配置
        """
        self.config = config
        self.detector = FaceDetector(config.model_path)
        self.recognizer = FaceRecognizer(config.known_faces_dir)
        self.logger = SentinelLogger(config.log_file)
        self.locker = WindowsLocker()
        self.notifier = EmailNotifier(config.notification_email) if config.notification_email else None
        self.cameras = self._init_cameras(config.cameras)
        self.running = False
        
    def _init_cameras(self, camera_indices: List[int]) -> List[cv2.VideoCapture]:
        """初始化摄像头"""
        cameras = []
        for idx in camera_indices:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                cameras.append(cap)
                self.logger.log(f"摄像头 {idx} 初始化成功")
            else:
                self.logger.log(f"警告: 无法打开摄像头 {idx}", print_console=True)
        return cameras
        
    def process_frame(self, frame: np.ndarray, camera_idx: int) -> bool:
        """
        处理摄像头帧
        
        参数:
            frame: 摄像头帧
            camera_idx: 摄像头索引
            
        返回:
            是否检测到目标人物
        """
        boxes = self.detector.detect(frame, self.config.confidence_threshold)
        if not boxes:
            return False
            
        detected = False
        for box in boxes:
            x1, y1, x2, y2, _ = box
            face_img = frame[int(y1):int(y2), int(x1):int(x2)]
            
            try:
                embedding = self.recognizer.get_embedding(face_img)
                person_name, similarity = self.recognizer.compare_faces(embedding, self.config.threshold)
                
                if person_name:
                    self.logger.log(f"摄像头 {camera_idx} 检测到已知人物: {person_name} (相似度: {similarity:.2%})")
                    detected = True
                    
                    if self.notifier:
                        notification = create_detection_notification(person_name, similarity, camera_idx)
                        self.notifier.send(notification['subject'], notification['body'])
                        
            except Exception as e:
                self.logger.log(f"人脸处理错误: {e}")
                
        return detected
        
    def run(self):
        """运行监控系统"""
        self.running = True
        self.logger.log("哨兵系统启动，开始监控...")
        
        try:
            while self.running:
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
            self.logger.log("用户中断监控")
        finally:
            self.shutdown()
            
    def shutdown(self):
        """关闭监控系统"""
        for cap in self.cameras:
            cap.release()
        cv2.destroyAllWindows()
        self.running = False
        self.logger.log("哨兵系统已关闭")