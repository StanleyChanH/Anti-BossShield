"""单元测试 — monitor.py 的 _draw_overlay 和 process_frame 缓存逻辑"""
import numpy as np
import pytest
import time as _time
from unittest.mock import MagicMock, patch

from boss_sentinel.tracker import Track
from boss_sentinel.config import SentinelConfig
from boss_sentinel.monitor import SentinelMonitor


# ---------------------------------------------------------------------------
# 辅助：创建不加载模型的 monitor
# ---------------------------------------------------------------------------

def _make_monitor(**config_overrides):
    """创建一个跳过模型加载的 SentinelMonitor"""
    config = SentinelConfig(**config_overrides)
    mon = SentinelMonitor.__new__(SentinelMonitor)
    mon.config = config
    mon.logger = MagicMock()
    mon.locker = MagicMock()
    mon.notifier = None
    mon.running = False
    mon.frame_count = 0
    mon.tracker = MagicMock()
    mon._callback = None
    mon._last_lock_time = 0.0
    mon._last_notify_time = {}
    mon._last_log_time = {}
    mon._models_loaded = True
    mon.detector = None
    mon.recognizer = None
    mon.cameras = []
    mon._config_watcher = None
    return mon


def _make_track(person_name=None, similarity=0.0, bbox=None, track_id=1):
    """创建测试用的 Track 对象"""
    return Track(
        track_id=track_id,
        bbox=bbox or (50, 50, 200, 200),
        person_name=person_name,
        similarity=similarity,
        disappeared=0,
        recognized=bool(person_name),
    )


# ---------------------------------------------------------------------------
# _draw_overlay 测试
# ---------------------------------------------------------------------------

class TestDrawOverlay:
    """测试 SentinelMonitor._draw_overlay 绘制逻辑"""

    def test_overlay_with_target_person(self):
        """目标人物应绘制红色框 + 名字标签"""
        monitor = _make_monitor()
        tracks = {1: _make_track("boss", similarity=0.85)}
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = monitor._draw_overlay(frame, tracks)

        assert result is not None
        assert result.shape == (480, 640, 3)
        # 红色框像素应存在 (R 通道)
        assert np.any(result[:, :, 2] > 0)
        # 原始帧不应被修改（非 inplace）
        assert not np.any(frame[:, :, 2] > 0)

    def test_overlay_with_unknown_face(self):
        """未知人脸应绘制绿色框"""
        monitor = _make_monitor()
        tracks = {1: _make_track(person_name=None)}
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = monitor._draw_overlay(frame, tracks)

        assert result is not None
        # 绿色框像素应存在 (G 通道)
        assert np.any(result[:, :, 1] > 0)

    def test_overlay_skips_disappeared_tracks(self):
        """disappeared > 0 的跟踪对象不应被绘制"""
        monitor = _make_monitor()
        track = _make_track("boss", similarity=0.9)
        track.disappeared = 5
        tracks = {1: track}
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = monitor._draw_overlay(frame, tracks)

        # 不应有任何绘制（全黑）
        assert not np.any(result > 0)

    def test_overlay_inplace_mode(self):
        """inplace=True 时应修改原始帧"""
        monitor = _make_monitor()
        tracks = {1: _make_track("boss", similarity=0.9)}
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = monitor._draw_overlay(frame, tracks, inplace=True)

        # inplace 模式下返回值应和输入是同一对象
        assert result is frame
        # 原始帧应被修改
        assert np.any(frame[:, :, 2] > 0)

    def test_overlay_copy_mode_preserves_original(self):
        """inplace=False（默认）不应修改原始帧"""
        monitor = _make_monitor()
        tracks = {1: _make_track("boss", similarity=0.9)}
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = monitor._draw_overlay(frame, tracks, inplace=False)

        assert result is not frame
        assert not np.any(frame > 0)  # 原始帧仍全黑

    def test_overlay_empty_tracks(self):
        """空跟踪列表应返回原帧的副本"""
        monitor = _make_monitor()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = monitor._draw_overlay(frame, {})

        assert result.shape == frame.shape
        assert not np.any(result > 0)


# ---------------------------------------------------------------------------
# process_frame 缓存命中逻辑测试
# ---------------------------------------------------------------------------

class TestProcessFrameCachedCallback:
    """测试 process_frame 缓存命中时不再跳过回调/日志"""

    def _make_process_monitor(self):
        """创建可直接调用 process_frame 的 mock monitor"""
        mon = _make_monitor(frame_skip=1)
        mon._callback = MagicMock()
        # detector 必须返回检测框，否则 process_frame 在 tracker.update([]) 后直接返回 False
        mon.detector = MagicMock()
        mon.detector.detect.return_value = [[50, 50, 200, 200, 0.9]]
        return mon

    def test_cached_track_triggers_callback(self):
        """缓存命中的跟踪对象仍应触发回调"""
        mon = self._make_process_monitor()

        # 第一次调用：detector 返回框，tracker.update 会返回新的 tracks
        # 我们用真实的 FaceTracker 来跟踪
        from boss_sentinel.tracker import FaceTracker
        real_tracker = FaceTracker(max_disappeared=30)
        mon.tracker = real_tracker

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # 第一次调用：会走 else 分支（非缓存），需要 recognizer
        # 为了简化，让 recognizer 返回 boss
        mon.recognizer = MagicMock()
        mon.recognizer.get_embedding.return_value = np.zeros(512)
        mon.recognizer.compare_faces.return_value = ("boss", 0.85)

        mon.process_frame(frame, 0)
        assert mon._callback.called, "首次识别应触发回调"

        # 重置 callback mock
        mon._callback.reset_mock()

        # 第二次调用：track 已缓存，走 if track.recognized 分支
        mon.process_frame(frame, 0)
        assert mon._callback.called, "缓存命中后仍应触发回调（M2 修复验证）"

    def test_cached_track_logs_after_cooldown(self):
        """缓存命中的跟踪对象应在冷却期后再次记录日志"""
        mon = self._make_process_monitor()

        from boss_sentinel.tracker import FaceTracker
        real_tracker = FaceTracker(max_disappeared=30)
        mon.tracker = real_tracker

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        mon.recognizer = MagicMock()
        mon.recognizer.get_embedding.return_value = np.zeros(512)
        mon.recognizer.compare_faces.return_value = ("boss", 0.85)

        # 第一次调用
        mon.process_frame(frame, 0)
        first_log_count = mon.logger.log.call_count

        # 模拟冷却期过去（日志冷却 5 秒）
        mon._last_log_time["boss"] = _time.time() - 10

        # 第二次调用（缓存命中）
        mon.process_frame(frame, 0)

        # 应该有新的日志输出
        assert mon.logger.log.call_count > first_log_count, \
            "缓存命中 + 冷却期过后应产生新日志"
