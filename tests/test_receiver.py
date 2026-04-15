"""Tests for the incoming VK long poll receiver."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.core import Event, HomeAssistant, callback

from custom_components.ha_vk.api import VkClient, VkClientConfig, VkLongPollServer
from custom_components.ha_vk.const import INCOMING_EVENT
from custom_components.ha_vk.receiver import VkIncomingMessageReceiver


@pytest.mark.asyncio
async def test_receiver_emits_home_assistant_event(hass: HomeAssistant) -> None:
    """The receiver should convert normalized VK updates into HA bus events."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=2000000123, group_id=42))
    client.async_get_long_poll_server = AsyncMock(  # type: ignore[method-assign]
        return_value=VkLongPollServer(server="https://lp.example.com", key="secret", ts="100")
    )
    client.async_check_long_poll = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            (
                VkLongPollServer(server="https://lp.example.com", key="secret", ts="101"),
                [{"type": "message_new"}],
            ),
            asyncio.CancelledError(),
        ]
    )
    client.normalize_incoming_message_event = Mock(  # type: ignore[method-assign]
        return_value={
            "group_id": 42,
            "peer_id": 2000000123,
            "from_id": 555,
            "conversation_message_id": 77,
            "message_id": 99,
            "event_id": "abc",
            "date": 1710000000,
            "text": "hello",
            "attachments": [],
            "raw_event": {"type": "message_new"},
        }
    )

    received: list[Event] = []
    event_received = asyncio.Event()

    @callback
    def _handle_event(event: Event) -> None:
        received.append(event)
        event_received.set()

    unsub = hass.bus.async_listen(INCOMING_EVENT, _handle_event)
    receiver = VkIncomingMessageReceiver(hass, "entry-1", client)

    try:
        await receiver.async_start()
        await asyncio.wait_for(event_received.wait(), timeout=1)
    finally:
        await receiver.async_stop()
        unsub()

    assert len(received) == 1
    assert received[0].data["entry_id"] == "entry-1"
    assert received[0].data["text"] == "hello"
