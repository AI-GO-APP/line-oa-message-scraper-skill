# LINE OA Message Scraper Skill

> 給 AI Agent（Claude Code / Codex / Cursor / Antigravity）用的 Skill：給一個 `chat.line.biz` 連結，
> 就把該 LINE 官方帳號後台的**全部對話串與訊息**匯出成一份 CSV。
> 僅用於匯出你本人有管理權限的官方帳號資料。

- 文字訊息、圖片／影片／檔案 URL（不論過期與否）、貼圖索引、群組成員與發送者名稱
- 每個對話串往回翻到伺服器不再給資料為止；對話串列表與訊息都自動處理分頁（lazy loading）
- **用你正在使用、已登入的 Chrome**，不另開乾淨瀏覽器、不必重新登入
- **全程唯讀**：只發 GET、不載入聊天介面，不會送出訊息，也不會把客戶訊息標為已讀
- 可中斷續爬；可選擇下載未過期的媒體檔

## 安裝

```bash
npx skills add AI-GO-APP/line-oa-message-scraper-skill
```

<details>
<summary>手動安裝</summary>

```bash
git clone https://github.com/AI-GO-APP/line-oa-message-scraper-skill.git ~/.claude/skills/line-oa-message-scraper
```

保留完整目錄結構——`SKILL.md` 會引用 `scripts/` 與 `references/`。

</details>

依賴（只有 Playwright，**不需要** `playwright install`，因為不會啟動新瀏覽器）：

```bash
pip install -r scripts/requirements.txt
```

## 三種執行方式（都用你已登入的 Chrome）

| 方式 | 需要 | 特點 |
|---|---|---|
| **A. 腳本（CDP）** | 開啟 Chrome 遠端除錯（一次性） | 最穩：資料直接寫入本機、可中斷續爬 |
| **B. Claude in Chrome 擴充功能** | agent 有 Claude in Chrome | 不需開遠端除錯；完成後下載一個檔案再轉 CSV |
| **C. 自己貼進 Console** | 什麼都不用 | 按 F12 貼上 `scripts/crawl_in_page.js`，再轉 CSV |

Skill 會自動判斷用哪一種；三種都支援下載媒體檔。

**開啟遠端除錯（方式 A，選用）**：Chrome 144 以上，在網址列開 `chrome://inspect/#remote-debugging`，
開啟允許遠端除錯的選項。之後每次腳本連線，Chrome 會跳出確認視窗，按「允許」即可。
這是瀏覽器安全設定，AI agent 無法也不會替你開啟。

## 使用

對 agent 說：

> 把 https://chat.line.biz/Uxxxxxxxx 的對話全部匯出成 CSV

或直接執行腳本：

```bash
python scripts/line_oa_scrape.py doctor                                   # 檢查連線與登入
python scripts/line_oa_scrape.py list                                     # 列出可存取的 OA
python scripts/line_oa_scrape.py scrape https://chat.line.biz/Uxxxxxxxx   # 全量爬取
python scripts/line_oa_scrape.py scrape --all --download-media --out ./backup
python scripts/line_oa_scrape.py export --out ./backup                    # 由原始資料重新產生 CSV
python scripts/line_oa_scrape.py export ~/Downloads/line_oa_export.zip --out ./backup   # 匯入方式 B／C 的產出
```

| 參數 | 作用 |
|---|---|
| 多個連結 / `--all` | 一次爬多個 OA／帳號下全部 CHAT 模式的 OA，合併成一份 CSV |
| `--out DIR` | 輸出資料夾（預設 `line_oa_export`） |
| `--download-media` | 一併下載未過期的圖片、影片、檔案 |
| `--limit-chats N` | 每個 OA 只爬前 N 個對話串（試跑） |
| `--delay SEC` | 請求間隔（預設 0.3 秒） |
| `--include-read-events` | CSV 包含已讀事件 |
| `--cdp ENDPOINT` | 手動指定 Chrome 端點（放在子指令之前） |

中斷後重跑同一指令會從斷點接續；沒有新訊息的對話串直接沿用。

## 已知限制

- **只拿得到後台還顯示的範圍**：免費方案約最近 6 個月（進階方案最長 5 年），文字也一樣。
  需要長期保存請定期重爬累積。
- **已過期的媒體**：URL 照樣輸出，但檔案已刪除，打開會 404。
- **媒體 URL 需要登入**：要在已登入後台的瀏覽器中開啟；貼圖 URL 是公開的。
- **BOT 模式的 OA**：沒有聊天功能，無法爬取，會被略過。
- 使用 LINE 後台的非公開 API，LINE 改版可能導致失效；細節見 `references/api.md`。

## 目錄結構

```
line-oa-message-scraper-skill/
├── SKILL.md                  # Agent 工作流程與鐵則
├── README.md
├── VERSION / CHANGELOG.md
├── references/
│   ├── api.md                # chat.line.biz 內部 API、事件結構、媒體網址規則
│   └── csv-schema.md         # CSV 欄位定義
└── scripts/
    ├── line_oa_scrape.py     # 主腳本：連上使用者的 Chrome（CDP）爬取、下載媒體、輸出 CSV
    ├── crawl_in_page.js      # 瀏覽器內抓取腳本（方式 B、C；可含媒體，產出單一 zip）
    └── requirements.txt
```

## 資料安全

輸出包含客戶個資與完整對話。請存放在受控位置，不要 commit 進 repo 或上傳到外部服務。
