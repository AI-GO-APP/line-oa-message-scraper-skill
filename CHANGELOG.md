# Changelog

## 1.3.0 — 2026-10-05

一併抓客服資料，匯入 CRM 不漏人。

- 好友名單（`/api/v2/bots/{botId}/contacts`）：含加了好友但從沒傳過訊息的人；與對話串列表合併輸出
  `line_oa_<時間戳>_contacts.csv`（一人一列，含好友狀態、標籤、指派、已完成／待處理／垃圾訊息）
- 每個對話串的記事本（`/notes`）→ `<chatId>.notes.json` 與 `line_oa_<時間戳>_notes.csv`；記事本不會改動對話串時間，續爬時每串重抓
- 標籤定義（`/tags`）→ `_tags.json`；主 CSV 新增 `chat_tags`、`assigned_to` 兩欄（加在最後，舊欄位不變）
- `bizId=__AUTO_RESPONSE` 標成「自動回應」，不再當成管理員；管理員已被移除時標「（已移除的管理員 …）」，不再冒用 OA 名稱
- `crawl_in_page.js` 同步抓上述資料，新增 `limitChats` 試跑參數
- `crawl_in_page.js` 的等待改用 Web Worker 計時：分頁在背景時不再被 Chrome 降速到每秒 1 個請求以下
- 摘要新增好友名單人數、沒有對話串的人數、記事本與標籤數
- 修正：訊息含 U+2028／U+2029 時 `export` 讀 `.jsonl` 會切斷 JSON（改為只用 `
` 分行）

## 1.2.0 — 2026-09-29

新增自我更新機制（與 aigo-app-builder-skill 相同的機制與頻率）。

- `scripts/check_update.py`：遠端 `VERSION` 較新時直接強制同步本機所有已註冊安裝；
  遠端版本每 3 小時抓一次、比對每次都做；開發用副本（版本較高或非 main 分支）略過
- SKILL.md 新增步驟 0：每次觸發先執行更新檢查
- `resources/hooks/`：Claude Code、Codex 的 SessionStart hook 範本
- README 改寫為完整文件，新增「維護者規則：PR 合併即發布」
- `.github/workflows/release-check.yml`：PR 改到 Skill 內容時檢查 VERSION 前進與 CHANGELOG 小節

## 1.1.0 — 2026-09-29

不開 Chrome 遠端除錯也能完整使用。

- `crawl_in_page.js` 新增 `downloadMedia`：取回未過期的圖片／影片／檔案，與資料包打包成單一
  `line_oa_export.zip` 只下載一次（避開 Chrome 擋同網站連續自動下載）
- `export` 可直接匯入 `line_oa_export.zip`：校驗 CRC、解出媒體、建立索引並填入 CSV 的 `local_path`
- SKILL.md 改為三條路徑（CDP 腳本／Claude in Chrome／使用者自貼 Console），並寫明 agent 不能代開遠端除錯

## 1.0.0 — 2026-09-29

首次發布。

- `line_oa_scrape.py`：透過 CDP 連上使用者正在使用的 Chrome，於 `chat.line.biz/api/v1/me`
  分頁內代發 GET，全量爬取對話串（合併 ALL／SPAM／DONE 資料夾）、群組成員與所有事件，輸出 CSV
- 子指令 `doctor`、`list`、`scrape`（含 `--all`、`--download-media`、續爬）、`export`
- `crawl_in_page.js`：Claude in Chrome 擴充功能路徑，下載資料包後以 `export` 轉 CSV
- 檔案類媒體改用 `/download?filename=` 網址（原網址會 404）
