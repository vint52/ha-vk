# Getting VK Tokens and IDs

This guide explains, step by step, how to obtain all VK values required by `ha-vk`:

- `VK access token`
- `VK peer ID`
- `VK group ID`
- `VK wall access token`

## What each value is used for

- `VK access token`: community token used for messages, image uploads, video uploads, and wall posts without image upload restrictions.
- `VK peer ID`: destination for messages. This can be a user ID or a chat peer ID.
- `VK group ID`: numeric community ID used for wall posts.
- `VK wall access token`: optional user token required for photos/videos on the community wall and for uploading videos on behalf of a user. Without it, videos in messages can still be sent as documents, but photos and videos cannot be posted on the community wall.

## 1. Create a VK community

If you already have a community, skip this step.

1. Open `https://vk.com/groups?tab=admin`.
2. Click `Create community`.
3. Choose the type you need and finish creation.

This community will be used by the integration for messaging and wall posts.

## 2. Enable community messages

1. Open your community settings.
2. Go to the messages section.
3. Enable community messages.

Without this, sending messages through VK API may fail.

## 3. Get `VK access token`

This is the main token for the integration.

1. Open your community settings.
2. Go to `Work with API` -> `Access keys`.
3. Click `Create key`.
4. Grant the permissions you need:
   - `Community messages` for `messages.send`
   - `Photos` for image uploads
   - `Video` for video uploads
   - `Documents` if you want to upload videos as documents
   - `Wall` if you want to publish wall posts
5. Copy the created token.
6. Paste it into the `VK access token` field during `ha-vk` setup.

## 4. Get `VK group ID`

You need the numeric community ID for wall posts.

### Option 1. From the community URL

If your community address looks like:

- `vk.com/club123456789`
- `vk.com/public123456789`

then the numeric part is your `VK group ID`.

### Option 2. From community settings

If your community uses a short name instead of a numeric URL:

1. Open the community settings.
2. Look for the numeric ID in the main information section.

### Option 3. Via VK API docs tool

You can also inspect the community through `groups.getById`:

- `https://vk.com/dev/groups.getById`

## 5. Get `VK peer ID`

This value depends on where you want messages to go.

### Personal messages

Use the numeric user ID.

If the profile URL looks like `vk.com/id123456`, then:

- `VK peer ID = 123456`

If the profile uses a short name, you can resolve the numeric ID through:

- `https://vk.com/dev/users.get`

### Group chats

For a chat, the value is:

- `peer_id = 2000000000 + chat_id`

How to get `chat_id`:

1. Open the chat in VK Web.
2. Look at the URL.
3. If you see something like `im?sel=c123`, then:
   - `chat_id = 123`
   - `VK peer ID = 2000000123`

## 6. Get `VK wall access token`

This token is optional, but it is required for photos and videos on the community wall, and for uploading videos on behalf of a user.

VK allows posting on behalf of the community with a community token, but wall photos and videos, as well as VK videos that must be uploaded as a user, require a user token with the proper scopes.

### Step-by-step

1. Create a VK application of type `Standalone`:
   - `https://vk.com/editapp?act=create`
2. Save the application and copy its `client_id`.
3. Open this URL in your browser, replacing `CLIENT_ID` with your real value:

```text
https://oauth.vk.com/authorize?client_id=CLIENT_ID&display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=wall,photos,video,offline&response_type=token&v=5.131
```

4. Sign in to VK if needed and allow access.
5. After redirect, inspect the browser address bar.
6. Find `access_token=...` in the URL fragment.
7. Copy that token and use it as `VK wall access token`.

You can also use:

- `https://vkhost.github.io/`

If `vkhost` shows an error like `{"error":"invalid_request","error_description":"application is blocked"}`, the app currently selected on the page is not issuing the required user token. Go back and try another app from the `vkhost` list, for example `VK Admin`, `VK Admin (iOS)`, `vk.com`, or `Kate Mobile`. The list of available apps on the service may change over time.

When requesting the token, make sure these scopes are included:

- `wall`
- `photos`
- `video`
- `offline`

The VK user who grants access must be an admin of the target community.

## 7. Which fields are mandatory

- `VK access token`: required
- `VK peer ID`: required
- `VK group ID`: required for wall posts
- `VK wall access token`: required for photos/videos on the community wall and for uploading videos as VK videos

If you only send messages, images, or videos to chats and users, you can usually leave `VK wall access token` empty. Without it, videos will fall back to document uploads when direct VK video upload is unavailable.

## Common issues

- `Group authorization failed: method is unavailable with group auth`: use `VK wall access token` for photos/videos on the community wall and for uploading videos as VK videos.
- `VK wall access token is invalid`: generate a new user token. If you use `https://vkhost.github.io/` and see `{"error":"invalid_request","error_description":"application is blocked"}`, try another app from the `vkhost` list.
- Messages are not sent to the target chat: verify that `VK peer ID` is correct.
- Wall posts fail: verify that `VK group ID` is numeric and matches the target community.
