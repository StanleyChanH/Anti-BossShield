import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QPushButton, QTextEdit, QLabel,
                            QLineEdit, QFormLayout, QGroupBox, QProgressDialog,
                            QSystemTrayIcon, QMenu, QAction, QStyle)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QIcon, QFont
from .monitor import SentinelMonitor
from .config import SentinelConfig


class SentinelThread(QThread):
    """哨兵系统线程"""
    detection_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)  # (进度百分比, 消息)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)  # 状态变化信号

    def __init__(self, config: SentinelConfig):
        super().__init__()
        self.config = config
        self.monitor = None

    def run(self):
        """重写run方法"""
        try:
            # 初始化 SentinelMonitor（使用懒加载）
            self.progress_signal.emit(10, "正在加载配置...")
            self.monitor = SentinelMonitor(self.config, lazy_load=True)

            # 加载模型
            self.progress_signal.emit(30, "正在加载YOLOv8模型...")
            self.monitor.initialize_models()

            self.progress_signal.emit(80, "模型加载完成，准备启动监控...")
            import time
            time.sleep(0.5)

            self.progress_signal.emit(90, "开始监控...")
            self.status_signal.emit("monitoring")
            self.monitor.run(callback=self.detection_callback)

        except Exception as e:
            self.error_signal.emit(f"初始化失败: {str(e)}")
            self.status_signal.emit("error")

    def detection_callback(self, person_name):
        """检测回调函数"""
        self.detection_signal.emit(f"检测到目标人物: {person_name}")

    def stop(self):
        """停止监控"""
        if self.monitor:
            self.monitor.stop()
        self.status_signal.emit("stopped")


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
        self.detection_interval = QLineEdit("1")
        self.cameras = QLineEdit("0")
        self.threshold = QLineEdit("0.7")
        self.confidence_threshold = QLineEdit("0.7")
        self.frame_skip = QLineEdit("3")
        self.use_gpu = QLineEdit("true")

        layout.addRow("模型路径:", self.model_path)
        layout.addRow("人脸目录:", self.known_faces_dir)
        layout.addRow("日志文件:", self.log_file)
        layout.addRow("检测间隔(秒):", self.detection_interval)
        layout.addRow("摄像头ID(逗号分隔):", self.cameras)
        layout.addRow("识别阈值:", self.threshold)
        layout.addRow("置信度阈值:", self.confidence_threshold)
        layout.addRow("帧跳过数(性能优化):", self.frame_skip)
        layout.addRow("使用GPU加速:", self.use_gpu)

        self.setLayout(layout)

    def get_config(self) -> SentinelConfig:
        """获取配置 - 返回 SentinelConfig 对象"""
        return SentinelConfig(
            model_path=self.model_path.text(),
            known_faces_dir=self.known_faces_dir.text(),
            log_file=self.log_file.text(),
            detection_interval=int(self.detection_interval.text()),
            cameras=[int(cam.strip()) for cam in self.cameras.text().split(",") if cam.strip()],
            threshold=float(self.threshold.text()),
            confidence_threshold=float(self.confidence_threshold.text()),
            frame_skip=int(self.frame_skip.text()),
            use_gpu=self.use_gpu.text().lower() == "true"
        )

    def load_config(self, config_dict: dict):
        """加载配置到UI"""
        self.model_path.setText(config_dict.get('model_path', 'yolov8n-face.pt'))
        self.known_faces_dir.setText(config_dict.get('known_faces_dir', 'known_faces'))
        self.log_file.setText(config_dict.get('log_file', 'sentinel_log.txt'))
        self.detection_interval.setText(str(config_dict.get('detection_interval', 1)))
        self.cameras.setText(','.join(map(str, config_dict.get('cameras', [0]))))
        self.threshold.setText(str(config_dict.get('threshold', 0.7)))
        self.confidence_threshold.setText(str(config_dict.get('confidence_threshold', 0.7)))
        self.frame_skip.setText(str(config_dict.get('frame_skip', 3)))
        self.use_gpu.setText(str(config_dict.get('use_gpu', True)).lower())


