import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

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
    cameras: List[int] = None
    log_file: str = "sentinel_log.txt"
    notification_email: Optional[EmailConfig] = None

    def __post_init__(self):
        """配置验证"""
        if self.cameras is None:
            self.cameras = [0]
        
        if not os.path.exists(self.known_faces_dir):
            os.makedirs(self.known_faces_dir, exist_ok=True)

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
        notification_email=email_config
    )

def save_config(config: SentinelConfig, file_path: str) -> None:
    """保存配置到文件"""
    import json
    config_dict = {
        'known_faces_dir': config.known_faces_dir,
        'model_path': config.model_path,
        'detection_interval': config.detection_interval,
        'threshold': config.threshold,
        'confidence_threshold': config.confidence_threshold,
        'show_feed': config.show_feed,
        'cameras': config.cameras,
        'log_file': config.log_file
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
    
    with open(file_path, 'w') as f:
        json.dump(config_dict, f, indent=4)