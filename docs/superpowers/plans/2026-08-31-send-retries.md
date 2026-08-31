# Send Retries Implementation Plan

> **Note:** во время выполнения план был дополнен по итогам код-ревью
> (потолок бэкоффа `SEND_RETRY_MAX_DELAY`, `guid` для `wall.post`,
> санитизация лога, `max=10` в селекторе, валидация с `send_retries=0`).
> Актуальное описание — в спеке `docs/superpowers/specs/2026-08-31-send-retries-design.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retry all network steps of VK message/post sending on transient network errors, with a configurable retry count (issue #11).

**Architecture:** A private `_with_retries()` helper in `VkClient` wraps the HTTP portion of the three network primitives (`_api_call`, `_download_file`, `_upload_file`). Only transport errors (`TimeoutError`, `aiohttp.ClientError`) are retried with exponential backoff (1s → 2s → 4s). A new `send_retries` option (default 3, 0 = disabled) is added to the config/options flow.

**Tech Stack:** Python 3.13, aiohttp, Home Assistant custom component, pytest + pytest-homeassistant-custom-component.

**Spec:** `docs/superpowers/specs/2026-08-31-send-retries-design.md`

**Test command:** `python -m pytest` (from repo root, uv venv activated; per-file: `python -m pytest tests/test_api.py -v`)

---

## File map

- Modify: `custom_components/ha_vk/const.py` — constants `CONF_SEND_RETRIES`, `DEFAULT_SEND_RETRIES`, `SEND_RETRY_BACKOFF_BASE`
- Modify: `custom_components/ha_vk/api.py` — config field + parsing, `_with_retries` helper, wiring into `_api_call` / `_download_file` / `_upload_file`
- Modify: `custom_components/ha_vk/config_flow.py` — schema field + options persistence
- Modify: `custom_components/ha_vk/strings.json`, `translations/en.json`, `translations/ru.json` — field labels
- Modify: `tests/test_api.py`, `tests/test_config_flow.py` — new tests
- Modify: `README.md`, `README.en.md`, `CHANGELOG.md` — docs

---

### Task 1: `send_retries` config field and parsing

**Files:**
- Modify: `custom_components/ha_vk/const.py`
- Modify: `custom_components/ha_vk/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py` (note: `VkConfigError` must be added to the existing import from `custom_components.ha_vk.api`):

```python
def test_build_client_config_parses_send_retries() -> None:
    """send_retries should be parsed as a non-negative integer."""

    config = build_client_config(
        {
            "vk_access_token": "token",
            "vk_peer_id": "1",
            "send_retries": "5",
        }
    )

    assert config.send_retries == 5


def test_build_client_config_defaults_send_retries() -> None:
    """send_retries should default to 3 when absent."""

    config = build_client_config(
        {
            "vk_access_token": "token",
            "vk_peer_id": "1",
        }
    )

    assert config.send_retries == 3


