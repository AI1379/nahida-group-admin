"""跨适配器的群管理能力门面。"""

from .group import (
    kick_group_member,
    mute_group_member,
    react_to_message,
    recall_message,
    send_group_message,
    set_special_title,
)

__all__ = [
    "set_special_title",
    "mute_group_member",
    "react_to_message",
    "kick_group_member",
    "send_group_message",
    "recall_message",
]
