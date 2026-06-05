import os
import json
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import dataclasses

@dataclass
class EmailConfig:
    """邮件通知配置"""
    sender: str
    receiver: str
    smtp_server: str
    smtp_port: int
    username: str
    password: str
    use_ssl: bool = False

@dataclass
class SentinelConfig:
    """哨兵系统配置"""
    known_faces_dir: str = "known_faces"
    model_path: str = "yolov8n-face.pt"
    threshold: float = 0.7
    confidence_threshold: float = 0.7
    show_feed: bool = True
    cameras: List[int] = field(default_factory=lambda: [0])
    log_file: str = "sentinel_log.txt"
    notification_email: Optional[EmailConfig] = None
    # 性能优化配置
    frame_skip: int = 3  # 帧跳过数，每N帧处理一次
    use_gpu: bool = True  # 是否使用GPU加速
    lock_cooldown: int = 30  # 锁屏后冷却秒数，冷却期内不重复锁屏
    notify_cooldown: int = 60  # 同一人通知冷却秒数
    alert_sound: bool = True    # 是否播放告警声音
    alert_tray: bool = True     # 是否显示托盘通知
    # 新增配置
    target_names: List[str] = field(default_factory=list)
    tracker_max_disappeared: int = 30
    away_timeout: float = 30.0
    enable_shoulder_surfing: bool = False
    enable_intruder_capture: bool = False
    enable_pomodoro: bool = False
    enable_mqtt: bool = False
    enable_drowsiness: bool = False
    mqtt_broker: str = ''
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = 'boss_sentinel'
    pomodoro_focus_minutes: int = 25
    pomodoro_break_minutes: int = 5
    intruder_save_dir: str = 'intruder_photos'
    drowsiness_ear_threshold: float = 0.2
    enable_head_pose: bool = False  # 头部姿态估计（替代疲劳检测，YOLOv8 精度可用）
    head_pose_alert_threshold: float = 30.0  # 头部偏转角度阈值（度）
    roles: Dict[str, List[str]] = field(default_factory=lambda: {"owner": [], "boss": []})
    enable_lock: bool = True  # 是否在检测到目标时执行锁屏（前端可动态切换）

    def __post_init__(self):
        """配置验证"""
        if self.cameras is None:
            self.cameras = [0]

        if not isinstance(self.threshold, (int, float)) or not (0.0 <= float(self.threshold) <= 1.0):
            raise ValueError(f"threshold must be a float between 0.0 and 1.0, got {self.threshold!r}")
        if not isinstance(self.confidence_threshold, (int, float)) or not (0.0 <= float(self.confidence_threshold) <= 1.0):
            raise ValueError(f"confidence_threshold must be a float between 0.0 and 1.0, got {self.confidence_threshold!r}")
        if not isinstance(self.frame_skip, int) or self.frame_skip < 1:
            raise ValueError(f"frame_skip must be an int >= 1, got {self.frame_skip!r}")
        if not isinstance(self.lock_cooldown, (int, float)) or self.lock_cooldown < 0:
            raise ValueError(f"lock_cooldown must be a number >= 0, got {self.lock_cooldown!r}")
        if not isinstance(self.notify_cooldown, (int, float)) or self.notify_cooldown < 0:
            raise ValueError(f"notify_cooldown must be a number >= 0, got {self.notify_cooldown!r}")

        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir, exist_ok=True)


