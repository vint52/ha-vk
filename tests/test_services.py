"""Tests for ha_vk service registration and validation."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_vk.const import DOMAIN
from custom_components.ha_vk.receiver import HaVkEntryRuntime
from custom_components.ha_vk.services import MESSAGE_SERVICE_SCHEMA, async_register_services


def test_message_service_schema_requires_message_or_media() -> None:
    """The unified send_message service should require content."""

    with pytest.raises(vol.Invalid, match="At least one of message, image, or video"):
        MESSAGE_SERVICE_SCHEMA({})


def test_message_service_schema_rejects_image_and_video_together() -> None:
    """The unified send_message service should accept only one media type."""

    with pytest.raises(vol.Invalid, match="Only one of image or video can be provided"):
        MESSAGE_SERVICE_SCHEMA(
            {
                "image": "http://example.com/image.jpg",
                "video": "http://example.com/clip.mp4",
            }
        )


async def test_send_message_service_passes_media_fields_to_client(hass: HomeAssistant) -> None:
    """The unified service should forward media arguments to the VK client."""

    client = Mock()
    client.async_send_message = AsyncMock()
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-1")
    entry.add_to_hass(hass)
    entry.runtime_data = HaVkEntryRuntime(client=client)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    await async_register_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {
            "entry_id": "entry-1",
            "message": "Motion clip",
            "video": "http://example.com/clip.mp4",
            "type": "document",
        },
        blocking=True,
    )

    client.async_send_message.assert_awaited_once_with(
        message="Motion clip",
        title=None,
        image_url=None,
        video_url="http://example.com/clip.mp4",
        send_type="document",
    )
