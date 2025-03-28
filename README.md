# Anti-BossShield 监控系统

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

## 打包为EXE

1. 安装PyInstaller:
```bash
pip install pyinstaller
```

2. 执行打包(包含所有依赖):
```bash
pyinstaller --onefile --windowed --name BossSentinel --add-data "boss_sentinel;boss_sentinel" --hidden-import="cv2" --hidden-import="ultralytics" --paths="d:\Anti-BossShield" boss_sentinel/__main__.py
```

3. 打包结果:
   - 生成文件: dist/BossSentinel.exe (约500MB)
   - 生成目录: build/ (可删除)

4. 使用说明:
   - 将config.json.example复制为config.json并配置
   - 创建known_faces目录并添加目标人物照片
   - 双击BossSentinel.exe运行图形界面
   - 首次运行会自动下载yolov8n-face.pt模型

5. 注意事项:
   - 打包过程可能需要10-15分钟
   - 最终exe文件较大(包含所有依赖)
   - 确保系统有足够内存运行