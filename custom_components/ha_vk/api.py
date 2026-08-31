"""Async VK API client used by the Home Assistant integration."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout, FormData

from .const import (
    DEFAULT_API_VERSION,
    DEFAULT_REQUEST_TIMEOUT,
    SEND_TYPE_DOCUMENT,
    SEND_TYPE_VIDEO,
)

VK_API_BASE = "https://api.vk.com/method"
VK_LONG_POLL_MODE = 2
VK_LONG_POLL_VERSION = 10
VK_LONG_POLL_WAIT = 25


VK_ERROR_AUTH_FAILED = 5
VK_ERROR_ACCESS_DENIED = 15
VK_ERROR_GROUP_AUTH_FAILED = 27
VK_ERROR_APP_AUTH_FAILED = 28
VK_AUTH_ERROR_CODES = frozenset(
    {
        VK_ERROR_AUTH_FAILED,
        VK_ERROR_ACCESS_DENIED,
        VK_ERROR_GROUP_AUTH_FAILED,
        VK_ERROR_APP_AUTH_FAILED,
    }
)


class VkApiError(RuntimeError):
    """Raised when VK API returns an error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        """Initialize the error with an optional VK error code."""

        super().__init__(message)
        self.code = code


class VkAuthError(VkApiError):
    """Raised when VK rejects the used access token."""


class VkNetworkError(VkApiError):
    """Raised when VK is unreachable or the request times out."""


class VkLongPollError(VkApiError):
    """Raised when the long poll transport fails."""


class VkConfigError(RuntimeError):
    """Raised when integration configuration is invalid."""


def is_auth_error(err: VkApiError) -> bool:
    """Return True when the error indicates an invalid or expired token."""

    return isinstance(err, VkAuthError) or err.code in VK_AUTH_ERROR_CODES


@dataclass(slots=True, frozen=True)
class VkClientConfig:
    """Configuration required for VK operations."""

    access_token: str
    peer_id: int
    enable_incoming_messages: bool = False
    wall_access_token: str | None = None
    group_id: int | None = None
    api_version: str = DEFAULT_API_VERSION
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT


@dataclass(slots=True, frozen=True)
class VkLongPollServer:
    """Connection parameters for VK group long poll."""

    server: str
    key: str
    ts: str

    def with_ts(self, ts: Any) -> VkLongPollServer:
        """Return a new server state with an updated ts cursor."""

        return replace(self, ts=str(ts))


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
        enable_incoming_messages=bool(data.get("enable_incoming_messages", False)),
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


def _coerce_int(value: Any, default: int | None = None) -> int | None:
    """Best-effort conversion for optional integer values."""

    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def format_service_message(message: str | None = None, title: str | None = None) -> str:
    """Format an optional message body for media service calls."""

    body = (message or "").strip()
    heading = title.strip() if title else ""

    if heading and body:
        return f"{heading}\n{body}"
    if heading:
        return heading
    return body


