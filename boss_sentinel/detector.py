from ultralytics import YOLO
from typing import Optional, List
import numpy as np
import torch

class FaceDetector:
    """基于YOLOv8的人脸检测器"""

    def __init__(self, model_path: str = "yolov8n-face.pt", use_gpu: bool = True):
        """
        初始化人脸检测器

        参数:
            model_path: YOLOv8模型路径
            use_gpu: 是否使用GPU加速
        """
        # 检测CUDA是否可用
        self.device = 'cuda:0' if (use_gpu and torch.cuda.is_available()) else 'cpu'
        print(f"使用设备: {self.device}")

        # 加载模型到指定设备
        self.model = YOLO(model_path)
        self.model.to(self.device)

    def detect(self, frame: np.ndarray, confidence_threshold: float = 0.7) -> Optional[List[List[float]]]:
        """
        检测图像中的人脸

        参数:
            frame: 输入图像(BGR格式)
            confidence_threshold: 置信度阈值

        返回:
            人脸边界框列表，每个边界框格式为[x1, y1, x2, y2, confidence]
            如果没有检测到人脸则返回None
        """
        results = self.model(frame, verbose=False)
        if not results:
            return None

        boxes = []
        for box in results[0].boxes:
            x1, y1, x2, y2, conf, cls = box.data.tolist()[0]
            if conf >= confidence_threshold:
                boxes.append([x1, y1, x2, y2, conf])

        return boxes if boxes else None
