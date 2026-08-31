"""Background long poll receiver for incoming VK community messages."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import VkApiError, VkClient, VkLongPollServer, is_auth_error
from .const import (
    DOMAIN,
    INCOMING_EVENT,
    LOGGER,
    LONG_POLL_MAX_RETRY_DELAY,
    LONG_POLL_RETRY_DELAY,
)

COMMAND_PREFIX = "/"


def parse_command(text: str) -> dict[str, object] | None:
    """Parse a "/command arg1 arg2" message text, or return None."""

    stripped = text.strip()
    body = stripped.removeprefix(COMMAND_PREFIX)
    if body == stripped or not body or body[0].isspace():
        return None

    tokens = body.split()
    return {
        "command": tokens[0].lower(),
        "args": tokens[1:],
        "args_text": body[len(tokens[0]) :].strip(),
    }


class VkIncomingMessageReceiver:
    """Read VK long poll updates and emit Home Assistant events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: VkClient) -> None:
        """Initialize the receiver."""

        self._hass = hass
        self._entry = entry
        self._client = client
        self._task: asyncio.Task[None] | None = None

    async def async_start(self) -> None:
        """Start the background receiver task."""

        if self._task is not None:
            return

        self._task = self._entry.async_create_background_task(
            self._hass,
            self._async_run(),
            name=f"{DOMAIN}_receiver_{self._entry.entry_id}",
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
        retry_delay = LONG_POLL_RETRY_DELAY

        while True:
            try:
                if server is None:
                    server = await self._client.async_get_long_poll_server()

                server, updates = await self._client.async_check_long_poll(server)
                self._process_updates(updates)
                retry_delay = LONG_POLL_RETRY_DELAY
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - the loop must survive any failure
                entry_id = self._entry.entry_id
                if isinstance(err, VkApiError) and is_auth_error(err):
                    LOGGER.error(
                        "VK incoming receiver auth error for %s, starting reauth: %s",
                        entry_id,
                        err,
                    )
                    self._entry.async_start_reauth(self._hass)
                    return
                if isinstance(err, VkApiError):
                    LOGGER.warning("VK incoming receiver error for %s: %s", entry_id, err)
                else:
                    LOGGER.exception("Unexpected VK incoming receiver error for %s", entry_id)
                server = None
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, LONG_POLL_MAX_RETRY_DELAY)

    def _process_updates(self, updates: list[dict]) -> None:
        """Emit Home Assistant events for normalized incoming messages."""

        for event in updates:
            normalized = self._client.normalize_incoming_message_event(event)
            if normalized is None:
                continue

            self._hass.bus.async_fire(
                INCOMING_EVENT,
                {"entry_id": self._entry.entry_id, **normalized},
            )


@dataclass(slots=True)
class HaVkEntryRuntime:
    """Runtime state for a configured ha_vk entry."""

    client: VkClient
    receiver: VkIncomingMessageReceiver | None = None

    async def async_stop(self) -> None:
        """Stop background resources owned by the runtime."""

        if self.receiver is not None:
            await self.receiver.async_stop()


type HaVkConfigEntry = ConfigEntry[HaVkEntryRuntime]