def test_build_client_config_rejects_invalid_send_retries() -> None:
    """Negative or non-numeric send_retries should raise VkConfigError."""

    base = {"vk_access_token": "token", "vk_peer_id": "1"}

    with pytest.raises(VkConfigError, match="Send retries"):
        build_client_config({**base, "send_retries": -1})

    with pytest.raises(VkConfigError, match="Send retries"):
        build_client_config({**base, "send_retries": "abc"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -k send_retries -v`
Expected: FAIL — `VkClientConfig` has no attribute `send_retries` (and NameError/ImportError for `VkConfigError` until the import is added).

- [ ] **Step 3: Implement constants and parsing**

In `custom_components/ha_vk/const.py`, add after `CONF_REQUEST_TIMEOUT = "request_timeout"`:

```python
CONF_SEND_RETRIES = "send_retries"
```

and after `DEFAULT_REQUEST_TIMEOUT = 30.0`:

```python
DEFAULT_SEND_RETRIES = 3
SEND_RETRY_BACKOFF_BASE = 1.0
```

In `custom_components/ha_vk/api.py`:

1. Extend the `.const` import:

```python
from .const import (
    DEFAULT_API_VERSION,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SEND_RETRIES,
    SEND_TYPE_DOCUMENT,
    SEND_TYPE_VIDEO,
)
```

(`SEND_RETRY_BACKOFF_BASE` and `LOGGER` are imported in Task 2.)

2. Add a field to `VkClientConfig` after `request_timeout`:

```python
    send_retries: int = DEFAULT_SEND_RETRIES
```

3. In `build_client_config`, after the `request_timeout = _parse_float(...)` block, add:

```python
    send_retries_raw = data.get("send_retries", DEFAULT_SEND_RETRIES)
    try:
        send_retries = int(float(send_retries_raw))
    except (TypeError, ValueError) as err:
        raise VkConfigError("Send retries must be an integer") from err
    if send_retries < 0:
        raise VkConfigError("Send retries must be zero or greater")
```

and pass it in the returned config:

```python
    return VkClientConfig(
        access_token=access_token,
        peer_id=peer_id,
        enable_incoming_messages=bool(data.get("enable_incoming_messages", False)),
        wall_access_token=wall_access_token,
        group_id=group_id,
        api_version=api_version,
        request_timeout=request_timeout,
        send_retries=send_retries,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_vk/const.py custom_components/ha_vk/api.py tests/test_api.py
git commit -m "feat: add send_retries client config option (#11)"
```

---

### Task 2: Retry helper and `_api_call` wiring

**Files:**
- Modify: `custom_components/ha_vk/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_api.py`, extend the mock import line to include `patch`:

```python
from unittest.mock import AsyncMock, Mock, patch
```

Append the tests:

```python
@pytest.mark.asyncio
async def test_api_call_retries_network_errors_until_success() -> None:
    """Transport failures should be retried with exponential backoff."""

    session = Mock()
    session.post = Mock(
        side_effect=[ClientError(), ClientError(), MockAsyncResponse({"response": 1})]
    )
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, send_retries=3))

    with patch("custom_components.ha_vk.api.asyncio.sleep", new_callable=AsyncMock) as sleep:
        result = await client._api_call("messages.send", token="token")

    assert result == 1
    assert session.post.call_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [1.0, 2.0]


@pytest.mark.asyncio
async def test_api_call_raises_network_error_after_exhausting_retries() -> None:
    """After send_retries extra attempts the original VkNetworkError should surface."""

    session = Mock()
    session.post = Mock(side_effect=ClientError())
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, send_retries=2))

    with (
        patch("custom_components.ha_vk.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(VkNetworkError),
    ):
        await client._api_call("messages.send", token="token")

    assert session.post.call_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [1.0, 2.0]


@pytest.mark.asyncio
async def test_api_call_does_not_retry_vk_api_errors() -> None:
    """Logical VK errors (error payload) should not be retried."""

    session = Mock()
    session.post = Mock(
        return_value=MockAsyncResponse({"error": {"error_code": 100, "error_msg": "Bad params"}})
    )
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, send_retries=3))

    with (
        patch("custom_components.ha_vk.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(VkApiError),
    ):
        await client._api_call("messages.send", token="token")

    assert session.post.call_count == 1
    sleep.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_call_with_zero_retries_makes_single_attempt() -> None:
    """send_retries=0 should keep the current single-attempt behavior."""

    session = Mock()
    session.post = Mock(side_effect=ClientError())
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, send_retries=0))

    with (
        patch("custom_components.ha_vk.api.asyncio.sleep", new_callable=AsyncMock) as sleep,
        pytest.raises(VkNetworkError),
    ):
        await client._api_call("messages.send", token="token")

    assert session.post.call_count == 1
    sleep.assert_not_awaited()
