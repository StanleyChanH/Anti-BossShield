"""Email notification service for Boss Sentinel."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict

from .config import EmailConfig

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Email notification service.

    Supports both SMTP with STARTTLS (the default) and SMTP_SSL
    (when ``use_ssl`` is enabled in :class:`EmailConfig`).
    """

    def __init__(self, config: EmailConfig, timeout: int = 30) -> None:
        """Initialise the email notification service.

        Args:
            config: Email server configuration.
            timeout: Connection timeout in seconds (default 30).
        """
        self.config = config
        self.timeout = timeout

    def send(self, subject: str, body: str) -> bool:
        """Send an email notification.

        Args:
            subject: Email subject line.
            body: Plain-text email body.

        Returns:
            ``True`` if the email was sent successfully,
            ``False`` otherwise.
        """
        try:
            msg = MIMEMultipart()
            msg["From"] = self.config.sender
            msg["To"] = self.config.receiver
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain"))

            if self.config.use_ssl:
                logger.debug(
                    "Connecting to %s:%d via SMTP_SSL",
                    self.config.smtp_server,
                    self.config.smtp_port,
                )
                with smtplib.SMTP_SSL(
                    self.config.smtp_server,
                    self.config.smtp_port,
                    timeout=self.timeout,
                ) as server:
                    server.login(self.config.username, self.config.password)
                    server.send_message(msg)
            else:
                logger.debug(
                    "Connecting to %s:%d via SMTP+STARTTLS",
                    self.config.smtp_server,
                    self.config.smtp_port,
                )
                with smtplib.SMTP(
                    self.config.smtp_server,
                    self.config.smtp_port,
                    timeout=self.timeout,
                ) as server:
                    server.starttls()
                    server.login(self.config.username, self.config.password)
                    server.send_message(msg)

            logger.info("Email sent successfully to %s", self.config.receiver)
            return True
        except Exception as e:
            logger.error("Failed to send email: %s", e)
            return False


def create_detection_notification(
    person_name: str,
    similarity: float,
    camera_idx: int,
) -> Dict[str, str]:
    """Create a detection notification message.

    Args:
        person_name: Name of the detected person.
        similarity: Recognition similarity score (0.0 -- 1.0).
        camera_idx: Index of the camera that captured the detection.

    Returns:
        A dictionary with ``'subject'`` and ``'body'`` keys.
    """
    return {
        "subject": "哨兵系统检测到已知人物",
        "body": (
            f"哨兵系统检测到已知人物！\n"
            f"\n"
            f"详细信息:\n"
            f"- 人物名称: {person_name}\n"
            f"- 相似度: {similarity:.2%}\n"
            f"- 摄像头索引: {camera_idx}\n"
            f"- 检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        ),
    }
