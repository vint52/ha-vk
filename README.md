# ha-vk

[Русский](README.md) | [English](README.en.md)

[![Home Assistant Custom Integration](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://github.com/vint52/ha-vk)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://github.com/vint52/ha-vk?tab=readme-ov-file#%D1%83%D1%81%D1%82%D0%B0%D0%BD%D0%BE%D0%B2%D0%BA%D0%B0)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://github.com/vint52/ha-vk/blob/main/pyproject.toml)
[![Validate](https://github.com/vint52/ha-vk/actions/workflows/validate.yml/badge.svg)](https://github.com/vint52/ha-vk/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

![Логотип ha-vk](custom_components/ha_vk/brand/logo.png)

[![Откройте ваш экземпляр Home Assistant и сразу перейдите к добавлению этого репозитория в HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vint52&repository=ha-vk&category=integration)

VK-клиент для Home Assistant.

Пользовательская интеграция с поддержкой установки через HACS для отправки сообщений VK, изображений, видео и постов на стену из Home Assistant.

Интеграция основана на логике более раннего проекта [`vint52/homeassistent_vk_proxy`](https://github.com/vint52/homeassistent_vk_proxy) и сохраняет ту же функциональность:

- текстовые сообщения через `notify`
- текстовые сообщения с необязательным изображением или видео через `ha_vk.send_message`
- посты на стену через `ha_vk.send_post`
- входящие сообщения сообщества как события Home Assistant через `ha_vk_incoming_message`

## Установка

### HACS

`ha-vk` доступен как пользовательский репозиторий HACS.

[![Откройте ваш экземпляр Home Assistant и сразу перейдите к добавлению этого репозитория в HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vint52&repository=ha-vk&category=integration)

Используйте кнопку выше, чтобы открыть этот репозиторий напрямую в HACS.

_или_

1. Добавьте этот репозиторий в HACS как пользовательский репозиторий типа `Integration`.
2. Установите `ha-vk`.
3. Перезапустите Home Assistant.
4. Перейдите в `Settings -> Devices & services -> Add integration`.
5. Найдите `VK Client for Home Assistant`.

## Конфигурация

Во время настройки мастер запросит:

- `Notify entity name`: используется как имя notify-сущности в Home Assistant
- `VK access token`: токен сообщества для сообщений и загрузки файлов
- `VK peer ID`: ID пользователя или peer ID чата
- `VK group ID`: требуется для публикации постов на стену и входящих сообщений сообщества
- `Enable incoming VK messages`: включает VK long poll и события Home Assistant для новых сообщений из настроенного peer
- `VK wall access token`: необязательный пользовательский токен для фото/видео на стене сообщества и загрузки видео от имени пользователя
- `VK API version`: по умолчанию `5.131`
- `Request timeout`: по умолчанию `30`

Подробная инструкция по получению всех нужных VK-токенов и ID находится в [`TOKENS.md`](TOKENS.md).
Готовые сценарии автоматизаций и варианты использования собраны в [`docs/examples.md`](docs/examples.md).

После завершения настройки Home Assistant создаст notify-сущность с именем на основе выбранного названия.
Пример: если указать `ha-vk`, будет создана notify-сущность вроде `notify.ha_vk`.
Позже это название можно изменить в параметрах интеграции, чтобы переименовать созданную notify-сущность.

## Использование

### Сообщения и вложения

```yaml
action: ha_vk.send_message
data:
  message: "Door opened"
  title: "Home Assistant"
```

Или через действие notify-сущности Home Assistant:

```yaml
action: notify.send_message
data:
  entity_id: notify.ha_vk
  message: "Door opened"
  title: "Home Assistant"
```

`title` необязателен. Если он указан, то добавляется перед основным текстом сообщения.

Отправка изображения тем же сервисом:

```yaml
action: ha_vk.send_message
data:
  message: "Снимок с камеры"
  image: "http://frigate.local/api/events/123/snapshot.jpg?bbox=1&crop=0"
```

Отправка видео тем же сервисом:

```yaml
action: ha_vk.send_message
data:
  message: "Клип движения"
  video: "http://frigate.local/api/events/123/clip.mp4"
  type: "video"
```

Используйте `type: document`, если нужно принудительно загружать файл как документ, а не как VK-видео. В одном вызове `ha_vk.send_message` можно передавать только одно из полей `image` или `video`.

### Входящие сообщения

Если включен `Enable incoming VK messages`, настроен `VK group ID`, а токен сообщества имеет доступ к сообщениям сообщества, `ha-vk` запускает VK long poll и создает событие Home Assistant для каждого нового входящего сообщения из настроенного `VK peer ID`.

Тип события:

```text
ha_vk_incoming_message
```

В payload события входят:

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

Если текст сообщения начинается с `/`, дополнительно публикуется событие
`ha_vk_command` с полями `command`, `args` и `args_text` — см.
[примеры](docs/examples.md).

Пример automation:

```yaml
automation:
  - alias: Реакция на входящее сообщение VK
    trigger:
      - platform: event
        event_type: ha_vk_incoming_message
    action:
      - action: logbook.log
        data:
          name: VK
          message: "{{ trigger.event.data.text }}"
```

### Пост на стену

```yaml
action: ha_vk.send_post
data:
  message: "Пост с картинкой"
  image: "http://frigate.local/api/events/123/snapshot.jpg?bbox=1&crop=0"
```

## Примеры работы

### Фото и видео в сообщениях группы

Пример отправки фото и видео в сообщения группы VK:

![Пример фото и видео в сообщениях группы](docs/messages-and-video-example.png)

### Информация и фото на стене сообщества

Пример публикации фото и текстовой информации на стене сообщества:

![Пример поста на стене сообщества](docs/wall-post-example.png)

## Несколько аккаунтов или чатов VK

Если настроено несколько записей `ha-vk`, в вызовах сервисов `ha_vk.*` нужно явно передавать `entry_id`:

```yaml
action: ha_vk.send_post
data:
  entry_id: "01JABCDEF0123456789"
  message: "Пост в конкретный профиль"
```

Каждая запись конфигурации также получает собственную notify-сущность в домене `notify`.

## Примечания по настройке VK

- `VK peer ID`: используйте ID пользователя для личных сообщений или `2000000000 + chat_id` для групповых чатов.
- Входящие сообщения создаются только для настроенного `VK peer ID`.
- `VK group ID`: обязателен для входящих сообщений сообщества, потому что VK group long poll привязан к ID сообщества.
- `VK wall access token`: нужен для фото/видео на стене сообщества и для загрузки видео от имени пользователя. Без него видео в сообщениях можно отправлять как документ, но фото и видео на стену сообщества отправлять нельзя.
- Интеграция скачивает медиа по URL из Home Assistant, поэтому эти URL должны быть доступны из экземпляра HA.

## Устранение неполадок

- `Failed to download media file`: URL медиафайла недоступен из Home Assistant.
- `URL content type ... is not supported`: удаленный сервер вернул тип содержимого, который не является изображением или видео.
- Если `ha_vk.send_post` публикует только текст без изображения: настройте пользовательский токен со scope `wall`, `photos`, `video` и `offline` в `VK wall access token`.
- `Входящие сообщения VK недоступны для этой конфигурации сообщества`: проверьте, что в VK включены сообщения сообщества и токен сообщества имеет доступ к long poll для выбранной группы.
- `VK wall access token is invalid`: получите новый пользовательский токен. Если берете его через `https://vkhost.github.io/` и видите `{"error":"invalid_request","error_description":"application is blocked"}`, попробуйте другое приложение из списка сервиса, например `VK Admin`, `VK Admin (iOS)`, `vk.com` или `Kate Mobile`.
- `Multiple ha-vk entries are configured; pass entry_id explicitly`: добавьте `entry_id` в вызов пользовательского сервиса.

## Open Source

- Лицензия: [`LICENSE`](LICENSE)
- Вклад в проект: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Кодекс сообщества: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- Безопасность: [`SECURITY.md`](SECURITY.md)
- Поддержка: [`SUPPORT.md`](SUPPORT.md)
