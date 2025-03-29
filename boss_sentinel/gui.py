import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QTextEdit, QLabel, 
                            QLineEdit, QFormLayout, QGroupBox)
from PyQt5.QtCore import QThread, pyqtSignal
from .main import BossSentinel

class SentinelThread(QThread):
    """哨兵系统线程"""
    detection_signal = pyqtSignal(str)
    
    def __init__(self, config):
        super().__init__()
        self.sentinel = BossSentinel()
        self.sentinel.config = config
        
    def run(self):
        """重写run方法"""
        self.sentinel.start_monitoring(self.detection_callback)
        
    def detection_callback(self, person_name):
        """检测回调函数"""
        self.detection_signal.emit(f"检测到目标人物: {person_name}")

class ConfigGroup(QGroupBox):
    """配置组"""
    def __init__(self):
        super().__init__("配置")
        self.init_ui()
        
    def init_ui(self):
        layout = QFormLayout()
        
        self.model_path = QLineEdit("yolov8n-face.pt")
        self.known_faces_dir = QLineEdit("known_faces")
        self.log_file = QLineEdit("sentinel_log.txt")
        self.detection_interval = QLineEdit("5")
        self.cameras = QLineEdit("0")
        self.confidence_threshold = QLineEdit("0.7")
        
        layout.addRow("模型路径:", self.model_path)
        layout.addRow("人脸目录:", self.known_faces_dir)
        layout.addRow("日志文件:", self.log_file)
        layout.addRow("检测间隔(秒):", self.detection_interval)
        layout.addRow("摄像头ID(逗号分隔):", self.cameras)
        layout.addRow("置信度阈值:", self.confidence_threshold)
        
        self.setLayout(layout)
    
    def get_config(self):
        """获取配置"""
        return {
            "model_path": self.model_path.text(),
            "known_faces_dir": self.known_faces_dir.text(),
            "log_file": self.log_file.text(),
            "detection_interval": int(self.detection_interval.text()),
            "cameras": [int(cam) for cam in self.cameras.text().split(",")],
            "confidence_threshold": float(self.confidence_threshold.text())
        }
        
    def load_config(self, config_dict: dict):
        """加载配置到UI"""
        self.model_path.setText(config_dict.get('model_path', 'yolov8n-face.pt'))
        self.known_faces_dir.setText(config_dict.get('known_faces_dir', 'known_faces'))
        self.log_file.setText(config_dict.get('log_file', 'sentinel_log.txt'))
        self.detection_interval.setText(str(config_dict.get('detection_interval', 5)))
        self.cameras.setText(','.join(map(str, config_dict.get('cameras', [0]))))
        self.confidence_threshold.setText(str(config_dict.get('confidence_threshold', 0.7)))

class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Boss哨兵系统")
        self.resize(600, 400)
        self.init_ui()
        
    def init_ui(self):
        # 主布局
        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # 配置组
        self.config_group = ConfigGroup()
        layout.addWidget(self.config_group)
        
        # 控制按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("启动")
        self.stop_btn = QPushButton("停止")
        self.load_btn = QPushButton("加载配置")
        self.save_btn = QPushButton("保存配置")
        self.stop_btn.setEnabled(False)
        
        self.start_btn.clicked.connect(self.start_sentinel)
        self.stop_btn.clicked.connect(self.stop_sentinel)
        self.load_btn.clicked.connect(self.load_config_from_file)
        self.save_btn.clicked.connect(self.save_config_to_file)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.load_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)
        
        # 日志显示
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(QLabel("检测日志:"))
        layout.addWidget(self.log_display)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        
        # 哨兵线程
        self.sentinel_thread = None
    
    def start_sentinel(self):
        """启动哨兵"""
        config = self.config_group.get_config()
        self.sentinel_thread = SentinelThread(config)
        self.sentinel_thread.detection_signal.connect(self.update_log)
        self.sentinel_thread.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_display.append("哨兵系统已启动...")
    
    def stop_sentinel(self):
        """停止哨兵"""
        if self.sentinel_thread:
            self.sentinel_thread.terminate()
            self.sentinel_thread.wait()
            
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_display.append("哨兵系统已停止")
    
    def update_log(self, message):
        """更新日志"""
        self.log_display.append(message)
        
    def load_config_from_file(self):
        """从文件加载配置"""
        from .config import load_config
        import json
        
        try:
            with open('config.json', 'r') as f:
                config_dict = json.load(f)
                self.config_group.load_config(config_dict)
                self.log_display.append("配置已从文件加载")
        except Exception as e:
            self.log_display.append(f"加载配置失败: {str(e)}")
    
    def save_config_to_file(self):
        """保存配置到文件"""
        from .config import save_config, SentinelConfig
        
        try:
            config_dict = self.config_group.get_config()
            config = SentinelConfig(
                known_faces_dir=config_dict['known_faces_dir'],
                model_path=config_dict['model_path'],
                detection_interval=config_dict['detection_interval'],
                confidence_threshold=config_dict['confidence_threshold'],
                cameras=config_dict['cameras'],
                log_file=config_dict['log_file']
            )
            save_config(config, 'config.json')
            self.log_display.append("配置已保存到文件")
        except Exception as e:
            self.log_display.append(f"保存配置失败: {str(e)}")

def run_gui():
    """运行GUI"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_gui()