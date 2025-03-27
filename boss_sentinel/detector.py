from ultralytics import YOLO
import cv2
from typing import Optional, List
import numpy as np

class FaceDetector:
    """基于YOLOv8的人脸检测器"""
    
    def __init__(self, model_path: str = "yolov8n-face.pt"):
        """
        初始化人脸检测器
        
        参数:
            model_path: YOLOv8模型路径
        """
        self.model = YOLO(model_path)
        
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
        
    def draw_boxes(self, frame: np.ndarray, boxes: List[List[float]], color: tuple = (0, 255, 0), thickness: int = 2) -> np.ndarray:
        """
        在图像上绘制人脸边界框
        
        参数:
            frame: 原始图像
            boxes: 人脸边界框列表
            color: 边界框颜色(BGR)
            thickness: 边界框线宽
            
        返回:
            绘制了边界框的图像
        """
        for box in boxes:
            x1, y1, x2, y2, _ = box
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)
        return frame