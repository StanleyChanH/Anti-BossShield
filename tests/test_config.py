"""测试配置模块"""
import pytest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from boss_sentinel.config import SentinelConfig, EmailConfig, load_config, save_config
import json
import tempfile


class TestSentinelConfig:
    """测试SentinelConfig类"""

    def test_default_config(self):
        """测试默认配置"""
        config = SentinelConfig()
        assert config.known_faces_dir == "known_faces"
        assert config.model_path == "yolov8n-face.pt"
        assert config.detection_interval == 1
        assert config.threshold == 0.7
        assert config.confidence_threshold == 0.7
        assert config.show_feed == True
        assert config.cameras == [0]
        assert config.log_file == "sentinel_log.txt"
        assert config.frame_skip == 3
        assert config.use_gpu == True

    def test_custom_config(self):
        """测试自定义配置"""
        config = SentinelConfig(
            known_faces_dir="custom_faces",
            model_path="custom_model.pt",
            detection_interval=2,
            threshold=0.8,
            confidence_threshold=0.6,
            frame_skip=5,
            use_gpu=False
        )
        assert config.known_faces_dir == "custom_faces"
        assert config.model_path == "custom_model.pt"
        assert config.detection_interval == 2
        assert config.threshold == 0.8
        assert config.confidence_threshold == 0.6
        assert config.frame_skip == 5
        assert config.use_gpu == False

    def test_config_with_email(self):
        """测试带邮件通知的配置"""
        email_config = EmailConfig(
            sender="test@example.com",
            receiver="receiver@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            username="user",
            password="pass"
        )
        config = SentinelConfig(
            notification_email=email_config
        )
        assert config.notification_email is not None
        assert config.notification_email.sender == "test@example.com"


class TestConfigLoadSave:
    """测试配置加载和保存"""

    def test_load_config(self):
        """测试从字典加载配置"""
        config_dict = {
            'known_faces_dir': 'test_faces',
            'model_path': 'test_model.pt',
            'detection_interval': 3,
            'threshold': 0.9,
            'confidence_threshold': 0.8,
            'show_feed': False,
            'cameras': [0, 1],
            'log_file': 'test.log',
            'frame_skip': 5,
            'use_gpu': False
        }

        config = load_config(config_dict)
        assert config.known_faces_dir == 'test_faces'
        assert config.model_path == 'test_model.pt'
        assert config.detection_interval == 3
        assert config.frame_skip == 5
        assert config.use_gpu == False

    def test_save_and_load_config(self):
        """测试保存和加载配置"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            # 创建配置
            config = SentinelConfig(
                known_faces_dir="test_faces",
                frame_skip=7,
                use_gpu=True
            )

            # 保存配置
            save_config(config, temp_path)

            # 加载配置
            with open(temp_path, 'r') as f:
                loaded_dict = json.load(f)

            assert loaded_dict['known_faces_dir'] == "test_faces"
            assert loaded_dict['frame_skip'] == 7
            assert loaded_dict['use_gpu'] == True

        finally:
            # 清理
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_load_config_with_defaults(self):
        """测试加载配置时使用默认值"""
        config_dict = {
            'known_faces_dir': 'faces',
        }

        config = load_config(config_dict)
        assert config.known_faces_dir == 'faces'
        assert config.frame_skip == 3  # 默认值
        assert config.use_gpu == True  # 默认值
