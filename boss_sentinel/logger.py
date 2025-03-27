from datetime import datetime
from typing import Optional
import os

class SentinelLogger:
    """哨兵系统日志记录器"""
    
    def __init__(self, log_file: str = "sentinel_log.txt"):
        """
        初始化日志记录器
        
        参数:
            log_file: 日志文件路径
        """
        self.log_file = log_file
        self._init_log_file()
        
    def _init_log_file(self):
        """初始化日志文件"""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, 'a') as f:
            f.write(f"\n\n=== 哨兵系统启动 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            
    def log(self, message: str, print_console: bool = True):
        """
        记录日志
        
        参数:
            message: 日志消息
            print_console: 是否同时打印到控制台
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        
        if print_console:
            print(log_entry.strip())
            
        with open(self.log_file, 'a') as f:
            f.write(log_entry)
            
    def get_last_n_entries(self, n: int = 10) -> Optional[list[str]]:
        """
        获取最近的n条日志记录
        
        参数:
            n: 要获取的日志条目数
            
        返回:
            日志条目列表(从旧到新)或None(如果日志文件不存在)
        """
        if not os.path.exists(self.log_file):
            return None
            
        with open(self.log_file, 'r') as f:
            lines = f.readlines()
            
        return lines[-n:] if len(lines) >= n else lines