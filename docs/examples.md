# Примеры ha-vk

На этой странице собраны практические примеры для `ha-vk`, особенно для входящих сообщений сообщества VK и автоматизаций Home Assistant.

## Событие

Входящие сообщения сообщества публикуются как событие Home Assistant:

```text
ha_vk_incoming_message
```

Обычно в событии доступны поля:

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

## Варианты использования

- Простые команды бота: `/ping`, `/status`, `/help`
- Управление сигнализацией из VK-чата
- Получение снимков и видео по запросу
- Интерактивные ответы на уведомления
- Ограничение доступа по списку `from_id`
- Разные сценарии для нескольких сообществ или чатов
- Логирование и архивирование входящих сообщений в Home Assistant

## 1. Минимальный лог входящих сообщений

```yaml
automation:
  - alias: Лог входящих сообщений VK
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message
    action:
      - action: logbook.log
        data:
          name: VK
          message: "{{ trigger.event.data.text }}"
```

## 2. Простые ответы на команды

```yaml
automation:
  - alias: Ответы на команды VK
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
                  message: "Доступные команды: /ping, /status, /photo, /video"
```

## 3. Управление сигнализацией

```yaml
automation:
  - alias: Управление сигнализацией из VK
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
                  message: "Сигнализация поставлена на охрану"

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
                  message: "Сигнализация снята с охраны"
```

## 4. Отправка снимка из Frigate по запросу

```yaml
automation:
  - alias: Команда VK для снимка
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
          message: "Последний снимок с камеры"
          image: "http://frigate.local/api/front_door/latest.jpg"
```

## 5. Отправка видео из Frigate по запросу

```yaml
automation:
  - alias: Команда VK для видео
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
          message: "Последний клип движения"
          video: "http://frigate.local/api/events/latest_front_door/clip.mp4"
          type: video
```

## 6. Белый список отправителей

```yaml
automation:
  - alias: Команды VK только для доверенных пользователей
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
                  message: "Home Assistant работает"
```

## 7. Отказ неизвестным отправителям

```yaml
automation:
  - alias: Отказ неизвестным отправителям VK
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
          message: "Доступ запрещен"
```

## 8. Разное поведение для нескольких записей

```yaml
automation:
  - alias: Маршрутизация VK по entry_id
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

## 9. Отправка тревоги Frigate в VK

```yaml
automation:
  - alias: Отправка события Frigate в VK
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door_motion
        to: "on"

    action:
      - action: ha_vk.send_message
        data:
          message: "Обнаружено движение у входной двери"
          image: "http://frigate.local/api/front_door/latest.jpg"
```

## Примечания

- Замените entity ID, URL и значения `from_id` на свои.
- Если у вас несколько записей `ha-vk`, лучше явно передавать `entry_id`.
- Для кода сигнализации и других чувствительных значений используйте `!secret`.
- URL медиа должны быть доступны из Home Assistant.

