"""Service registration for the ha_vk integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import VkApiError, VkClient, VkConfigError
from .const import (
    ATTR_IMAGE,
    ATTR_MESSAGE,
    ATTR_TITLE,
    ATTR_TYPE,
    ATTR_VIDEO,
    CONF_ENTRY_ID,
    DOMAIN,
    SEND_TYPE_DOCUMENT,
    SEND_TYPE_VIDEO,
    SERVICE_SEND_MESSAGE,
    SERVICE_SEND_POST,
)
from .receiver import HaVkConfigEntry

MESSAGE_SERVICE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(CONF_ENTRY_ID): cv.string,
            vol.Optional(ATTR_MESSAGE): cv.string,
            vol.Optional(ATTR_TITLE): cv.string,
            vol.Optional(ATTR_IMAGE): cv.url,
            vol.Optional(ATTR_VIDEO): cv.url,
            vol.Optional(ATTR_TYPE, default=SEND_TYPE_VIDEO): vol.In(
                [SEND_TYPE_VIDEO, SEND_TYPE_DOCUMENT]
            ),
        }
    ),
    lambda data: _validate_send_message_data(data),
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
                message=call.data.get(ATTR_MESSAGE),
                title=call.data.get(ATTR_TITLE),
                image_url=call.data.get(ATTR_IMAGE),
                video_url=call.data.get(ATTR_VIDEO),
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
        SERVICE_SEND_POST,
        handle_send_post,
        schema=POST_SERVICE_SCHEMA,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove services when the last entry is unloaded."""

    for service_name in (
        SERVICE_SEND_MESSAGE,
        SERVICE_SEND_POST,
    ):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)


def _resolve_client(hass: HomeAssistant, service_data: dict[str, Any]) -> VkClient:
    """Resolve the target VK client for a service call."""

    entries: list[HaVkConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("ha-vk is not configured")

    entry_id = service_data.get(CONF_ENTRY_ID)
    if entry_id:
        entry = next((item for item in entries if item.entry_id == entry_id), None)
        if entry is None:
            raise ServiceValidationError(f"Unknown ha-vk entry_id: {entry_id}")
        return entry.runtime_data.client

    if len(entries) == 1:
        return entries[0].runtime_data.client

    raise ServiceValidationError(
        "Multiple ha-vk entries are configured; pass entry_id explicitly"
    )


def _validate_send_message_data(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a combined text/media message service payload."""

    if not any(data.get(key) for key in (ATTR_MESSAGE, ATTR_IMAGE, ATTR_VIDEO)):
        raise vol.Invalid("At least one of message, image, or video must be provided")

    if data.get(ATTR_IMAGE) and data.get(ATTR_VIDEO):
        raise vol.Invalid("Only one of image or video can be provided")

    return data
