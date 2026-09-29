# Changelog

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
