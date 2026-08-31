# VK Command Support Implementation Plan (issue #10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse `/command arg1 arg2` texts in incoming VK messages and fire a dedicated `ha_vk_command` Home Assistant event with pre-parsed `command`/`args` fields.

**Architecture:** A pure `parse_command()` function in `custom_components/ha_vk/receiver.py` recognizes command texts; `VkIncomingMessageReceiver._process_updates` fires `ha_vk_command` right after the existing `ha_vk_incoming_message` event for the same message. No new config options; the existing event keeps firing for every message (backward compatible).

**Tech Stack:** Python 3.13, Home Assistant custom component, pytest + pytest-homeassistant-custom-component.

**Spec:** `docs/superpowers/specs/2026-08-31-vk-commands-design.md`

**Environment:** run tests as `.venv/bin/python -m pytest -q`, lint as `.venv/bin/ruff check custom_components tests`. Work happens on branch `feature/issue-10-commands`.

---

### Task 1: `parse_command` function

**Files:**
- Modify: `custom_components/ha_vk/receiver.py` (add function near the top, after imports)
- Test: `tests/test_receiver.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_receiver.py`:

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "/light kitchen off",
            {"command": "light", "args": ["kitchen", "off"], "args_text": "kitchen off"},
        ),
        ("/ping", {"command": "ping", "args": [], "args_text": ""}),
        (
            "  /Light   Kitchen   OFF  ",
            {"command": "light", "args": ["Kitchen", "OFF"], "args_text": "Kitchen   OFF"},
        ),
        (
            "/say Привет мир",
            {"command": "say", "args": ["Привет", "мир"], "args_text": "Привет мир"},
        ),
    ],
)
def test_parse_command_valid(text: str, expected: dict) -> None:
    """Command texts should be parsed into command, args and args_text."""

    assert parse_command(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "/", "/ foo", "hello", "light kitchen off"])
def test_parse_command_not_a_command(text: str) -> None:
    """Non-command texts should return None."""

    assert parse_command(text) is None
```

Also extend the receiver import at the top of `tests/test_receiver.py`:

```python
from custom_components.ha_vk.receiver import VkIncomingMessageReceiver, parse_command
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_receiver.py -q`
Expected: FAIL (ImportError: cannot import name 'parse_command')

- [ ] **Step 3: Write the implementation**

In `custom_components/ha_vk/receiver.py`, after the imports block, add:

```python
COMMAND_PREFIX = "/"


def parse_command(text: str) -> dict[str, object] | None:
    """Parse a "/command arg1 arg2" message text, or return None."""

    stripped = text.strip()
    body = stripped.removeprefix(COMMAND_PREFIX)
    if body == stripped or not body or body[0].isspace():
        return None

    tokens = body.split()
    return {
        "command": tokens[0].lower(),
        "args": tokens[1:],
        "args_text": body[len(tokens[0]) :].strip(),
    }
```

(Note: `body == stripped` means the prefix was absent; `body[0].isspace()` rejects `"/ foo"`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_receiver.py -q`
Expected: PASS (all tests, including the pre-existing receiver tests)

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check custom_components tests
git add custom_components/ha_vk/receiver.py tests/test_receiver.py
git commit -m "feat: add parse_command for VK command messages (#10)"
```

---

### Task 2: `ha_vk_command` event from the receiver

**Files:**
- Modify: `custom_components/ha_vk/const.py` (add constant near `INCOMING_EVENT`)
- Modify: `custom_components/ha_vk/receiver.py` (`_process_updates`, imports)
- Test: `tests/test_receiver.py` (append test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_receiver.py`:

```python
@pytest.mark.asyncio
async def test_receiver_emits_command_event(hass: HomeAssistant) -> None:
    """Command messages should fire both the incoming and the command event."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ha_vk.const import COMMAND_EVENT, DOMAIN

    client = VkClient(Mock(), VkClientConfig(access_token="token", peer_id=2000000123, group_id=42))
    client.async_get_long_poll_server = AsyncMock(  # type: ignore[method-assign]
        return_value=VkLongPollServer(server="https://lp.example.com", key="secret", ts="100")
    )
    client.async_check_long_poll = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            (
                VkLongPollServer(server="https://lp.example.com", key="secret", ts="101"),
                [{"type": "message_new"}, {"type": "message_new"}],
            ),
            asyncio.CancelledError(),
        ]
    )
    client.normalize_incoming_message_event = Mock(  # type: ignore[method-assign]
        side_effect=[
            {"peer_id": 2000000123, "from_id": 555, "text": "/light kitchen off"},
            {"peer_id": 2000000123, "from_id": 555, "text": "hello"},
        ]
    )

    incoming: list[Event] = []
    commands: list[Event] = []
    done = asyncio.Event()

    @callback
    def _handle_incoming(event: Event) -> None:
        incoming.append(event)
        if len(incoming) == 2:
            done.set()

    @callback
    def _handle_command(event: Event) -> None:
        commands.append(event)

    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-1")
    entry.add_to_hass(hass)

    unsub_incoming = hass.bus.async_listen(INCOMING_EVENT, _handle_incoming)
    unsub_command = hass.bus.async_listen(COMMAND_EVENT, _handle_command)
    receiver = VkIncomingMessageReceiver(hass, entry, client)

    try:
        await receiver.async_start()
        await asyncio.wait_for(done.wait(), timeout=1)
        await hass.async_block_till_done()
    finally:
        await receiver.async_stop()
        unsub_incoming()
        unsub_command()

    assert len(incoming) == 2
    assert len(commands) == 1
    data = commands[0].data
    assert data["entry_id"] == "entry-1"
    assert data["from_id"] == 555
    assert data["text"] == "/light kitchen off"
    assert data["command"] == "light"
    assert data["args"] == ["kitchen", "off"]
    assert data["args_text"] == "kitchen off"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_receiver.py::test_receiver_emits_command_event -q`