class MainWindow(QMainWindow):
    """主窗口 - 支持系统托盘"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Boss哨兵系统")
        self.resize(600, 450)
        self._is_monitoring = False
        self.init_ui()
        self.init_tray()

    def init_ui(self):
        """初始化UI"""
        # 主布局
        main_widget = QWidget()
        layout = QVBoxLayout()

        # 配置组
        self.config_group = ConfigGroup()
        layout.addWidget(self.config_group)

        # 控制按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("启动监控")
        self.stop_btn = QPushButton("停止监控")
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

        # 状态栏
        status_layout = QHBoxLayout()
        self.status_label = QLabel("状态: 就绪")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # 日志显示
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 9))
        layout.addWidget(QLabel("检测日志:"))
        layout.addWidget(self.log_display)

        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

        # 哨兵线程
        self.sentinel_thread = None
        self.progress_dialog = None

    def init_tray(self):
        """初始化系统托盘"""
        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)

        # 使用内置图标
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Boss哨兵系统")

        # 创建托盘菜单
        tray_menu = QMenu()

        # 显示/隐藏窗口
        self.show_action = QAction("显示窗口", self)
        self.show_action.triggered.connect(self.show_and_activate)
        tray_menu.addAction(self.show_action)

        # 启动/停止监控
        self.tray_start_action = QAction("启动监控", self)
        self.tray_start_action.triggered.connect(self.start_sentinel)
        tray_menu.addAction(self.tray_start_action)

        self.tray_stop_action = QAction("停止监控", self)
        self.tray_stop_action.triggered.connect(self.stop_sentinel)
        self.tray_stop_action.setEnabled(False)
        tray_menu.addAction(self.tray_stop_action)

        tray_menu.addSeparator()

        # 退出
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)

        # 双击托盘图标显示窗口
        self.tray_icon.activated.connect(self.on_tray_activated)

        # 显示托盘图标
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """托盘图标激活处理"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_and_activate()

    def show_and_activate(self):
        """显示并激活窗口"""
        self.show()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        """关闭事件 - 最小化到托盘而不是退出"""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Boss哨兵系统",
            "程序已最小化到系统托盘，双击图标可恢复窗口",
            QSystemTrayIcon.Information,
            2000
        )

    def quit_app(self):
        """退出应用"""
        if self.sentinel_thread and self._is_monitoring:
            self.stop_sentinel()
        self.tray_icon.hide()
        QApplication.quit()

    def start_sentinel(self):
        """启动哨兵"""
        config = self.config_group.get_config()

        # 创建进度对话框
        self.progress_dialog = QProgressDialog("正在初始化哨兵系统...", "取消", 0, 100, self)
        self.progress_dialog.setWindowTitle("初始化")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.show()

        self.sentinel_thread = SentinelThread(config)
        self.sentinel_thread.detection_signal.connect(self.update_log)
        self.sentinel_thread.progress_signal.connect(self.update_progress)
        self.sentinel_thread.error_signal.connect(self.on_init_error)
        self.sentinel_thread.finished.connect(self.on_init_finished)
        self.sentinel_thread.status_signal.connect(self.on_status_changed)
        self.sentinel_thread.start()

        self._is_monitoring = True
        self.update_ui_state("starting")

    def update_progress(self, value, message):
        """更新进度"""
        if self.progress_dialog:
            self.progress_dialog.setValue(value)
            self.progress_dialog.setLabelText(message)

    def on_init_error(self, error_msg):
        """初始化错误处理"""
        if self.progress_dialog:
            self.progress_dialog.close()
        self.log_display.append(f"错误: {error_msg}")
        self.tray_icon.showMessage("启动失败", error_msg, QSystemTrayIcon.Critical, 3000)
        self._is_monitoring = False
        self.update_ui_state("error")

    def on_init_finished(self):
        """初始化完成"""
        if self.progress_dialog:
            self.progress_dialog.close()
        self.log_display.append("哨兵系统已启动...")

    def on_status_changed(self, status):
        """状态变化处理"""
        if status == "monitoring":
            self.status_label.setText("状态: 监控中")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.update_ui_state("monitoring")
        elif status == "stopped":
            self.status_label.setText("状态: 已停止")
            self.status_label.setStyleSheet("color: gray; font-weight: bold;")
            self._is_monitoring = False
            self.update_ui_state("stopped")
        elif status == "error":
            self.status_label.setText("状态: 错误")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self._is_monitoring = False
            self.update_ui_state("error")

    def update_ui_state(self, state):
        """更新UI状态"""
        if state == "starting" or state == "monitoring":
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.tray_start_action.setEnabled(False)
            self.tray_stop_action.setEnabled(True)
        else:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.tray_start_action.setEnabled(True)
            self.tray_stop_action.setEnabled(False)

    def stop_sentinel(self):
        """停止哨兵"""
        if self.sentinel_thread:
            if self.sentinel_thread.monitor:
                self.sentinel_thread.monitor.stop()
            self.sentinel_thread.wait(3000)  # 等待最多3秒

        self._is_monitoring = False
        self.status_label.setText("状态: 已停止")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.log_display.append("哨兵系统已停止")
        self.update_ui_state("stopped")

    def update_log(self, message):
        """更新日志"""
        self.log_display.append(message)
        # 发送托盘通知
        self.tray_icon.showMessage(
            "检测到目标!",
            message,
            QSystemTrayIcon.Warning,
            3000
        )

    def load_config_from_file(self):
        """从文件加载配置"""
        from .config import load_config
        import json

        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
                self.config_group.load_config(config_dict)
                self.log_display.append("配置已从文件加载")
        except Exception as e:
            self.log_display.append(f"加载配置失败: {str(e)}")

    def save_config_to_file(self):
        """保存配置到文件"""
        from .config import save_config

        try:
            config = self.config_group.get_config()
            save_config(config, 'config.json')
            self.log_display.append("配置已保存到文件")
        except Exception as e:
            self.log_display.append(f"保存配置失败: {str(e)}")


def run_gui():
    """运行GUI"""
    # 设置高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出应用

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    run_gui()
