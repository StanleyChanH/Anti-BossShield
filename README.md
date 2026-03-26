<div align="center">

# 🛡️ Boss Sentinel

**智能人脸识别监控系统 - 当检测到特定人物时自动锁定屏幕**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-38%20passed-brightgreen)](tests/)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [配置](#-配置说明) • [开发](#-开发)

</div>

---

## 📖 简介

Boss Sentinel 是一个基于深度学习的 Windows 人脸识别监控系统。它使用 YOLOv8 进行实时人脸检测，FaceNet 进行高精度人脸识别，当检测到预先设定的目标人物时会自动锁定电脑屏幕。

> ⚠️ **免责声明**：本项目仅供学习和娱乐目的，请勿用于任何非法用途。

## ✨ 功能特性

| 功能 | 描述 |
|------|------|
| 🔍 **实时人脸检测** | 基于 YOLOv8 的高精度人脸检测，支持多摄像头 |
| 🎯 **多人物识别** | 支持多人子目录结构，每人可配置多张照片 |
| 🚀 **人脸跟踪** | 轻量级跟踪器，减少重复识别，提升性能 |
| 🔒 **自动锁屏** | 检测到目标人物时自动锁定 Windows |
| 📧 **邮件通知** | 可选的邮件报警功能，第一时间获知检测事件 |
| 💻 **系统托盘** | GUI 支持最小化到托盘，后台静默运行 |
| 🔥 **配置热重载** | 运行时修改配置自动生效，无需重启 |
| ⚡ **性能优化** | 帧跳过、GPU 加速、懒加载等多重优化 |

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/Anti-BossShield.git
cd Anti-BossShield

# 安装依赖
pip install -r requirements.txt
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

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `known_faces_dir` | `known_faces` | 人脸图片目录 |
| `model_path` | `yolov8n-face.pt` | YOLO 模型路径 |
| `threshold` | `0.7` | 人脸识别相似度阈值 (0.0-1.0) |
| `confidence_threshold` | `0.7` | 检测置信度阈值 |
| `frame_skip` | `3` | 帧跳过数，越大性能越好但响应变慢 |
| `use_gpu` | `true` | 是否使用 GPU 加速 |
| `cameras` | `[0]` | 摄像头 ID 列表 |
| `show_feed` | `true` | 是否显示摄像头画面 |

## 📁 项目结构

```
boss_sentinel/
├── __init__.py
├── __main__.py      # 包入口
├── config.py        # 配置管理 + 热重载
├── detector.py      # YOLOv8 人脸检测
├── recognizer.py    # FaceNet 人脸识别
├── tracker.py       # 人脸跟踪器
├── monitor.py       # 主监控逻辑
├── locker.py        # Windows 锁屏
├── notifier.py      # 邮件通知
├── logger.py        # 日志记录
└── gui.py           # PyQt5 图形界面

tests/               # 单元测试
├── test_config.py
├── test_detector.py
├── test_tracker.py
└── test_performance.py
```

## 🔧 开发

### 运行测试

```bash
pytest tests/ -v
```

### 打包为 EXE

```bash
pyinstaller BossSentinel.spec
```

生成的可执行文件位于 `dist/BossSentinel.exe`。

## 💻 系统要求

- **操作系统**: Windows 10/11
- **Python**: 3.9 - 3.12
- **硬件**: 摄像头（必需）、CUDA 兼容 GPU（可选，用于加速）

## 📝 注意事项

- 首次运行会自动下载 `yolov8n-face.pt` 模型（约 6MB）
- 配置文件 `config.json` 不会提交到 Git，请从示例文件复制
- 日志文件自动轮转（最大 1MB，保留 3 个备份）
- 检测截图保存在 `detections/` 目录，最多保留 20 张

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

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给一个 Star！⭐**

</div>
