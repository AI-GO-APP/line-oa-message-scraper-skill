# CSV 欄位定義

編碼 UTF-8 with BOM（Excel 直接開不亂碼）。一列一個事件，同一對話串內依時間由舊到新排序。
預設不含 `chatRead`（已讀）事件，加 `--include-read-events` 才輸出。同一則訊息重複出現時以
`type + message.id` 去重。

| 欄位 | 說明 |
|---|---|
| `bot_id` / `bot_name` | OA 的 ID 與名稱 |
| `chat_id` / `chat_type` / `chat_name` | 對話串 ID、類型（USER／GROUP／ROOM）、顯示名稱（用戶名或群組名） |
| `timestamp` | 台北時間 `YYYY-MM-DD HH:MM:SS` |
| `timestamp_ms` | 原始毫秒時間戳 |
| `event_type` | 見 `api.md` 事件表 |
| `direction` | `對方傳入`／`OA傳出`／`系統事件` |
| `sender_id` | 傳入為 LINE userId；傳出為管理員 `bizId`（沒有時為空） |
| `sender_name` | 一對一：用戶名；群組：由成員清單對應；傳出：管理員名稱，沒有則填 OA 名稱 |
| `message_id` / `message_type` | 訊息 ID 與類型；`unsend` 事件的 `message_id` 是被收回的那則 |
| `text` | 文字內容（可能含換行） |
| `content_url` / `preview_url` | 媒體網址，**不論是否過期都輸出**；檔案是 `/download?filename=` 形式 |
| `content_expired` | `Y`／`N` |
| `content_expires_at` | 媒體到期時間（台北時間） |
| `file_name` / `file_size` | 檔名與位元組數（檔案類） |
| `duration_ms` | 影片、音訊長度 |
| `local_path` | 有 `--download-media` 時，相對於輸出資料夾的本機檔案路徑 |
| `sticker_package_id` / `sticker_id` / `sticker_resource_type` | 貼圖索引 |
| `sticker_url` | 貼圖圖片（公開 CDN，靜態 PNG） |
| `quoted_message_id` | 回覆引用的訊息 ID |
| `raw_json` | 事件原始 JSON，保底未預期的類型與欄位 |
| `chat_tags` | 這個對話串目前的標籤名稱（`、` 分隔；含自動標籤） |
| `assigned_to` | 這個對話串目前指派給哪位管理員 |

`sender_name` 的 OA 傳出值：管理員名稱；`__AUTO_RESPONSE` 填「自動回應」；沒有 `bizId` 填 OA 名稱；
管理員已被移除時填「（已移除的管理員 xxxxxxxx）」。

## 好友名單 `line_oa_<時間戳>_contacts.csv`

好友名單（含從未聊過天的好友）與對話串列表的聯集，一人一列。

| 欄位 | 說明 |
|---|---|
| `bot_id` / `user_id` / `name` | OA、LINE userId、顯示名稱 |
| `friend` | `Y`＝目前是好友；`N`＝已封鎖或不是好友 |
| `chat_exists` | 有沒有對話串 |
| `tags` / `assigned_to` | 標籤名稱、指派的管理員 |
| `done` / `followed_up` / `spam` | 後台的已完成／待處理／垃圾訊息標記 |
| `last_received_at` / `last_sent_at` | 最後收到／傳出的時間（台北時間；沒有對話串時空白） |
| `raw_json` | 原始 JSON |

## 記事本 `line_oa_<時間戳>_notes.csv`

後台對話串右側的記事本，一則一列；沒有任何記事本時不產生這個檔案。

| 欄位 | 說明 |
|---|---|
| `bot_id` / `chat_id` / `chat_name` | 哪個對話串 |
| `note_id` / `created_at` / `updated_at` | 記事 ID 與時間（台北時間） |
| `author_id` / `author_name` | 撰寫的管理員 |
| `content` | 內容 |
| `raw_json` | 原始 JSON |
