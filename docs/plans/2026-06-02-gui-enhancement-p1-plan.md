# P1: GUI 功能增强 — 内嵌实时预览 + 告警 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将监控画面嵌入 PyQt5 GUI，绘制检测框与人名标注，新增声音和任务栏告警。

**Architecture:** `monitor.py` 新增 `_draw_overlay()` 绘制标注帧并通过 `frame_callback` 回调传递给 GUI；`gui.py` 新增 `VideoWidget` 接收帧并渲染；告警通过 `winsound` + `FlashWindow` 实现。CLI 模式保持 `cv2.imshow()` 不变。

**Tech Stack:** PyQt5、OpenCV (cv2)、winsound、ctypes

---

### Task 1: 配置扩展 — 新增告警开关

**Files:**
- Modify: `boss_sentinel/config.py:17-33` (SentinelConfig dataclass)
- Modify: `boss_sentinel/config.py:111-130` (load_config)
- Modify: `boss_sentinel/config.py:133-160` (save_config)
- Modify: `config.json.example`

**Step 1: 在 SentinelConfig 中新增字段**

在 `boss_sentinel/config.py` 的 `SentinelConfig` dataclass 中，`notify_cooldown` 之后新增：

```python
    alert_sound: bool = True    # 是否播放告警声音
    alert_tray: bool = True     # 是否显示托盘通知
```

**Step 2: 更新 load_config()**

在 `boss_sentinel/config.py` 的 `load_config()` 函数中，`notify_cooldown` 行之后新增：

```python
        alert_sound=config_dict.get('alert_sound', True),
        alert_tray=config_dict.get('alert_tray', True),
```

**Step 3: 更新 save_config()**

在 `boss_sentinel/config.py` 的 `save_config()` 函数中，`notify_cooldown` 行之后新增：

```python
        'alert_sound': config.alert_sound,
        'alert_tray': config.alert_tray,
```

**Step 4: 更新 config.json.example**

在 `config.json.example` 中新增：

```json
    "alert_sound": true,
    "alert_tray": true,
```

**Step 5: 验证导入无误**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.config import SentinelConfig; c = SentinelConfig(); print(c.alert_sound, c.alert_tray)"`
Expected: `True True`

**Step 6: Commit**

```bash
git add boss_sentinel/config.py config.json.example
git commit -m "feat(config): 新增 alert_sound/alert_tray 告警配置项"
```

---

### Task 2: Monitor — 检测框绘制方法

**Files:**
- Modify: `boss_sentinel/monitor.py:1-11` (imports)
- Modify: `boss_sentinel/monitor.py` (新增方法)

**Step 1: 确保 import cv2 已存在**

`monitor.py` 第 1 行已有 `import cv2`，无需改动。

**Step 2: 在 SentinelMonitor 类中新增 `_draw_overlay()` 方法**

在 `process_frame()` 方法之前（`_should_notify` 方法之后）插入：

```python
    def _draw_overlay(self, frame: np.ndarray, tracks: dict) -> np.ndarray:
        """在帧上绘制检测框和人名标注"""
        display = frame.copy()

        for track_id, track in tracks.items():
            if track.disappeared > 0:
                continue

            x1, y1, x2, y2 = [int(v) for v in track.bbox]

            if track.person_name:
                color = (0, 0, 255)  # 红色 BGR - 目标人物
                label = f"{track.person_name} ({track.similarity:.0%})"
            else:
                color = (0, 255, 0)  # 绿色 BGR - 未知人脸
                label = "unknown"

            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(display, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(display, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        return display
```

**Step 3: 验证方法存在**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.monitor import SentinelMonitor; print(hasattr(SentinelMonitor, '_draw_overlay'))"`
Expected: `True`

**Step 4: Commit**

```bash
git add boss_sentinel/monitor.py
git commit -m "feat(monitor): 新增 _draw_overlay() 检测框绘制方法"
```

---

### Task 3: Monitor — run() 支持 frame_callback

**Files:**
- Modify: `boss_sentinel/monitor.py:199-253` (run 方法)

**Step 1: 修改 run() 方法签名和逻辑**

将 `run()` 方法替换为：

