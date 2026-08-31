"""Tests for the VK API client helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientError

from custom_components.ha_vk.api import (
    VkApiError,
    VkAuthError,
    VkClient,
    VkClientConfig,
    VkLongPollError,
    VkLongPollServer,
    VkNetworkError,
    build_client_config,
    format_notify_message,
    format_service_message,
    is_auth_error,
)


class MockAsyncResponse:
    """Small async context manager for mocked aiohttp responses."""

    def __init__(self, payload, status: int = 200) -> None:
        self._payload = payload
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return str(self._payload)


def test_build_client_config_normalizes_values() -> None:
    """Config parsing should coerce numbers and trim tokens."""

    config = build_client_config(
        {
            "vk_access_token": " token ",
            "vk_peer_id": "123",
            "vk_group_id": "-456",
            "enable_incoming_messages": True,
            "vk_wall_access_token": " wall ",
            "vk_api_version": "5.200",
            "request_timeout": 45,
        }
    )

    assert config.access_token == "token"
    assert config.peer_id == 123
    assert config.enable_incoming_messages is True
    assert config.group_id == 456
    assert config.wall_access_token == "wall"
    assert config.api_version == "5.200"
    assert config.request_timeout == 45.0


def test_format_notify_message_with_title() -> None:
    """Notify titles should be prepended to the body."""

    assert format_notify_message("Body", "Title") == "Title\nBody"


def test_format_service_message_supports_optional_text() -> None:
    """Service messages should allow media-only payloads."""

    assert format_service_message("Body", "Title") == "Title\nBody"
    assert format_service_message(None, "Title") == "Title"
    assert format_service_message(None, None) == ""


@pytest.mark.asyncio
async def test_send_message_with_image_uses_attachment_path() -> None:
    """Unified send_message should support image attachments."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=1))
    client._upload_message_image = AsyncMock(return_value="photo1_2")  # type: ignore[method-assign]
    client._send_attachment = AsyncMock(return_value={"response": 1})  # type: ignore[method-assign]

    result = await client.async_send_message(
        message="Snapshot ready",
        image_url="http://example.com/image.jpg",
    )

    assert result == {"response": 1}
    client._upload_message_image.assert_awaited_once_with("http://example.com/image.jpg")
    client._send_attachment.assert_awaited_once_with("photo1_2", "Snapshot ready")


@pytest.mark.asyncio
async def test_send_message_with_video_uses_attachment_path() -> None:
    """Unified send_message should support video attachments."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=1))
    client._upload_video_attachment = AsyncMock(return_value="video1_2")  # type: ignore[method-assign]
    client._send_attachment = AsyncMock(return_value={"response": 1})  # type: ignore[method-assign]

    result = await client.async_send_message(
        message="Motion clip",
        title="Camera",
        video_url="http://example.com/clip.mp4",
        send_type="document",
    )

    assert result == {"response": 1}
    client._upload_video_attachment.assert_awaited_once_with(
        "http://example.com/clip.mp4",
        "document",
    )
    client._send_attachment.assert_awaited_once_with("video1_2", "Camera\nMotion clip")


@pytest.mark.asyncio
async def test_send_message_rejects_multiple_media_types() -> None:
    """Unified send_message should reject image and video together."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=1))

    with pytest.raises(VkApiError, match="Only one of image_url or video_url"):
        await client.async_send_message(
            image_url="http://example.com/image.jpg",
            video_url="http://example.com/clip.mp4",
        )


