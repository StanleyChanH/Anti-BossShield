import sys
import time
import numpy as np
import cv2
import winsound
from ctypes import windll
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QPushButton, QTextEdit, QLabel,
                            QLineEdit, QFormLayout, QGroupBox, QProgressDialog,
                            QSystemTrayIcon, QMenu, QAction, QStyle, QCheckBox,
                            QSpinBox, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap
from .monitor import SentinelMonitor
from .config import SentinelConfig


class SentinelThread(QThread):
    """哨兵系统线程"""
    detection_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)  # (进度百分比, 消息)
    error_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)  # 状态变化信号
    frame_signal = pyqtSignal(np.ndarray)  # 视频帧信号
    feature_signal = pyqtSignal(dict)  # 特性状态信号

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
            time.sleep(0.5)

            self.progress_signal.emit(90, "开始监控...")
            self.status_signal.emit("monitoring")
            self.monitor.run(
                callback=self.detection_callback,
                frame_callback=self._frame_callback
            )

        except Exception as e:
            self.error_signal.emit(f"初始化失败: {str(e)}")
            self.status_signal.emit("error")

    def _frame_callback(self, frame, feature_data=None):
        """帧回调 — 分离帧和特性数据"""
        self.frame_signal.emit(frame)
        if feature_data:
            self.feature_signal.emit(feature_data)

    def detection_callback(self, person_name):
        """检测回调函数"""
        self.detection_signal.emit(f"检测到目标人物: {person_name}")

    def stop(self):
        """停止监控"""
        if self.monitor:
            self.monitor.stop()
        # 不再手动 emit status_signal("stopped")
        # 线程结束后 finished 信号会触发 on_init_finished 统一处理状态