```python
    def run(self, callback: Optional[Callable[[str], None]] = None,
            frame_callback: Optional[Callable[[np.ndarray], None]] = None):
        """
        运行监控系统

        参数:
            callback: 检测到目标人物时的回调函数
            frame_callback: 每帧回调，传递带标注的画面（用于 GUI 内嵌预览）
        """
        self._callback = callback
        self.ensure_models_loaded()
        self.running = True
        self.logger.log("Sentinel started, monitoring...")

        try:
            while self.running:
                if self._config_watcher:
                    self._config_watcher.check_for_changes()

                for idx, cap in enumerate(self.cameras):
                    ret, frame = cap.read()
                    if not ret:
                        continue

                    detected = self.process_frame(frame, idx)

                    # 绘制标注
                    overlay_frame = self._draw_overlay(frame, self.tracker.tracks)

                    # 传递帧给调用方（GUI 模式）
                    if frame_callback:
                        frame_callback(overlay_frame)

                    # CLI 模式：用 cv2.imshow 显示
                    if self.config.show_feed and not frame_callback:
                        cv2.imshow(f'Camera {idx} - Press Q to quit', overlay_frame)

                    if detected and self._should_lock():
                        self.locker.lock()
                        self._last_lock_time = time.time()
                        self.logger.log(f"Screen locked, cooldown {self.config.lock_cooldown}s")

                if self.config.show_feed and not frame_callback:
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

        except KeyboardInterrupt:
            self.logger.log("User interrupted")
        finally:
            self.shutdown()
```

**关键变化：**
- `run()` 新增 `frame_callback` 参数
- `_draw_overlay()` 在每个摄像头帧上绘制标注
- `frame_callback` 存在时，不调用 `cv2.imshow()`（避免弹窗）
- CLI 模式（`frame_callback=None`）保持原有 `cv2.imshow()` 行为不变

**Step 2: 验证导入无误**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.monitor import SentinelMonitor; import inspect; sig = inspect.signature(SentinelMonitor.run); print(list(sig.parameters.keys()))"`
Expected: `['self', 'callback', 'frame_callback']`

**Step 3: Commit**

```bash
git add boss_sentinel/monitor.py
git commit -m "feat(monitor): run() 支持 frame_callback，分离 GUI/CLI 显示逻辑"
```

---

### Task 4: GUI — VideoWidget 组件

**Files:**
- Modify: `boss_sentinel/gui.py:1-10` (imports)
- Modify: `boss_sentinel/gui.py` (新增类)

**Step 1: 补充 import**

在 `gui.py` 顶部 import 区域新增：

```python
import numpy as np
import cv2
```

在 PyQt5.QtGui 导入中新增 `QImage, QPixmap`（`QIcon, QFont` 后面）：

```python
from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap
```

**Step 2: 在 ConfigGroup 类之前新增 VideoWidget 类**

在 `gui.py` 中 `ConfigGroup` 类定义之前（`SentinelThread` 类之后）插入：

```python
class VideoWidget(QLabel):
    """内嵌视频预览组件"""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background: black; color: gray; border: 1px solid #444;")
        self.setText("等待摄像头...")

    def update_frame(self, frame: np.ndarray):
        """更新显示帧"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        scaled = QPixmap.fromImage(qimg).scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

    def clear_frame(self):
        """停止时清空画面"""
        self.clear()
        self.setText("监控已停止")
```

**Step 3: 验证导入无误**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.gui import VideoWidget; print(VideoWidget.__name)"`
Expected: `VideoWidget`

**Step 4: Commit**

```bash
git add boss_sentinel/gui.py
git commit -m "feat(gui): 新增 VideoWidget 内嵌视频预览组件"
```

---

### Task 5: GUI — SentinelThread 帧信号集成

**Files:**
- Modify: `boss_sentinel/gui.py:12-56` (SentinelThread)

**Step 1: 在 SentinelThread 中新增 frame_signal**

在 `SentinelThread` 类的信号声明区域（`status_signal` 之后）新增：

```python
    frame_signal = pyqtSignal(np.ndarray)  # 视频帧信号
```

**Step 2: 修改 SentinelThread.run() 传递帧**

将 `SentinelThread.run()` 中的：

```python
            self.monitor.run(callback=self.detection_callback)
```

改为：

```python
            self.monitor.run(
                callback=self.detection_callback,
                frame_callback=self.frame_signal.emit
            )
```

**Step 3: 验证导入无误**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.gui import SentinelThread; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add boss_sentinel/gui.py
git commit -m "feat(gui): SentinelThread 新增 frame_signal 传递视频帧"
```

---

### Task 6: GUI — MainWindow 集成 VideoWidget

**Files:**
- Modify: `boss_sentinel/gui.py:120-393` (MainWindow)

**Step 1: 在 init_ui() 中添加 VideoWidget**

在 `MainWindow.init_ui()` 中，配置组之后、控制按钮之前，新增 VideoWidget：

```python
        # 视频预览
        self.video_widget = VideoWidget()
        layout.addWidget(self.video_widget)
```

**Step 2: 在 start_sentinel() 中连接帧信号**

在 `start_sentinel()` 方法中，`self.sentinel_thread.start()` 之前新增：

```python
        self.sentinel_thread.frame_signal.connect(self.video_widget.update_frame)
```

**Step 3: 在 stop_sentinel() 中清空画面**

在 `stop_sentinel()` 方法中，`self.log_display.append("哨兵系统已停止")` 之后新增：

```python
        self.video_widget.clear_frame()
