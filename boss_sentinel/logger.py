from datetime import datetime
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
        log_dir = os.path.dirname(self.log_file)
        if log_dir:  # 只有非空时才创建目录
            os.makedirs(log_dir, exist_ok=True)
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