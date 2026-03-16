"""The ha_vk integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VkClient, VkConfigError, build_client_config
from .const import DOMAIN, LOGGER
from .services import async_register_services, async_unregister_services

PLATFORMS: list[str] = ["notify"]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the ha_vk integration."""

    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ha_vk from a config entry."""

    try:
        client = VkClient(
            async_get_clientsession(hass),
            build_client_config({**entry.data, **entry.options}),
        )
    except VkConfigError as err:
        raise ConfigEntryError(str(err)) from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = client

    await async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    LOGGER.debug("Configured ha_vk entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a ha_vk config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    entry_data: dict[str, VkClient] = hass.data.get(DOMAIN, {})
    entry_data.pop(entry.entry_id, None)

    if not entry_data:
        await async_unregister_services(hass)

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry after options change."""

    await hass.config_entries.async_reload(entry.entry_id)
