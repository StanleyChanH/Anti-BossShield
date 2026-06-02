# P1: GUI 功能增强 — 内嵌实时预览 + 告警

**日期:** 2026-06-02
**状态:** 已批准
**迭代:** 方案 A - 视觉优先 / P1

---

## 目标

将监控画面从 OpenCV 外部弹窗迁移到 PyQt5 GUI 内嵌显示，同时增强告警机制，使系统从「能用」变为「好用」。

---

## 改动范围

| 文件 | 改动类型 | 具体内容 |
|------|---------|---------|
| `monitor.py` | 修改 | 新增 `_draw_overlay()` 绘制检测框；`run()` 新增 `frame_callback` 参数；CLI 模式保留 `cv2.imshow()` |
| `gui.py` | 修改 | 新增 `VideoWidget` 组件；`SentinelThread` 新增 `frame_signal`；配置组改为可折叠；新增告警处理逻辑 |
| `config.py` | 修改 | 新增 `alert_sound`、`alert_tray` 配置字段 |
| `config.json.example` | 修改 | 新增对应配置示例 |

**不改动:** `detector.py`、`recognizer.py`、`tracker.py`、`locker.py`、`notifier.py`、`logger.py`、`main.py`、`__main__.py`

---

## 1. 内嵌实时预览

### VideoWidget

自定义 `QLabel` 子类，负责将 `np.ndarray` 帧渲染为 `QPixmap` 显示：

- `update_frame(frame)` — BGR→RGB→QImage→QPixmap，`KeepAspectRatio` 自适应缩放
- `clear_frame()` — 停止时显示占位文字
- 最小尺寸 640x480，黑色背景

### 帧传递

`SentinelThread` 新增 `frame_signal = pyqtSignal(np.ndarray)`，`monitor.run()` 通过 `frame_callback` 参数回调传递帧。GUI 主线程接收信号后调用 `VideoWidget.update_frame()`。

### GUI 布局

```
┌─────────────────────────────────────────┐
│  配置组 (可折叠 QGroupBox)               │
├─────────────────────────────────────────┤
│          VideoWidget (视频预览)          │
│          640x480 最小尺寸               │
├─────────────────────────────────────────┤
│  [启动] [停止] [加载配置] [保存配置]      │
│  状态: 监控中                            │
├─────────────────────────────────────────┤
│  检测日志                               │
└─────────────────────────────────────────┘
```

---

## 2. 检测框与人名标注

`monitor._draw_overlay()` 在帧上绘制：

- **目标人物**: 红色边界框 + 白色文字标签（人名 + 相似度百分比）
- **未知人脸**: 绿色边界框 + "unknown" 标签
- **标签背景**: 实心矩形底色，保证文字可读
- **只绘制活跃跟踪** (`disappeared == 0`)，避免闪烁

绘制逻辑在 monitor 层，CLI 和 GUI 共享。

---

## 3. 多样化告警

### 告警方式

| 方式 | 实现 | 默认 |
|------|------|------|
| 系统提示音 | `winsound.MessageBeep(MB_ICONEXCLAMATION)` | 开启 |
| 托盘通知 | `tray_icon.showMessage()` (Critical 级别, 5s) | 开启 |
| 任务栏闪烁 | `FlashWindow(hwnd, True)` | 自动 |

### 配置项

```python
alert_sound: bool = True   # 是否播放告警声音
alert_tray: bool = True    # 是否显示托盘通知
```

### 冷却机制

所有告警遵循现有冷却：
- 锁屏冷却: `lock_cooldown` (30s)
- 通知冷却: `notify_cooldown` (60s/人)

---

## 4. 向后兼容

- CLI 模式: `run(frame_callback=None)` 时仍用 `cv2.imshow()` 显示带标注画面
- 新配置项有默认值，旧 `config.json` 无需修改
- `show_feed` 配置同时控制 CLI 和 GUI 的显示行为

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 帧传递性能 | `_draw_overlay()` 已做 `frame.copy()`，Qt signal 队列足够快 |
| 后台线程覆盖帧 | copy 后引用独立，不受影响 |
| winsound 阻塞 | `MessageBeep` 是异步的，不阻塞循环 |

---

## 后续迭代

- **P2**: 检测历史记录 + 统计面板
- **P3**: 人脸照片管理（GUI 内添加/删除/预览）
