"""Tests for ha_vk config entry lifecycle."""

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
async def test_entry_setup_starts_and_unload_stops_receiver(hass) -> None:
    """Entries with a group ID should manage the incoming receiver lifecycle."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="vk_alerts",
        data={
            CONF_NAME: "vk_alerts",
            CONF_VK_ACCESS_TOKEN: "token",
            CONF_PEER_ID: "2000000123",
            CONF_GROUP_ID: "42",
        },
        options={
            CONF_ENABLE_INCOMING_MESSAGES: True,
            CONF_API_VERSION: DEFAULT_API_VERSION,
            CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.ha_vk.receiver.VkIncomingMessageReceiver.async_start", new=AsyncMock()) as start,
        patch("custom_components.ha_vk.receiver.VkIncomingMessageReceiver.async_stop", new=AsyncMock()) as stop,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert start.await_count == 1

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert stop.await_count == 1


@pytest.mark.asyncio
async def test_entry_setup_stores_runtime_in_runtime_data(hass) -> None:
    """Runtime state should live in entry.runtime_data, not hass.data."""

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

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data is not None
    assert entry.runtime_data.client is not None
    assert not hass.data.get(DOMAIN)
