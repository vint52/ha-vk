"""Config flow tests for VK Client for Home Assistant."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_vk.api import VkApiError, VkLongPollError
from custom_components.ha_vk.const import (
    CONF_API_VERSION,
    CONF_ENABLE_INCOMING_MESSAGES,
    CONF_GROUP_ID,
    CONF_NAME,
    CONF_PEER_ID,
    CONF_REQUEST_TIMEOUT,
    CONF_SEND_RETRIES,
    CONF_VK_ACCESS_TOKEN,
    CONF_VK_WALL_ACCESS_TOKEN,
    DEFAULT_API_VERSION,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SEND_RETRIES,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The user flow should create a config entry after validation."""

    user_input = {
        CONF_NAME: "vk_alerts",
        CONF_VK_ACCESS_TOKEN: "token",
        CONF_PEER_ID: "2000000123",
        CONF_GROUP_ID: "42",
        CONF_ENABLE_INCOMING_MESSAGES: True,
        CONF_VK_WALL_ACCESS_TOKEN: "wall",
        CONF_API_VERSION: DEFAULT_API_VERSION,
        CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
        CONF_SEND_RETRIES: DEFAULT_SEND_RETRIES,
    }

    with patch(
        "custom_components.ha_vk.config_flow._async_validate_input",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=user_input,
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "vk_alerts"
    assert result["data"][CONF_PEER_ID] == "2000000123"
    assert result["options"][CONF_ENABLE_INCOMING_MESSAGES] is True
    assert result["options"][CONF_VK_WALL_ACCESS_TOKEN] == "wall"
    assert result["options"][CONF_SEND_RETRIES] == DEFAULT_SEND_RETRIES


async def test_options_flow_updates_options(hass: HomeAssistant) -> None:
    """Options flow should persist editable values and rekey the entry."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="vk_alerts",
        unique_id="peer:2000000123|group:42",
        data={
            CONF_NAME: "vk_alerts",
            CONF_VK_ACCESS_TOKEN: "token",
            CONF_PEER_ID: "2000000123",
            CONF_GROUP_ID: "42",
        },
        options={
            CONF_ENABLE_INCOMING_MESSAGES: False,
            CONF_VK_WALL_ACCESS_TOKEN: "old",
            CONF_API_VERSION: DEFAULT_API_VERSION,
            CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ha_vk.config_flow._async_validate_input",
        return_value=None,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "vk_family",
                CONF_VK_ACCESS_TOKEN: "new-token",
                CONF_PEER_ID: "2000000999",
                CONF_GROUP_ID: "77",
                CONF_ENABLE_INCOMING_MESSAGES: True,
                CONF_VK_WALL_ACCESS_TOKEN: "new",
                CONF_API_VERSION: "5.199",
                CONF_REQUEST_TIMEOUT: 60,
                CONF_SEND_RETRIES: 5,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_GROUP_ID] == "77"
    assert result["data"][CONF_ENABLE_INCOMING_MESSAGES] is True
    assert result["data"][CONF_VK_WALL_ACCESS_TOKEN] == "new"
    assert result["data"][CONF_SEND_RETRIES] == 5
    assert entry.title == "vk_family"
    assert entry.data[CONF_NAME] == "vk_family"
    assert entry.data[CONF_VK_ACCESS_TOKEN] == "new-token"
    assert entry.data[CONF_PEER_ID] == "2000000999"
    assert entry.unique_id == "peer:2000000999|group:77"


async def test_options_flow_rejects_duplicate_peer_and_group(hass: HomeAssistant) -> None:
    """Options flow should block unique ID collisions."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="vk_alerts",
        unique_id="peer:2000000123|group:42",
        data={
            CONF_NAME: "vk_alerts",
            CONF_VK_ACCESS_TOKEN: "token",
            CONF_PEER_ID: "2000000123",
            CONF_GROUP_ID: "42",
        },
        options={
            CONF_ENABLE_INCOMING_MESSAGES: False,
            CONF_VK_WALL_ACCESS_TOKEN: "old",
            CONF_API_VERSION: DEFAULT_API_VERSION,
            CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
        },
    )
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        title="vk_other",
        unique_id="peer:2000000555|group:77",
        data={
            CONF_NAME: "vk_other",
            CONF_VK_ACCESS_TOKEN: "other-token",
            CONF_PEER_ID: "2000000555",
            CONF_GROUP_ID: "77",
        },
        options={
            CONF_ENABLE_INCOMING_MESSAGES: False,
            CONF_VK_WALL_ACCESS_TOKEN: "",
            CONF_API_VERSION: DEFAULT_API_VERSION,
            CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
        },
    )
    entry.add_to_hass(hass)
    other_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "vk_family",
            CONF_VK_ACCESS_TOKEN: "new-token",
            CONF_PEER_ID: "2000000555",
            CONF_GROUP_ID: "77",
            CONF_ENABLE_INCOMING_MESSAGES: True,
            CONF_VK_WALL_ACCESS_TOKEN: "new",
            CONF_API_VERSION: "5.199",
            CONF_REQUEST_TIMEOUT: 60,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "already_configured"
    assert entry.unique_id == "peer:2000000123|group:42"


