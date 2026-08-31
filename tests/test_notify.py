"""Tests for the ha_vk notify entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_vk.const import (
    CONF_API_VERSION,
    CONF_ENABLE_INCOMING_MESSAGES,
    CONF_GROUP_ID,
    CONF_NAME,
    CONF_PEER_ID,
    CONF_REQUEST_TIMEOUT,
    CONF_VK_ACCESS_TOKEN,
    DEFAULT_API_VERSION,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_notify_entity_forwards_message_and_title(hass) -> None:
    """The notify entity should forward message and title to the VK client."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="vk_alerts",
        data={
            CONF_NAME: "vk_alerts",
            CONF_VK_ACCESS_TOKEN: "token",
            CONF_PEER_ID: "2000000123",
            CONF_GROUP_ID: "",
        },
        options={
            CONF_ENABLE_INCOMING_MESSAGES: False,
            CONF_API_VERSION: DEFAULT_API_VERSION,
            CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ha_vk.api.VkClient.async_send_message",
        new=AsyncMock(return_value={"response": 1}),
    ) as send:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_ids = hass.states.async_entity_ids("notify")
        assert len(entity_ids) == 1

        await hass.services.async_call(
            "notify",
            "send_message",
            {"entity_id": entity_ids[0], "message": "hello", "title": "Alert"},
            blocking=True,
        )

    send.assert_awaited_once_with(message="hello", title="Alert")
