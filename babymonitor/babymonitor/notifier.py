# notifier.py
import json
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

CONFIG_PATH = Path("config/settings.json")


def load_email_config():
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    return cfg.get("email", {})


def send_email_alert(subject: str, body: str):
    email_cfg = load_email_config()
    if not email_cfg.get("enabled", False):
        print("[Notifier] Email sending disabled in config.")
        return

    sender = email_cfg["sender_email"]
    password = email_cfg["sender_password"]
    receiver = email_cfg["receiver_email"]
    smtp_server = email_cfg["smtp_server"]
    smtp_port = email_cfg["smtp_port"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        print("[Notifier] Email sent.")
    except Exception as e:
        print("[Notifier] Failed to send email:", e)
