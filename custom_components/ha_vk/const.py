"""Constants for the ha-vk integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_NAME

DOMAIN = "ha_vk"
LOGGER = logging.getLogger(__package__)

CONF_API_VERSION = "vk_api_version"
CONF_GROUP_ID = "vk_group_id"
CONF_PEER_ID = "vk_peer_id"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_VK_ACCESS_TOKEN = "vk_access_token"
CONF_VK_WALL_ACCESS_TOKEN = "vk_wall_access_token"
CONF_ENTRY_ID = "entry_id"

DEFAULT_NAME = "ha-vk"
DEFAULT_API_VERSION = "5.131"
DEFAULT_REQUEST_TIMEOUT = 30.0

SERVICE_SEND_IMAGE = "send_image"
SERVICE_SEND_MESSAGE = "send_message"
SERVICE_SEND_VIDEO = "send_video"
SERVICE_SEND_POST = "send_post"

ATTR_IMAGE = "image"
ATTR_MESSAGE = "message"
ATTR_TITLE = "title"
ATTR_TYPE = "type"
ATTR_VIDEO = "video"

SEND_TYPE_VIDEO = "video"
SEND_TYPE_DOCUMENT = "document"

ENTRY_DATA_KEYS: tuple[str, ...] = (
    CONF_NAME,
    CONF_VK_ACCESS_TOKEN,
    CONF_PEER_ID,
    CONF_GROUP_ID,
)

ENTRY_OPTION_KEYS: tuple[str, ...] = (
    CONF_VK_WALL_ACCESS_TOKEN,
    CONF_API_VERSION,
    CONF_REQUEST_TIMEOUT,
)
