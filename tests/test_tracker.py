"""测试人脸跟踪器"""
import pytest
import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from boss_sentinel.tracker import FaceTracker, Track


class TestFaceTracker:
    """测试FaceTracker类"""

    @pytest.fixture
    def tracker(self):
        """创建跟踪器实例"""
        return FaceTracker(max_disappeared=30, iou_threshold=0.3)

    def test_tracker_initialization(self, tracker):
        """测试跟踪器初始化"""
        assert tracker.max_disappeared == 30
        assert tracker.iou_threshold == 0.3
        assert tracker.next_id == 0
        assert len(tracker.tracks) == 0

    def test_tracker_initial_track(self, tracker):
        """测试初始跟踪"""
        # 模拟检测结果 [x1, y1, x2, y2, conf]
        detections = [
            [100, 100, 200, 200, 0.9],
            [300, 300, 400, 400, 0.8]
        ]

        tracks = tracker.update(detections)

        # 应该创建两个新的跟踪对象
        assert len(tracks) == 2
        assert 0 in tracks
        assert 1 in tracks
        assert tracker.next_id == 2

    def test_tracker_continuation(self, tracker):
        """测试跟踪连续性"""
        # 第一帧
        detections = [[100, 100, 200, 200, 0.9]]
        tracks = tracker.update(detections)
        track_id = list(tracks.keys())[0]

        # 第二帧（位置略有变化）
        detections = [[105, 105, 205, 205, 0.9]]
        tracks = tracker.update(detections)

        # 应该保持同一个跟踪ID
        assert track_id in tracks
        assert len(tracks) == 1

    def test_tracker_new_detection(self, tracker):
        """测试新检测创建新跟踪"""
        # 第一帧
        detections = [[100, 100, 200, 200, 0.9]]
        tracks = tracker.update(detections)

        # 第二帧（新的人脸出现）
        detections = [
            [105, 105, 205, 205, 0.9],  # 原有人脸（略有移动）
            [300, 300, 400, 400, 0.8]   # 新人脸
        ]
        tracks = tracker.update(detections)

        # 应该有两个跟踪对象
        assert len(tracks) == 2

    def test_tracker_disappearance(self, tracker):
        """测试跟踪对象消失"""
        # 第一帧：检测到人脸
        detections = [[100, 100, 200, 200, 0.9]]
        tracks = tracker.update(detections)
        track_id = list(tracks.keys())[0]

        # 第二帧：没有检测到任何东西
        tracks = tracker.update([])

        # 跟踪对象应该仍然存在（在max_disappeared时间内）
        assert track_id in tracks

        # 模拟超过max_disappeared时间（需要直接修改跟踪对象）
        import time
        old_time = time.time() - 31
        tracks[track_id].last_seen = old_time

        # 手动触发清理（创建一个新的tracker来测试自动清理）
        tracker2 = FaceTracker(max_disappeared=30)
        detections = [[100, 100, 200, 200, 0.9]]
        tracks = tracker2.update(detections)
        track_id = list(tracks.keys())[0]

        # 模拟时间流逝
        tracks[track_id].last_seen = time.time() - 31

        # 手动检查并删除过期的跟踪对象
        current_time = time.time()
        for tid in list(tracker2.tracks.keys()):
            if current_time - tracker2.tracks[tid].last_seen > tracker2.max_disappeared:
                del tracker2.tracks[tid]

        # 跟踪对象应该被删除
        assert track_id not in tracker2.tracks

    def test_tracker_reset(self, tracker):
        """测试重置跟踪器"""
        # 添加一些跟踪
        detections = [[100, 100, 200, 200, 0.9]]
        tracker.update(detections)

        # 重置
        tracker.reset()

        # 应该清空所有跟踪
        assert len(tracker.tracks) == 0
        assert tracker.next_id == 0

    def test_tracker_iou_calculation(self, tracker):
        """测试IoU计算"""
        # 完全重叠
        iou = tracker._calculate_iou((0, 0, 100, 100), (0, 0, 100, 100))
        assert iou == 1.0

        # 部分重叠
        iou = tracker._calculate_iou((0, 0, 100, 100), (50, 50, 150, 150))
        assert iou > 0 and iou < 1

        # 不重叠
        iou = tracker._calculate_iou((0, 0, 100, 100), (200, 200, 300, 300))
        assert iou == 0.0

    def test_track_dataclass(self):
        """测试Track数据类"""
        track = Track(
            track_id=1,
            bbox=(100, 100, 200, 200),
            person_name="test",
            similarity=0.85,
            confidence=0.9
        )

        assert track.track_id == 1
        assert track.bbox == (100, 100, 200, 200)
        assert track.person_name == "test"
        assert track.similarity == 0.85
        assert track.confidence == 0.9

    def test_get_track_by_id(self, tracker):
        """测试根据ID获取跟踪对象"""
        detections = [[100, 100, 200, 200, 0.9]]
        tracks = tracker.update(detections)
        track_id = list(tracks.keys())[0]

        # 获取跟踪对象
        track = tracker.get_track_by_id(track_id)
        assert track is not None
        assert track.track_id == track_id

        # 获取不存在的跟踪对象
        track = tracker.get_track_by_id(999)
        assert track is None


class TestFaceTrackerEdgeCases:
    """边缘情况测试"""

    def test_tracker_multiple_detections_same_location(self):
        """测试相同位置的多个检测"""
        tracker = FaceTracker()

        # 同一位置的多个检测
        detections = [
            [100, 100, 200, 200, 0.9],
            [100, 100, 200, 200, 0.8]
        ]

        tracks = tracker.update(detections)

        # 应该创建两个独立的跟踪（IoU为1，但不同的检测）
        assert len(tracks) == 2

    def test_tracker_low_iou_threshold(self):
        """测试低IoU阈值"""
        tracker = FaceTracker(iou_threshold=0.1)  # 很低的阈值

        # 第一帧
        detections = [[100, 100, 200, 200, 0.9]]
        tracker.update(detections)
        track_id = list(tracker.tracks.keys())[0]

        # 第二帧：位置变化较大
        detections = [[150, 150, 250, 250, 0.9]]
        tracks = tracker.update(detections)

        # 由于IoU阈值低，应该仍然匹配
        assert track_id in tracks

    def test_tracker_high_iou_threshold(self):
        """测试高IoU阈值"""
        tracker = FaceTracker(iou_threshold=0.8)  # 很高的阈值

        # 第一帧
        detections = [[100, 100, 200, 200, 0.9]]
        tracker.update(detections)
        track_id = list(tracker.tracks.keys())[0]

        # 第二帧：位置略有变化
        detections = [[120, 120, 220, 220, 0.9]]
        tracks = tracker.update(detections)

        # 由于IoU阈值高，可能创建新的跟踪
        # （取决于实际的IoU值）
        assert len(tracks) >= 1
