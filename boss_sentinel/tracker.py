from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class Track:
    """跟踪对象"""
    track_id: int
    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    person_name: Optional[str] = None
    similarity: float = 0.0
    disappeared: int = 0  # 连续消失帧数
    recognized: bool = False  # 是否已识别过（缓存标记）

class FaceTracker:
    """轻量级人脸跟踪器"""

    def __init__(self, max_disappeared: int = 30, iou_threshold: float = 0.3):
        """
        初始化跟踪器

        参数:
            max_disappeared: 目标连续消失的最大帧数
            iou_threshold: IoU阈值，用于匹配检测框
        """
        self.max_disappeared = max_disappeared
        self.iou_threshold = iou_threshold
        self.next_id = 0
        self.tracks: Dict[int, Track] = {}

    def _calculate_iou(self, bbox1: Tuple[float, float, float, float],
                      bbox2: Tuple[float, float, float, float]) -> float:
        """计算两个边界框的IoU"""
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2

        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)

        if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
            return 0.0

        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)

        bbox1_area = (x1_max - x1_min) * (y1_max - y1_min)
        bbox2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = bbox1_area + bbox2_area - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def update(self, detections: list) -> Dict[int, Track]:
        """
        更新跟踪器

        参数:
            detections: 检测结果列表，每个元素为 (x1, y1, x2, y2, confidence)

        返回:
            当前所有活跃的跟踪对象
        """
        # 没有检测到任何目标，递增所有跟踪对象的消失计数
        if not detections:
            to_remove = []
            for track_id in list(self.tracks.keys()):
                self.tracks[track_id].disappeared += 1
                if self.tracks[track_id].disappeared > self.max_disappeared:
                    to_remove.append(track_id)
            for track_id in to_remove:
                del self.tracks[track_id]
            return self.tracks

        # 如果之前没有跟踪对象，为所有检测创建新跟踪
        if not self.tracks:
            for det in detections:
                x1, y1, x2, y2, conf = det
                self.tracks[self.next_id] = Track(
                    track_id=self.next_id,
                    bbox=(x1, y1, x2, y2),
                )
                self.next_id += 1
            return self.tracks

        # 匹配检测框和现有跟踪对象
        matched_detections = set()
        matched_tracks = set()

        for track_id, track in self.tracks.items():
            best_iou = 0.0
            best_det_idx = -1

            for det_idx, det in enumerate(detections):
                if det_idx in matched_detections:
                    continue

                iou = self._calculate_iou(track.bbox, det[:4])
                if iou > best_iou:
                    best_iou = iou
                    best_det_idx = det_idx

            if best_iou >= self.iou_threshold and best_det_idx != -1:
                x1, y1, x2, y2, conf = detections[best_det_idx]
                self.tracks[track_id].bbox = (x1, y1, x2, y2)
                self.tracks[track_id].disappeared = 0
                matched_detections.add(best_det_idx)
                matched_tracks.add(track_id)

        # 为未匹配的检测创建新跟踪
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_detections:
                x1, y1, x2, y2, conf = det
                self.tracks[self.next_id] = Track(
                    track_id=self.next_id,
                    bbox=(x1, y1, x2, y2),
                )
                self.next_id += 1

        # 移除超时消失的跟踪对象
        to_remove = []
        for track_id in list(self.tracks.keys()):
            if track_id not in matched_tracks:
                self.tracks[track_id].disappeared += 1
                if self.tracks[track_id].disappeared > self.max_disappeared:
                    to_remove.append(track_id)
        for track_id in to_remove:
            del self.tracks[track_id]

        return self.tracks