class VideoWidget(QLabel):
    """内嵌视频预览组件 — 带帧率节流和双缓冲

    注意：update_frame（信号槽）和 _render_frame（定时器）都通过 Qt 事件循环
    在主线程串行执行，无需互斥锁。
    """

    # 目标渲染帧率
    TARGET_FPS = 30

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("background: black; color: gray; border: 1px solid #444;")
        self.setText("等待摄像头...")

        # 双缓冲：最新帧由信号槽写入，定时器在主线程消费
        self._latest_frame = None
        self._frame_consumed = True  # 帧节流：上一帧已被消费才接受新帧
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._render_frame)
        self._render_timer.start(int(1000 / self.TARGET_FPS))

    def update_frame(self, frame: np.ndarray):
        """接收新帧（通过 QueuedConnection 在主线程执行）"""
        if not self._frame_consumed:
            return  # 上一帧尚未被渲染，跳过
        self._latest_frame = frame.copy()  # 立即复制，避免后台覆写
        self._frame_consumed = False

    def _render_frame(self):
        """定时器回调：在主线程渲染最新帧"""
        frame = self._latest_frame
        self._latest_frame = None
        self._frame_consumed = True

        if frame is None:
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        scaled = QPixmap.fromImage(qimg).scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(scaled)

    def clear_frame(self):
        """停止时清空画面"""
        self._latest_frame = None
        self._frame_consumed = True
        self.clear()
        self.setText("监控已停止")


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
        self.cameras = QLineEdit("0")
        self.threshold = QLineEdit("0.7")
        self.confidence_threshold = QLineEdit("0.7")
        self.frame_skip = QLineEdit("3")
        self.use_gpu = QCheckBox()
        self.use_gpu.setChecked(True)
        self.lock_cooldown = QLineEdit("30")
        self.notify_cooldown = QLineEdit("60")
        self.alert_sound = QCheckBox()
        self.alert_sound.setChecked(True)
        self.alert_tray = QCheckBox()
        self.alert_tray.setChecked(True)

        layout.addRow("模型路径:", self.model_path)
        layout.addRow("人脸目录:", self.known_faces_dir)
        layout.addRow("日志文件:", self.log_file)
        layout.addRow("摄像头ID(逗号分隔):", self.cameras)
        layout.addRow("识别阈值:", self.threshold)
        layout.addRow("置信度阈值:", self.confidence_threshold)
        layout.addRow("帧跳过数(性能优化):", self.frame_skip)
        layout.addRow("使用GPU加速:", self.use_gpu)
        layout.addRow("锁屏冷却(秒):", self.lock_cooldown)
        layout.addRow("通知冷却(秒):", self.notify_cooldown)
        layout.addRow("告警声音:", self.alert_sound)
        layout.addRow("托盘通知:", self.alert_tray)

        # --- 邮件通知配置（可折叠） ---
        self.email_group = QGroupBox("邮件通知")
        self.email_group.setCheckable(True)
        self.email_group.setChecked(False)
        email_layout = QFormLayout()

        self.email_smtp_server = QLineEdit()
        self.email_smtp_port = QSpinBox()
        self.email_smtp_port.setRange(1, 65535)
        self.email_smtp_port.setValue(587)
        self.email_sender = QLineEdit()
        self.email_password = QLineEdit()
        self.email_password.setEchoMode(QLineEdit.Password)
        self.email_receiver = QLineEdit()
        self.email_use_ssl = QCheckBox()

        email_layout.addRow("SMTP服务器:", self.email_smtp_server)
        email_layout.addRow("SMTP端口:", self.email_smtp_port)
        email_layout.addRow("发件人邮箱:", self.email_sender)
        email_layout.addRow("邮箱密码:", self.email_password)
        email_layout.addRow("收件人邮箱:", self.email_receiver)
        email_layout.addRow("使用SSL:", self.email_use_ssl)
        self.email_group.setLayout(email_layout)

        layout.addRow(self.email_group)

        # --- 特性开关配置（可折叠） ---
        self.features_group = QGroupBox("扩展特性")
        self.features_group.setCheckable(True)
        self.features_group.setChecked(False)
        features_layout = QFormLayout()

        self.enable_shoulder_surfing = QCheckBox()
        self.enable_intruder_capture = QCheckBox()
        self.enable_pomodoro = QCheckBox()
        self.enable_mqtt = QCheckBox()
        self.enable_drowsiness = QCheckBox()

        self.intruder_save_dir = QLineEdit("intruder_photos")
        self.pomodoro_focus_minutes = QSpinBox()
        self.pomodoro_focus_minutes.setRange(1, 120)
        self.pomodoro_focus_minutes.setValue(25)
        self.pomodoro_break_minutes = QSpinBox()
        self.pomodoro_break_minutes.setRange(1, 60)
        self.pomodoro_break_minutes.setValue(5)
        self.mqtt_broker = QLineEdit()
        self.mqtt_port = QSpinBox()
        self.mqtt_port.setRange(1, 65535)
        self.mqtt_port.setValue(1883)
        self.mqtt_topic_prefix = QLineEdit("boss_sentinel")
        self.drowsiness_ear_threshold = QLineEdit("0.2")

        features_layout.addRow("防偷窥检测:", self.enable_shoulder_surfing)
        features_layout.addRow("入侵者拍照:", self.enable_intruder_capture)
        features_layout.addRow("入侵照片目录:", self.intruder_save_dir)
        features_layout.addRow("番茄钟:", self.enable_pomodoro)
        features_layout.addRow("专注时长(分钟):", self.pomodoro_focus_minutes)
        features_layout.addRow("休息时长(分钟):", self.pomodoro_break_minutes)
        features_layout.addRow("MQTT桥接:", self.enable_mqtt)
        features_layout.addRow("MQTT服务器:", self.mqtt_broker)
        features_layout.addRow("MQTT端口:", self.mqtt_port)
        features_layout.addRow("MQTT主题前缀:", self.mqtt_topic_prefix)
        features_layout.addRow("疲劳检测:", self.enable_drowsiness)
        features_layout.addRow("EAR阈值:", self.drowsiness_ear_threshold)

        self.features_group.setLayout(features_layout)

        layout.addRow(self.features_group)

        self.setLayout(layout)

    def validate(self) -> bool:
        """验证配置输入，失败时弹出警告"""
        errors = []
        try:
            t = float(self.threshold.text())
            if not (0.0 <= t <= 1.0):
                errors.append("识别阈值必须在 0.0 ~ 1.0 之间")
        except ValueError:
            errors.append("识别阈值必须为数字")

        try:
            c = float(self.confidence_threshold.text())
            if not (0.0 <= c <= 1.0):
                errors.append("置信度阈值必须在 0.0 ~ 1.0 之间")
        except ValueError:
            errors.append("置信度阈值必须为数字")

        try:
            fs = int(self.frame_skip.text())
            if fs < 1:
                errors.append("帧跳过数必须 >= 1")
        except ValueError:
            errors.append("帧跳过数必须为整数")

        cam_text = self.cameras.text().strip()
        if not cam_text:
            errors.append("摄像头ID不能为空")
        else:
            try:
                [int(x.strip()) for x in cam_text.split(",") if x.strip()]
            except ValueError:
                errors.append("摄像头ID必须为逗号分隔的整数")

        if errors:
            QMessageBox.warning(
                None, "配置验证失败",
                "以下配置项有误，请修正后重试：\n\n" + "\n".join(f"  - {e}" for e in errors)
            )
            return False
        return True

    def get_config(self) -> SentinelConfig:
        """获取配置 - 返回 SentinelConfig 对象"""
        email_cfg = None
        if self.email_group.isChecked() and self.email_sender.text().strip():
            from .config import EmailConfig
            email_cfg = EmailConfig(
                sender=self.email_sender.text().strip(),
                receiver=self.email_receiver.text().strip(),
                smtp_server=self.email_smtp_server.text().strip(),
                smtp_port=self.email_smtp_port.value(),
                username=self.email_sender.text().strip(),
                password=self.email_password.text(),
                use_ssl=self.email_use_ssl.isChecked(),
            )

        return SentinelConfig(
            model_path=self.model_path.text(),
            known_faces_dir=self.known_faces_dir.text(),
            log_file=self.log_file.text(),
            cameras=[int(cam.strip()) for cam in self.cameras.text().split(",") if cam.strip()],
            threshold=float(self.threshold.text()),
            confidence_threshold=float(self.confidence_threshold.text()),
            frame_skip=int(self.frame_skip.text()),
            use_gpu=self.use_gpu.isChecked(),
            lock_cooldown=int(self.lock_cooldown.text()),
            notify_cooldown=int(self.notify_cooldown.text()),
            alert_sound=self.alert_sound.isChecked(),
            alert_tray=self.alert_tray.isChecked(),
            notification_email=email_cfg,
            enable_shoulder_surfing=self.enable_shoulder_surfing.isChecked(),
            enable_intruder_capture=self.enable_intruder_capture.isChecked(),
            enable_pomodoro=self.enable_pomodoro.isChecked(),
            enable_mqtt=self.enable_mqtt.isChecked(),
            enable_drowsiness=self.enable_drowsiness.isChecked(),
            intruder_save_dir=self.intruder_save_dir.text(),
            pomodoro_focus_minutes=self.pomodoro_focus_minutes.value(),
            pomodoro_break_minutes=self.pomodoro_break_minutes.value(),
            mqtt_broker=self.mqtt_broker.text(),
            mqtt_port=self.mqtt_port.value(),
            mqtt_topic_prefix=self.mqtt_topic_prefix.text(),
            drowsiness_ear_threshold=float(self.drowsiness_ear_threshold.text()),
        )

    def load_config(self, config_dict: dict):
        """加载配置到UI"""
        self.model_path.setText(config_dict.get('model_path', 'yolov8n-face.pt'))
        self.known_faces_dir.setText(config_dict.get('known_faces_dir', 'known_faces'))
        self.log_file.setText(config_dict.get('log_file', 'sentinel_log.txt'))
        self.cameras.setText(','.join(map(str, config_dict.get('cameras', [0]))))
        self.threshold.setText(str(config_dict.get('threshold', 0.7)))
        self.confidence_threshold.setText(str(config_dict.get('confidence_threshold', 0.7)))
        self.frame_skip.setText(str(config_dict.get('frame_skip', 3)))
        self.use_gpu.setChecked(config_dict.get('use_gpu', True))
        self.lock_cooldown.setText(str(config_dict.get('lock_cooldown', 30)))
        self.notify_cooldown.setText(str(config_dict.get('notify_cooldown', 60)))
        self.alert_sound.setChecked(config_dict.get('alert_sound', True))
        self.alert_tray.setChecked(config_dict.get('alert_tray', True))
        # 邮件配置
        email = config_dict.get('notification_email')
        if email and isinstance(email, dict):
            self.email_group.setChecked(True)
            self.email_smtp_server.setText(email.get('smtp_server', ''))
            self.email_smtp_port.setValue(email.get('smtp_port', 587))
            self.email_sender.setText(email.get('sender', ''))
            self.email_password.setText(email.get('password', ''))
            self.email_receiver.setText(email.get('receiver', ''))
            self.email_use_ssl.setChecked(email.get('use_ssl', False))
        # 扩展特性配置
        if any(config_dict.get(k) for k in (
            'enable_shoulder_surfing', 'enable_intruder_capture',
            'enable_pomodoro', 'enable_mqtt', 'enable_drowsiness'
        )):
            self.features_group.setChecked(True)
        self.enable_shoulder_surfing.setChecked(config_dict.get('enable_shoulder_surfing', False))
        self.enable_intruder_capture.setChecked(config_dict.get('enable_intruder_capture', False))
        self.intruder_save_dir.setText(config_dict.get('intruder_save_dir', 'intruder_photos'))
        self.enable_pomodoro.setChecked(config_dict.get('enable_pomodoro', False))
        self.pomodoro_focus_minutes.setValue(config_dict.get('pomodoro_focus_minutes', 25))
        self.pomodoro_break_minutes.setValue(config_dict.get('pomodoro_break_minutes', 5))
        self.enable_mqtt.setChecked(config_dict.get('enable_mqtt', False))
        self.mqtt_broker.setText(config_dict.get('mqtt_broker', ''))
        self.mqtt_port.setValue(config_dict.get('mqtt_port', 1883))
        self.mqtt_topic_prefix.setText(config_dict.get('mqtt_topic_prefix', 'boss_sentinel'))
        self.enable_drowsiness.setChecked(config_dict.get('enable_drowsiness', False))
        self.drowsiness_ear_threshold.setText(str(config_dict.get('drowsiness_ear_threshold', 0.2)))