```

Also update the existing `test_api_call_raises_network_error` (it uses the default config, which now retries — without patching it would really sleep 1+2+4 seconds):

```python
@pytest.mark.asyncio
async def test_api_call_raises_network_error() -> None:
    """Transport failures should raise VkNetworkError."""

    session = Mock()
    session.post = Mock(side_effect=ClientError())
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, send_retries=0))

    with pytest.raises(VkNetworkError):
        await client._api_call("users.get", token="token")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -k "retri or retry or zero_retries" -v`
Expected: new tests FAIL (`session.post.call_count == 3` is 1, no sleep calls / `AttributeError` patching `asyncio` if the module doesn't import it yet).

- [ ] **Step 3: Implement `_with_retries` and rewire `_api_call`**

In `custom_components/ha_vk/api.py`:

1. Add `import asyncio` at the top (after `from __future__ import annotations`, with the other stdlib imports) and extend the typing import:

```python
import asyncio
import mimetypes
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
```

2. Extend the `.const` import:

```python
from .const import (
    DEFAULT_API_VERSION,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SEND_RETRIES,
    LOGGER,
    SEND_RETRY_BACKOFF_BASE,
    SEND_TYPE_DOCUMENT,
    SEND_TYPE_VIDEO,
)
```

3. Add the helper method to `VkClient`, right above `_api_call`:

```python
    async def _with_retries(self, label: str, request: Callable[[], Awaitable[Any]]) -> Any:
        """Run a network request, retrying transport failures with backoff."""

        attempts = self._config.send_retries + 1
        for attempt in range(attempts):
            try:
                return await request()
            except (TimeoutError, ClientError):
                if attempt + 1 >= attempts:
                    raise
                delay = SEND_RETRY_BACKOFF_BASE * 2**attempt
                LOGGER.warning(
                    "%s: network error, retry %d/%d in %.0fs",
                    label,
                    attempt + 1,
                    attempts - 1,
                    delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")  # pragma: no cover
```

4. Replace the body of `_api_call` after the `payload.update(...)` line with:

```python
        timeout = ClientTimeout(total=self._config.request_timeout)

        async def _request() -> Any:
            async with self._session.post(
                f"{VK_API_BASE}/{method}",
                data=payload,
                timeout=timeout,
            ) as response:
                if response.status >= 400:
                    raise VkApiError(f"{method}: {await _summarize_response(response)}")
                return await response.json(content_type=None)

        try:
            data = await self._with_retries(method, _request)
        except (TimeoutError, ClientError) as err:
            raise VkNetworkError(f"{method}: network error") from err
```

The remainder of `_api_call` (the `isinstance` check, `error` handling, and `response` extraction) stays unchanged.

- [ ] **Step 4: Run the full API test file**

Run: `python -m pytest tests/test_api.py -v`
Expected: all PASS (including the pre-existing long poll and auth error tests — long poll uses `session.get` directly and must NOT gain retries).

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_vk/api.py tests/test_api.py
git commit -m "feat: retry VK API calls on network errors with backoff (#11)"
```

---

### Task 3: Retries for media download and upload

**Files:**
- Modify: `custom_components/ha_vk/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Extend the response mock and write the failing tests**

Replace the `MockAsyncResponse.__init__` and add a `read` method in `tests/test_api.py` so the class becomes:

```python
class MockAsyncResponse:
    """Small async context manager for mocked aiohttp responses."""

    def __init__(
        self,
        payload=None,
        status: int = 200,
        content_type: str = "application/json",
        body: bytes = b"",
    ) -> None:
        self._payload = payload
        self._body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def json(self, content_type=None):
        return self._payload

    async def read(self):
        return self._body

    async def text(self):
        return str(self._payload)
```

(Existing tests keep passing: the defaults match the old behavior, `payload` stays the first positional argument.)

Append the tests:

```python
@pytest.mark.asyncio
async def test_download_file_retries_network_errors() -> None:
    """Media downloads should be retried on transport failures."""

    session = Mock()
    session.get = Mock(
        side_effect=[
            ClientError(),
            MockAsyncResponse(content_type="image/jpeg", body=b"img"),
        ]
    )
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, send_retries=1))

    with patch("custom_components.ha_vk.api.asyncio.sleep", new_callable=AsyncMock) as sleep:
        content, content_type, filename = await client._download_file(
            "http://example.com/pic.jpg",
            "image/",
        )

    assert content == b"img"
    assert content_type == "image/jpeg"
    assert filename == "pic.jpg"
    assert session.get.call_count == 2
    sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_upload_file_retries_network_errors() -> None:
    """Uploads to VK upload servers should be retried on transport failures."""

    session = Mock()
    session.post = Mock(side_effect=[TimeoutError(), MockAsyncResponse({"photo": "data"})])
    client = VkClient(session, VkClientConfig(access_token="token", peer_id=1, send_retries=1))

    with patch("custom_components.ha_vk.api.asyncio.sleep", new_callable=AsyncMock) as sleep:
        payload = await client._upload_file(
            "http://upload.example.com",
            field_name="photo",
            filename="pic.jpg",
            content=b"img",
            content_type="image/jpeg",
        )

    assert payload == {"photo": "data"}
    assert session.post.call_count == 2
    sleep.assert_awaited_once_with(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -k "download_file_retries or upload_file_retries" -v`
Expected: FAIL — download/upload raise `VkApiError` after the first `ClientError`/`TimeoutError` instead of retrying.

- [ ] **Step 3: Wire `_with_retries` into `_download_file` and `_upload_file`**

In `custom_components/ha_vk/api.py`, replace the `try:` block of `_download_file` (keeping everything from `if not content:` down unchanged):

```python
        timeout = ClientTimeout(total=self._config.request_timeout)

        async def _request() -> tuple[bytes, str]:
            async with self._session.get(
                source_url,
                timeout=timeout,
                allow_redirects=True,
            ) as response:
                if response.status >= 400:
                    raise VkApiError(f"Failed to download file ({await _summarize_response(response)})")
                downloaded = await response.read()
                return downloaded, response.headers.get("Content-Type", "").split(";")[0].strip()

        try:
            content, content_type = await self._with_retries(f"download {source_url}", _request)
        except (TimeoutError, ClientError) as err:
            raise VkApiError("Failed to download media file") from err
```

Replace the `try:` block of `_upload_file` (keeping the `FormData` setup and the trailing `isinstance` check unchanged):

```python
        timeout = ClientTimeout(total=self._config.request_timeout)

        async def _request() -> Any:
            async with self._session.post(upload_url, data=form, timeout=timeout) as response:
                if response.status >= 400:
                    raise VkApiError(f"Upload failed ({await _summarize_response(response)})")
                return await response.json(content_type=None)

        try:
            payload = await self._with_retries("upload to VK", _request)
        except (TimeoutError, ClientError) as err:
            raise VkApiError("Failed to upload media to VK") from err
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_vk/api.py tests/test_api.py
git commit -m "feat: retry media download/upload on network errors (#11)"
```

---

### Task 4: Config flow option and translations

**Files:**
- Modify: `custom_components/ha_vk/config_flow.py`
- Modify: `custom_components/ha_vk/strings.json`
- Modify: `custom_components/ha_vk/translations/en.json`
- Modify: `custom_components/ha_vk/translations/ru.json`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_config_flow.py`, extend the `.const` import with `CONF_SEND_RETRIES` and `DEFAULT_SEND_RETRIES`:

```python
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
```

In `test_user_flow_creates_entry`, add to `user_input`:

```python
        CONF_SEND_RETRIES: DEFAULT_SEND_RETRIES,
```

and add an assertion at the end:

```python
    assert result["options"][CONF_SEND_RETRIES] == DEFAULT_SEND_RETRIES
```

In `test_options_flow_updates_options`, add to the `user_input` of `async_configure`:

```python
                CONF_SEND_RETRIES: 5,
```

and add an assertion after `assert result["data"][CONF_VK_WALL_ACCESS_TOKEN] == "new"`:

```python
    assert result["data"][CONF_SEND_RETRIES] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config_flow.py -v`
Expected: FAIL — `KeyError: 'send_retries'` (option not persisted by `_entry_options`).

- [ ] **Step 3: Implement the option in the flow**

In `custom_components/ha_vk/config_flow.py`:

1. Extend the `.const` import with `CONF_SEND_RETRIES` and `DEFAULT_SEND_RETRIES` (alphabetical order, matching the existing style).

2. In `_build_schema`, add after the `CONF_REQUEST_TIMEOUT` field:

```python
            vol.Required(
                CONF_SEND_RETRIES,
                default=values.get(CONF_SEND_RETRIES, DEFAULT_SEND_RETRIES),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
```

3. In `_entry_options`, add after the `CONF_REQUEST_TIMEOUT` line:

```python
        CONF_SEND_RETRIES: int(user_input.get(CONF_SEND_RETRIES, DEFAULT_SEND_RETRIES)),
```

4. In `custom_components/ha_vk/strings.json` and `custom_components/ha_vk/translations/en.json`, add after every `"request_timeout": "Request timeout"` line (both `config.step.user.data` and `options.step.init.data`):

```json
          "send_retries": "Send retries on network errors"
```

(mind the comma on the previous line).

5. In `custom_components/ha_vk/translations/ru.json`, add after every `"request_timeout": "Таймаут запроса"` line (both sections):

```json
          "send_retries": "Повторы отправки при сбоях сети"
```

- [ ] **Step 4: Run the config flow and full suites**

Run: `python -m pytest tests/test_config_flow.py -v && python -m pytest`
Expected: all PASS.

Also verify the JSON files parse:

Run: `python -c "import json,glob; [json.load(open(p)) for p in ['custom_components/ha_vk/strings.json'] + glob.glob('custom_components/ha_vk/translations/*.json')]; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_vk/config_flow.py custom_components/ha_vk/strings.json custom_components/ha_vk/translations/en.json custom_components/ha_vk/translations/ru.json tests/test_config_flow.py
git commit -m "feat: expose send_retries in config and options flow (#11)"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Document the new option**

In `README.md`, after the line ``- `Request timeout`: по умолчанию `30` `` add:

```markdown
- `Send retries on network errors`: число повторов при сетевых ошибках, по умолчанию `3` (значение `0` отключает повторы)
```

In `README.en.md`, after the line ``- `Request timeout`: defaults to `30` `` add:

```markdown
- `Send retries on network errors`: retry count for transient network errors, defaults to `3` (`0` disables retries)
```

In `CHANGELOG.md`, add to the `## Unreleased` → `### Добавлено` list:

```markdown
- Повторы отправки при сетевых ошибках с экспоненциальным backoff (1с → 2с → 4с): ретраятся вызовы VK API, скачивание медиа и загрузка на upload-серверы. Количество повторов настраивается опцией `Send retries on network errors` (по умолчанию 3, 0 — отключено). (#11)
```

- [ ] **Step 2: Run linters/tests one last time**

Run: `python -m pytest`
Expected: all PASS.

If the repo lint job is configured locally, also run: `ruff check custom_components tests`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add README.md README.en.md CHANGELOG.md
git commit -m "docs: document send retries option (#11)"
```
