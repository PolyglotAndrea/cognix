"""Unified external channel ingress layer."""

from cognix.channels.base import (
    ChannelAttachment,
    ChannelDispatchResult,
    ChannelEvent,
    ChannelRouteTarget,
)
from cognix.channels.router import MessageRouter

__all__ = [
    "ChannelAttachment",
    "ChannelDispatchResult",
    "ChannelEvent",
    "ChannelRouteTarget",
    "MessageRouter",
]
