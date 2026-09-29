# chat.line.biz 內部 API 筆記

2026-09 實測。這些是 LINE 官方帳號後台前端使用的非公開 API，可能隨改版變動；
出現大量非預期 404／400 時先懷疑 API 改版，用瀏覽器開發者工具觀察後台實際發出的請求再修正。

所有請求都在 `https://chat.line.biz` 同源、帶登入 cookie 的 GET。本 skill 不使用任何 POST／PUT。

## 端點

| 用途 | 端點 | 分頁 |
|---|---|---|
| 登入者資訊（登入檢查） | `GET /api/v1/me` | — |
| 帳號可存取的 OA | `GET /api/v1/bots?limit=1000&noFilter=true` | 無 |
| 單一 OA 資訊 | `GET /api/v1/bots/{botId}?noFilter=true` | — |
| OA 管理員（`bizId` → 名稱） | `GET /api/v1/bots/{botId}/owners` | 無 |
| 對話串列表 | `GET /api/v2/bots/{botId}/chats?folderType={ALL\|SPAM\|DONE}&limit=25` | 回應 `next`，下一頁帶 `&next=` |
| 群組成員 | `GET /api/v1/bots/{botId}/chats/{chatId}/members?limit=100` | 回應 `next` |
| 對話事件 | `GET /api/v3/bots/{botId}/chats/{chatId}/messages` | 回應 `backward`，往更舊翻頁帶 `?backward=` |

- 第一頁是最新的事件，`backward` 往回翻；**回應沒有 `backward` 就是到底了**。
- `backward` 帶錯會回 `400 {"code":"malformed_next_token"}`。
- `folderType` 可用值：`ALL`、`INBOX`、`UNREAD`、`FOLLOW_UP`、`DONE`、`SPAM`；其餘回 400。
  `ALL` 與 `INBOX` 相同，是否含 `SPAM`／`DONE` 未證實，所以合併三者後以 `chatId` 去重。
- 非 CHAT 模式的 OA 在對話相關端點回 `403 {"code":"not_chat_mode_bot"}`。
- 登入失效時 API 會 302 導向登入頁；腳本用 `redirect: 'manual'` 攔下並視為 401。
- 前端另有官方的單串匯出 `/download/{botId}/{chatId}/messages.csv?timezoneOffset=`，
  在介面上是付費功能，本 skill 未使用。

## 會產生副作用、必須避開的請求

後台介面在開啟對話串時會自動發出：

- `PUT /api/v2/bots/{botId}/chats/{chatId}/markAsRead` —— 標為已讀，並改動 `lastTalkedAt`
- `PUT /api/v1/bots/{botId}/streaming/state` —— 載入後台介面時送出

所以腳本一律停在 `/api/v1/me` 這個 JSON 頁面，不載入後台介面。

## 對話串物件（chats 的 list 元素）

```
chatId, chatType (USER | GROUP | ROOM), status, updatedAt, lastReceivedAt, lastSentAt,
lastTalkedAt, lastReadAt, read, done, followedUp, spam, tagIds, autoTagIds,
profile: USER → {userId, name, friend, iconHash, lastActivityExpiresAt}
         GROUP → {groupId, name, count, iconHash}
latestEvent (GROUP 才有)
```

增量判斷用 `max(lastReceivedAt, lastSentAt, updatedAt)`。`lastTalkedAt` 會被已讀動作改動，不可用。

## 事件物件（messages 的 list 元素）

共同欄位：`type`、`timestamp`（毫秒）、`source: {chatId, userId?}`。

| `type` | 說明 | 重要欄位 |
|---|---|---|
| `message` | 對方（用戶或群組成員）傳入 | `message` |
| `messageSent` | OA 傳出 | `message`、`bizId`（哪位管理員；自動回應沒有）、`sendId` |
| `unsend` | 收回 | `unsend.messageId` |
| `chatRead` | 對方已讀 | `read.watermark` |
| `follow` / `unfollow` | 加入／封鎖好友 | — |
| `join` / `memberJoined` / `memberLeft` | 群組事件 | `joined.members` / `left.members` |
| `postback` | 按鈕回傳 | — |

`message.type`：

| 類型 | 欄位 |
|---|---|
| `text` | `text`、`quotedMessageId`、`quoteToken` |
| `image` / `video` / `audio` | `contentHash`、`expired`、`expiredAt`、`contentProvider{type,contentHash,expired,expiredAt}`；影片與音訊有 `duration` |
| `file` | 同上，加 `fileName`、`fileSize` |
| `sticker` | `packageId`、`stickerId`、`stickerResourceType`（`STATIC`、`ANIMATION`…） |
| `unsent` | 只剩 `id`（已收回的原訊息） |

`contentProvider.type` 為 `external` 時改帶 `originalContentUrl`、`previewImageUrl`（外部 URL）。

## 媒體網址

前端設定 `CONTENT: https://chat-content.line.biz` + `/bot/{botId}/{contentHash}`。

| 類型 | 原檔 | 預覽 |
|---|---|---|
| image / video / audio | `https://chat-content.line.biz/bot/{botId}/{contentHash}` | `…/preview`（image、video） |
| file | `https://chat-content.line.biz/bot/{botId}/{contentHash}/download?filename={fileName}` | — |
| sticker | `https://stickershop.line-scdn.net/stickershop/v1/sticker/{stickerId}/android/sticker.png`（公開） | — |

- `chat-content.line.biz` 需要後台登入 cookie；從 `chat.line.biz` 頁面以 `credentials: 'include'` fetch 可跨域取得。
- 實測：未過期的圖片、影片、檔案全部 200 且大小相符；已過期的一律 404。
- 檔案若不加 `/download` 會 404。
