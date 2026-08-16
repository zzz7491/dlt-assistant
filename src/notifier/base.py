"""通知接口抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    """所有通知渠道的统一接口。"""

    @abstractmethod
    def send_text(self, text: str) -> bool:
        """发送纯文本通知，返回是否成功。"""
        raise NotImplementedError
