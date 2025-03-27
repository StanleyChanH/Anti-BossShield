import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Optional
from .config import EmailConfig

class EmailNotifier:
    """邮件通知服务"""
    
    def __init__(self, config: EmailConfig):
        """
        初始化邮件通知服务
        
        参数:
            config: 邮件配置
        """
        self.config = config
        
    def send(self, subject: str, body: str) -> bool:
        """
        发送邮件通知
        
        参数:
            subject: 邮件主题
            body: 邮件正文
            
        返回:
            是否发送成功
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.sender
            msg['To'] = self.config.receiver
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.username, self.config.password)
                server.send_message(msg)
                
            return True
        except Exception as e:
            print(f"发送邮件失败: {e}")
            return False

def create_detection_notification(person_name: str, similarity: float, camera_idx: int) -> Dict[str, str]:
    """创建检测通知内容"""
    return {
        'subject': "哨兵系统检测到已知人物",
        'body': f"""
哨兵系统检测到已知人物！

详细信息:
- 人物名称: {person_name}
- 相似度: {similarity:.2%}
- 摄像头索引: {camera_idx}
- 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    }