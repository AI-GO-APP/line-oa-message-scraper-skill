# LINE OA Message Scraper Skill

> 給 AI Agent（Claude Code / Codex / Cursor / Antigravity）用的 Skill：給一個 `chat.line.biz` 連結，
> 就把該 LINE 官方帳號後台的**全部對話串與訊息**匯出成一份 CSV。
> 僅用於匯出你本人有管理權限的官方帳號資料。

## 目錄

- [功能](#功能)
- [安裝](#安裝)
- [三種執行方式](#三種執行方式)
- [使用方式](#使用方式)
- [輸出](#輸出)
- [已知限制](#已知限制)
- [保持更新](#保持更新)
- [維護者規則：PR 合併即發布](#維護者規則pr-合併即發布)
- [目錄結構](#目錄結構)
- [資料安全](#資料安全)
- [License](#license)

## 功能

| 項目 | 內容 |
|---|---|
| 訊息內容 | 文字、引用、收回、加入／退出／封鎖等系統事件，含發送者名稱（一對一用戶、群組成員、哪位管理員） |
| 媒體 | 圖片、影片、音訊、檔案的 URL，**不論過期與否**都輸出；可選擇下載未過期的檔案 |
| 貼圖 | `packageId`、`stickerId`、類型與公開圖片 URL |
| 範圍 | 對話串列表與每串訊息都自動翻頁（lazy loading），每串翻到伺服器不再給資料為止；含垃圾訊息、已完成資料夾 |
| 瀏覽器 | **用你正在使用、已登入的 Chrome**，不另開乾淨瀏覽器、不必重新登入 |
| 安全 | **全程唯讀**：只對 `/api/` 發 GET、不載入聊天介面，不會送出訊息，也不會把客戶訊息標為已讀 |
| 可靠性 | 請求限速與自動重試；方式 A 可中斷續爬，沒有新訊息的對話串直接沿用 |

## 安裝

用 [`skills`](https://github.com/vercel-labs/skills) CLI 安裝（會自動偵測 agent 並裝到正確位置）：

```bash
npx skills add AI-GO-APP/line-oa-message-scraper-skill
```

<details>
<summary>手動安裝（git clone）</summary>

```bash
# Claude Code 使用者層級
git clone https://github.com/AI-GO-APP/line-oa-message-scraper-skill.git ~/.claude/skills/line-oa-message-scraper

# 專案內
git clone https://github.com/AI-GO-APP/line-oa-message-scraper-skill.git .claude/skills/line-oa-message-scraper
```

保留完整目錄結構——`SKILL.md` 會引用 `scripts/`、`references/`、`resources/`。
一台機器建議只裝一份（user scope）；裝多份時更新機制會一起同步，但沒必要。

</details>

依賴：方式 A 需要 Playwright（**不需要** `playwright install`，因為不會啟動新瀏覽器）；
方式 B、C 與更新檢查只用 Python 標準函式庫。

```bash
pip install -r scripts/requirements.txt
```

## 三種執行方式

三種都用你自己已登入的 Chrome，產出相同。Skill 會依序自動判斷：

| 方式 | 需要 | 特點 |
|---|---|---|
| **A. 腳本（CDP）** | 開啟 Chrome 遠端除錯（一次性） | 最穩：資料直接寫入本機、可中斷續爬、適合大型 OA |
| **B. Claude in Chrome 擴充功能** | agent 有 Claude in Chrome | 不需開遠端除錯；完成後下載一個檔案再轉 CSV |
| **C. 自己貼進 Console** | 什麼都不用 | 按 F12 貼上 `scripts/crawl_in_page.js`，再轉 CSV |

**開啟遠端除錯（方式 A，選用）**：Chrome 144 以上，在網址列開 `chrome://inspect/#remote-debugging`，
開啟允許遠端除錯的選項。之後每次腳本連線，Chrome 會跳出確認視窗，按「允許」即可。
這是瀏覽器安全設定，AI agent 無法也不會替你開啟；不開也能用方式 B、C。

## 使用方式

### 對 agent 說

> 把 https://chat.line.biz/Uxxxxxxxx 的對話全部匯出成 CSV，媒體也下載

### 直接執行腳本（方式 A）

```bash
python scripts/line_oa_scrape.py doctor                                   # 檢查連線與登入
python scripts/line_oa_scrape.py list                                     # 列出可存取的 OA 與是否可爬
python scripts/line_oa_scrape.py scrape https://chat.line.biz/Uxxxxxxxx   # 全量爬取
python scripts/line_oa_scrape.py scrape --all --download-media --out ./backup
python scripts/line_oa_scrape.py export --out ./backup                    # 由原始資料重新產生 CSV
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

### 自己在 Console 執行（方式 C）

1. 在已登入的 Chrome 開 `https://chat.line.biz/api/v1/me`（看到 JSON 代表已登入）
2. 按 F12 → Console，先貼設定再貼 `scripts/crawl_in_page.js` 全文，按 Enter
   （Chrome 第一次貼上程式碼會要求先輸入 `allow pasting`）：
   ```js
   window.__LINE_OA_CONFIG = { botIds: ['Uxxxxxxxx'], downloadMedia: true };
   ```
3. 等 `__lineOaCrawl.status` 變成 `'done'`，會自動下載 `line_oa_export.zip`
   （沒要媒體則是 `line_oa_bundle.json`）
4. 轉成 CSV：
   ```bash
   python scripts/line_oa_scrape.py export ~/Downloads/line_oa_export.zip --out ./backup
   ```

## 輸出

```
<輸出資料夾>/
├── line_oa_<時間戳>.csv      # 主產出，UTF-8 BOM（Excel 可直接開）
├── summary.json              # 每個 OA 的對話串數、空對話串數、事件數、時間範圍、媒體數
├── raw/<botId>/              # 原始 JSON；調整欄位時用 export 重新產生 CSV，不必重爬
│   ├── _bot.json  _chats.json  _state.json
│   ├── <chatId>.jsonl        # 每行一個事件
│   └── <chatId>.members.json # 群組成員
└── media/<botId>/<chatId>/<日期_時間>_<訊息ID>_<檔名>   # 只有下載媒體時才有
```

CSV 欄位定義見 [`references/csv-schema.md`](references/csv-schema.md)；
API 與事件結構見 [`references/api.md`](references/api.md)。

## 已知限制

| 現象 | 原因 |
|---|---|
| 較舊的對話串抓不到訊息 | 後台只提供還顯示的範圍：免費方案約最近 6 個月（進階方案最長 5 年），文字也一樣。需要長期保存請定期重爬累積 |
| 已過期媒體的 URL 打不開 | 檔案已從 LINE 伺服器刪除；URL 照樣輸出，`content_expired=Y` |
| 媒體 URL 在別的瀏覽器打不開 | `chat-content.line.biz` 需要後台登入；貼圖 URL 是公開的 |
| 某些 OA 被略過 | 回應模式是 BOT（聊天功能關閉）的 OA 沒有對話可讀 |
| 方式 B、C 中斷要重跑 | 資料暫存在分頁記憶體；單一 zip 上限 65,535 個檔案、4 GB。大型 OA 請用方式 A |
| 未來可能失效 | 使用 LINE 後台的非公開 API，LINE 改版時需要更新本 Skill |

## 保持更新

機制與頻率和 [aigo-app-builder-skill](https://github.com/AI-GO-APP/aigo-app-builder-skill) 相同。

Skill 內含版本標記（`VERSION`）與更新腳本（`scripts/check_update.py`），比對本地與 GitHub main 上的
`VERSION`；**遠端較新時直接把本機所有已註冊安裝強制同步到遠端 main，不詢問、不保留本地修改**。

| 項目 | 行為 |
|---|---|
| 觸發時機 | 每次 Skill 被觸發（`SKILL.md` 步驟 0）；另可加裝 SessionStart hook（見下） |
| 檢查頻率 | 遠端 `VERSION` 每 **3 小時**最多抓一次並快取；本地與遠端的**比對每次都做** |
| 失敗重試 | 同一份安裝對同一個遠端版本同步失敗後，**3 小時內**不再重試 |
| 離線／逾時 | 一律靜默略過，不影響使用（抓 `VERSION` 逾時 3 秒） |
| git 安裝 | `git fetch origin main` → `git reset --hard FETCH_HEAD` → `git clean -fd`（gitignore 項目不動） |
| 複製式安裝 | 下載遠端 `main.zip` 鏡像覆蓋：遠端有的全部寫入，本地多出來的刪除 |
| 永遠保留 | `.git`、`.venv`、`.aigo`、`.claude`、`.env`、`node_modules`、`line_oa_export` |
| 多份安裝 | 每份執行過檢查的安裝都會登記；任一份發現新版時，清單裡所有落後的安裝一起同步 |
| 開發用副本 | 本地版本**高於**遠端、或 git 副本**不在 main／master 分支** → 略過不動 |
| 狀態檔 | `~/.aigo/line_oa_scraper_update_check.json`（與 builder skill 的狀態檔分開） |

**你在安裝目錄裡做的任何修改都會被覆蓋**；要改 Skill 內容請對本 repo 開 PR。

### 加裝 SessionStart hook（Claude Code / Codex，推薦）

在 Skill 載入**之前**就完成同步，新版在當下就生效。範本在 `resources/hooks/`，
把 `<SKILL_DIR>` 換成本機 skill 路徑後合併進設定：

| Agent | 設定檔 | 範本 |
|---|---|---|
| Claude Code | `~/.claude/settings.json` 或 `<專案>/.claude/settings.json` | `resources/hooks/claude-code.settings.example.json` |
| Codex CLI（>= v0.124.0） | `~/.codex/config.toml` 或 `<repo>/.codex/config.toml` | `resources/hooks/codex.config.example.toml` |

已有 builder skill 的 hook 時，把本項目加進同一個 `SessionStart` 陣列即可，兩者互不干擾。

### 手動執行

```bash
python scripts/check_update.py               # 檢查並同步（macOS/Linux 用 python3）；沒動作就沒輸出
python scripts/check_update.py --force       # 忽略 3 小時節流（含失敗重試抑制）
python scripts/check_update.py --json        # 機器可讀輸出，含每份安裝的同步結果
python scripts/check_update.py --check-only  # 只報告不同步（維護者／CI 用）
```

## 維護者規則：PR 合併即發布

`main` 分支上的 `VERSION` 就是「已發布版本」。**PR 合併進 main 的那一刻就是發布**：
使用者端最晚 3 小時內（或下一次觸發 Skill 時）會被自動強制同步到新版。所以進 main 的每個變更都要當成正式發布對待。

> `main` **沒有開啟分支保護**，GitHub 不會強制擋下直推或 CI 未過的合併——以下規則靠每位維護者自行遵守。
> `release-check` CI 失敗時請先修好再合併，不要略過。

### 規則

1. **不直接推 main**，一律開分支、發 PR、合併。分支命名沿用 builder skill 的慣例：
   `feat/…`（新功能）、`fix/…`（修正）、`docs/…`（只動文件）、`chore/…`（CI、雜項）。
2. **改到 Skill 內容就要 bump `VERSION`**。Skill 內容＝`SKILL.md`、`scripts/`、`references/`、`resources/`。
   沒 bump 的話合併後**沒有任何使用者會收到更新**。只動 `README.md`、`CHANGELOG.md`、`.github/` 可以不 bump。
3. **版本號用 semver**，在 PR 裡就改好，不要合併後再補：

   | 變更 | 版本 | 例 |
   |---|---|---|
   | 修正錯誤、文件措辭、不改行為 | patch | 1.2.0 → 1.2.1 |
   | 新功能、新參數、新輸出欄位（向下相容） | minor | 1.2.1 → 1.3.0 |
   | 破壞性變更：CSV 欄位改名／刪除、參數移除、輸出結構改變 | major | 1.3.0 → 2.0.0 |

4. **`CHANGELOG.md` 最上方新增一節** `## X.Y.Z — YYYY-MM-DD`，寫使用者看得懂的變更。
   - 舊版安裝只會讀到新版那一節的**前 20 行**，當作同步後的變更摘要顯示給使用者。
   - **破壞性變更要在該節第一行寫「破壞性」或「BREAKING」**，並說明不更新會怎樣。
     這兩個字樣會讓同步失敗時的提醒升級，不能埋在後面。
5. **PR 標題**：`類型: 說明（版本）`，例如 `fix: 檔案下載改走 /download 網址（1.2.1）`。
6. **合併前自我驗證**（PR 描述裡寫出做了哪些）：
   - `release-check` CI 通過（語法檢查、VERSION 前進、CHANGELOG 有對應小節）
   - 改到爬取邏輯：至少用一個真實 OA 跑過 `--limit-chats 3`，確認 CSV 與 `summary.json` 正常
   - 改到唯讀相關的程式碼：確認仍然只對 `/api/` 發 GET、沒有載入聊天介面
   - 改到 `check_update.py`：用 `LINE_OA_SCRAPER_UPDATE_STATE_FILE` 指向暫存檔，測 git 與複製式兩種安裝的同步
7. **合併方式**：squash merge，commit 訊息沿用 PR 標題。
8. **合併後**：到 GitHub 的 raw `VERSION` 確認已是新版號（CDN 可能延遲數分鐘），
   需要時用 `python scripts/check_update.py --force` 讓本機安裝立即同步。

### 開發環境注意

- 在 **feature 分支**上開發：更新機制會把非 main／master 分支的 git 副本視為開發用副本而略過。
- 在 main 上修改但還沒 bump `VERSION` 時，若遠端出了新版，本機副本會被強制同步覆蓋——
  所以先開分支再動手。
- 不要在安裝目錄（`~/.claude/skills/…`）裡直接改檔，會被下次同步蓋掉。

### CI

`.github/workflows/release-check.yml` 在每個對 main 的 PR 上執行：

- `scripts/*.py` 編譯檢查、`crawl_in_page.js` 語法檢查
- 若 PR 改到 Skill 內容：`VERSION` 必須是合法 semver 且大於 main 上的版本，`CHANGELOG.md` 必須有 `## <新版號>` 一節

## 目錄結構

```
line-oa-message-scraper-skill/
├── SKILL.md                  # Agent 工作流程、鐵則、三條路徑的判斷
├── README.md                 # 本文件
├── VERSION                   # 已發布版本（更新檢查的比對基準）
├── CHANGELOG.md              # 版本變更紀錄
├── LICENSE                   # MIT 授權
├── references/
│   ├── api.md                # chat.line.biz 內部 API、事件結構、媒體網址規則、需避開的請求
│   └── csv-schema.md         # CSV 欄位定義
├── resources/hooks/          # SessionStart 更新檢查 hook 範本（Claude Code、Codex）
├── scripts/
│   ├── line_oa_scrape.py     # 方式 A：連上使用者的 Chrome（CDP）爬取、下載媒體、輸出 CSV；export 匯入 B／C 的產出
│   ├── crawl_in_page.js      # 方式 B、C：瀏覽器內抓取，可含媒體，產出單一檔案
│   ├── check_update.py       # 自我更新（零相依）
│   └── requirements.txt
└── .github/workflows/release-check.yml
```

## 資料安全

- 輸出包含客戶個資與完整對話。請存放在受控位置，不要 commit 進任何 repo 或上傳到外部服務。
- 不要把輸出資料夾放在 Skill 安裝目錄裡：自我更新會鏡像覆蓋該目錄（`line_oa_export/` 例外）。
- 方式 B、C 的產出會先落在「下載」資料夾，匯入後記得移走。

## License

[MIT](LICENSE)
