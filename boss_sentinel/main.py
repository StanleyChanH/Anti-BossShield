import os
import cv2
import time
import json
import logging
from logging.handlers import RotatingFileHandler
from ultralytics import YOLO
from pathlib import Path
from datetime import datetime

class BossSentinel:
    def __init__(self, config_path="config.json"):
        self.load_config(config_path)
        self.setup_logging()
        self.verify_paths()
        self.model = YOLO(self.config["model_path"])
        self.known_faces = self.load_known_faces()
        self.detection_dir = Path("detections")
        self.detection_dir.mkdir(exist_ok=True)
        
    def load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path) as f:
                self.config = json.load(f)
        except Exception as e:
            raise RuntimeError(f"加载配置文件失败: {e}")

    def setup_logging(self):
        """配置日志系统(带轮转功能)"""
        # 设置日志文件最大1MB，保留3个备份
        handler = RotatingFileHandler(
            self.config["log_file"],
            maxBytes=1024*1024,
            backupCount=3,
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        ))
        
        self.logger = logging.getLogger("BossSentinel")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(handler)
        self.logger.debug("日志系统初始化完成(带轮转功能)")

    def verify_paths(self):
        """验证所有路径是否存在"""
        required_paths = [
            ("known_faces_dir", "known_faces目录不存在"),
            ("model_path", "模型文件不存在")
        ]
        
        for key, error_msg in required_paths:
            path = Path(self.config[key])
            if not path.exists():
                raise FileNotFoundError(f"{error_msg}: {path}")

    def load_known_faces(self):
        """加载已知人脸(支持多人物)"""
        known_dir = Path(self.config["known_faces_dir"])
        if not known_dir.exists():
            self.logger.error(f"目录不存在: {known_dir}")
            return {}
            
        known_faces = {}
        for person_dir in known_dir.iterdir():
            if person_dir.is_dir():
                faces = []
                for img_path in person_dir.glob("*.jpg"):
                    img = cv2.imread(str(img_path))
                    if img is not None:
                        self.logger.info(f"加载 {person_dir.name} 的人脸图片: {img_path.name}")
                        faces.append(img)
                    else:
                        self.logger.warning(f"无法加载图片: {img_path}")
                
                if faces:
                    known_faces[person_dir.name] = faces
                    
        if not known_faces:
            self.logger.warning("没有加载任何人脸图片")
        return known_faces

    def run(self):
        """运行监控系统"""
        self.logger.info("启动Boss哨兵系统")
        try:
            while True:
                self.monitor()
                time.sleep(self.config["detection_interval"])
        except KeyboardInterrupt:
            self.logger.info("手动停止监控")
        except Exception as e:
            self.logger.error(f"监控出错: {e}")
            raise

    def monitor(self):
        """执行监控逻辑"""
        for cam_id in self.config["cameras"]:
            cap = cv2.VideoCapture(cam_id)
            if not cap.isOpened():
                self.logger.error(f"无法打开摄像头 {cam_id}")
                continue
                
            ret, frame = cap.read()
            if ret:
                self.process_frame(frame)
                
            cap.release()

    def process_frame(self, frame):
        """处理视频帧"""
        results = self.model(frame)
        self.logger.info(f"检测结果: {results}")
        
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                self.logger.info(f"检测到{len(boxes)}个人脸框，置信度: {boxes.conf}")
                
            is_detected, person_name = self.is_boss_detected(result)
            if is_detected:
                self.logger.info(f"检测到匹配人物: {person_name}，准备锁屏")
                self.save_detection(frame, person_name)
                self.lock_screen()
                self.send_alert(person_name)
                return

    def is_boss_detected(self, detection_result):
        """判断是否检测到目标人物"""
        if not self.known_faces:
            self.logger.warning("没有加载已知人脸数据")
            return False, None
            
        boxes = detection_result.boxes
        if boxes is None:
            return False, None
            
        # 获取检测到的人脸区域
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = box.conf.item()
            
            if conf > self.config["confidence_threshold"]:
                # TODO: 实现实际的人脸特征匹配
                # 目前简单返回第一个匹配的人物
                for person_name in self.known_faces:
                    self.logger.info(f"检测到匹配人物: {person_name}")
                    return True, person_name
                    
        return False, None

    def lock_screen(self):
        """锁定屏幕"""
        os.system("rundll32.exe user32.dll,LockWorkStation")
        self.logger.info("检测到老板，已锁定屏幕")

    def save_detection(self, frame, person_name):
        """保存检测到的人物截图"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{person_name}_{timestamp}.jpg"
        save_path = self.detection_dir / filename
        
        # 保存图片
        cv2.imwrite(str(save_path), frame)
        self.logger.info(f"已保存检测截图: {save_path}")
        
        # 清理旧文件，最多保留20张
        detection_files = sorted(self.detection_dir.glob("*.jpg"), key=os.path.getmtime)
        if len(detection_files) > 20:
            for old_file in detection_files[:-20]:
                old_file.unlink()
                self.logger.debug(f"清理旧文件: {old_file}")

    def send_alert(self, person_name):
        """发送警报"""
        self.logger.warning(f"警报: 检测到 {person_name}!")
        # TODO: 实现邮件/通知发送

if __name__ == "__main__":
    try:
        sentinel = BossSentinel()
        sentinel.run()
    except Exception as e:
            print(f"系统错误: {e}")