async def test_user_flow_surfaces_incoming_message_setup_errors(hass: HomeAssistant) -> None:
    """Long poll validation failures should get a dedicated config flow error."""

    user_input = {
        CONF_NAME: "vk_alerts",
        CONF_VK_ACCESS_TOKEN: "token",
        CONF_PEER_ID: "2000000123",
        CONF_GROUP_ID: "42",
        CONF_ENABLE_INCOMING_MESSAGES: True,
        CONF_VK_WALL_ACCESS_TOKEN: "",
        CONF_API_VERSION: DEFAULT_API_VERSION,
        CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
    }

    with patch(
        "custom_components.ha_vk.config_flow._async_validate_input",
        side_effect=VkLongPollError("groups.getLongPollServer: access denied", code=15),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=user_input,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "incoming_not_available"


async def test_validate_input_uses_shared_session(hass: HomeAssistant) -> None:
    """Validation must reuse the shared HA session instead of creating new ones."""

    from unittest.mock import AsyncMock

    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.ha_vk import config_flow

    with patch.object(config_flow, "VkClient") as vk_client:
        vk_client.return_value.async_validate_config = AsyncMock()
        await config_flow._async_validate_input(
            hass,
            {
                CONF_VK_ACCESS_TOKEN: "token",
                CONF_PEER_ID: "2000000123",
            },
        )

    assert vk_client.call_args[0][0] is async_get_clientsession(hass)


async def test_validate_input_disables_retries(hass: HomeAssistant) -> None:
    """Config validation should fail fast instead of retrying for minutes."""

    from unittest.mock import AsyncMock

    from custom_components.ha_vk import config_flow

    with patch.object(config_flow, "VkClient") as vk_client:
        vk_client.return_value.async_validate_config = AsyncMock()
        await config_flow._async_validate_input(
            hass,
            {
                CONF_VK_ACCESS_TOKEN: "token",
                CONF_PEER_ID: "2000000123",
                CONF_SEND_RETRIES: 7,
            },
        )

    config = vk_client.call_args[0][1]
    assert config.send_retries == 0


def test_validation_error_key_maps_typed_exceptions() -> None:
    """Error keys should be derived from exception types, not message text."""

    from custom_components.ha_vk.api import (
        VkAuthError,
        VkLongPollError,
        VkNetworkError,
    )
    from custom_components.ha_vk.config_flow import _validation_error_key

    assert _validation_error_key(VkLongPollError("boom")) == "incoming_not_available"
    assert _validation_error_key(VkAuthError("boom", code=5)) == "invalid_auth"
    assert _validation_error_key(VkNetworkError("boom")) == "cannot_connect"
    assert _validation_error_key(VkApiError("boom")) == "vk_error"


async def test_reauth_flow_updates_tokens(hass: HomeAssistant) -> None:
    """Reauth should revalidate and persist fresh tokens without recreating the entry."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="vk_alerts",
        unique_id="peer:2000000123|group:42",
        data={
            CONF_NAME: "vk_alerts",
            CONF_VK_ACCESS_TOKEN: "stale-token",
            CONF_PEER_ID: "2000000123",
            CONF_GROUP_ID: "42",
        },
        options={
            CONF_ENABLE_INCOMING_MESSAGES: False,
            CONF_VK_WALL_ACCESS_TOKEN: "stale-wall",
            CONF_API_VERSION: DEFAULT_API_VERSION,
            CONF_REQUEST_TIMEOUT: DEFAULT_REQUEST_TIMEOUT,
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.ha_vk.config_flow._async_validate_input",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_VK_ACCESS_TOKEN: "fresh-token",
                CONF_VK_WALL_ACCESS_TOKEN: "fresh-wall",
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_VK_ACCESS_TOKEN] == "fresh-token"
    assert entry.options[CONF_VK_WALL_ACCESS_TOKEN] == "fresh-wall"