class MainWindow(QMainWindow):
    """主窗口 - 支持系统托盘"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Boss哨兵系统")
        self.resize(720, 800)
        self._is_monitoring = False
        self._current_config: SentinelConfig = None  # 启动时缓存的配置
        self.init_ui()
        self.init_tray()

    def init_ui(self):
        """初始化UI"""
        # 主布局
        main_widget = QWidget()
        layout = QVBoxLayout()

        # 配置组
        self.config_group = ConfigGroup()
        self.config_group.setCheckable(True)
        self.config_group.setChecked(False)  # 默认折叠
        self.config_group.setTitle("配置 (点击展开)")
        layout.addWidget(self.config_group)

        # 视频预览
        self.video_widget = VideoWidget()
        layout.addWidget(self.video_widget)

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

        # Feature status indicators
        self.pomodoro_label = QLabel("")
        self.pomodoro_label.setStyleSheet("color: #2196F3; font-size: 11px;")
        self.pomodoro_label.setVisible(False)
        status_layout.addWidget(self.pomodoro_label)

        self.drowsiness_label = QLabel("")
        self.drowsiness_label.setStyleSheet("font-size: 11px;")
        self.drowsiness_label.setVisible(False)
        status_layout.addWidget(self.drowsiness_label)

        self.shoulder_surfing_label = QLabel("")
        self.shoulder_surfing_label.setStyleSheet("font-size: 11px;")
        self.shoulder_surfing_label.setVisible(False)
        status_layout.addWidget(self.shoulder_surfing_label)

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
        """关闭事件 - 监控运行中需确认；否则最小化到托盘"""
        if self.sentinel_thread and self._is_monitoring:
            reply = QMessageBox.question(
                self, "确认退出",
                "监控正在运行中，停止监控并退出？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return

            # 停止线程并等待
            self._stop_sentinel_async()
            self._pending_close = True
            event.ignore()

            # 5秒超时定时器：强制退出
            self._close_timeout_timer = QTimer(self)
            self._close_timeout_timer.setSingleShot(True)
            self._close_timeout_timer.timeout.connect(self._force_close)
            self._close_timeout_timer.start(5000)
            return

        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Boss哨兵系统",
            "程序已最小化到系统托盘，双击图标可恢复窗口",
            QSystemTrayIcon.Information,
            2000
        )

    def _stop_sentinel_async(self):
        """异步停止哨兵线程（不阻塞UI）"""
        if self.sentinel_thread:
            self.status_label.setText("状态: 正在停止...")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.sentinel_thread.stop()

    def _force_close(self):
        """超时后强制退出"""
        self._do_close()

    def _do_close(self):
        """真正关闭窗口并退出"""
        self.tray_icon.hide()
        QApplication.quit()

    def quit_app(self):
        """退出应用"""
        if self.sentinel_thread and self._is_monitoring:
            self._pending_close = True
            self._stop_sentinel_async()
            # 5秒超时强制退出
            self._close_timeout_timer = QTimer(self)
            self._close_timeout_timer.setSingleShot(True)
            self._close_timeout_timer.timeout.connect(self._force_close)
            self._close_timeout_timer.start(5000)
            return
        self._do_close()

    def start_sentinel(self):
        """启动哨兵"""
        # 防止重复启动
        if self.sentinel_thread and self.sentinel_thread.isRunning():
            return

        # 输入验证
        if not self.config_group.validate():
            return

        config = self.config_group.get_config()
        self._current_config = config  # 缓存配置，告警时直接使用

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
        self.sentinel_thread.frame_signal.connect(self.video_widget.update_frame)
        self.sentinel_thread.feature_signal.connect(self._update_feature_status)
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
        self.update_log(f"错误: {error_msg}")
        self.tray_icon.showMessage("启动失败", error_msg, QSystemTrayIcon.Critical, 3000)
        self._is_monitoring = False
        self._current_config = None
        self.update_ui_state("error")

    def on_init_finished(self):
        """线程结束 — 统一的状态清理入口"""
        if self.progress_dialog:
            self.progress_dialog.close()

        self._is_monitoring = False
        self._current_config = None
        self.status_label.setText("状态: 已停止")
        self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.update_log("哨兵系统已停止")
        self.video_widget.clear_frame()
        self.update_ui_state("stopped")

        # Reset feature status indicators
        self.pomodoro_label.setVisible(False)
        self.pomodoro_label.setText("")
        self.drowsiness_label.setVisible(False)
        self.drowsiness_label.setText("")
        self.shoulder_surfing_label.setVisible(False)
        self.shoulder_surfing_label.setText("")

        # 如果有 pending close 请求，现在执行关闭
        if getattr(self, '_pending_close', False):
            self._pending_close = False
            if hasattr(self, '_close_timeout_timer'):
                self._close_timeout_timer.stop()
            self._do_close()

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
            self._current_config = None
            self.update_ui_state("stopped")
        elif status == "error":
            self.status_label.setText("状态: 错误")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self._is_monitoring = False
            self._current_config = None
            self.update_ui_state("error")

    def _update_feature_status(self, feature_data: dict):
        """Update feature status indicators from monitor feature data."""
        # Pomodoro status
        pomo = feature_data.get('pomodoro')
        if pomo:
            state = pomo.get('state', 'idle')
            remaining = pomo.get('remaining_seconds', 0)
            completed = pomo.get('completed_pomodoros', 0)
            mins, secs = divmod(int(remaining), 60)
            self.pomodoro_label.setText(
                f"Pomodoro: {state} {mins:02d}:{secs:02d} ({completed} done)"
            )
            self.pomodoro_label.setVisible(True)
        else:
            self.pomodoro_label.setVisible(False)

        # Drowsiness status
        drow = feature_data.get('drowsiness')
        if drow:
            level = drow.get('alert_level', 'normal')
            ear = drow.get('ear_value', -1.0)
            blink = drow.get('blink_rate', 0.0)
            color_map = {'normal': 'green', 'drowsy': 'orange', 'critical': 'red'}
            color = color_map.get(level, 'gray')
            self.drowsiness_label.setStyleSheet(f"color: {color}; font-size: 11px;")
            ear_str = f"{ear:.2f}" if ear >= 0 else "N/A"
            self.drowsiness_label.setText(f"Drowsiness: {level} (EAR:{ear_str} Blink:{blink:.0f}/min)")
            self.drowsiness_label.setVisible(True)
        else:
            self.drowsiness_label.setVisible(False)

        # Shoulder surfing status
        ss = feature_data.get('shoulder_surfing')
        if ss:
            vuln = ss.get('is_vulnerable', False)
            total = ss.get('total_faces', 0)
            unauth = ss.get('unauthorized_count', 0)
            if vuln:
                self.shoulder_surfing_label.setStyleSheet("color: red; font-size: 11px;")
                self.shoulder_surfing_label.setText(f"SHOULDER SURFING: {unauth} unauthorized / {total} total")
            else:
                self.shoulder_surfing_label.setStyleSheet("color: green; font-size: 11px;")
                self.shoulder_surfing_label.setText(f"Privacy: OK ({total} face(s))")
            self.shoulder_surfing_label.setVisible(True)
        else:
            self.shoulder_surfing_label.setVisible(False)

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
        """停止哨兵 — 信号驱动，不手动更新状态"""
        if self.sentinel_thread:
            self.status_label.setText("状态: 正在停止...")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.sentinel_thread.stop()
            # 不再手动设置 self._is_monitoring / status_label / update_ui_state
            # 所有状态变更由 SentinelThread.finished → on_init_finished 处理

    def update_log(self, message):
        """更新日志 — 超过 500 行时删除最旧的 50 行"""
        self.log_display.append(message)

        # 日志行数限制
        if self.log_display.document().blockCount() > 500:
            cursor = self.log_display.textCursor()
            cursor.movePosition(cursor.Start)
            for _ in range(50):
                cursor.movePosition(cursor.Down, cursor.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除剩余的换行符

        # 从消息中提取人名并触发告警
        if "检测到目标人物" in message:
            person_name = message.replace("检测到目标人物: ", "").strip()
            self._trigger_alerts(person_name)

    def _trigger_alerts(self, person_name: str):
        """触发告警 — 使用启动时缓存的配置"""
        config = self._current_config
        if config is None:
            return

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
