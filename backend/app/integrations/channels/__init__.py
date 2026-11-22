"""渠道适配层：Shopee / Shopify 只读集成（契约 / 映射 / Mock / 客户端 / 工厂）。"""

from .base import (
    ChannelAdapter,
    ChannelAuthError,
    ChannelError,
    ChannelNotFound,
    ChannelUnavailable,
    normalize_sku,
    split_sku,
)
from .factory import (
    PLATFORMS,
    channel_health,
    channel_mode,
    channel_overview,
    get_channel,
)

__all__ = [
    "ChannelAdapter",
    "ChannelAuthError",
    "ChannelError",
    "ChannelNotFound",
    "ChannelUnavailable",
    "PLATFORMS",
    "channel_health",
    "channel_mode",
    "channel_overview",
    "get_channel",
    "normalize_sku",
    "split_sku",
]
