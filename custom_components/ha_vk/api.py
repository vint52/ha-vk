"""Async VK API client used by the Home Assistant integration."""

from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout, FormData

from .const import (
    DEFAULT_API_VERSION,
    DEFAULT_REQUEST_TIMEOUT,
    SEND_TYPE_DOCUMENT,
)

VK_API_BASE = "https://api.vk.com/method"


class VkApiError(RuntimeError):
    """Raised when VK API returns an error."""


class VkConfigError(RuntimeError):
    """Raised when integration configuration is invalid."""


@dataclass(slots=True, frozen=True)
class VkClientConfig:
    """Configuration required for VK operations."""

    access_token: str
    peer_id: int
    wall_access_token: str | None = None
    group_id: int | None = None
    api_version: str = DEFAULT_API_VERSION
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT


def build_client_config(data: dict[str, Any]) -> VkClientConfig:
    """Build a validated client configuration from stored entry data."""

    access_token = str(data["vk_access_token"]).strip()
    if not access_token:
        raise VkConfigError("VK access token is empty")

    peer_id = _parse_int(data["vk_peer_id"], "VK peer ID")
    group_id_raw = data.get("vk_group_id")
    group_id = None if group_id_raw in (None, "") else abs(_parse_int(group_id_raw, "VK group ID"))

    wall_access_token_raw = data.get("vk_wall_access_token")
    wall_access_token = None
    if wall_access_token_raw:
        wall_access_token = str(wall_access_token_raw).strip() or None

    api_version = str(data.get("vk_api_version", DEFAULT_API_VERSION)).strip() or DEFAULT_API_VERSION
    request_timeout = _parse_float(
        data.get("request_timeout", DEFAULT_REQUEST_TIMEOUT),
        "Request timeout",
    )

    return VkClientConfig(
        access_token=access_token,
        peer_id=peer_id,
        wall_access_token=wall_access_token,
        group_id=group_id,
        api_version=api_version,
        request_timeout=request_timeout,
    )


def _parse_int(value: Any, label: str) -> int:
    """Parse an integer configuration value."""

    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as err:
        raise VkConfigError(f"{label} must be an integer") from err


def _parse_float(value: Any, label: str) -> float:
    """Parse a float configuration value."""

    try:
        parsed = float(value)
    except (TypeError, ValueError) as err:
        raise VkConfigError(f"{label} must be a number") from err

    if parsed <= 0:
        raise VkConfigError(f"{label} must be greater than zero")

    return parsed


def format_notify_message(message: str, title: str | None = None) -> str:
    """Format Home Assistant notify payload for VK text messages."""

    body = message.strip()
    if not body:
        raise VkApiError("Message is empty")

    if title:
        heading = title.strip()
        if heading:
            return f"{heading}\n{body}"

    return body


