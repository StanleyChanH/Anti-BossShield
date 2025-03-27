# Boss Sentinel 监控系统

基于YOLOv8的人脸识别监控系统，当检测到特定人物时自动锁定Windows屏幕。

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

2. 修改config.json配置：
   - `known_faces_dir`: 人脸图片目录
   - `model_path`: YOLO模型路径
   - `detection_interval`: 检测间隔(秒)

3. 运行系统：
```bash
python -m boss_sentinel.main
```

## 文件结构

```
├── boss_sentinel/       # 核心代码
├── known_faces/         # 目标人物照片
│   ├── boss/            # 人物1
│   └── colleague/       # 人物2
├── detections/          # 检测截图
├── config.json          # 配置文件
├── requirements.txt     # 依赖文件
└── README.md            # 说明文档
```

## 注意事项

- 需要Windows系统
- 确保摄像头可用
- 首次使用需下载yolov8n-face.pt模型