<div align="center">

# 🛡️ Boss Sentinel

**智能人脸识别监控系统 - 当检测到特定人物时自动锁定屏幕**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/uv-managed-261230?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [配置](#-配置说明) • [开发](#-开发)

</div>

---

## 📖 简介

Boss Sentinel 是一个基于深度学习的 Windows 人脸识别监控系统。它使用 YOLOv8 进行实时人脸检测，FaceNet 进行高精度人脸识别，当检测到预先设定的目标人物时会自动锁定电脑屏幕。除了核心的监控功能外，还提供了肩窥检测、入侵者拍照、番茄工作法、智能家居联动、疲劳检测等丰富的扩展功能。

> ⚠️ **免责声明**：本项目仅供学习和娱乐目的，请勿用于任何非法用途。

## ✨ 功能特性

### 核心功能

| 功能 | 描述 |
|------|------|
| 🔍 **实时人脸检测** | 基于 YOLOv8 的高精度人脸检测，支持多摄像头，GPU/FP16 加速 |
| 🎯 **多人物识别** | FaceNet 512D 嵌入 + 余弦相似度，支持人脸对齐、批处理推理 |
| 🚀 **智能跟踪** | 每摄像头独立跟踪器，识别缓存减少重复计算 |
| 🔒 **自动锁屏** | 检测到目标人物时自动锁定 Windows，支持目标名单过滤 |
| 📧 **邮件通知** | SMTP/SMTP_SSL 邮件报警，异步发送不阻塞主循环 |
| 💻 **系统托盘** | PyQt5 GUI 支持最小化到托盘，后台静默运行 |
| 🔥 **配置热重载** | 运行时修改配置自动生效，无需重启 |
| ⚡ **性能优化** | 自适应帧跳过、GPU 加速、批处理推理、向量化的嵌入比较 |

### 🎯 扩展功能（可选，默认关闭）

| 功能 | 描述 |
|------|------|
| 🛡️ **肩窥探测器** | 检测身后有人偷看屏幕，计算隐私等级，触发隐私保护 |
| 📸 **入侵者拍照** | 用户离开期间检测到陌生人自动拍照 + 时间戳水印 + 邮件通知 |
| 🍅 **番茄钟伴侣** | 用户坐下自动开始专注计时，离开自动暂停，每日效率报告 |
| 🏠 **MQTT 智能家居** | 发布在场状态到 MQTT，联动 Home Assistant 自动化灯光/空调 |
| 😴 **疲劳检测** | 追踪眼睛纵横比（EAR），检测犯困触发音频提醒 |

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/Anti-BossShield.git
cd Anti-BossShield

# 使用 uv 安装依赖（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 可选依赖

```bash
# MQTT 智能家居功能
pip install paho-mqtt

# 高精度疲劳检测（不安装也能用 YOLOv8 关键点近似）
pip install mediapipe
```

### 配置

1. **创建配置文件**
   ```bash
   cp config.json.example config.json
   ```

2. **准备人脸图片**
   ```
   known_faces/
   ├── boss/
   │   ├── photo1.jpg
   │   ├── photo2.jpg
   │   └── photo3.jpg
   └── other_person/
       └── photo1.jpg
   ```

### 运行

**GUI 模式（推荐）：**
```bash
python -m boss_sentinel
```

**命令行模式：**
```bash
python -m boss_sentinel.main
```

## ⚙️ 配置说明

### 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `known_faces_dir` | `known_faces` | 人脸图片目录 |
| `model_path` | `yolov8n-face.pt` | YOLO 模型路径 |
| `threshold` | `0.7` | 人脸识别相似度阈值 (0.0-1.0) |
| `confidence_threshold` | `0.7` | 检测置信度阈值 |
| `frame_skip` | `3` | 帧跳过数，越大性能越好但响应变慢 |
| `use_gpu` | `true` | 是否使用 GPU 加速 |
| `lock_cooldown` | `30` | 锁屏冷却秒数 |
| `notify_cooldown` | `60` | 同一人通知冷却秒数 |
| `cameras` | `[0]` | 摄像头 ID 列表 |
| `show_feed` | `true` | 是否显示摄像头画面 |
| `target_names` | `[]` | 触发锁屏的目标名单（空=所有人） |
| `tracker_max_disappeared` | `30` | 跟踪器消失帧数阈值 |
| `away_timeout` | `30.0` | 用户离开多少秒视为不在场 |

### 扩展功能参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_shoulder_surfing` | `false` | 启用肩窥检测 |
| `enable_intruder_capture` | `false` | 启用入侵者拍照 |
| `enable_pomodoro` | `false` | 启用番茄工作法计时 |
| `enable_mqtt` | `false` | 启用 MQTT 智能家居桥接 |
| `enable_drowsiness` | `false` | 启用疲劳检测 |
| `mqtt_broker` | `""` | MQTT broker 地址 |
| `mqtt_port` | `1883` | MQTT broker 端口 |
| `mqtt_topic_prefix` | `"boss_sentinel"` | MQTT 主题前缀 |
| `pomodoro_focus_minutes` | `25` | 番茄钟专注时长（分钟） |
| `pomodoro_break_minutes` | `5` | 番茄钟休息时长（分钟） |
| `intruder_save_dir` | `"intruder_photos"` | 入侵者照片保存目录 |
| `drowsiness_ear_threshold` | `0.2` | 疲劳检测 EAR 阈值 |

## 📁 项目结构

```
boss_sentinel/
├── __init__.py
├── __main__.py            # 包入口（含中文路径修复）
├── config.py              # 配置管理 + 热重载 + 验证
├── detector.py            # YOLOv8 人脸检测（GPU/FP16 + 关键点）
├── recognizer.py          # FaceNet 人脸识别（批处理 + 对齐 + 向量化）
├── tracker.py             # 人脸跟踪 + 识别缓存
├── monitor.py             # 主监控逻辑（上下文管理器 + 自适应帧跳过）
├── locker.py              # Windows 锁屏 (LockWorkStation)
├── notifier.py            # 邮件通知（SMTP/SMTP_SSL + 异步）
├── logger.py              # 日志记录（RotatingFileHandler）
├── gui.py                 # PyQt5 图形界面 + 功能状态指示
├── main.py                # CLI 入口
├── shoulder_surfing.py    # 🛡️ 肩窥探测器（可选）
├── intruder_capture.py    # 📸 入侵者拍照（可选）
├── pomodoro.py            # 🍅 番茄钟伴侣（可选）
├── mqtt_bridge.py         # 🏠 MQTT 智能家居桥接（可选）
└── drowsiness_detector.py # 😴 疲劳检测（可选）

tests/                     # 单元测试
```

## 🔧 开发

### 运行测试

```bash
uv run pytest tests/ -v
```

### 打包为 EXE

```bash
uv run pyinstaller BossSentinel.spec
```

生成的可执行文件位于 `dist/BossSentinel.exe`。

## 💻 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.9 - 3.12
- **包管理**: [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- **硬件**: 摄像头（必需）、CUDA 兼容 GPU（可选，用于加速）
- **可选**: paho-mqtt（MQTT 功能）、mediapipe（高精度疲劳检测）

## 📝 注意事项

- 首次运行会自动下载 `yolov8n-face.pt` 模型（约 6MB）
- 配置文件 `config.json` 不会提交到 Git，请从示例文件复制
- 日志文件自动轮转（最大 1MB，保留 5 个备份）
- 所有扩展功能默认关闭，需在 config.json 中手动启用
- 可选依赖缺失时功能会被静默禁用并记录警告日志

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 📄 License

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [YOLOv8](https://github.com/ultralytics/ultralytics) - 人脸检测
- [FaceNet PyTorch](https://github.com/timesler/facenet-pytorch) - 人脸识别
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) - 图形界面
- [paho-mqtt](https://www.eclipse.org/paho/python.php) - MQTT 通信
- [MediaPipe](https://mediapipe.dev/) - 面部网格（疲劳检测）

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给一个 Star！⭐**

</div>
