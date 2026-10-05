---
name: line-oa-message-scraper
description: 全量爬取 LINE 官方帳號後台（chat.line.biz）的所有對話串與訊息，輸出成單一 CSV（文字、圖片／影片／檔案 URL 不論過期與否、貼圖索引、群組成員與發送者名稱），可選擇下載未過期媒體。使用者給一個或多個 chat.line.biz/U... 連結、或要求匯出／備份／爬取 LINE OA 聊天記錄、客服對話、LINE 官方帳號訊息時使用。預設使用使用者「正在使用、已登入」的 Chrome，不另開乾淨瀏覽器；全程唯讀，不送出訊息、不標為已讀。
---

# LINE OA Message Scraper

給定 `https://chat.line.biz/<OA ID>`（任何子路徑都行，例如 `/chat/<chatId>`），在使用者已登入的
Chrome 裡把該 OA 的**全部對話串**、每串**翻到伺服器不再給資料為止**的全部事件抓下來，輸出一份 CSV。

腳本在 `scripts/`（相對本 SKILL.md 的目錄，下稱 `<SKILL_DIR>`）。API 與事件結構細節見
`references/api.md`；CSV 欄位定義見 `references/csv-schema.md`。

## 步驟 0：Skill 自我更新（每次觸發時執行，發現新版即強制同步）

> 若已裝 SessionStart hook（見 README「保持更新」），這一步會被節流自動略過，不必重複執行。

```bash
python <SKILL_DIR>/scripts/check_update.py     # macOS / Linux 用 python3
```

- **零相依**：只用 Python 標準函式庫，任何環境都能直接跑。
- **腳本自己動手，不徵詢**：遠端 `VERSION` 比本地新，就直接把本機所有已註冊安裝強制同步到遠端
  main（git 安裝 `fetch` + `reset --hard` + `clean`；複製式安裝下載 `main.zip` 鏡像覆蓋）。
  本地修改一律被遠端取代。你**不需要也不可以**替使用者決定「要不要更新」。
- **無輸出 = 沒事**：已是最新、離線、或同一版本 3 小時內已失敗過都靜默結束，直接往下做。
  遠端版本每 3 小時才抓一次，但本地與遠端的比對每次都做。
- **有輸出**，逐行處理：
  - **「已同步」**→ **立刻重新讀取本 SKILL.md 與相關 `references/`**，讓新版指令在本回合生效；
    把版本落差與變更摘要**告知**使用者（告知，不是徵詢）。
  - **「失敗」**→ 把失敗原因與腳本印出的手動指令給使用者，請他們處理完再繼續。
    若有「破壞性變更」警語，明確說明停在舊版會失敗，後續遇到錯誤時優先懷疑版本落差。
  - **「開發副本，略過」**→ 那是正在改 skill 的工作區（本地版本較高，或 git 不在 main／master），不用處理。
- **禁止繞過**：不要為了保住本地修改而跳過本步驟或改用 `--check-only`。要改 skill 內容，走 repo 的 PR。

## 鐵則（違反任何一條都要停下來）

1. **不送出任何訊息、不改任何狀態**。只對 `chat.line.biz/api/...` 發 GET。不點擊後台介面、
   不在搜尋框按 Enter、不開啟任何對話串畫面——**開啟對話串畫面會觸發 `markAsRead`**，
   把客戶的未讀狀態洗掉並改動 `lastTalkedAt`。兩支腳本都停在 `https://chat.line.biz/api/v1/me`
   這個 JSON 頁面執行，完全不載入聊天介面。
2. **用使用者正在使用的 Chrome，不另開乾淨瀏覽器**，也不要求使用者在新視窗重新登入。
3. **不代填帳密、不代按安全設定**。登入與 `chrome://inspect` 的遠端除錯開關都由使用者自己操作。
4. **爬到伺服器不給為止，不自我設限**；但不要嘗試繞過方案限制或權限（見「已知限制」）。

## 流程

### 步驟 1：解析目標

從連結取出 OA ID（`U` + 32 位十六進位）。多個連結就多個 OA；使用者說「全部」就用 `--all`
（只會爬 CHAT 模式的 OA）。不確定有哪些 OA 時先跑 `list`。

### 步驟 2：選擇執行路徑（依序判斷）

三條路徑都使用使用者自己已登入的 Chrome，產出相同（CSV、原始資料、可選的媒體檔）。

