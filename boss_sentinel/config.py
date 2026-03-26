import os
import json
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

@dataclass
class EmailConfig:
    """邮件通知配置"""
    sender: str
    receiver: str
    smtp_server: str
    smtp_port: int
    username: str
    password: str

@dataclass
class SentinelConfig:
    """哨兵系统配置"""
    known_faces_dir: str = "known_faces"
    model_path: str = "yolov8n-face.pt"
    detection_interval: int = 1
    threshold: float = 0.7
    confidence_threshold: float = 0.7
    show_feed: bool = True
    cameras: List[int] = field(default_factory=lambda: [0])
    log_file: str = "sentinel_log.txt"
    notification_email: Optional[EmailConfig] = None
    # 性能优化配置
    frame_skip: int = 3  # 帧跳过数，每N帧处理一次
    use_gpu: bool = True  # 是否使用GPU加速

    def __post_init__(self):
        """配置验证"""
        if self.cameras is None:
            self.cameras = [0]

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
                self._last_mtime = current_mtime
                new_config = self._load_from_file()
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


def load_config(config_dict: Dict[str, Any]) -> SentinelConfig:
    """从字典加载配置"""
    email_config = None
    if config_dict.get('notification_email'):
        email_config = EmailConfig(**config_dict['notification_email'])

    return SentinelConfig(
        known_faces_dir=config_dict.get('known_faces_dir'),
        model_path=config_dict.get('model_path'),
        detection_interval=config_dict.get('detection_interval'),
        threshold=config_dict.get('threshold'),
        confidence_threshold=config_dict.get('confidence_threshold'),
        show_feed=config_dict.get('show_feed'),
        cameras=config_dict.get('cameras'),
        log_file=config_dict.get('log_file'),
        notification_email=email_config,
        frame_skip=config_dict.get('frame_skip', 3),
        use_gpu=config_dict.get('use_gpu', True)
    )


def save_config(config: SentinelConfig, file_path: str) -> None:
    """保存配置到文件"""
    config_dict = {
        'known_faces_dir': config.known_faces_dir,
        'model_path': config.model_path,
        'detection_interval': config.detection_interval,
        'threshold': config.threshold,
        'confidence_threshold': config.confidence_threshold,
        'show_feed': config.show_feed,
        'cameras': config.cameras,
        'log_file': config.log_file,
        'frame_skip': config.frame_skip,
        'use_gpu': config.use_gpu
    }

    if config.notification_email:
        config_dict['notification_email'] = {
            'sender': config.notification_email.sender,
            'receiver': config.notification_email.receiver,
            'smtp_server': config.notification_email.smtp_server,
            'smtp_port': config.notification_email.smtp_port,
            'username': config.notification_email.username,
            'password': config.notification_email.password
        }

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=4, ensure_ascii=False)