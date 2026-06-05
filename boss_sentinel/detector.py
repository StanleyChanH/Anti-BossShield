import logging
from ultralytics import YOLO
from typing import Optional, List, Dict, Any
import numpy as np
import torch

logger = logging.getLogger(__name__)


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
        try:
            self.model = YOLO(model_path)
            self.model.to(self.device)
        except Exception as e:
            raise RuntimeError(
                f"加载YOLOv8模型失败: {model_path}。"
                f"请确认模型文件存在且未损坏。错误详情: {e}"
            ) from e

    def detect(self, frame: np.ndarray, confidence_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        检测图像中的人脸

        参数:
            frame: 输入图像(BGR格式)
            confidence_threshold: 置信度阈值

        返回:
            人脸检测列表，每个元素为字典:
            {
                'bbox': [x1, y1, x2, y2],
                'confidence': float,
                'keypoints': [[x, y], ...] 或 None
            }
            如果没有检测到人脸则返回空列表
        """
        use_half = self.device == 'cuda' or self.device.startswith('cuda')
        results = self.model(frame, verbose=False, device=self.device, half=use_half)
        if not results:
            return []

        frame_h, frame_w = frame.shape[:2]
        detections: List[Dict[str, Any]] = []

        # 提取关键点数据
        keypoints_data = None
        try:
            if results[0].keypoints is not None and results[0].keypoints.data is not None:
                keypoints_data = results[0].keypoints.data
        except (AttributeError, IndexError):
            keypoints_data = None

        for i, box in enumerate(results[0].boxes):
            # 防御性检查: 验证 box.data 格式
            try:
                if box.data is None or box.data.numel() == 0:
                    continue
                raw = box.data.tolist()
                if not raw or not isinstance(raw[0], (list, tuple)) or len(raw[0]) < 5:
                    continue
                x1, y1, x2, y2, conf, cls = raw[0]
            except (TypeError, ValueError, IndexError) as e:
                logger.warning("跳过格式异常的检测框: %s", e)
                continue

            if conf < confidence_threshold:
                continue

            # 边界钳制: 确保坐标在图像范围内
            x1 = max(0.0, min(float(x1), float(frame_w)))
            y1 = max(0.0, min(float(y1), float(frame_h)))
            x2 = max(0.0, min(float(x2), float(frame_w)))
            y2 = max(0.0, min(float(y2), float(frame_h)))

            # 提取关键点
            face_keypoints: Optional[List[List[float]]] = None
            if keypoints_data is not None and i < len(keypoints_data):
                try:
                    kp = keypoints_data[i]
                    face_keypoints = [[float(kp[j][0]), float(kp[j][1])] for j in range(len(kp))]
                except (IndexError, TypeError, ValueError):
                    face_keypoints = None

            detections.append({
                'bbox': [x1, y1, x2, y2],
                'confidence': float(conf),
                'keypoints': face_keypoints,
            })

        return detections

    def cleanup(self) -> None:
        """释放模型资源"""
        if hasattr(self, 'model') and self.model is not None:
            del self.model
            self.model = None
        if self.device != 'cpu' and torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("FaceDetector 资源已释放")