| 條件 | 路徑 |
|---|---|
| `python <SKILL_DIR>/scripts/line_oa_scrape.py doctor` 顯示「連線與登入狀態正常」 | **路徑 A：腳本（CDP）**——最穩：資料直接落地、可續爬 |
| doctor 找不到 Chrome 端點，但本 session 有 Claude in Chrome 工具（`mcp__claude-in-chrome__*`） | **路徑 B：擴充功能**——不需要開遠端除錯 |
| 兩者都沒有 | **路徑 C：使用者自己貼進 Console**——不需要任何工具；或請使用者開遠端除錯後走路徑 A |

**遠端除錯不是必要條件。** 沒開時走路徑 B 或 C，功能相同（含媒體下載），只是不能中斷續爬。
要不要開由使用者決定；開的方法（Chrome 144 以上，一次性設定）：在 Chrome 網址列開
`chrome://inspect/#remote-debugging`，開啟允許遠端除錯的選項；之後每次腳本連線 Chrome 會跳出確認
視窗，按「允許」。

**agent 不能、也不可以替使用者開啟遠端除錯**：這是瀏覽器安全設定；Claude in Chrome 無法操作
`chrome://` 頁面，computer-use 對瀏覽器只有唯讀權限；Chrome 136 起對預設設定檔也不再接受
`--remote-debugging-port` 啟動參數，重啟 Chrome 帶參數這條路也行不通。

路徑 A 首次使用需安裝依賴：`pip install -r <SKILL_DIR>/scripts/requirements.txt`（只有 Playwright；
**不需要** `playwright install`，因為不啟動任何新瀏覽器）。路徑 B、C 的 `export` 只用 Python 標準函式庫。

### 路徑 A：腳本連上使用者的 Chrome（CDP）

```bash
python <SKILL_DIR>/scripts/line_oa_scrape.py scrape https://chat.line.biz/Uxxxxxxxx --out <輸出資料夾>
```

- 腳本自動找到使用者的 Chrome（`DevToolsActivePort` 或 9222 埠），在其中開一個新分頁停在 JSON 頁面，
  全部請求由這個分頁代發（自動帶登入 cookie），結束時只關掉自己開的分頁。
- 未登入時會在該分頁開登入頁，請使用者登入；登入成功後自動繼續。
- 常用參數：多個連結、`--all`、`--download-media`（下載未過期的圖片／影片／檔案）、
  `--limit-chats N`（試跑）、`--delay 0.3`（請求間隔秒數）、`--include-read-events`。
  指定端點用全域參數：`line_oa_scrape.py --cdp ws://... scrape ...`。
- **可中斷續爬**：進度存在 `<輸出>/raw/<botId>/_state.json`。重跑同一指令會從斷點接續；
  沒有新訊息的對話串直接沿用。
- 大型 OA 耗時長，用背景執行並定期看輸出。

### 路徑 B：Claude in Chrome 擴充功能

1. `tabs_context_mcp` → 在自己的分頁群組中開一個分頁，`navigate` 到 `https://chat.line.biz/api/v1/me`。
   看到 JSON（含 `name`）才代表已登入；被導到 `account.line.biz` 就請使用者登入。
2. 用 `javascript_tool` 執行：先一行設定，再接 `scripts/crawl_in_page.js` 的**完整內容**：
   ```js
   window.__LINE_OA_CONFIG = { botIds: ['Uxxxxxxxx'], downloadMedia: false, delayMs: 300, autoDownload: true };
   // ↓ 接著貼上 crawl_in_page.js 全文
   ```
   要媒體檔就設 `downloadMedia: true`（會先爬完訊息再逐一取回未過期媒體，全部在記憶體裡打包）。
   腳本立刻回傳 `started`，在背景執行。**單次 `javascript_tool` 呼叫約 45 秒逾時**，
   所以不要在同一次呼叫裡等它跑完。
3. 輪詢進度（每次等 ≤ 30 秒）：
   ```js
   const S = window.__lineOaCrawl;
   for (let i = 0; i < 15 && S.status === 'running'; i++) await new Promise(r => setTimeout(r, 2000));
   JSON.stringify({ status: S.status, error: S.error, progress: S.progress, requests: S.requests, summary: S.summary() })
   ```
   `javascript_tool` 回傳值約 1,000 字就會截斷，**只回摘要，不要回傳原始資料**。
4. 完成後瀏覽器自動下載**一個**檔案到使用者的「下載」資料夾：沒要媒體是 `line_oa_bundle.json`，
   要媒體是 `line_oa_export.zip`（內含資料包與 `media/`）。若沒有出現，多半是 Chrome 擋了同一網站的
   「多重自動下載」：請使用者在網址列右側的下載圖示允許，再執行 `window.__lineOaCrawl.download()`。
