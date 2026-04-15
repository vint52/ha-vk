"""Background long poll receiver for incoming VK community messages."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from .api import VkApiError, VkClient, VkLongPollServer
from .const import DOMAIN, INCOMING_EVENT, LOGGER, LONG_POLL_RETRY_DELAY


class VkIncomingMessageReceiver:
    """Read VK long poll updates and emit Home Assistant events."""

    def __init__(self, hass: HomeAssistant, entry_id: str, client: VkClient) -> None:
        """Initialize the receiver."""

        self._hass = hass
        self._entry_id = entry_id
        self._client = client
        self._task: asyncio.Task[None] | None = None

    async def async_start(self) -> None:
        """Start the background receiver task."""

        if self._task is not None:
            return

        self._task = asyncio.create_task(
            self._async_run(),
            name=f"{DOMAIN}_receiver_{self._entry_id}",
        )

    async def async_stop(self) -> None:
        """Stop the background receiver task."""

        if self._task is None:
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _async_run(self) -> None:
        """Poll VK long poll forever and emit normalized events."""

        server: VkLongPollServer | None = None

        while True:
            try:
                if server is None:
                    server = await self._client.async_get_long_poll_server()

                server, updates = await self._client.async_check_long_poll(server)
                for event in updates:
                    normalized = self._client.normalize_incoming_message_event(event)
                    if normalized is None:
                        continue

                    self._hass.bus.async_fire(
                        INCOMING_EVENT,
                        {"entry_id": self._entry_id, **normalized},
                    )
            except asyncio.CancelledError:
                raise
            except VkApiError as err:
                LOGGER.warning("VK incoming receiver error for %s: %s", self._entry_id, err)
                server = None
                await asyncio.sleep(LONG_POLL_RETRY_DELAY)


@dataclass(slots=True)
class HaVkEntryRuntime:
    """Runtime state for a configured ha_vk entry."""

    client: VkClient
    receiver: VkIncomingMessageReceiver | None = None

    async def async_stop(self) -> None:
        """Stop background resources owned by the runtime."""

        if self.receiver is not None:
            await self.receiver.async_stop()
