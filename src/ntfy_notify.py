"""Push notifications via self-hosted ntfy server."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()


def send_notification(title: str, message: str, priority: str = "default") -> bool:
    url = os.getenv("NTFY_URL")
    topic = os.getenv("NTFY_TOPIC")
    if not url or not topic:
        print("Warning: NTFY_URL or NTFY_TOPIC not set in .env, skipping notification")
        return False

    endpoint = f"{url.rstrip('/')}/{topic}"
    try:
        resp = requests.post(
            endpoint,
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "rotating_light",
            },
            timeout=10,
        )
        resp.raise_for_status()
        print(f"Notification sent: {title}")
        return True
    except requests.RequestException as e:
        print(f"Failed to send notification: {e}")
        return False
