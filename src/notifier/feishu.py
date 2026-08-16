"""飞书自定义机器人通知（扩展，默认关闭，需在 config 中开启）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import requests

from .base import Notifier


class FeishuNotifier(Notifier):
    def __init__(self, webhook: str, secret: str = ""):
        self.webhook = webhook
        self.secret = secret

    def _sign(self, timestamp: str) -> str:
        if not self.secret:
            return ""
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(self.secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def send_text(self, text: str) -> bool:
        timestamp = str(int(time.time()))
        payload: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
        if self.secret:
            payload["timestamp"] = timestamp
            payload["sign"] = self._sign(timestamp)
        try:
            r = requests.post(self.webhook, json=payload, timeout=10)
            return r.status_code == 200 and r.json().get("code") == 0
        except Exception as e:
            print(f"[feishu] 发送失败：{e}")
            return False