class VkClient:
    """Small async wrapper over the VK HTTP API."""

    def __init__(self, session: ClientSession, config: VkClientConfig) -> None:
        """Initialize the client."""

        self._session = session
        self._config = config

    @property
    def supports_incoming_messages(self) -> bool:
        """Return True when the config can listen for incoming messages."""

        return self._config.enable_incoming_messages and self._config.group_id is not None

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
        if self._config.enable_incoming_messages:
            await self.async_get_long_poll_server()
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

    async def async_get_long_poll_server(self) -> VkLongPollServer:
        """Fetch long poll connection parameters for the configured community."""

        if self._config.group_id is None:
            raise VkConfigError("VK group ID is required for incoming messages")

        try:
            response = await self._api_call(
                "groups.getLongPollServer",
                token=self._config.access_token,
                group_id=self._config.group_id,
            )
        except VkLongPollError:
            raise
        except VkApiError as err:
            raise VkLongPollError(str(err), code=err.code) from err
        if not isinstance(response, dict):
            raise VkLongPollError("groups.getLongPollServer: invalid response from VK")

        try:
            server = str(response["server"]).strip()
            key = str(response["key"]).strip()
            ts = str(response["ts"]).strip()
        except KeyError as err:
            raise VkLongPollError("groups.getLongPollServer: missing long poll data") from err

        if not server or not key or not ts:
            raise VkLongPollError("groups.getLongPollServer: invalid long poll data")

        return VkLongPollServer(server=server, key=key, ts=ts)

    async def async_check_long_poll(
        self,
        server: VkLongPollServer,
    ) -> tuple[VkLongPollServer, list[dict[str, Any]]]:
        """Read one batch of long poll updates."""

        timeout = ClientTimeout(total=self._config.request_timeout + VK_LONG_POLL_WAIT + 5)
        try:
            async with self._session.get(
                server.server,
                params={
                    "act": "a_check",
                    "key": server.key,
                    "ts": server.ts,
                    "wait": VK_LONG_POLL_WAIT,
                    "mode": VK_LONG_POLL_MODE,
                    "version": VK_LONG_POLL_VERSION,
                },
                timeout=timeout,
            ) as response:
                if response.status >= 400:
                    raise VkLongPollError(f"VK long poll: {await _summarize_response(response)}")
                payload = await response.json(content_type=None)
        except (TimeoutError, ClientError) as err:
            raise VkLongPollError("VK long poll: network error") from err

        if not isinstance(payload, dict):
            raise VkLongPollError("VK long poll: invalid response from VK")

        failed = payload.get("failed")
        if failed is not None:
            try:
                failed_code = int(failed)
            except (TypeError, ValueError) as err:
                raise VkLongPollError("VK long poll: invalid failure code") from err

            if failed_code == 1:
                ts = payload.get("ts")
                if ts is None:
                    raise VkLongPollError("VK long poll: missing ts after failed=1")
                return server.with_ts(ts), []

            if failed_code in (2, 3):
                return await self.async_get_long_poll_server(), []

            raise VkLongPollError(f"VK long poll: failed={failed_code}")

        updates = payload.get("updates")
        ts = payload.get("ts")
        if not isinstance(updates, list) or ts is None:
            raise VkLongPollError("VK long poll: missing updates payload")

        normalized_updates = [item for item in updates if isinstance(item, dict)]
        return server.with_ts(ts), normalized_updates

    def normalize_incoming_message_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize a VK message_new event for Home Assistant automations."""

        if event.get("type") != "message_new":
            return None

        event_object = event.get("object")
        if not isinstance(event_object, dict):
            return None

        message = event_object.get("message", event_object)
        if not isinstance(message, dict):
            return None

        peer_id = _coerce_int(message.get("peer_id"))
        if peer_id is None or peer_id != self._config.peer_id:
            return None

        if _coerce_int(message.get("out"), default=0) != 0:
            return None

        attachments = message.get("attachments")
        if not isinstance(attachments, list):
            attachments = []

        text = message.get("text")
        return {
            "group_id": _coerce_int(event.get("group_id"), self._config.group_id),
            "peer_id": peer_id,
            "from_id": _coerce_int(message.get("from_id")),
            "conversation_message_id": _coerce_int(message.get("conversation_message_id")),
            "message_id": _coerce_int(message.get("id")),
            "event_id": event.get("event_id"),
            "date": _coerce_int(message.get("date")),
            "text": text if isinstance(text, str) else "",
            "attachments": attachments,
            "raw_event": event,
        }

    async def async_send_message(
        self,
        message: str | None = None,
        title: str | None = None,
        image_url: str | None = None,
        video_url: str | None = None,
        send_type: str = SEND_TYPE_VIDEO,
    ) -> dict[str, Any]:
        """Send a plain text message or a message with media."""

        if image_url and video_url:
            raise VkApiError("Only one of image_url or video_url can be provided")

        if image_url or video_url:
            attachment = (
                await self._upload_message_image(image_url)
                if image_url
                else await self._upload_video_attachment(video_url, send_type)
            )
            return await self._send_attachment(attachment, format_service_message(message, title))

        payload = {
            "peer_id": self._config.peer_id,
            "random_id": 0,
            "message": format_notify_message(message or "", title),
        }
        response = await self._api_call("messages.send", token=self._config.access_token, **payload)
        return {"response": response}

    async def _upload_message_image(self, image_url: str) -> str:
        """Upload an image and return its VK attachment identifier."""

        return await self._upload_photo_attachment(
            image_url,
            token=self._config.access_token,
            get_server_method="photos.getMessagesUploadServer",
            save_method="photos.saveMessagesPhoto",
            server_params={"peer_id": self._config.peer_id},
        )

    async def async_send_video(
        self,
        video_url: str,
        send_type: str,
    ) -> dict[str, Any]:
        """Download a video and send it as a VK video or document."""

        return await self._send_attachment(await self._upload_video_attachment(video_url, send_type))

    async def _upload_video_attachment(
        self,
        video_url: str,
        send_type: str,
    ) -> str:
        """Upload a video and return its VK attachment identifier."""

        content, content_type, filename = await self._download_file(
            video_url,
            ("video/", "application/octet-stream"),
        )

        upload_token = self._config.wall_access_token
        if send_type == SEND_TYPE_DOCUMENT or not upload_token:
            return await self._save_video_document_attachment(content, content_type, filename)

        try:
            return await self._save_video_attachment(
                upload_token,
                content,
                content_type,
                filename,
            )
        except VkAuthError as err:
            if err.code == VK_ERROR_GROUP_AUTH_FAILED:
                return await self._save_video_document_attachment(content, content_type, filename)
            raise VkAuthError("VK wall access token is invalid", code=err.code) from err

    async def async_send_post(self, message: str, image_url: str | None = None) -> dict[str, Any]:
        """Create a wall post, optionally with an uploaded image."""

        if self._config.group_id is None:
            raise VkConfigError("VK group ID is required for wall posts")

        attachments = None
        token = self._config.wall_access_token or self._config.access_token
        if image_url and self._config.wall_access_token:
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

        return await self._upload_photo_attachment(
            image_url,
            token=token,
            get_server_method="photos.getWallUploadServer",
            save_method="photos.saveWallPhoto",
            server_params={"group_id": self._config.group_id},
            save_params={"group_id": self._config.group_id},
        )

    async def _upload_photo_attachment(
        self,
        image_url: str,
        token: str,
        get_server_method: str,
        save_method: str,
        server_params: dict[str, Any],
        save_params: dict[str, Any] | None = None,
    ) -> str:
        """Download a photo, push it through a VK upload server, and save it."""

        content, content_type, filename = await self._download_file(image_url, "image/")
        upload = await self._api_call(get_server_method, token=token, **server_params)
        upload_response = await self._upload_file(
            upload["upload_url"],
            field_name="photo",
            filename=filename,
            content=content,
            content_type=content_type,
        )
        photos = await self._api_call(
            save_method,
            token=token,
            **(save_params or {}),
            **upload_response,
        )
        return _photo_attachment(_first_item(photos, "photo"))

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

    async def _save_video_document_attachment(
        self,
        content: bytes,
        content_type: str,
        filename: str,
    ) -> str:
        """Upload a video as a document and return its VK attachment identifier."""

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
        return _build_attachment("doc", owner_id, doc_id, doc_info.get("access_key"))

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
        except (TimeoutError, ClientError) as err:
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
        except (TimeoutError, ClientError) as err:
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
                data = await response.json(content_type=None)
        except (TimeoutError, ClientError) as err:
            raise VkNetworkError(f"{method}: network error") from err

        if not isinstance(data, dict):
            raise VkApiError(f"{method}: invalid response from VK")

        error = data.get("error")
        if error:
            message = error.get("error_msg", "Unknown VK API error")
            code = _coerce_int(error.get("error_code"))
            if code in VK_AUTH_ERROR_CODES:
                raise VkAuthError(f"{method}: {message}", code=code)
            raise VkApiError(f"{method}: {message}", code=code)

        if "response" not in data:
            raise VkApiError(f"{method}: missing response payload")

        return data["response"]


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
