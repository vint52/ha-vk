"""Tests for the VK API client helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.ha_vk.api import (
    VkApiError,
    VkClient,
    VkClientConfig,
    build_client_config,
    format_notify_message,
    format_service_message,
)


def test_build_client_config_normalizes_values() -> None:
    """Config parsing should coerce numbers and trim tokens."""

    config = build_client_config(
        {
            "vk_access_token": " token ",
            "vk_peer_id": "123",
            "vk_group_id": "-456",
            "vk_wall_access_token": " wall ",
            "vk_api_version": "5.200",
            "request_timeout": 45,
        }
    )

    assert config.access_token == "token"
    assert config.peer_id == 123
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
async def test_send_video_falls_back_to_document_upload() -> None:
    """Group-token video failures should fall back to document uploads."""

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=1))
    client._download_file = AsyncMock(return_value=(b"video", "video/mp4", "clip.mp4"))  # type: ignore[method-assign]
    client._save_video_attachment = AsyncMock(side_effect=VkApiError("Group authorization failed"))  # type: ignore[method-assign]
    client._save_video_document_attachment = AsyncMock(return_value="doc1_2")  # type: ignore[method-assign]
    client._send_attachment = AsyncMock(return_value={"response": 1})  # type: ignore[method-assign]

    result = await client.async_send_video("http://example.com/clip.mp4", "video")

    assert result == {"response": 1}
    client._save_video_document_attachment.assert_awaited_once()
    client._send_attachment.assert_awaited_once_with("doc1_2")


@pytest.mark.asyncio
async def test_send_post_with_image_requires_wall_token() -> None:
    """Wall image uploads should require a dedicated user token."""

    client = VkClient(
        Mock(),
        VkClientConfig(access_token="token", peer_id=1, group_id=42),
    )

    with pytest.raises(VkApiError, match="wall access token is required"):
        await client.async_send_post("hello", "http://example.com/image.jpg")