class ConfigWatcher:
    """配置文件监控器 - 支持热重载"""

    def __init__(self, config_path: str, on_change: Optional[Callable[[SentinelConfig], None]] = None):
        """
        初始化配置监控器

        参数:
            config_path: 配置文件路径
            on_change: 配置变化时的回调函数
        """
        self.config_path = config_path
        self.on_change = on_change
        self._last_mtime: float = 0
        self._last_check: float = 0
        self._check_interval: float = 2.0  # 每2秒检查一次
        self._current_config: Optional[SentinelConfig] = None

        if os.path.exists(config_path):
            self._last_mtime = os.path.getmtime(config_path)
            self._current_config = self._load_from_file()

    def _load_from_file(self) -> SentinelConfig:
        """从文件加载配置"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
        return load_config(config_dict)

    def check_for_changes(self) -> Optional[SentinelConfig]:
        """
        检查配置文件是否有变化

        返回:
            如果配置有变化，返回新的配置对象；否则返回 None
        """
        current_time = time.time()

        # 限制检查频率
        if current_time - self._last_check < self._check_interval:
            return None

        self._last_check = current_time

        if not os.path.exists(self.config_path):
            return None

        try:
            current_mtime = os.path.getmtime(self.config_path)
            if current_mtime > self._last_mtime:
                new_config = self._load_from_file()
                self._last_mtime = current_mtime
                self._current_config = new_config

                if self.on_change:
                    self.on_change(new_config)

                return new_config
        except Exception as e:
            print(f"配置文件读取错误: {e}")

        return None

    @property
    def current_config(self) -> Optional[SentinelConfig]:
        """获取当前配置"""
        return self._current_config


def load_config(config_dict) -> SentinelConfig:
    """从字典或文件路径加载配置

    Args:
        config_dict: 配置字典或 JSON 文件路径字符串
    """
    # 支持传入文件路径字符串
    if isinstance(config_dict, str):
        with open(config_dict, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)

    email_config = None
    if config_dict.get('notification_email'):
        email_data = {k: v for k, v in config_dict['notification_email'].items() if v is not None}
        email_config = EmailConfig(**email_data)

    # Filter None values and unknown keys from config dict
    valid_fields = set(SentinelConfig.__dataclass_fields__.keys())
    config_dict = {k: v for k, v in config_dict.items() if v is not None and k in valid_fields}

    # Merge with field defaults for missing keys
    defaults = {f.name: f.default for f in SentinelConfig.__dataclass_fields__.values() if f.default is not dataclasses.MISSING}
    defaults_factory = {f.name: f.default_factory() for f in SentinelConfig.__dataclass_fields__.values() if f.default_factory is not dataclasses.MISSING}
    merged = {**defaults, **defaults_factory, **config_dict, 'notification_email': email_config}

    return SentinelConfig(**merged)


def save_config(config: SentinelConfig, file_path: str) -> None:
    """保存配置到文件"""
    config_dict = {
        'known_faces_dir': config.known_faces_dir,
        'model_path': config.model_path,
        'threshold': config.threshold,
        'confidence_threshold': config.confidence_threshold,
        'show_feed': config.show_feed,
        'cameras': config.cameras,
        'log_file': config.log_file,
        'frame_skip': config.frame_skip,
        'use_gpu': config.use_gpu,
        'lock_cooldown': config.lock_cooldown,
        'notify_cooldown': config.notify_cooldown,
        'alert_sound': config.alert_sound,
        'alert_tray': config.alert_tray,
        'target_names': config.target_names,
        'tracker_max_disappeared': config.tracker_max_disappeared,
        'away_timeout': config.away_timeout,
        'enable_shoulder_surfing': config.enable_shoulder_surfing,
        'enable_intruder_capture': config.enable_intruder_capture,
        'enable_pomodoro': config.enable_pomodoro,
        'enable_mqtt': config.enable_mqtt,
        'enable_drowsiness': config.enable_drowsiness,
        'mqtt_broker': config.mqtt_broker,
        'mqtt_port': config.mqtt_port,
        'mqtt_topic_prefix': config.mqtt_topic_prefix,
        'pomodoro_focus_minutes': config.pomodoro_focus_minutes,
        'pomodoro_break_minutes': config.pomodoro_break_minutes,
        'intruder_save_dir': config.intruder_save_dir,
        'drowsiness_ear_threshold': config.drowsiness_ear_threshold,
        'enable_head_pose': config.enable_head_pose,
        'head_pose_alert_threshold': config.head_pose_alert_threshold,
        'roles': config.roles,
        'enable_lock': config.enable_lock
    }

    if config.notification_email:
        config_dict['notification_email'] = {
            'sender': config.notification_email.sender,
            'receiver': config.notification_email.receiver,
            'smtp_server': config.notification_email.smtp_server,
            'smtp_port': config.notification_email.smtp_port,
            'username': config.notification_email.username,
            'password': config.notification_email.password,
            'use_ssl': config.notification_email.use_ssl
        }

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=4, ensure_ascii=False)