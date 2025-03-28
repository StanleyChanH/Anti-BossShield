# Anti-BossShield 监控系统

基于YOLOv8的人脸识别监控系统，当检测到特定人物时自动锁定Windows屏幕。反老板专用，有打工人提供更多场景，我继续增加功能，欢迎大家提出建议。

## 功能特性

- 实时摄像头监控
- 多人物识别（支持known_faces目录下多个人物文件夹）
- 自动锁定Windows屏幕
- 检测截图保存（最多保留20张）
- 详细的日志记录（带轮转功能）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

1. 准备known_faces目录：
   - 为每个监控目标创建单独文件夹
   - 在文件夹中放入多张该人物的照片

2. 复制示例配置文件：
```bash
cp config.json.example config.json
```

3. 修改config.json配置：
   - `known_faces_dir`: 人脸图片目录
   - `model_path`: YOLO模型路径
   - `detection_interval`: 检测间隔(秒)

4. 运行系统：

命令行模式：
```bash
python -m boss_sentinel.main
```

图形界面模式：
```bash
python -m boss_sentinel
```

5. GUI功能：
- 启动/停止监控
- 实时显示检测结果
- 配置摄像头ID和置信度阈值
- 查看日志输出

## 项目结构 (优化版)

```
├── boss_sentinel/       # 核心代码
│   ├── __init__.py
│   ├── config.py
│   ├── detector.py
│   ├── gui.py          # 图形界面
│   ├── main.py         # 主逻辑
│   └── __main__.py     # 入口文件
├── known_faces/        # 目标人物照片
│   └── boss/
├── detections/         # 检测截图
├── config.json.example # 配置文件示例
├── requirements.txt    # 依赖文件
├── setup.py            # 安装脚本
└── README.md           # 说明文档
```

## 注意事项

- 需要Windows系统
- 确保摄像头可用
- 首次使用需下载yolov8n-face.pt模型
- 配置文件需从config.json.example复制创建

## 终端使用
- 简单打包了个exe文件，直接双击运行即可，不需要安装python环境。