"""The ha_vk integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VkClient, VkConfigError, build_client_config
from .const import DOMAIN, LOGGER
from .receiver import HaVkConfigEntry, HaVkEntryRuntime, VkIncomingMessageReceiver
from .services import async_register_services, async_unregister_services

PLATFORMS: list[str] = ["notify"]


async def async_setup_entry(hass: HomeAssistant, entry: HaVkConfigEntry) -> bool:
    """Set up ha_vk from a config entry."""

    try:
        client = VkClient(
            async_get_clientsession(hass),
            build_client_config({**entry.data, **entry.options}),
        )
    except VkConfigError as err:
        raise ConfigEntryError(str(err)) from err

    runtime = HaVkEntryRuntime(client=client)
    entry.runtime_data = runtime
    if client.supports_incoming_messages:
        runtime.receiver = VkIncomingMessageReceiver(hass, entry, client)
        await runtime.receiver.async_start()

    try:
        await async_register_services(hass)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await runtime.async_stop()
        if not _has_other_loaded_entries(hass, entry):
            await async_unregister_services(hass)
        raise

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    LOGGER.debug("Configured ha_vk entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HaVkConfigEntry) -> bool:
    """Unload a ha_vk config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    await entry.runtime_data.async_stop()

    if not _has_other_loaded_entries(hass, entry):
        await async_unregister_services(hass)

    return True


def _has_other_loaded_entries(hass: HomeAssistant, entry: HaVkConfigEntry) -> bool:
    """Return True when another ha_vk entry is still loaded."""

    return any(
        other.entry_id != entry.entry_id
        for other in hass.config_entries.async_loaded_entries(DOMAIN)
    )


async def _async_reload_entry(hass: HomeAssistant, entry: HaVkConfigEntry) -> None:
    """Reload the config entry after options change."""

    await hass.config_entries.async_reload(entry.entry_id)
