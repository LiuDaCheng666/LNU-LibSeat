import smtplib
from email.header import Header
from email.mime.text import MIMEText

from core.logger import get_logger

logger = get_logger(__name__)


def _get_smtp_creds():
    """延迟读取 SMTP 配置。"""
    import config as _cfg

    user = getattr(_cfg, "SMTP_USER", "") or "lnu_library@163.com"
    pwd = getattr(_cfg, "SMTP_PASS", "") or "LWQWA366dd2g6msK"
    return user, pwd


def build_success_email(account: str, room: str, seat: str, start_time: str, end_time: str):
    """Build the success-email subject/body used by the main booking flow."""
    subject = f"🎉 预约成功｜座位 {seat} @ {room}"
    body = "\n".join(
        [
            "🎉 预约成功",
            "",
            "你的图书馆座位已经锁定啦。",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"👤 预约账号：{account}",
            f"🏫 目标场馆：{room}",
            f"💺 锁定座位：{seat}",
            f"⏰ 预约时段：{start_time} - {end_time}",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "📌 温馨提醒：请按时到馆签到。",
            "📚 祝你学习顺利，效率拉满。",
        ]
    )
    return subject, body


def _smtp_server_for_user(user: str) -> str:
    user = (user or "").lower()
    if "163.com" in user:
        return "smtp.163.com"
    if "126.com" in user:
        return "smtp.126.com"
    return "smtp.qq.com"


def send_email(title: str, content: str = "") -> bool:
    """
    发送纯文本邮件通知。
    发件人：项目内置邮箱；收件人：config.py 中的 RECEIVER_EMAIL。
    """
    import config as _cfg

    smtp_user, smtp_pass = _get_smtp_creds()
    receiver = (getattr(_cfg, "RECEIVER_EMAIL", "") or "").strip()

    if not receiver:
        logger.info("未配置收件邮箱，跳过邮件发送")
        return False

    if not smtp_user or not smtp_pass:
        logger.warning("SMTP credentials not configured; Email disabled")
        return False

    smtp_server = _smtp_server_for_user(smtp_user)

    message = MIMEText(content or "", "plain", "utf-8")
    message["From"] = f"LNU_Assistant <{smtp_user}>"
    message["To"] = receiver
    message["Subject"] = Header(title or "LNU-LibSeat 通知", "utf-8")

    try:
        with smtplib.SMTP_SSL(smtp_server, 465, timeout=10) as smtp_obj:
            smtp_obj.login(smtp_user, smtp_pass)
            smtp_obj.sendmail(smtp_user, [receiver], message.as_string())
        logger.info("邮件已发送至 %s", receiver)
        return True
    except smtplib.SMTPException as e:
        logger.exception("Failed to send Email (SMTP Error): %s", e)
        return False
    except Exception as e:
        logger.exception("Failed to send Email (Unknown Error): %s", e)
        return False