5. 轉 CSV（zip 會同時解出媒體並填入 CSV 的 `local_path`）：
   ```bash
   python <SKILL_DIR>/scripts/line_oa_scrape.py export "<下載資料夾>/line_oa_export.zip" --out <輸出資料夾>
   ```
   匯入後把下載資料夾裡的檔案移走或提醒使用者，避免含個資的副本留在「下載」。

限制：資料都暫存在分頁記憶體，中斷就得重跑；單一 zip 上限 65,535 個檔案、4 GB。
媒體量很大的 OA 建議改走路徑 A。

### 路徑 C：使用者自己在 Console 執行

沒有任何瀏覽器工具時，請使用者：

1. 在已登入的 Chrome 開 `https://chat.line.biz/api/v1/me`（看到 JSON 代表已登入）
2. 按 F12 → Console，先貼上設定行（`window.__LINE_OA_CONFIG = {...}`，同路徑 B），
   再貼上 `scripts/crawl_in_page.js` 全文，按 Enter
   （Chrome 第一次貼上程式碼會要求先輸入 `allow pasting`）
3. 等 Console 輸入 `__lineOaCrawl.status` 顯示 `'done'`，檔案會自動下載
4. agent 接手執行路徑 B 的第 5 步

### 步驟 3：驗收與回報

讀 `<輸出>/summary.json`（每條路徑都會產生），向使用者回報：

- 每個 OA 的對話串數、**取不到任何訊息的對話串數**、事件筆數、最舊～最新時間
- 媒體數與其中已過期數；有下載媒體時回報下載成功／失敗數
- 被略過的 OA（非 CHAT 模式、無權限）與原因
- 好友名單人數（其中沒有對話串的人數）、記事本則數、標籤數
- CSV 路徑（主檔、`_contacts.csv`、有記事本時的 `_notes.csv`）

回報前抽查 CSV：訊息列的 `sender_name` 應幾乎都有值、媒體列都有 `content_url`、
貼圖列都有 `sticker_package_id` 與 `sticker_id`。

## 已知限制（回報時要說清楚，不要當成爬蟲的 bug）

| 現象 | 原因 |
|---|---|
| 較舊的對話串回傳空清單 | 後台免費方案只提供約最近 6 個月的聊天記錄（付費進階方案最長 5 年），**文字也不例外**。這是伺服器端限制，任何參數都繞不過。需要長期保存就定期（間隔小於 6 個月）重爬累積 |
| 已過期的媒體 URL 打不開（404） | 檔案已從 LINE 伺服器刪除。URL 仍照樣輸出，`content_expired=Y` |
| 媒體 URL 在未登入的瀏覽器打不開 | `chat-content.line.biz` 需要後台登入 cookie；貼圖 URL 則是公開的 |
| OA 被略過並顯示 `not_chat_mode_bot` | 該 OA 的回應模式是 BOT（聊天功能關閉），後台沒有對話可讀 |
| OA 傳出的訊息沒有管理員名字 | 自動回應的 `bizId` 是 `__AUTO_RESPONSE`（`sender_name` 填「自動回應」）；Messaging API、歡迎訊息沒有 `bizId`，`sender_name` 填 OA 名稱 |
| 群組的成員清單查不到 | 已退出的群組回 404，不影響訊息本身 |

## 輸出結構

```
<輸出資料夾>/
├── line_oa_<時間戳>.csv      # 主產出，UTF-8 BOM（Excel 可直接開）
├── line_oa_<時間戳>_contacts.csv  # 好友名單（含從未聊過天的好友）
├── line_oa_<時間戳>_notes.csv     # 記事本（有才產生）
├── summary.json              # 匯出摘要
├── raw/<botId>/              # 原始 JSON（調整欄位時用 export 重新產生 CSV，不必重爬）
│   ├── _bot.json  _chats.json  _state.json  _tags.json  _contacts.json
│   ├── <chatId>.jsonl        # 每行一個事件
│   ├── <chatId>.notes.json   # 記事本（有才產生）
│   └── <chatId>.members.json # 群組成員
└── media/<botId>/<chatId>/   # 只有 --download-media 才有
```

輸出含客戶個資與對話內容：放在使用者指定的位置，不要 commit 進 repo、不要上傳到外部服務。
**不要把輸出資料夾設在 skill 安裝目錄裡**——自我更新會鏡像覆蓋該目錄（預設名稱 `line_oa_export/`
雖有保護，但其他名稱會被刪除）。
