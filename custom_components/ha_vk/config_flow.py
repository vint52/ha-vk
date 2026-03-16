"""Config flow for the ha_vk integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import VkApiError, VkClient, VkConfigError, build_client_config
from .const import (
    CONF_API_VERSION,
    CONF_GROUP_ID,
    CONF_PEER_ID,
    CONF_REQUEST_TIMEOUT,
    CONF_VK_ACCESS_TOKEN,
    CONF_VK_WALL_ACCESS_TOKEN,
    DEFAULT_API_VERSION,
    DEFAULT_NAME,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
)


async def _async_validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> None:
    """Validate the provided config against VK."""

    client = VkClient(
        async_create_clientsession(hass),
        build_client_config(user_input),
    )
    await client.async_validate_config()


def _build_user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Build the initial setup form schema."""

    values = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=values.get(CONF_NAME, DEFAULT_NAME)): selector.TextSelector(
                selector.TextSelectorConfig(),
            ),
            vol.Required(CONF_VK_ACCESS_TOKEN, default=values.get(CONF_VK_ACCESS_TOKEN, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
            ),
            vol.Required(CONF_PEER_ID, default=values.get(CONF_PEER_ID, "")): selector.TextSelector(
                selector.TextSelectorConfig(),
            ),
            vol.Optional(CONF_GROUP_ID, default=values.get(CONF_GROUP_ID, "")): selector.TextSelector(
                selector.TextSelectorConfig(),
            ),
            vol.Optional(
                CONF_VK_WALL_ACCESS_TOKEN,
                default=values.get(CONF_VK_WALL_ACCESS_TOKEN, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
            ),
            vol.Required(
                CONF_API_VERSION,
                default=values.get(CONF_API_VERSION, DEFAULT_API_VERSION),
            ): selector.TextSelector(selector.TextSelectorConfig()),
            vol.Required(
                CONF_REQUEST_TIMEOUT,
                default=values.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _build_options_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Build the options flow schema."""

    values = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=values.get(CONF_NAME, DEFAULT_NAME)): selector.TextSelector(
                selector.TextSelectorConfig(),
            ),
            vol.Optional(
                CONF_GROUP_ID,
                default=values.get(CONF_GROUP_ID, ""),
            ): selector.TextSelector(selector.TextSelectorConfig()),
            vol.Optional(
                CONF_VK_WALL_ACCESS_TOKEN,
                default=values.get(CONF_VK_WALL_ACCESS_TOKEN, ""),
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
            ),
            vol.Required(
                CONF_API_VERSION,
                default=values.get(CONF_API_VERSION, DEFAULT_API_VERSION),
            ): selector.TextSelector(selector.TextSelectorConfig()),
            vol.Required(
                CONF_REQUEST_TIMEOUT,
                default=values.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _entry_unique_id(user_input: dict[str, Any]) -> str:
    """Build a stable unique ID for the config entry."""

    group_id = str(user_input.get(CONF_GROUP_ID, "")).strip() or "none"
    return f"peer:{str(user_input[CONF_PEER_ID]).strip()}|group:{group_id}"


def _entry_data(user_input: dict[str, Any]) -> dict[str, Any]:
    """Extract persisted config entry data."""

    return {
        CONF_NAME: str(user_input[CONF_NAME]).strip() or DEFAULT_NAME,
        CONF_VK_ACCESS_TOKEN: str(user_input[CONF_VK_ACCESS_TOKEN]).strip(),
        CONF_PEER_ID: str(user_input[CONF_PEER_ID]).strip(),
        CONF_GROUP_ID: str(user_input.get(CONF_GROUP_ID, "")).strip(),
    }


def _entry_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Extract persisted config entry options."""

    return {
        CONF_GROUP_ID: str(user_input.get(CONF_GROUP_ID, "")).strip(),
        CONF_VK_WALL_ACCESS_TOKEN: str(user_input.get(CONF_VK_WALL_ACCESS_TOKEN, "")).strip(),
        CONF_API_VERSION: str(user_input.get(CONF_API_VERSION, DEFAULT_API_VERSION)).strip()
        or DEFAULT_API_VERSION,
        CONF_REQUEST_TIMEOUT: float(user_input.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)),
    }


class HaVkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the ha_vk integration."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "HaVkOptionsFlow":
        """Return the options flow handler."""

        return HaVkOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _async_validate_input(self.hass, user_input)
            except VkConfigError:
                errors["base"] = "invalid_input"
            except VkApiError as err:
                lower = str(err).lower()
                if "invalid access token" in lower or "access denied" in lower:
                    errors["base"] = "invalid_auth"
                elif "network error" in lower:
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "vk_error"
            else:
                await self.async_set_unique_id(_entry_unique_id(user_input))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_entry_data(user_input)[CONF_NAME],
                    data=_entry_data(user_input),
                    options=_entry_options(user_input),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(user_input),
            errors=errors,
        )


class HaVkOptionsFlow(config_entries.OptionsFlow):
    """Handle ha_vk integration options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""

        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage the options flow."""

        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            merged = {**self.config_entry.data, **user_input}
            try:
                await _async_validate_input(self.hass, merged)
            except VkConfigError:
                errors["base"] = "invalid_input"
            except VkApiError as err:
                lower = str(err).lower()
                if "invalid access token" in lower or "access denied" in lower:
                    errors["base"] = "invalid_auth"
                elif "network error" in lower:
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "vk_error"
            else:
                new_name = str(user_input[CONF_NAME]).strip() or DEFAULT_NAME
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=new_name,
                    data={**self.config_entry.data, CONF_NAME: new_name},
                )
                return self.async_create_entry(title="", data=_entry_options(user_input))

            current = {**current, **user_input}

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(current),
            errors=errors,
        )