@pytest.mark.asyncio
async def test_send_video_without_wall_token_uses_document_upload() -> None:
    """Without a wall token, videos should be sent as documents immediately."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=1))
    client._download_file = AsyncMock(return_value=(b"video", "video/mp4", "clip.mp4"))  # type: ignore[method-assign]
    client._save_video_attachment = AsyncMock()  # type: ignore[method-assign]
    client._save_video_document_attachment = AsyncMock(return_value="doc1_2")  # type: ignore[method-assign]
    client._send_attachment = AsyncMock(return_value={"response": 1})  # type: ignore[method-assign]

    result = await client.async_send_video("http://example.com/clip.mp4", "video")

    assert result == {"response": 1}
    client._save_video_attachment.assert_not_awaited()
    client._save_video_document_attachment.assert_awaited_once()
    client._send_attachment.assert_awaited_once_with("doc1_2")


@pytest.mark.asyncio
async def test_send_video_with_invalid_wall_token_raises_clear_error() -> None:
    """Invalid wall tokens should surface a clear upload error."""

    client = VkClient(
        Mock(),
        VkClientConfig(access_token="token", wall_access_token="wall", peer_id=1),
    )
    client._download_file = AsyncMock(return_value=(b"video", "video/mp4", "clip.mp4"))  # type: ignore[method-assign]
    client._save_video_attachment = AsyncMock(  # type: ignore[method-assign]
        side_effect=VkAuthError("video.save: invalid access token", code=5)
    )
    client._save_video_document_attachment = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(VkAuthError, match="VK wall access token is invalid"):
        await client.async_send_video("http://example.com/clip.mp4", "video")

    client._save_video_document_attachment.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_post_with_image_without_wall_token_skips_attachment() -> None:
    """Wall posts should stay text-only when no wall token is configured."""

    client = VkClient(
        Mock(),
        VkClientConfig(access_token="token", peer_id=1, group_id=42),
    )
    client._upload_wall_photo = AsyncMock(return_value="photo1_2")  # type: ignore[method-assign]
    client._api_call = AsyncMock(return_value=123)  # type: ignore[method-assign]

    result = await client.async_send_post("hello", "http://example.com/image.jpg")

    assert result == {"response": 123}
    client._upload_wall_photo.assert_not_awaited()
    client._api_call.assert_awaited_once_with(
        "wall.post",
        token="token",
        owner_id=-42,
        from_group=1,
        message="hello",
        attachments=None,
    )


@pytest.mark.asyncio
async def test_get_long_poll_server_returns_normalized_values() -> None:
    """Long poll setup should parse required server fields."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=1, group_id=42))
    client._api_call = AsyncMock(  # type: ignore[method-assign]
        return_value={"server": "https://lp.example.com", "key": "secret", "ts": 15}
    )

    server = await client.async_get_long_poll_server()

    assert server == VkLongPollServer(
        server="https://lp.example.com",
        key="secret",
        ts="15",
    )


@pytest.mark.asyncio
async def test_check_long_poll_returns_updates_and_advances_ts() -> None:
    """Long poll reads should return update batches and the next ts cursor."""

    session = Mock()
    session.get = Mock(
        return_value=MockAsyncResponse(
            {
                "ts": "101",
                "updates": [
                    {"type": "message_new", "object": {"message": {"peer_id": 1}}},
                    "skip-me",
                ],
            }
        )
    )
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, group_id=42))

    next_server, updates = await client.async_check_long_poll(
        VkLongPollServer(server="https://lp.example.com", key="secret", ts="100")
    )

    assert next_server.ts == "101"
    assert updates == [{"type": "message_new", "object": {"message": {"peer_id": 1}}}]
    session.get.assert_called_once()


@pytest.mark.asyncio
async def test_check_long_poll_refreshes_server_when_key_expires() -> None:
    """Long poll should request a fresh server when VK invalidates the key."""

    session = Mock()
    session.get = Mock(return_value=MockAsyncResponse({"failed": 2}))
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, group_id=42))
    client.async_get_long_poll_server = AsyncMock(  # type: ignore[method-assign]
        return_value=VkLongPollServer(server="https://lp2.example.com", key="fresh", ts="200")
    )

    next_server, updates = await client.async_check_long_poll(
        VkLongPollServer(server="https://lp.example.com", key="secret", ts="100")
    )

    assert next_server.server == "https://lp2.example.com"
    assert updates == []
    client.async_get_long_poll_server.assert_awaited_once()