Expected: FAIL (ImportError: cannot import name 'COMMAND_EVENT' from custom_components.ha_vk.const)

- [ ] **Step 3: Write the implementation**

In `custom_components/ha_vk/const.py`, next to `INCOMING_EVENT`:

```python
COMMAND_EVENT = "ha_vk_command"
```

In `custom_components/ha_vk/receiver.py`, add `COMMAND_EVENT` to the `.const` import:

```python
from .const import (
    COMMAND_EVENT,
    DOMAIN,
    INCOMING_EVENT,
    LOGGER,
    LONG_POLL_MAX_RETRY_DELAY,
    LONG_POLL_RETRY_DELAY,
)
```

Replace the body of `_process_updates` with:

```python
    def _process_updates(self, updates: list[dict]) -> None:
        """Emit Home Assistant events for normalized incoming messages."""

        for event in updates:
            normalized = self._client.normalize_incoming_message_event(event)
            if normalized is None:
                continue

            payload = {"entry_id": self._entry.entry_id, **normalized}
            self._hass.bus.async_fire(INCOMING_EVENT, payload)

            text = normalized.get("text")
            parsed = parse_command(text) if isinstance(text, str) else None
            if parsed is not None:
                self._hass.bus.async_fire(COMMAND_EVENT, {**payload, **parsed})
```

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all tests)

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check custom_components tests
git add custom_components/ha_vk/const.py custom_components/ha_vk/receiver.py tests/test_receiver.py
git commit -m "feat: emit ha_vk_command event for /command messages (#10)"
```

---

### Task 3: Documentation

**Files:**
- Modify: `docs/examples.md` (after the `ha_vk_incoming_message` field list in the «Событие» section)
- Modify: `docs/examples.en.md` (same place in the English version)
- Modify: `README.md` and `README.en.md` (the incoming-messages section that documents `ha_vk_incoming_message` and its field list)

- [ ] **Step 1: Document the command event in `docs/examples.md`**

After the field list of `ha_vk_incoming_message` (the list ending with `raw_event`), insert:

```markdown
### Событие команды

Если текст сообщения начинается с `/`, дополнительно к `ha_vk_incoming_message`
публикуется событие:

```text
ha_vk_command
```

Оно содержит все поля `ha_vk_incoming_message` плюс:

- `command` — имя команды в нижнем регистре, например `light`
- `args` — список аргументов, например `["kitchen", "off"]`
- `args_text` — хвост строки после имени команды, например `kitchen off`

Например, сообщение `/light kitchen off` даёт `command: light`,
`args: ["kitchen", "off"]`.

Пример автоматизации:

```yaml
automation:
  - alias: Управление светом из VK
    mode: parallel
    trigger:
      - platform: event
        event_type: ha_vk_command
        event_data:
          command: light
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.args | length == 2 }}"
    action:
      - action: "light.turn_{{ trigger.event.data.args[1] }}"
        target:
          entity_id: "light.{{ trigger.event.data.args[0] }}"
```
```

- [ ] **Step 2: Document the command event in `docs/examples.en.md`**

Insert the equivalent English section at the same place:

```markdown
### Command event

If the message text starts with `/`, an additional event is fired next to
`ha_vk_incoming_message`:

```text
ha_vk_command
```

It contains every `ha_vk_incoming_message` field plus:

- `command` — lowercase command name, for example `light`
- `args` — argument list, for example `["kitchen", "off"]`
- `args_text` — the rest of the line after the command name, for example `kitchen off`

For example, the message `/light kitchen off` yields `command: light`,
`args: ["kitchen", "off"]`.

Automation example:

```yaml
automation:
  - alias: Control lights from VK
    mode: parallel
    trigger:
      - platform: event
        event_type: ha_vk_command
        event_data:
          command: light
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.args | length == 2 }}"
    action:
      - action: "light.turn_{{ trigger.event.data.args[1] }}"
        target:
          entity_id: "light.{{ trigger.event.data.args[0] }}"
```
```

- [ ] **Step 3: Mention the command event in both READMEs**

In `README.md`, in the incoming-messages section (after the `ha_vk_incoming_message` field list), add:

```markdown
Если текст сообщения начинается с `/`, дополнительно публикуется событие
`ha_vk_command` с полями `command`, `args` и `args_text` — см.
[примеры](docs/examples.md).
```

In `README.en.md`, at the same place, add:

```markdown
If the message text starts with `/`, an additional `ha_vk_command` event is
fired with `command`, `args` and `args_text` fields — see
[examples](docs/examples.en.md).
```

- [ ] **Step 4: Verify and commit**

Run: `.venv/bin/python -m pytest -q` — Expected: PASS.

```bash
git add docs/examples.md docs/examples.en.md README.md README.en.md
git commit -m "docs: document ha_vk_command event (#10)"
```
