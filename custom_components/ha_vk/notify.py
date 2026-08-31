"""Notify entity platform for the ha_vk integration."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import VkApiError, VkConfigError
from .const import DEFAULT_NAME, DOMAIN
from .receiver import HaVkEntryRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ha_vk notify entity from a config entry."""

    async_add_entities([HaVkNotifyEntity(hass, entry)])


class HaVkNotifyEntity(NotifyEntity):
    """Notify entity backed by a VK chat or user."""

    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the notify entity."""

        runtime: HaVkEntryRuntime = hass.data[DOMAIN][entry.entry_id]
        self._client = runtime.client
        self._attr_name = entry.title or DEFAULT_NAME
        self._attr_unique_id = entry.entry_id

    async def async_send_message(
        self,
        message: str,
        title: str | None = None,
    ) -> None:
        """Send a notification message via VK."""

        try:
            await self._client.async_send_message(message=message, title=title)
        except (VkApiError, VkConfigError) as err:
            raise HomeAssistantError(str(err)) from err