class VkClient:
    """Small async wrapper over the VK HTTP API."""

    def __init__(self, session: ClientSession, config: VkClientConfig) -> None:
        """Initialize the client."""

        self._session = session
        self._config = config

    async def async_validate_config(self) -> None:
        """Validate a config entry against VK API."""

        await self._api_call(
            "messages.getConversationsById",
            token=self._config.access_token,
            peer_ids=self._config.peer_id,
            extended=0,
        )
        if self._config.group_id is not None:
            await self._api_call(
                "groups.getById",
                token=self._config.access_token,
                group_id=self._config.group_id,
            )
        if self._config.wall_access_token:
            if self._config.group_id is None:
                await self._api_call(
                    "users.get",
                    token=self._config.wall_access_token,
                )
            else:
                await self._api_call(
                    "photos.getWallUploadServer",
                    token=self._config.wall_access_token,
                    group_id=self._config.group_id,
                )

    async def async_send_message(self, message: str, title: str | None = None) -> dict[str, Any]:
        """Send a plain text message."""

        payload = {
            "peer_id": self._config.peer_id,
            "random_id": 0,
            "message": format_notify_message(message, title),
        }
        response = await self._api_call("messages.send", token=self._config.access_token, **payload)
        return {"response": response}

    async def async_send_image(self, image_url: str) -> dict[str, Any]:
        """Download an image and send it to VK messages."""

        content, content_type, filename = await self._download_file(image_url, "image/")
        upload = await self._api_call(
            "photos.getMessagesUploadServer",
            token=self._config.access_token,
            peer_id=self._config.peer_id,
        )
        upload_response = await self._upload_file(
            upload["upload_url"],
            field_name="photo",
            filename=filename,
            content=content,
            content_type=content_type,
        )
        photos = await self._api_call(
            "photos.saveMessagesPhoto",
            token=self._config.access_token,
            **upload_response,
        )
        photo_info = _first_item(photos, "photo")
        return await self._send_attachment(_photo_attachment(photo_info))

    async def async_send_video(
        self,
        video_url: str,
        send_type: str,
    ) -> dict[str, Any]:
        """Download a video and send it as a VK video or document."""

        content, content_type, filename = await self._download_file(
            video_url,
            ("video/", "application/octet-stream"),
        )

        if send_type == SEND_TYPE_DOCUMENT:
            return await self._send_video_as_document(content, content_type, filename)

        upload_token = self._config.wall_access_token or self._config.access_token
        try:
            attachment = await self._save_video_attachment(
                upload_token,
                content,
                content_type,
                filename,
            )
        except VkApiError as err:
            if self._config.wall_access_token or "group authorization failed" not in str(err).lower():
                raise
            return await self._send_video_as_document(content, content_type, filename)

        return await self._send_attachment(attachment)

    async def async_send_post(self, message: str, image_url: str | None = None) -> dict[str, Any]:
        """Create a wall post, optionally with an uploaded image."""

        if self._config.group_id is None:
            raise VkConfigError("VK group ID is required for wall posts")

        attachments = None
        token = self._config.access_token
        if image_url:
            if not self._config.wall_access_token:
                raise VkApiError(
                    "VK wall access token is required for posts with images. "
                    "Use a user token with wall/photos/offline permissions."
                )
            token = self._config.wall_access_token
            attachments = await self._upload_wall_photo(image_url, token)

        response = await self._api_call(
            "wall.post",
            token=token,
            owner_id=-self._config.group_id,
            from_group=1,
            message=message,
            attachments=attachments,
        )
        return {"response": response}

    async def _send_attachment(self, attachment: str, message: str = "") -> dict[str, Any]:
        """Send a previously uploaded VK attachment."""

        response = await self._api_call(
            "messages.send",
            token=self._config.access_token,
            peer_id=self._config.peer_id,
            random_id=0,
            message=message,
            attachment=attachment,
        )
        return {"response": response}

    async def _upload_wall_photo(self, image_url: str, token: str) -> str:
        """Upload an image for a wall post."""

        if self._config.group_id is None:
            raise VkConfigError("VK group ID is required for wall photo uploads")

        content, content_type, filename = await self._download_file(image_url, "image/")
        upload = await self._api_call(
            "photos.getWallUploadServer",
            token=token,
            group_id=self._config.group_id,
        )
        upload_response = await self._upload_file(
            upload["upload_url"],
            field_name="photo",
            filename=filename,
            content=content,
            content_type=content_type,
        )
        upload_response["group_id"] = self._config.group_id
        photos = await self._api_call(
            "photos.saveWallPhoto",
            token=token,
            **upload_response,
        )
        photo_info = _first_item(photos, "photo")
        return _photo_attachment(photo_info)

    async def _save_video_attachment(
        self,
        token: str,
        content: bytes,
        content_type: str,
        filename: str,
    ) -> str:
        """Upload a video and return a VK attachment identifier."""

        values: dict[str, Any] = {
            "name": filename,
            "is_private": 1,
        }
        if token == self._config.wall_access_token and self._config.group_id is not None:
            values["group_id"] = self._config.group_id

        response = await self._api_call("video.save", token=token, **values)
        upload_url = response.pop("upload_url", None)
        if not upload_url:
            raise VkApiError("video.save did not return an upload URL")

        await self._upload_file(
            upload_url,
            field_name="video_file",
            filename=filename,
            content=content,
            content_type=content_type,
        )

        owner_id = response.get("owner_id")
        video_id = response.get("video_id") or response.get("vid") or response.get("id")
        if owner_id is None or video_id is None:
            raise VkApiError("Invalid video data from VK API")

        return _build_attachment("video", owner_id, video_id, response.get("access_key"))

    async def _send_video_as_document(
        self,
        content: bytes,
        content_type: str,
        filename: str,
    ) -> dict[str, Any]:
        """Fallback upload path for videos when video.save is unavailable."""

        upload = await self._api_call(
            "docs.getMessagesUploadServer",
            token=self._config.access_token,
            peer_id=self._config.peer_id,
            type="doc",
        )
        upload_response = await self._upload_file(
            upload["upload_url"],
            field_name="file",
            filename=filename,
            content=content,
            content_type=content_type,
        )
        save_response = await self._api_call(
            "docs.save",
            token=self._config.access_token,
            title=filename,
            **upload_response,
        )
        doc_info = _extract_doc_info(save_response)
        owner_id = doc_info.get("owner_id")
        doc_id = doc_info.get("id") or doc_info.get("doc_id")
        if owner_id is None or doc_id is None:
            raise VkApiError("Invalid document data from VK API")
        return await self._send_attachment(
            _build_attachment("doc", owner_id, doc_id, doc_info.get("access_key"))
        )

    async def _download_file(
        self,
        source_url: str,
        expected_content_types: str | tuple[str, ...],
    ) -> tuple[bytes, str, str]:
        """Download and validate a remote media file."""

        timeout = ClientTimeout(total=self._config.request_timeout)
        try:
            async with self._session.get(source_url, timeout=timeout, allow_redirects=True) as response:
                if response.status >= 400:
                    raise VkApiError(f"Failed to download file ({await _summarize_response(response)})")
                content = await response.read()
                content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        except (ClientError, asyncio.TimeoutError) as err:
            raise VkApiError("Failed to download media file") from err

        if not content:
            raise VkApiError("Downloaded media file is empty")

        if not content_type:
            raise VkApiError("Downloaded media file has no content type")

        expected_prefixes = (
            (expected_content_types,)
            if isinstance(expected_content_types, str)
            else expected_content_types
        )
        if not any(content_type.lower().startswith(prefix.lower()) for prefix in expected_prefixes):
            joined = ", ".join(expected_prefixes)
            raise VkApiError(f"URL content type {content_type} is not supported, expected {joined}")

        return content, content_type, _filename_from_url(source_url, content_type)

    async def _upload_file(
        self,
        upload_url: str,
        field_name: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        """Upload a media file to a VK upload URL."""

        form = FormData()
        form.add_field(field_name, content, filename=filename, content_type=content_type)

        timeout = ClientTimeout(total=self._config.request_timeout)
        try:
            async with self._session.post(upload_url, data=form, timeout=timeout) as response:
                if response.status >= 400:
                    raise VkApiError(f"Upload failed ({await _summarize_response(response)})")
                payload = await response.json(content_type=None)
        except (ClientError, asyncio.TimeoutError) as err:
            raise VkApiError("Failed to upload media to VK") from err

        if not isinstance(payload, dict):
            raise VkApiError("Upload response from VK is invalid")

        return payload

    async def _api_call(self, method: str, token: str, **params: Any) -> Any:
        """Call a VK API method and return its `response` payload."""

        payload = {
            "access_token": token,
            "v": self._config.api_version,
        }
        payload.update({key: value for key, value in params.items() if value is not None})

        timeout = ClientTimeout(total=self._config.request_timeout)
        try:
            async with self._session.post(
                f"{VK_API_BASE}/{method}",
                data=payload,
                timeout=timeout,
            ) as response:
                if response.status >= 400:
                    raise VkApiError(f"{method}: {await _summarize_response(response)}")
                payload = await response.json(content_type=None)
        except (ClientError, asyncio.TimeoutError) as err:
            raise VkApiError(f"{method}: network error") from err

        if not isinstance(payload, dict):
            raise VkApiError(f"{method}: invalid response from VK")

        error = payload.get("error")
        if error:
            message = error.get("error_msg", "Unknown VK API error")
            raise VkApiError(f"{method}: {message}")

        if "response" not in payload:
            raise VkApiError(f"{method}: missing response payload")

        return payload["response"]


def _filename_from_url(source_url: str, content_type: str) -> str:
    """Build a usable filename from a source URL and response content type."""

    name = Path(urlparse(source_url).path).name or "file"
    if "." not in name:
        extension = mimetypes.guess_extension(content_type)
        if extension:
            name = f"{name}{extension}"
    return name


def _build_attachment(prefix: str, owner_id: Any, item_id: Any, access_key: str | None) -> str:
    """Build a VK attachment string."""

    attachment = f"{prefix}{owner_id}_{item_id}"
    if access_key:
        attachment = f"{attachment}_{access_key}"
    return attachment


def _photo_attachment(photo_info: dict[str, Any]) -> str:
    """Build an attachment string for a VK photo."""

    owner_id = photo_info.get("owner_id")
    photo_id = photo_info.get("id") or photo_info.get("photo_id")
    if owner_id is None or photo_id is None:
        raise VkApiError("Invalid photo data from VK API")
    return _build_attachment("photo", owner_id, photo_id, photo_info.get("access_key"))


def _extract_doc_info(save_response: Any) -> dict[str, Any]:
    """Normalize document save response shapes from VK."""

    if isinstance(save_response, dict) and "doc" in save_response:
        return save_response["doc"]
    if isinstance(save_response, dict) and save_response.get("type") == "doc" and "doc" in save_response:
        return save_response["doc"]
    if isinstance(save_response, list):
        return _first_item(save_response, "document")
    raise VkApiError("Invalid document data from VK API")


def _first_item(value: Any, label: str) -> dict[str, Any]:
    """Return the first dictionary item from a VK list response."""

    if not isinstance(value, list) or not value:
        raise VkApiError(f"Invalid {label} data from VK API")
    item = value[0]
    if not isinstance(item, dict):
        raise VkApiError(f"Invalid {label} data from VK API")
    return item


async def _summarize_response(response: ClientResponse) -> str:
    """Build a compact error description for a HTTP response."""

    content_type = response.headers.get("Content-Type", "unknown")
    text = (await response.text()).strip()
    if text:
        text = " ".join(text.split())
        if len(text) > 200:
            text = f"{text[:200]}..."
        return f"HTTP {response.status}, content-type {content_type}, body: {text}"
    return f"HTTP {response.status}, content-type {content_type}"
