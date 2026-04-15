# ha-vk Examples

This page collects practical examples for `ha-vk`, especially for incoming VK community messages and Home Assistant automations.

## Event Reference

Incoming community messages are emitted as the Home Assistant event:

```text
ha_vk_incoming_message
```

Common event fields:

- `entry_id`
- `group_id`
- `peer_id`
- `from_id`
- `conversation_message_id`
- `message_id`
- `event_id`
- `date`
- `text`
- `attachments`
- `raw_event`

## Common Use Cases

- Simple bot commands such as `/ping`, `/status`, `/help`
- Alarm control from VK chat
- Camera snapshots and motion clips on demand
- Notifications with interactive follow-up commands
- Access control with a sender allowlist
- Separate automations for multiple VK communities or chats
- Logging or archiving incoming messages inside Home Assistant

## 1. Minimal Incoming Message Logger

```yaml
automation:
  - alias: Log incoming VK message
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message
    action:
      - action: logbook.log
        data:
          name: VK
          message: "{{ trigger.event.data.text }}"
```

## 2. Simple Command Replies

```yaml
automation:
  - alias: VK command replies
    mode: parallel
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message

    variables:
      entry_id: "{{ trigger.event.data.entry_id }}"
      text: "{{ trigger.event.data.text | default('') | trim | lower }}"

    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ text == '/ping' }}"
            sequence:
              - action: ha_vk.send_message
                data:
                  entry_id: "{{ entry_id }}"
                  message: "pong"

          - conditions:
              - condition: template
                value_template: "{{ text == '/help' }}"
            sequence:
              - action: ha_vk.send_message
                data:
                  entry_id: "{{ entry_id }}"
                  message: "Available commands: /ping, /status, /photo, /video"
```

## 3. Alarm Control

```yaml
automation:
  - alias: VK alarm control
    mode: parallel
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message

    variables:
      entry_id: "{{ trigger.event.data.entry_id }}"
      text: "{{ trigger.event.data.text | default('') | trim | lower }}"
      alarm_entity: alarm_control_panel.home_alarm

    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ text == '/arm' }}"
            sequence:
              - action: alarm_control_panel.alarm_arm_away
                target:
                  entity_id: "{{ alarm_entity }}"
              - action: ha_vk.send_message
                data:
                  entry_id: "{{ entry_id }}"
                  message: "Alarm armed"

          - conditions:
              - condition: template
                value_template: "{{ text == '/disarm' }}"
            sequence:
              - action: alarm_control_panel.alarm_disarm
                target:
                  entity_id: "{{ alarm_entity }}"
                data:
                  code: !secret alarm_code
              - action: ha_vk.send_message
                data:
                  entry_id: "{{ entry_id }}"
                  message: "Alarm disarmed"
```

## 4. Frigate Snapshot on Demand

```yaml
automation:
  - alias: VK snapshot command
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message

    variables:
      entry_id: "{{ trigger.event.data.entry_id }}"
      text: "{{ trigger.event.data.text | default('') | trim | lower }}"

    condition:
      - condition: template
        value_template: "{{ text == '/photo' }}"

    action:
      - action: ha_vk.send_message
        data:
          entry_id: "{{ entry_id }}"
          message: "Latest camera snapshot"
          image: "http://frigate.local/api/front_door/latest.jpg"
```

## 5. Frigate Video Clip on Demand

```yaml
automation:
  - alias: VK video command
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message

    variables:
      entry_id: "{{ trigger.event.data.entry_id }}"
      text: "{{ trigger.event.data.text | default('') | trim | lower }}"

    condition:
      - condition: template
        value_template: "{{ text == '/video' }}"

    action:
      - action: ha_vk.send_message
        data:
          entry_id: "{{ entry_id }}"
          message: "Latest motion clip"
          video: "http://frigate.local/api/events/latest_front_door/clip.mp4"
          type: video
```

## 6. Sender Allowlist

```yaml
automation:
  - alias: VK allowlisted commands
    mode: parallel
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message

    variables:
      allowed_from_ids:
        - 123456789
        - 987654321
      from_id: "{{ trigger.event.data.from_id | int(0) }}"
      entry_id: "{{ trigger.event.data.entry_id }}"
      text: "{{ trigger.event.data.text | default('') | trim | lower }}"

    condition:
      - condition: template
        value_template: "{{ from_id in allowed_from_ids }}"

    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ text == '/status' }}"
            sequence:
              - action: ha_vk.send_message
                data:
                  entry_id: "{{ entry_id }}"
                  message: "Home Assistant is running"
```

## 7. Deny Unknown Senders

```yaml
automation:
  - alias: VK reject unknown sender
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message

    variables:
      allowed_from_ids:
        - 123456789
        - 987654321
      from_id: "{{ trigger.event.data.from_id | int(0) }}"
      entry_id: "{{ trigger.event.data.entry_id }}"

    condition:
      - condition: template
        value_template: "{{ from_id not in allowed_from_ids }}"

    action:
      - action: ha_vk.send_message
        data:
          entry_id: "{{ entry_id }}"
          message: "Access denied"
```

## 8. Separate Behavior for Multiple Entries

```yaml
automation:
  - alias: VK route by entry
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message

    variables:
      entry_id: "{{ trigger.event.data.entry_id }}"

    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ entry_id == 'entry_for_family_chat' }}"
            sequence:
              - action: logbook.log
                data:
                  name: VK Family
                  message: "{{ trigger.event.data.text }}"

          - conditions:
              - condition: template
                value_template: "{{ entry_id == 'entry_for_security_chat' }}"
            sequence:
              - action: logbook.log
                data:
                  name: VK Security
                  message: "{{ trigger.event.data.text }}"
```

## 9. Push Frigate Alert to VK

```yaml
automation:
  - alias: Send Frigate alert to VK
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door_motion
        to: "on"

    action:
      - action: ha_vk.send_message
        data:
          message: "Motion detected at front door"
          image: "http://frigate.local/api/front_door/latest.jpg"
```

## Notes

- Replace entity IDs, URLs, and `from_id` values with your own.
- If you have multiple `ha-vk` entries, prefer passing `entry_id` explicitly.
- Use `!secret` for alarm codes and other sensitive values.
- Media URLs must be reachable from your Home Assistant instance.

