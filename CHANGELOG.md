# Changelog

## 1.0.0 — 2026-09-29

首次發布。

- `line_oa_scrape.py`：透過 CDP 連上使用者正在使用的 Chrome，於 `chat.line.biz/api/v1/me`
  分頁內代發 GET，全量爬取對話串（合併 ALL／SPAM／DONE 資料夾）、群組成員與所有事件，輸出 CSV
- 子指令 `doctor`、`list`、`scrape`（含 `--all`、`--download-media`、續爬）、`export`
- `crawl_in_page.js`：Claude in Chrome 擴充功能路徑，下載資料包後以 `export` 轉 CSV
- 檔案類媒體改用 `/download?filename=` 網址（原網址會 404）
