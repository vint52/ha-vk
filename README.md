# ha-vk

[English](README.md) | [Русский](README.ru.md)

[![Home Assistant Custom Integration](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white)](https://github.com/vint52/ha-vk)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://github.com/vint52/ha-vk?tab=readme-ov-file#installation)
[![Version](https://img.shields.io/badge/version-0.1.1-blue)](https://github.com/vint52/ha-vk)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://github.com/vint52/ha-vk/blob/main/pyproject.toml)

![ha-vk logo](custom_components/ha_vk/brand/logo.png)

[![Open your Home Assistant instance and open the HACS custom repository dialog with this repository pre-filled.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vint52&repository=ha-vk&category=integration)

VK Client for Home Assistant.

HACS-installable custom integration for sending VK messages, images, videos, and wall posts directly from Home Assistant without an external HTTP proxy.

This integration is based on the behavior of the earlier [`vint52/homeassistent_vk_proxy`](https://github.com/vint52/homeassistent_vk_proxy) project and keeps the same functional parity:

- text messages via `notify`
- images via `ha_vk.send_image`
- videos via `ha_vk.send_video`
- wall posts via `ha_vk.send_post`

## Installation

### HACS

`ha-vk` is available as a custom HACS repository.

[![Open your Home Assistant instance and open the HACS custom repository dialog with this repository pre-filled.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vint52&repository=ha-vk&category=integration)

Use the button above to open this repository directly in HACS.

_or_

1. Add this repository to HACS as a custom repository of type `Integration`.
2. Install `ha-vk`.
3. Restart Home Assistant.
4. Go to `Settings -> Devices & services -> Add integration`.
5. Search for `VK Client for Home Assistant`.

## Configuration

The setup flow asks for:

- `Notify entity name`: used as the Home Assistant notify entity name
- `VK access token`: community token used for messages and uploads
- `VK peer ID`: user ID or chat peer ID
- `VK group ID`: required for wall posts
- `VK wall access token`: optional user token needed for wall posts with images
- `VK API version`: defaults to `5.131`
- `Request timeout`: defaults to `30`

After setup, Home Assistant creates a notify entity named from your chosen title.
Example: if the title is `ha-vk`, you will get a notify entity such as `notify.ha_vk`.
You can later change this title in the integration options to rename the generated notify entity.

## Usage

### Text notifications

```yaml
action: ha_vk.send_message
data:
  message: "Door opened"
  title: "Home Assistant"
```

Or via the Home Assistant notify entity action:

```yaml
action: notify.send_message
data:
  entity_id: notify.ha_vk
  message: "Door opened"
  title: "Home Assistant"
```

`title` is optional. If present, it is prepended to the message body.

### Image

```yaml
action: ha_vk.send_image
data:
  image: "http://frigate.local/api/events/123/snapshot.jpg?bbox=1&crop=0"
```

### Video

```yaml
action: ha_vk.send_video
data:
  video: "http://frigate.local/api/events/123/clip.mp4"
  type: "video"
```

Use `type: document` to force document upload when VK video upload is not desired.

### Wall post

```yaml
action: ha_vk.send_post
data:
  message: "Post with image"
  image: "http://frigate.local/api/events/123/snapshot.jpg?bbox=1&crop=0"
```

## Multiple VK accounts or chats

If you configure multiple ha-vk entries, service calls under `ha_vk.*` must include `entry_id`:

```yaml
action: ha_vk.send_post
data:
  entry_id: "01JABCDEF0123456789"
  message: "Post to a specific profile"
```

Each config entry also gets its own notify entity under the `notify` domain.

## VK setup notes

- `VK peer ID`: use a user ID for direct messages, or `2000000000 + chat_id` for group chats.
- `VK wall access token`: required for `/send_post` with image uploads because community tokens cannot upload wall photos.
- The integration downloads media URLs from Home Assistant, so the URLs must be reachable from your HA instance.

## Troubleshooting

- `Failed to download media file`: the media URL is unreachable from Home Assistant.
- `URL content type ... is not supported`: the remote server returned a non-image or non-video content type.
- `VK wall access token is required for posts with images`: configure a user token with `wall`, `photos`, and `offline` scopes.
- `Multiple ha-vk entries are configured; pass entry_id explicitly`: add `entry_id` to the custom service call.
