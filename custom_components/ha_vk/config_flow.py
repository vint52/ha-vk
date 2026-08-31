"""Config flow for the ha_vk integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    VkApiError,
    VkAuthError,
    VkClient,
    VkConfigError,
    VkLongPollError,
    VkNetworkError,
    build_client_config,
)
from .const import (
    CONF_API_VERSION,
    CONF_ENABLE_INCOMING_MESSAGES,
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
        async_get_clientsession(hass),
        build_client_config(user_input),
    )
    await client.async_validate_config()


def _build_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Build the form schema shared by the setup and options flows."""

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
                CONF_ENABLE_INCOMING_MESSAGES,
                default=values.get(CONF_ENABLE_INCOMING_MESSAGES, False),
            ): selector.BooleanSelector(),
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


def _validation_error_key(err: VkApiError | VkConfigError) -> str:
    """Map a validation exception to a strings.json error key."""

    if isinstance(err, VkConfigError):
        if "incoming messages" in str(err).lower():
            return "incoming_not_available"
        return "invalid_input"
    if isinstance(err, VkLongPollError):
        return "incoming_not_available"
    if isinstance(err, VkAuthError):
        return "invalid_auth"
    if isinstance(err, VkNetworkError):
        return "cannot_connect"
    return "vk_error"


def _entry_unique_id(user_input: dict[str, Any]) -> str:
    """Build a stable unique ID for the config entry."""

    group_id = str(user_input.get(CONF_GROUP_ID, "")).strip() or "none"
    return f"peer:{str(user_input[CONF_PEER_ID]).strip()}|group:{group_id}"


def _is_unique_id_available(
    hass: HomeAssistant,
    unique_id: str,
    current_entry_id: str | None = None,
) -> bool:
    """Return whether the given unique ID is unused by other ha_vk entries."""

    return not any(
        entry.unique_id == unique_id and entry.entry_id != current_entry_id
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


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
        CONF_ENABLE_INCOMING_MESSAGES: bool(user_input.get(CONF_ENABLE_INCOMING_MESSAGES, False)),
        CONF_VK_WALL_ACCESS_TOKEN: str(user_input.get(CONF_VK_WALL_ACCESS_TOKEN, "")).strip(),
        CONF_API_VERSION: str(user_input.get(CONF_API_VERSION, DEFAULT_API_VERSION)).strip()
        or DEFAULT_API_VERSION,
        CONF_REQUEST_TIMEOUT: float(user_input.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)),
    }


class HaVkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the ha_vk integration."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> HaVkOptionsFlow:
        """Return the options flow handler."""

        return HaVkOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _async_validate_input(self.hass, user_input)
            except (VkApiError, VkConfigError) as err:
                errors["base"] = _validation_error_key(err)
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
            data_schema=_build_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication after VK rejected the stored tokens."""

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Ask for fresh tokens and revalidate them."""

        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            merged = {**reauth_entry.data, **reauth_entry.options, **user_input}
            try:
                await _async_validate_input(self.hass, merged)
            except (VkApiError, VkConfigError) as err:
                errors["base"] = _validation_error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_VK_ACCESS_TOKEN: str(user_input[CONF_VK_ACCESS_TOKEN]).strip(),
                    },
                    options={
                        **reauth_entry.options,
                        CONF_VK_WALL_ACCESS_TOKEN: str(
                            user_input.get(CONF_VK_WALL_ACCESS_TOKEN, "")
                        ).strip(),
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_VK_ACCESS_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
                    ),
                    vol.Optional(
                        CONF_VK_WALL_ACCESS_TOKEN,
                        default=reauth_entry.options.get(CONF_VK_WALL_ACCESS_TOKEN, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
                    ),
                }
            ),
            errors=errors,
        )


class HaVkOptionsFlow(config_entries.OptionsFlow):
    """Handle ha_vk integration options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage the options flow."""

        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            merged = {**self.config_entry.data, **self.config_entry.options, **user_input}
            new_unique_id = _entry_unique_id(merged)
            if not _is_unique_id_available(
                self.hass,
                new_unique_id,
                current_entry_id=self.config_entry.entry_id,
            ):
                errors["base"] = "already_configured"
            else:
                try:
                    await _async_validate_input(self.hass, merged)
                except (VkApiError, VkConfigError) as err:
                    errors["base"] = _validation_error_key(err)
                else:
                    new_name = str(merged[CONF_NAME]).strip() or DEFAULT_NAME
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        title=new_name,
                        unique_id=new_unique_id,
                        data=_entry_data(merged),
                    )
                    return self.async_create_entry(title="", data=_entry_options(merged))

            current = {**current, **user_input}

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(current),
            errors=errors,
        )
