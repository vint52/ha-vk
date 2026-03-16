"""Service registration for the ha_vk integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .api import VkApiError, VkConfigError
from .const import (
    ATTR_IMAGE,
    ATTR_MESSAGE,
    ATTR_TYPE,
    ATTR_TITLE,
    ATTR_VIDEO,
    CONF_ENTRY_ID,
    DOMAIN,
    SEND_TYPE_DOCUMENT,
    SEND_TYPE_VIDEO,
    SERVICE_SEND_IMAGE,
    SERVICE_SEND_MESSAGE,
    SERVICE_SEND_POST,
    SERVICE_SEND_VIDEO,
)

MESSAGE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
    }
)

IMAGE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): cv.string,
        vol.Required(ATTR_IMAGE): cv.url,
    }
)

VIDEO_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): cv.string,
        vol.Required(ATTR_VIDEO): cv.url,
        vol.Optional(ATTR_TYPE, default=SEND_TYPE_VIDEO): vol.In(
            [SEND_TYPE_VIDEO, SEND_TYPE_DOCUMENT]
        ),
    }
)

POST_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTRY_ID): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_IMAGE): cv.url,
    }
)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services once."""

    if hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
        return

    async def handle_send_message(call: ServiceCall) -> None:
        client = _resolve_client(hass, call.data)
        try:
            await client.async_send_message(
                message=call.data[ATTR_MESSAGE],
                title=call.data.get(ATTR_TITLE),
            )
        except (VkApiError, VkConfigError) as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_send_image(call: ServiceCall) -> None:
        client = _resolve_client(hass, call.data)
        try:
            await client.async_send_image(call.data[ATTR_IMAGE])
        except (VkApiError, VkConfigError) as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_send_video(call: ServiceCall) -> None:
        client = _resolve_client(hass, call.data)
        try:
            await client.async_send_video(
                video_url=call.data[ATTR_VIDEO],
                send_type=call.data[ATTR_TYPE],
            )
        except (VkApiError, VkConfigError) as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_send_post(call: ServiceCall) -> None:
        client = _resolve_client(hass, call.data)
        try:
            await client.async_send_post(
                message=call.data[ATTR_MESSAGE],
                image_url=call.data.get(ATTR_IMAGE),
            )
        except (VkApiError, VkConfigError) as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        handle_send_message,
        schema=MESSAGE_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_IMAGE,
        handle_send_image,
        schema=IMAGE_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_VIDEO,
        handle_send_video,
        schema=VIDEO_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_POST,
        handle_send_post,
        schema=POST_SERVICE_SCHEMA,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove services when the last entry is unloaded."""

    for service_name in (
        SERVICE_SEND_MESSAGE,
        SERVICE_SEND_IMAGE,
        SERVICE_SEND_VIDEO,
        SERVICE_SEND_POST,
    ):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)


def _resolve_client(hass: HomeAssistant, service_data: dict[str, Any]):
    """Resolve the target VK client for a service call."""

    clients = hass.data.get(DOMAIN, {})
    if not clients:
        raise ServiceValidationError("ha-vk is not configured")

    entry_id = service_data.get(CONF_ENTRY_ID)
    if entry_id:
        client = clients.get(entry_id)
        if client is None:
            raise ServiceValidationError(f"Unknown ha-vk entry_id: {entry_id}")
        return client

    if len(clients) == 1:
        return next(iter(clients.values()))

    raise ServiceValidationError(
        "Multiple ha-vk entries are configured; pass entry_id explicitly"
    )
