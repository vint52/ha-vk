# Send retries on network errors — design

Issue: #11 — «поддержка повторов отправки в случае ошибки»

## Problem

Сейчас любая сетевая ошибка (обрыв связи, таймаут) во время отправки сообщения,
медиа или поста мгновенно завершает операцию исключением `VkNetworkError` /
`VkApiError`. Кратковременные сбои связи приводят к потере уведомлений.

## Solution overview

Добавить повторы (retry) с экспоненциальным бэкоффом для всех сетевых шагов
внутри `VkClient`, с настраиваемым количеством повторов в опциях интеграции.

## Configuration

- Новая опция `send_retries` (`CONF_SEND_RETRIES = "send_retries"`).
- Дефолт `DEFAULT_SEND_RETRIES = 3`; значение `0` отключает повторы
  (текущее поведение).
- Поле в общей схеме config/options flow (`_build_schema`): NumberSelector,
  `min=0`, `step=1`, mode BOX.
- Сохраняется в options (`_entry_options`).
- `VkClientConfig` получает поле `send_retries: int = DEFAULT_SEND_RETRIES`.
- `build_client_config` парсит значение как целое `>= 0`
  (`VkConfigError` при некорректном значении, включая `OverflowError`
  от бесконечных значений).
- Переводы: `strings.json`, `translations/en.json`, `translations/ru.json`.

## Retry logic (api.py)

- Внутренний async-хелпер в `VkClient` (например, `_with_retries(coro_factory)`),
  оборачивающий HTTP-часть трёх сетевых примитивов:
  - `_api_call` — все вызовы VK API;
  - `_download_file` — скачивание медиа по URL;
  - `_upload_file` — загрузка на upload-сервер VK.
- Повторяются только транспортные ошибки: `TimeoutError` и `aiohttp.ClientError`.
- НЕ повторяются: логические ошибки VK API (`error` в ответе, включая auth),
  HTTP-статусы `>= 400`, ошибки валидации содержимого.
- Бэкофф: `SEND_RETRY_BACKOFF_BASE = 1.0` секунда, экспоненциально —
  паузы 1s, 2s, 4s, … (`base * 2**attempt`) через `asyncio.sleep`,
  с потолком `SEND_RETRY_MAX_DELAY = 60.0` секунд
  (`min(base * 2**attempt, SEND_RETRY_MAX_DELAY)`), по аналогии
  с `LONG_POLL_MAX_RETRY_DELAY` в receiver — иначе большое значение
  `send_retries` даёт многочасовые паузы внутри notify-вызова.
- Максимум `send_retries` повторов (то есть `send_retries + 1` попыток).
- После исчерпания попыток наружу летят те же исключения, что и сейчас
  (`VkNetworkError` из `_api_call`, `VkApiError` из download/upload) —
  контракт для вызывающих не меняется.
- Каждая неудачная попытка перед повтором логируется на уровне WARNING
  (метод/шаг, номер попытки, пауза до следующей).
- Long poll (`async_check_long_poll`) не оборачивается — у receiver уже есть
  собственный цикл переподключения (`LONG_POLL_RETRY_DELAY`).
- `_api_call` общий, поэтому валидация конфига и `groups.getLongPollServer`
  тоже получают устойчивость к сбоям — принято как желаемое поведение.
- Идемпотентность `messages.send` обеспечивает существующий `random_id`
  (VK дедуплицирует повторы).

## Testing

- Успех после N сетевых ошибок (< лимита) — результат возвращается,
  число HTTP-запросов равно числу попыток.
- Исчерпание лимита — `VkNetworkError` (или `VkApiError` для download/upload).
- Ошибка VK API (error в теле) и `VkAuthError` — без повторов, одна попытка.
- `send_retries=0` — ровно одна попытка.
- Бэкофф — паузы 1/2/4 с замоканным `asyncio.sleep`.
- `build_client_config`: парсинг `send_retries`, дефолт, отрицательное /
  нечисловое значение → `VkConfigError`.
- Config flow: опция сохраняется в options.

## Out of scope

- Повторы long poll (уже есть в receiver).
- Очередь отложенной доставки / персистентность недоставленных сообщений.
- Retry-After / обработка rate limit VK (error_code 6).
