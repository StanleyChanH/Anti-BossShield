"""
Boss Sentinel CLI 入口模块
"""
import json
from .monitor import SentinelMonitor
from .config import SentinelConfig, load_config


def main():
    """CLI入口点"""
    import argparse
    parser = argparse.ArgumentParser(description="Boss哨兵系统")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--web", action="store_true", help="启动 Web UI 界面")
    parser.add_argument("--port", type=int, default=8970, help="Web UI 端口 (默认 8970)")
    args = parser.parse_args()

    if args.web:
        from .web.server import run_server
        run_server(port=args.port)
    else:
        with open(args.config, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
        config = load_config(config_dict)
        monitor = SentinelMonitor(config, config_path=args.config)
        monitor.run()


if __name__ == "__main__":
    main()
