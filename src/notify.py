"""Push notifications via NTFY and/or Apprise."""

import os
import requests
import apprise
from dotenv import load_dotenv

load_dotenv()


def send_notification(
    title: str,
    message: str,
    priority: int = None,
    markdown: bool = False,
    attach_url: str = None,
) -> bool:
    priority = priority or int(os.getenv("NOTIFY_PRIORITY", "5"))
    sent_any = False

    # Native NTFY
    ntfy_url = os.getenv("NTFY_URL")
    ntfy_topic = os.getenv("NTFY_TOPIC")

    if ntfy_url and ntfy_topic:
        endpoint = f"{ntfy_url.rstrip('/')}/{ntfy_topic}"
        headers = {
            "Title": title,
            "X-Priority": str(priority),
            "Tags": "rotating_light",
        }
        if markdown:
            headers["Markdown"] = "yes"
        if attach_url:
            headers["X-Attach"] = attach_url
        try:
            resp = requests.post(
                endpoint,
                data=message.encode("utf-8"),
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            print(f"Notification sent (NTFY): {title}")
            if attach_url:
                print(f"  Attached: {attach_url}")
            sent_any = True
        except requests.RequestException as e:
            print(f"NTFY notification failed: {e}")

    # Apprise
    apprise_urls = os.getenv("APPRISE_URLS")
    if apprise_urls:
        app = apprise.Apprise()
        for url in [u.strip() for u in apprise_urls.split(",") if u.strip()]:
            app.add(url)

        if app:
            try:
                result = app.send(title=title, body=message, priority=priority)
                if result:
                    print(f"Notification sent (Apprise): {title}")
                    sent_any = True
                else:
                    print(f"Apprise notification failed: {title}")
            except Exception as e:
                print(f"Apprise notification error: {e}")

    if not sent_any:
        print("Warning: No notification service configured")

    return sent_any