```

**Step 4: 让配置组可折叠**

在 `init_ui()` 中，将：

```python
        self.config_group = ConfigGroup()
        layout.addWidget(self.config_group)
```

改为：

```python
        self.config_group = ConfigGroup()
        self.config_group.setCheckable(True)
        self.config_group.setChecked(False)  # 默认折叠
        self.config_group.setTitle("配置 (点击展开)")
        layout.addWidget(self.config_group)
```

**Step 5: 验证导入无误**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.gui import MainWindow; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add boss_sentinel/gui.py
git commit -m "feat(gui): MainWindow 集成 VideoWidget，配置组可折叠"
```

---

### Task 7: GUI — ConfigGroup 新增告警配置

**Files:**
- Modify: `boss_sentinel/gui.py:58-117` (ConfigGroup)

**Step 1: 在 init_ui() 中新增告警配置字段**

在 `ConfigGroup.init_ui()` 中，`notify_cooldown` 行之后新增：

```python
        self.alert_sound = QLineEdit("true")
        self.alert_tray = QLineEdit("true")

        layout.addRow("告警声音:", self.alert_sound)
        layout.addRow("托盘通知:", self.alert_tray)
```

**Step 2: 在 get_config() 中新增**

在 `ConfigGroup.get_config()` 中，`notify_cooldown` 行之后新增：

```python
            alert_sound=self.alert_sound.text().lower() == "true",
            alert_tray=self.alert_tray.text().lower() == "true",
```

**Step 3: 在 load_config() 中新增**

在 `ConfigGroup.load_config()` 中，`notify_cooldown` 行之后新增：

```python
        self.alert_sound.setText(str(config_dict.get('alert_sound', True)).lower())
        self.alert_tray.setText(str(config_dict.get('alert_tray', True)).lower())
```

**Step 4: 验证导入无误**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.gui import ConfigGroup; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add boss_sentinel/gui.py
git commit -m "feat(gui): ConfigGroup 新增告警配置字段"
```

---

### Task 8: GUI — 告警处理

**Files:**
- Modify: `boss_sentinel/gui.py:1-10` (imports)
- Modify: `boss_sentinel/gui.py` (MainWindow 方法)

**Step 1: 在文件顶部新增 import**

```python
import winsound
from ctypes import windll
```

**Step 2: 在 MainWindow 中新增告警方法**

在 `MainWindow` 类中新增：

```python
    def _trigger_alerts(self, person_name: str):
        """触发告警"""
        config = self.config_group.get_config()

        # 系统提示音
        if config.alert_sound:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

        # 任务栏闪烁
        try:
            hwnd = int(self.winId())
            windll.user32.FlashWindow(hwnd, True)
        except Exception:
            pass

        # 托盘通知
        if config.alert_tray:
            self.tray_icon.showMessage(
                "⚠️ 检测到目标!",
                f"检测到: {person_name}",
                QSystemTrayIcon.Critical,
                5000
            )
```

**Step 3: 修改 update_log() 调用告警**

将 `update_log()` 方法改为：

```python
    def update_log(self, message):
        """更新日志"""
        self.log_display.append(message)
        # 从消息中提取人名并触发告警
        if "检测到目标人物" in message:
            person_name = message.replace("检测到目标人物: ", "").strip()
            self._trigger_alerts(person_name)
```

**Step 4: 验证导入无误**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.gui import MainWindow; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add boss_sentinel/gui.py
git commit -m "feat(gui): 新增多样化告警（声音+任务栏闪烁+托盘通知）"
```

---

### Task 9: 集成验证

**Step 1: 全模块导入测试**

Run: `.venv/Scripts/python.exe -c "from boss_sentinel.config import SentinelConfig; from boss_sentinel.monitor import SentinelMonitor; from boss_sentinel.gui import MainWindow, VideoWidget; print('All imports OK')"`

Expected: `All imports OK`

**Step 2: CLI 模式冒烟测试**

Run: `.venv/Scripts/python.exe -m boss_sentinel.main --config config.json`

验证：
- 摄像头初始化正常
- 检测框和标注正常显示
- 按 Q 可退出
- 不应出现 AttributeError 或 ImportError

**Step 3: GUI 模式冒烟测试**

Run: `.venv/Scripts/python.exe -m boss_sentinel --gui`

验证：
- VideoWidget 显示黑色占位（"等待摄像头..."）
- 配置组默认折叠，点击可展开
- 点击「启动监控」后预览区域显示摄像头画面
- 画面上有检测框和人名标注
- 检测到目标时有声音和托盘通知
- 点击「停止监控」后预览显示"监控已停止"
- 关闭窗口最小化到托盘正常

**Step 4: 最终 Commit**

```bash
git add -A
git commit -m "feat: P1 完成 — 内嵌实时预览 + 检测框标注 + 多样化告警"
```