def test_normalize_incoming_message_event_filters_to_configured_peer() -> None:
    """Only inbound message_new events for the configured peer should be emitted."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=2000000123, group_id=42))

    payload = client.normalize_incoming_message_event(
        {
            "type": "message_new",
            "group_id": 42,
            "event_id": "abc",
            "object": {
                "message": {
                    "id": 99,
                    "date": 1710000000,
                    "peer_id": 2000000123,
                    "from_id": 555,
                    "conversation_message_id": 77,
                    "text": "hello",
                    "attachments": [{"type": "photo"}],
                    "out": 0,
                }
            },
        }
    )

    assert payload == {
        "group_id": 42,
        "peer_id": 2000000123,
        "from_id": 555,
        "conversation_message_id": 77,
        "message_id": 99,
        "event_id": "abc",
        "date": 1710000000,
        "text": "hello",
        "attachments": [{"type": "photo"}],
        "raw_event": {
            "type": "message_new",
            "group_id": 42,
            "event_id": "abc",
            "object": {
                "message": {
                    "id": 99,
                    "date": 1710000000,
                    "peer_id": 2000000123,
                    "from_id": 555,
                    "conversation_message_id": 77,
                    "text": "hello",
                    "attachments": [{"type": "photo"}],
                    "out": 0,
                }
            },
        },
    }
    assert (
        client.normalize_incoming_message_event(
            {
                "type": "message_new",
                "object": {"message": {"peer_id": 2, "out": 0}},
            }
        )
        is None
    )


@pytest.mark.asyncio
async def test_api_call_raises_typed_auth_error_with_code() -> None:
    """VK auth error codes should raise VkAuthError carrying the code."""

    session = Mock()
    session.post = Mock(
        return_value=MockAsyncResponse(
            {"error": {"error_code": 5, "error_msg": "User authorization failed."}}
        )
    )
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1))

    with pytest.raises(VkAuthError) as excinfo:
        await client._api_call("users.get", token="token")

    assert excinfo.value.code == 5


@pytest.mark.asyncio
async def test_api_call_raises_generic_error_with_code() -> None:
    """Non-auth VK errors should stay VkApiError but keep the code."""

    session = Mock()
    session.post = Mock(
        return_value=MockAsyncResponse({"error": {"error_code": 100, "error_msg": "Bad params"}})
    )
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1))

    with pytest.raises(VkApiError) as excinfo:
        await client._api_call("users.get", token="token")

    assert not isinstance(excinfo.value, VkAuthError)
    assert excinfo.value.code == 100


@pytest.mark.asyncio
async def test_api_call_raises_network_error() -> None:
    """Transport failures should raise VkNetworkError."""

    session = Mock()
    session.post = Mock(side_effect=ClientError())
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1))

    with pytest.raises(VkNetworkError):
        await client._api_call("users.get", token="token")


@pytest.mark.asyncio
async def test_get_long_poll_server_wraps_errors_as_long_poll_error() -> None:
    """Long poll server failures should surface as VkLongPollError with the code."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=1, group_id=42))
    client._api_call = AsyncMock(  # type: ignore[method-assign]
        side_effect=VkAuthError("groups.getLongPollServer: access denied", code=15)
    )

    with pytest.raises(VkLongPollError) as excinfo:
        await client.async_get_long_poll_server()

    assert excinfo.value.code == 15
    assert is_auth_error(excinfo.value)


@pytest.mark.asyncio
async def test_check_long_poll_network_error_is_long_poll_error() -> None:
    """Long poll transport failures should raise VkLongPollError."""

    session = Mock()
    session.get = Mock(side_effect=ClientError())
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, group_id=42))

    with pytest.raises(VkLongPollError):
        await client.async_check_long_poll(
            VkLongPollServer(server="https://lp.example.com", key="secret", ts="100")
        )


def test_is_auth_error_matches_types_and_codes() -> None:
    """is_auth_error should match VkAuthError instances and wrapped auth codes."""

    assert is_auth_error(VkAuthError("bad token", code=5))
    assert is_auth_error(VkLongPollError("wrapped", code=27))
    assert not is_auth_error(VkApiError("other", code=100))
    assert not is_auth_error(VkApiError("no code"))


@pytest.mark.asyncio
async def test_send_video_falls_back_to_document_on_group_auth_error() -> None:
    """Group authorization failures should fall back to document upload."""

    client = VkClient(
        Mock(),
        VkClientConfig(access_token="token", wall_access_token="wall", peer_id=1),
    )
    client._download_file = AsyncMock(return_value=(b"video", "video/mp4", "clip.mp4"))  # type: ignore[method-assign]
    client._save_video_attachment = AsyncMock(  # type: ignore[method-assign]
        side_effect=VkAuthError("video.save: group authorization failed", code=27)
    )
    client._save_video_document_attachment = AsyncMock(return_value="doc1_2")  # type: ignore[method-assign]
    client._send_attachment = AsyncMock(return_value={"response": 1})  # type: ignore[method-assign]

    result = await client.async_send_video("http://example.com/clip.mp4", "video")

    assert result == {"response": 1}
    client._save_video_document_attachment.assert_awaited_once()
