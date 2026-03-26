"""
Boss Sentinel 主入口模块

注意: BossSentinel 类已废弃，请直接使用 SentinelMonitor。
此模块保留仅为向后兼容。
"""
import warnings

# 废弃警告
warnings.warn(
    "BossSentinel 类已废弃，请使用 SentinelMonitor。"
    "参见 monitor.py 和 config.py 获取新接口。",
    DeprecationWarning,
    stacklevel=2
)


class BossSentinel:
    """
    [已废弃] 请使用 SentinelMonitor 替代

    此类保留仅为向后兼容，内部委托给 SentinelMonitor 实现。
    """

    def __init__(self, config_path="config.json", lazy_load=True):
        """
        初始化哨兵系统（已废弃）

        参数:
            config_path: 配置文件路径
            lazy_load: 是否延迟加载模型
        """
        import json
        from .monitor import SentinelMonitor
        from .config import SentinelConfig, load_config

        # 加载配置
        with open(config_path) as f:
            config_dict = json.load(f)
        self.config_dict = config_dict
        self._config_obj: SentinelConfig = load_config(config_dict)

        # 委托给 SentinelMonitor
        self._monitor = SentinelMonitor(self._config_obj, lazy_load=lazy_load)
        self._models_loaded = self._monitor._models_loaded

    def initialize_models(self):
        """初始化模型（已废弃）"""
        self._monitor.initialize_models()
        self._models_loaded = True

    def ensure_models_loaded(self):
        """确保模型已加载（已废弃）"""
        self._monitor.ensure_models_loaded()
        self._models_loaded = self._monitor._models_loaded

    def start_monitoring(self, callback=None):
        """启动监控（已废弃）"""
        self._monitor.run(callback=callback)

    def run(self):
        """运行（已废弃）"""
        self._monitor.run()

    # 保留旧的属性访问以保持兼容性
    @property
    def model(self):
        """兼容旧API: 获取YOLO模型"""
        return self._monitor.detector.model if self._monitor.detector else None

    @property
    def face_recognizer(self):
        """兼容旧API: 获取人脸识别器"""
        return self._monitor.recognizer

    @property
    def known_faces(self):
        """兼容旧API: 获取已知人脸特征"""
        return self._monitor.recognizer.known_embeddings if self._monitor.recognizer else None

    @property
    def config(self):
        """兼容旧API: 获取配置字典"""
        return self.config_dict

    @config.setter
    def config(self, value):
        """兼容旧API: 设置配置"""
        if isinstance(value, dict):
            self.config_dict = value
            from .config import load_config
            self._config_obj = load_config(value)
            self._monitor.config = self._config_obj


def main():
    """CLI入口点"""
    import argparse
    parser = argparse.ArgumentParser(description="Boss哨兵系统")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--gui", action="store_true", help="启动GUI界面")
    args = parser.parse_args()

    if args.gui:
        from .gui import run_gui
        run_gui()
    else:
        sentinel = BossSentinel(config_path=args.config)
        sentinel.run()


if __name__ == "__main__":
    main()
