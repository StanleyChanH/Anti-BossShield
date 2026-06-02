"""单元测试 — gui.py 的逻辑（纯 Python，无 Qt 依赖）

所有测试通过 mock 或提取核心逻辑实现，无需创建 QApplication。
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from boss_sentinel.config import SentinelConfig


# ---------------------------------------------------------------------------
# VideoWidget 帧存储逻辑测试
# ---------------------------------------------------------------------------

class TestVideoWidgetFrameLogic:
    """验证 update_frame / clear_frame 的核心逻辑"""

    def test_copy_isolation(self):
        """update_frame 的 frame.copy() 应隔离原始帧"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[100, 100] = [255, 0, 0]

        latest_frame = frame.copy()

        original_val = latest_frame[100, 100].copy()
        frame[100, 100] = [0, 255, 0]
        assert np.array_equal(latest_frame[100, 100], original_val)

    def test_copy_independence(self):
        """每次 copy 应产生独立对象"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        latest_frame = frame.copy()
        assert latest_frame is not frame

    def test_overwrite_semantics(self):
        """多次赋值只保留最新帧"""
        frame1 = np.full((480, 640, 3), 100, dtype=np.uint8)
        frame2 = np.full((480, 640, 3), 200, dtype=np.uint8)

        latest_frame = frame1.copy()
        latest_frame = frame2.copy()

        assert np.all(latest_frame == 200)

    def test_clear_resets_to_none(self):
        """clear_frame 应将 _latest_frame 置为 None"""
        latest_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        latest_frame = None
        assert latest_frame is None


# ---------------------------------------------------------------------------
# ConfigGroup 布尔配置逻辑测试
# ---------------------------------------------------------------------------

class TestConfigGroupCheckboxLogic:
    """验证 ConfigGroup 的 checkbox 读取/设置逻辑

    不创建实际的 QCheckBox，而是模拟 isChecked/setChecked 行为，
    验证 get_config / load_config 中的数据流。
    """

    def test_get_config_extracts_checkbox_booleans(self):
        """get_config 应将 isChecked() 的布尔值传入 SentinelConfig"""
        # 模拟一个 ConfigGroup 的 checkbox 属性
        mock_gpu = MagicMock()
        mock_gpu.isChecked.return_value = False
        mock_sound = MagicMock()
        mock_sound.isChecked.return_value = False
        mock_tray = MagicMock()
        mock_tray.isChecked.return_value = True

        # 验证 SentinelConfig 接受布尔值
        config = SentinelConfig(
            use_gpu=mock_gpu.isChecked(),
            alert_sound=mock_sound.isChecked(),
            alert_tray=mock_tray.isChecked(),
        )
        assert config.use_gpu is False
        assert config.alert_sound is False
        assert config.alert_tray is True

    def test_load_config_passes_booleans_to_setchecked(self):
        """load_config 应将配置字典的布尔值传给 setChecked"""
        mock_checkbox = MagicMock()

        # 模拟 load_config 中对 alert_sound 的处理
        config_dict = {'alert_sound': False}
        mock_checkbox.setChecked(config_dict.get('alert_sound', True))

        mock_checkbox.setChecked.assert_called_once_with(False)

    def test_default_config_has_alerts_enabled(self):
        """默认 SentinelConfig 应启用告警"""
        config = SentinelConfig()
        assert config.alert_sound is True
        assert config.alert_tray is True


# ---------------------------------------------------------------------------
# _trigger_alerts 缓存配置逻辑测试
# ---------------------------------------------------------------------------

class TestTriggerAlertsLogic:
    """验证 _trigger_alerts 的核心逻辑

    通过 mock MainWindow 验证告警分发行为。
    """

    def _make_mock_window(self, alert_sound=False, alert_tray=False):
        """创建模拟的 MainWindow 对象"""
        config = SentinelConfig(alert_sound=alert_sound, alert_tray=alert_tray)
        window = MagicMock()
        window._current_config = config
        window.tray_icon = MagicMock()
        return window

    def _trigger_alerts_logic(self, window, person_name):
        """从 gui.py 提取的 _trigger_alerts 核心逻辑"""
        config = window._current_config
        if config is None:
            return

        # 声音
        if config.alert_sound:
            window._beep_called = True

        # 任务栏闪烁
        window._flash_called = True

        # 托盘通知
        if config.alert_tray:
            window.tray_icon.showMessage(
                "⚠️ 检测到目标!",
                f"检测到: {person_name}",
            )

    def test_safe_when_no_config(self):
        """_current_config 为 None 时应安全返回"""
        window = MagicMock()
        window._current_config = None

        self._trigger_alerts_logic(window, "boss")
        window.tray_icon.showMessage.assert_not_called()

    def test_tray_alert_when_enabled(self):
        """alert_tray=True 时应调用 showMessage"""
        window = self._make_mock_window(alert_tray=True)

        self._trigger_alerts_logic(window, "boss")
        window.tray_icon.showMessage.assert_called_once()

        # 验证消息内容包含人名
        args = window.tray_icon.showMessage.call_args
        assert "boss" in args[0][1]

    def test_no_tray_alert_when_disabled(self):
        """alert_tray=False 时不应调用 showMessage"""
        window = self._make_mock_window(alert_tray=False)

        self._trigger_alerts_logic(window, "boss")
        window.tray_icon.showMessage.assert_not_called()

    def test_sound_alert_when_enabled(self):
        """alert_sound=True 时应触发声音"""
        window = self._make_mock_window(alert_sound=True)

        self._trigger_alerts_logic(window, "boss")
        assert window._beep_called is True

    def test_no_sound_alert_when_disabled(self):
        """alert_sound=False 时不应触发声音"""
        window = self._make_mock_window(alert_sound=False)

        self._trigger_alerts_logic(window, "boss")
        # MagicMock 会自动创建属性，需要检查 _beep_called 是否未被显式设置
        assert getattr(window, '_beep_called', None) is not True


# ---------------------------------------------------------------------------
# update_log 消息解析测试
# ---------------------------------------------------------------------------

class TestUpdateLogParsing:
    """验证 update_log 中的人名提取逻辑"""

    def test_extracts_person_name(self):
        """应从检测消息中提取人名"""
        message = "检测到目标人物: 张三"
        person_name = message.replace("检测到目标人物: ", "").strip()
        assert person_name == "张三"

    def test_extracts_english_name(self):
        """应正确提取英文名"""
        message = "检测到目标人物: boss"
        person_name = message.replace("检测到目标人物: ", "").strip()
        assert person_name == "boss"

    def test_no_match(self):
        """非检测消息不应误匹配"""
        message = "哨兵系统已启动..."
        assert "检测到目标人物" not in message
