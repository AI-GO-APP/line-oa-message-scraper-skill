#!/usr/bin/env python3
"""LINE OA Message Scraper — 把 LINE 官方帳號後台 (chat.line.biz) 的對話全量匯出成 CSV。

連線方式: 透過 Chrome DevTools Protocol 連上「使用者正在使用、已登入」的 Chrome，
在其中開一個分頁停在 chat.line.biz 的 JSON API 頁面，由該分頁代發 GET 請求。
不會另開乾淨的瀏覽器，也不會載入聊天介面。

安全保證:
  * 對 chat.line.biz 只發 GET，且路徑必須以 /api/ 開頭 (見 Api.get)
  * 不載入聊天介面 → 不會觸發 markAsRead、不會改動未讀狀態、不可能送出訊息
  * 結束時只關閉自己開的分頁，不關閉使用者的瀏覽器

子指令:
  doctor                 檢查 Chrome 連線與登入狀態
  list                   列出帳號可存取的所有 OA 與是否可爬
  scrape <url...>|--all  全量爬取並輸出 CSV
  export [bundle.json]   由瀏覽器內抓取的資料包或既有原始資料重新產生 CSV
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import socket
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

BASE = "https://chat.line.biz"
HOME_PATH = "/api/v1/me"  # 停在 JSON 頁面，完全不載入聊天介面
CONTENT_BASE = "https://chat-content.line.biz"
STICKER_URL = "https://stickershop.line-scdn.net/stickershop/v1/sticker/{}/android/sticker.png"
TAIPEI = timezone(timedelta(hours=8))
BOT_ID_RE = re.compile(r"(U[0-9a-f]{32})")
FOLDERS = ("ALL", "SPAM", "DONE")  # ALL 可能不含垃圾訊息／已完成，合併後去重

CSV_COLUMNS = [
    "bot_id", "bot_name", "chat_id", "chat_type", "chat_name",
    "timestamp", "timestamp_ms", "event_type", "direction",
    "sender_id", "sender_name", "message_id", "message_type", "text",
    "content_url", "preview_url", "content_expired", "content_expires_at",
    "file_name", "file_size", "duration_ms", "local_path",
    "sticker_package_id", "sticker_id", "sticker_resource_type", "sticker_url",
    "quoted_message_id", "raw_json",
]

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str = "", end: str = "\n") -> None:
    print(msg, end=end, flush=True)


# ─────────────────────────── 連上使用者的 Chrome ───────────────────────────

def chrome_user_data_dirs() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        names = [r"Google\Chrome", r"Google\Chrome Beta", r"Google\Chrome SxS",
                 r"Microsoft\Edge", r"BraveSoftware\Brave-Browser", "Chromium"]
        return [local / n / "User Data" for n in names]
    if sys.platform == "darwin":
        sup = home / "Library" / "Application Support"
        names = ["Google/Chrome", "Google/Chrome Beta", "Google/Chrome Canary",
                 "Microsoft Edge", "BraveSoftware/Brave-Browser", "Chromium"]
        return [sup / n for n in names]
    cfg = home / ".config"
    return [cfg / n for n in ("google-chrome", "google-chrome-beta", "chromium",
                              "microsoft-edge", "BraveSoftware/Brave-Browser")]


def cdp_candidates(explicit: str | None) -> list[str]:
    out: list[str] = []
    for value in (explicit, os.environ.get("LINE_OA_CDP")):
        if value:
            out.append(value)
    # Chrome 144+ 在 chrome://inspect/#remote-debugging 開啟後會寫入 DevToolsActivePort
    for d in chrome_user_data_dirs():
        f = d / "DevToolsActivePort"
        try:
            lines = f.read_text(encoding="utf-8").split()
        except OSError:
            continue
        if len(lines) >= 2:
            out.append(f"ws://127.0.0.1:{lines[0]}{lines[1]}")
    # 傳統 --remote-debugging-port 啟動的瀏覽器
    for port in (9222, 9223, 9229):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                ws = json.load(r).get("webSocketDebuggerUrl")
                if ws:
                    out.append(ws)
        except Exception:
            pass
    # 部分 Chrome 版本開啟 chrome://inspect 遠端除錯後只聽 9222、不寫 DevToolsActivePort，
    # 也沒有 /json/version；最後嘗試直接以 WebSocket 連線
    if not out:
        try:
            socket.create_connection(("127.0.0.1", 9222), timeout=1).close()
            out.append("ws://127.0.0.1:9222/devtools/browser")
        except OSError:
            pass
    return list(dict.fromkeys(out))


ENABLE_HELP = """\
找不到可連線的 Chrome。本工具只使用你「正在使用、已登入」的 Chrome，不會另開瀏覽器。
請擇一設定後重試:
  1. (建議) 在 Chrome 網址列開啟 chrome://inspect/#remote-debugging ，
     開啟允許遠端除錯的選項。之後每次連線 Chrome 會跳出確認視窗，按「允許」即可。
  2. 若 Chrome 是以 --remote-debugging-port=9222 啟動，直接重試；
     或用 --cdp ws://127.0.0.1:<port>/devtools/browser/<id> 指定端點。
"""


def connect_live_chrome(pw, explicit: str | None):
    candidates = cdp_candidates(explicit)
    if not candidates:
        raise SystemExit(ENABLE_HELP)
    errors = []
    for endpoint in candidates:
        log(f"連線到 Chrome: {endpoint.split('/devtools')[0]} …（若 Chrome 跳出確認視窗請按「允許」）")
        try:
            return pw.chromium.connect_over_cdp(endpoint, timeout=90_000)
        except Exception as e:
            errors.append(f"  {endpoint}: {str(e).splitlines()[0]}")
    raise SystemExit(ENABLE_HELP + "\n嘗試過的端點:\n" + "\n".join(errors))


JS_FETCH = """async (path) => {
  try {
    const r = await fetch(path, {method: 'GET', credentials: 'include', redirect: 'manual'});
    if (r.type === 'opaqueredirect') return {status: 401, text: ''};
    return {status: r.status, text: await r.text()};
  } catch (e) { return {status: -1, text: String(e)}; }
}"""

JS_FETCH_BINARY = """async (url) => {
  try {
    const r = await fetch(url, {method: 'GET', credentials: 'include'});
    if (!r.ok) return {status: r.status};
    const buf = new Uint8Array(await r.arrayBuffer());
    let s = '';
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return {status: r.status, type: r.headers.get('content-type') || '', b64: btoa(s)};
  } catch (e) { return {status: -1, error: String(e)}; }
}"""


class SessionExpired(Exception):
    pass


class LiveTab:
    """在使用者的 Chrome 裡開一個專用分頁，停在 chat.line.biz 的 JSON API 頁面。"""

    def __init__(self, browser):
        if not browser.contexts:
            raise SystemExit("已連上 Chrome，但沒有可用的瀏覽器設定檔視窗。")
        self.context = browser.contexts[0]
        self.page = None

    def open(self) -> None:
        self.page = self.context.new_page()
        self.page.goto(BASE + HOME_PATH, wait_until="domcontentloaded", timeout=60_000)

    def close(self) -> None:
        if self.page and not self.page.is_closed():
            self.page.close()

    def _ensure_page(self) -> None:
        if self.page is None or self.page.is_closed():
            self.open()
        elif urlparse(self.page.url).netloc != "chat.line.biz":
            self.page.goto(BASE + HOME_PATH, wait_until="domcontentloaded", timeout=60_000)

    def fetch(self, path: str) -> tuple[int, str]:
        self._ensure_page()
        res = self.page.evaluate(JS_FETCH, path)
        return res["status"], res["text"]

    def fetch_binary(self, url: str) -> tuple[int, str, bytes]:
        self._ensure_page()
        res = self.page.evaluate(JS_FETCH_BINARY, url)
        body = base64.b64decode(res["b64"]) if res.get("b64") else b""
        return res["status"], res.get("type", ""), body

    def logged_in(self) -> bool:
        try:
            status, _ = self.fetch(HOME_PATH)
        except Exception:
            return False
        return status == 200

    def ensure_login(self, wait_seconds: int = 600) -> None:
        if self.logged_in():
            return
        log("這個 Chrome 尚未登入 LINE 官方帳號後台。已在新分頁開啟登入頁，請在該分頁登入…")
        self.page.goto(BASE + "/", wait_until="domcontentloaded")
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            time.sleep(3)
            try:
                host = urlparse(self.page.url).netloc
            except Exception:
                continue
            if host == "chat.line.biz":
                # 登入完成後立刻離開聊天介面，回到 JSON 頁面
                self.page.goto(BASE + HOME_PATH, wait_until="domcontentloaded")
                if self.logged_in():
                    log("登入成功。")
                    return
        raise SystemExit("等待登入逾時。")


# ─────────────────────────────── 唯讀 API ───────────────────────────────

class Api:
    """只允許對 /api/ 發 GET。這是「不送出任何訊息」的最後一道保險。"""

    def __init__(self, tab: LiveTab, delay: float):
        self.tab = tab
        self.delay = delay
        self.requests = 0

    def get(self, path: str, allow_status: tuple[int, ...] = ()) -> tuple[int, dict]:
        if not path.startswith("/api/"):
            raise ValueError(f"拒絕非 API 路徑: {path}")
        for attempt in range(6):
            time.sleep(self.delay)
            try:
                status, text = self.tab.fetch(path)
            except Exception as e:  # 分頁被關閉、瀏覽器暫時無回應等
                wait = 2 ** attempt
                log(f"    分頁錯誤 ({str(e).splitlines()[0][:80]})，{wait}s 後重試")
                time.sleep(wait)
                continue
            self.requests += 1
            if status == 200:
                return status, json.loads(text)
            if status in allow_status:
                try:
                    return status, json.loads(text)
                except ValueError:
                    return status, {}
            if status == 401:
                raise SessionExpired()
            if status in (-1, 429) or status >= 500:
                wait = 2 ** attempt * 2
                log(f"    HTTP {status}，{wait}s 後重試")
                time.sleep(wait)
                continue
            raise RuntimeError(f"GET {path} -> HTTP {status}: {text[:200]}")
        raise RuntimeError(f"GET {path} 重試多次仍失敗")

    def paged(self, path: str, token_key: str, allow_status: tuple[int, ...] = ()):
        """依 token 分頁逐頁 yield list；遇到 allow_status 的錯誤時停止。"""
        token = None
        while True:
            sep = "&" if "?" in path else "?"
            url = path + (f"{sep}{token_key}={quote(token, safe='')}" if token else "")
            status, data = self.get(url, allow_status)
            if status != 200:
                return
            yield data.get("list", [])
            token = data.get(token_key)
            if not token:
                return


# ─────────────────────────────── 爬取 ───────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def list_bots(api: Api) -> list[dict]:
    _, data = api.get("/api/v1/bots?limit=1000&noFilter=true")
    return data.get("list", [])


def crawl_bot(api: Api, bot_id: str, out_dir: Path, limit_chats: int | None) -> dict | None:
    status, bot = api.get(f"/api/v1/bots/{bot_id}?noFilter=true", allow_status=(403, 404))
    if status != 200:
        log(f"\n!! 無法存取 OA {bot_id} (HTTP {status} {bot.get('code', '')})，略過")
        return None
    log(f"\n=== {bot.get('name')} ({bot_id}) ===")
    if bot.get("responseMode") != "CHAT":
        log(f"!! 此 OA 的回應模式是 {bot.get('responseMode')}，後台沒有聊天功能，無法爬取，略過")
        return None

    bot_dir = out_dir / "raw" / bot_id
    bot_dir.mkdir(parents=True, exist_ok=True)
    _, owners = api.get(f"/api/v1/bots/{bot_id}/owners", allow_status=(403,))

    chats: dict[str, dict] = {}
    for folder in FOLDERS:
        for page in api.paged(f"/api/v2/bots/{bot_id}/chats?folderType={folder}&limit=25",
                              "next", allow_status=(400,)):
            for c in page:
                chats.setdefault(c["chatId"], c)
            log(f"  對話串列表: {len(chats)}", end="\r")
    chat_list = list(chats.values())
    log(f"  對話串列表: {len(chat_list)} 個")
    if limit_chats:
        chat_list = chat_list[:limit_chats]

    save_json(bot_dir / "_bot.json", {"bot": bot, "owners": owners.get("list", [])})
    save_json(bot_dir / "_chats.json", chat_list)

    state_path = bot_dir / "_state.json"
    state = load_json(state_path, {})

    for i, chat in enumerate(chat_list, 1):
        chat_id = chat["chatId"]
        name = (chat.get("profile") or {}).get("name", "")
        # 以最後收發時間判斷有無新訊息（lastTalkedAt 會被已讀動作改動，不採用）
        marker = max(chat.get("lastReceivedAt") or 0, chat.get("lastSentAt") or 0,
                     chat.get("updatedAt") or 0)
        st = state.get(chat_id, {})
        msg_path = bot_dir / f"{chat_id}.jsonl"
        label = f"  [{i}/{len(chat_list)}] {name[:20]}"

        if st.get("done") and st.get("marker") == marker and msg_path.exists():
            log(f"{label}: 無新訊息，沿用 ({st.get('count', 0)} 則)")
            continue

        if chat.get("chatType") != "USER":
            members = []
            # 已退出的群組會回 404，不影響訊息抓取
            for page in api.paged(f"/api/v1/bots/{bot_id}/chats/{chat_id}/members?limit=100",
                                  "next", allow_status=(403, 404)):
                members.extend(page)
            save_json(bot_dir / f"{chat_id}.members.json", members)

        # 同一輪中斷時，從上次的 backward token 接續
        resume = (not st.get("done") and st.get("marker") == marker
                  and st.get("backward") and msg_path.exists())
        token = st["backward"] if resume else None
        count = st.get("count", 0) if resume else 0

        with msg_path.open("a" if resume else "w", encoding="utf-8") as f:
            while True:
                path = f"/api/v3/bots/{bot_id}/chats/{chat_id}/messages"
                if token:
                    path += f"?backward={quote(token, safe='')}"
                _, data = api.get(path)
                events = data.get("list", [])
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                count += len(events)
                token = data.get("backward")
                state[chat_id] = {"done": not token, "marker": marker,
                                  "backward": token, "count": count}
                save_json(state_path, state)
                log(f"{label}: {count} 則", end="\r")
                if not token:
                    break
        log(f"{label}: {count} 則 (到底)")
    return bot


def media_url(bot_id: str, msg: dict) -> tuple[str, str]:
    """回傳 (content_url, preview_url)。不論是否過期都組出網址。"""
    provider = msg.get("contentProvider") or {}
    content_hash = msg.get("contentHash") or provider.get("contentHash")
    if content_hash:
        url = f"{CONTENT_BASE}/bot/{bot_id}/{content_hash}"
        if msg.get("type") == "file":
            # 檔案必須走 /download，直接取原網址會 404
            return f"{url}/download?filename={quote(msg.get('fileName') or 'file')}", ""
        preview = f"{url}/preview" if msg.get("type") in ("image", "video") else ""
        return url, preview
    if provider.get("originalContentUrl"):
        return provider["originalContentUrl"], provider.get("previewImageUrl", "")
    return "", ""


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n]', "_", name).strip()[:120] or "file"


def download_media(tab: LiveTab, out_dir: Path, bot_ids: list[str], delay: float) -> None:
    for bot_id in bot_ids:
        bot_dir = out_dir / "raw" / bot_id
        if not bot_dir.exists():
            continue
        index_path = out_dir / "media" / bot_id / "_index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index = load_json(index_path, {})
        ok = skipped = fail = 0
        for msg_path in sorted(bot_dir.glob("*.jsonl")):
            chat_id = msg_path.stem
            for line in msg_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                msg = ev.get("message") or {}
                url, _ = media_url(bot_id, msg)
                if not url or not msg.get("id"):
                    continue
                if msg["id"] in index:
                    continue
                if msg.get("expired"):
                    skipped += 1
                    continue
                time.sleep(delay)
                status, ctype, body = tab.fetch_binary(url)
                if status != 200:
                    fail += 1
                    continue
                if msg.get("fileName"):
                    fname = safe_name(msg["fileName"])
                else:
                    ext = mimetypes.guess_extension((ctype or "").split(";")[0]) or ".bin"
                    fname = f"{msg.get('type', 'media')}{'.jpg' if ext == '.jpe' else ext}"
                stamp = datetime.fromtimestamp((ev.get("timestamp") or 0) / 1000, TAIPEI)
                rel = Path("media") / bot_id / chat_id / f"{stamp:%Y%m%d_%H%M%S}_{msg['id']}_{fname}"
                target = out_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                index[msg["id"]] = rel.as_posix()
                ok += 1
                if ok % 20 == 0:
                    save_json(index_path, index)
                log(f"  媒體 {bot_id[:8]}: 下載 {ok} / 已過期略過 {skipped} / 失敗 {fail}", end="\r")
        save_json(index_path, index)
        log(f"  媒體 {bot_id[:8]}: 下載 {ok} / 已過期略過 {skipped} / 失敗 {fail}      ")


# ─────────────────────────────── 輸出 CSV ───────────────────────────────

def fmt_ts(ms) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def event_key(ev: dict) -> str:
    mid = (ev.get("message") or {}).get("id")
    if mid:
        return f"{ev.get('type')}:{mid}"
    return json.dumps(ev, sort_keys=True, ensure_ascii=False)


def build_row(ev: dict, bot_id: str, bot_name: str, chat: dict,
              members: dict, owners: dict, media_index: dict) -> dict:
    profile = chat.get("profile") or {}
    msg = ev.get("message") or {}
    src = ev.get("source") or {}
    etype = ev.get("type", "")
    sender_id = src.get("userId", "")

    if etype == "messageSent":
        direction = "OA傳出"
        sender_id = ev.get("bizId") or sender_id
        # 沒有 bizId 的是自動回應或 Messaging API 送出的訊息
        sender_name = owners.get(ev.get("bizId"), "") or bot_name
    elif etype == "message":
        direction = "對方傳入"
        sender_name = profile.get("name", "") if chat.get("chatType") == "USER" \
            else members.get(sender_id, "")
    else:
        direction = "系統事件"
        sender_name = members.get(sender_id, "") if sender_id else ""

    row = dict.fromkeys(CSV_COLUMNS, "")
    row.update({
        "bot_id": bot_id, "bot_name": bot_name,
        "chat_id": chat["chatId"], "chat_type": chat.get("chatType", ""),
        "chat_name": profile.get("name", ""),
        "timestamp": fmt_ts(ev.get("timestamp")), "timestamp_ms": ev.get("timestamp", ""),
        "event_type": etype, "direction": direction,
        "sender_id": sender_id, "sender_name": sender_name,
        "message_id": msg.get("id", ""), "message_type": msg.get("type", ""),
        "text": msg.get("text", ""),
        "quoted_message_id": msg.get("quotedMessageId", ""),
        "raw_json": json.dumps(ev, ensure_ascii=False),
    })

    url, preview = media_url(bot_id, msg)
    if url:
        provider = msg.get("contentProvider") or {}
        expired = msg.get("expired", provider.get("expired"))
        row.update({
            "content_url": url, "preview_url": preview,
            "content_expired": "" if expired is None else ("Y" if expired else "N"),
            "content_expires_at": fmt_ts(msg.get("expiredAt") or provider.get("expiredAt")),
            "local_path": media_index.get(msg.get("id"), ""),
        })
    row["file_name"] = msg.get("fileName", "")
    row["file_size"] = msg.get("fileSize", "")
    row["duration_ms"] = msg.get("duration", "")

    if msg.get("type") == "sticker":
        row["sticker_package_id"] = msg.get("packageId", "")
        row["sticker_id"] = msg.get("stickerId", "")
        row["sticker_resource_type"] = msg.get("stickerResourceType", "")
        if msg.get("stickerId"):
            row["sticker_url"] = STICKER_URL.format(msg["stickerId"])

    if etype == "unsend":
        row["message_id"] = (ev.get("unsend") or {}).get("messageId", "")
    return row


def export_csv(out_dir: Path, bot_ids: list[str], include_read_events: bool) -> tuple[Path, dict]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"line_oa_{stamp}.csv"
    summary: dict = {"csv": str(csv_path.resolve()), "generated_at": stamp, "bots": []}
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for bot_id in bot_ids:
            bot_dir = out_dir / "raw" / bot_id
            meta = load_json(bot_dir / "_bot.json", {})
            bot_name = (meta.get("bot") or {}).get("name", "")
            owners = {o.get("bizId"): o.get("name", "") for o in meta.get("owners", [])}
            media_index = load_json(out_dir / "media" / bot_id / "_index.json", {})
            chats = load_json(bot_dir / "_chats.json", [])
            s = {"bot_id": bot_id, "bot_name": bot_name, "chats": len(chats),
                 "empty_chats": 0, "rows": 0, "by_type": {}, "media": 0,
                 "media_expired": 0, "oldest": None, "newest": None}
            for chat in chats:
                msg_path = bot_dir / f"{chat['chatId']}.jsonl"
                members = {m.get("userId"): m.get("name", "") for m in
                           load_json(bot_dir / f"{chat['chatId']}.members.json", [])}
                seen, events = set(), []
                if msg_path.exists():
                    for line in msg_path.read_text(encoding="utf-8").splitlines():
                        if not line.strip():
                            continue
                        ev = json.loads(line)
                        if ev.get("type") == "chatRead" and not include_read_events:
                            continue
                        key = event_key(ev)
                        if key not in seen:
                            seen.add(key)
                            events.append(ev)
                if not events:
                    s["empty_chats"] += 1
                events.sort(key=lambda e: e.get("timestamp") or 0)
                for ev in events:
                    row = build_row(ev, bot_id, bot_name, chat, members, owners, media_index)
                    writer.writerow(row)
                    k = f"{row['event_type']}/{row['message_type'] or '-'}"
                    s["by_type"][k] = s["by_type"].get(k, 0) + 1
                    if row["content_url"]:
                        s["media"] += 1
                        s["media_expired"] += row["content_expired"] == "Y"
                    if row["timestamp"]:
                        s["oldest"] = min(filter(None, [s["oldest"], row["timestamp"]]))
                        s["newest"] = max(filter(None, [s["newest"], row["timestamp"]]))
                s["rows"] += len(events)
            summary["bots"].append(s)
    summary["rows"] = sum(b["rows"] for b in summary["bots"])
    save_json(out_dir / "summary.json", summary)
    return csv_path, summary


def print_summary(summary: dict) -> None:
    log("\n──────── 匯出摘要 ────────")
    for b in summary["bots"]:
        log(f"{b['bot_name']} ({b['bot_id']})")
        log(f"  對話串 {b['chats']}（其中 {b['empty_chats']} 個取不到任何訊息）")
        log(f"  事件 {b['rows']} 筆，時間 {b['oldest']} ~ {b['newest']}")
        log(f"  媒體 {b['media']} 個，其中已過期 {b['media_expired']} 個")
    log(f"CSV: {summary['csv']}  （共 {summary['rows']} 筆）")


MEDIA_ENTRY_RE = re.compile(r"^media/(U[0-9a-f]{32})/([^/]+)/\d{8}_\d{6}_(\d+)_[^/]+$")


def import_bundle(bundle_path: Path, out_dir: Path) -> list[str]:
    """匯入 crawl_in_page.js 的產出，展開成 raw/ 與 media/ 的標準結構。

    接受 line_oa_bundle.json，或含 line_oa_bundle.json 與 media/ 的 line_oa_export.zip。
    """
    if bundle_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(bundle_path) as z:
            bad = z.testzip()
            if bad:
                raise SystemExit(f"zip 內容損毀: {bad}")
            bundle = json.loads(z.read("line_oa_bundle.json").decode("utf-8"))
            indexes: dict[str, dict] = {}
            for name in z.namelist():
                m = MEDIA_ENTRY_RE.match(name)
                if not m or ".." in name:
                    continue  # 只接受預期格式的路徑，防止寫到輸出資料夾以外
                target = out_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                indexes.setdefault(m.group(1), {})[m.group(3)] = name
            for bot_id, idx in indexes.items():
                index_path = out_dir / "media" / bot_id / "_index.json"
                save_json(index_path, {**load_json(index_path, {}), **idx})
                log(f"  媒體 {bot_id[:8]}: 解出 {len(idx)} 個檔案")
    else:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    bot_ids = []
    for bot_id, b in bundle["bots"].items():
        bot_dir = out_dir / "raw" / bot_id
        bot_dir.mkdir(parents=True, exist_ok=True)
        save_json(bot_dir / "_bot.json", {"bot": b["bot"], "owners": b.get("owners", [])})
        save_json(bot_dir / "_chats.json", b["chats"])
        for chat_id, members in b.get("members", {}).items():
            save_json(bot_dir / f"{chat_id}.members.json", members)
        for chat_id, events in b.get("events", {}).items():
            with (bot_dir / f"{chat_id}.jsonl").open("w", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        bot_ids.append(bot_id)
    return bot_ids


# ─────────────────────────────── CLI ───────────────────────────────

def parse_bot_ids(urls: list[str]) -> list[str]:
    ids = []
    for url in urls:
        m = BOT_ID_RE.search(url)
        if not m:
            raise SystemExit(f"無法從連結解析 OA ID（應為 chat.line.biz/U 開頭 33 碼）: {url}")
        if m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def with_live_chrome(args, fn, wait_login: bool = True):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = connect_live_chrome(pw, args.cdp)
        tab = LiveTab(browser)
        try:
            tab.open()
            if wait_login:
                tab.ensure_login()
            return fn(tab)
        finally:
            tab.close()  # 只關自己開的分頁；不關閉使用者的瀏覽器


def cmd_doctor(args) -> None:
    candidates = cdp_candidates(args.cdp)
    log("可用的 Chrome 端點: " + (", ".join(c.split("/devtools")[0] for c in candidates) or "無"))
    if not candidates:
        raise SystemExit(ENABLE_HELP)

    def run(tab: LiveTab):
        log("已連上 Chrome。")
        if not tab.logged_in():
            raise SystemExit("這個 Chrome 尚未登入 LINE 官方帳號後台 (chat.line.biz)，請先登入。")
        _, me = Api(tab, 0).get(HOME_PATH)
        log(f"已登入後台: {me.get('name') or '(未提供名稱)'}")
        log("連線與登入狀態正常，可以開始爬取。")
    with_live_chrome(args, run, wait_login=False)


def cmd_list(args) -> None:
    def run(tab: LiveTab):
        bots = list_bots(Api(tab, 0.2))
        log(f"\n{'可爬':<4} {'模式':<5} {'權限':<9} 名稱  →  連結")
        for b in bots:
            ok = "是" if b.get("responseMode") == "CHAT" else "否"
            log(f"{ok:<4} {b.get('responseMode', ''):<5} {b.get('userPermissionType', ''):<9} "
                f"{b.get('name')}  →  {BASE}/{b['botId']}")
        log(f"\n共 {len(bots)} 個 OA；只有 CHAT 模式的 OA 後台有聊天記錄可爬。")
    with_live_chrome(args, run)


def cmd_scrape(args) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    def run(tab: LiveTab):
        api = Api(tab, args.delay)
        if args.all:
            bot_ids = [b["botId"] for b in list_bots(api) if b.get("responseMode") == "CHAT"]
        else:
            bot_ids = parse_bot_ids(args.urls)
        done = []
        for bot_id in bot_ids:
            while True:
                try:
                    if crawl_bot(api, bot_id, out_dir, args.limit_chats):
                        done.append(bot_id)
                    break
                except SessionExpired:
                    log("\n登入已失效（進度已保存），請重新登入…")
                    tab.page.goto(BASE + HOME_PATH)
                    tab.ensure_login()
        if args.download_media:
            download_media(tab, out_dir, done, args.delay)
        log(f"\n共發出 {api.requests} 次 GET 請求。")
        return done

    if not args.all and not args.urls:
        raise SystemExit("請提供 chat.line.biz 連結，或使用 --all")
    done = with_live_chrome(args, run)
    csv_path, summary = export_csv(out_dir, done, args.include_read_events)
    print_summary(summary)


def cmd_export(args) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.bundle:
        bot_ids = import_bundle(Path(args.bundle), out_dir)
    else:
        bot_ids = sorted(p.name for p in (out_dir / "raw").glob("U*") if p.is_dir())
    if not bot_ids:
        raise SystemExit(f"{out_dir / 'raw'} 裡沒有任何原始資料。")
    _, summary = export_csv(out_dir, bot_ids, args.include_read_events)
    print_summary(summary)


def main() -> None:
    p = argparse.ArgumentParser(description="LINE OA Message Scraper：全量匯出 chat.line.biz 對話為 CSV")
    p.add_argument("--cdp", help="Chrome DevTools 端點 (預設自動偵測使用者正在使用的 Chrome)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="檢查 Chrome 連線與登入狀態")
    sub.add_parser("list", help="列出可存取的 OA")

    s = sub.add_parser("scrape", help="全量爬取並輸出 CSV")
    s.add_argument("urls", nargs="*", help="chat.line.biz/U... 連結，可多個")
    s.add_argument("--all", action="store_true", help="爬取帳號下所有 CHAT 模式的 OA")
    s.add_argument("--out", default="line_oa_export", help="輸出資料夾 (預設 line_oa_export)")
    s.add_argument("--delay", type=float, default=0.3, help="每次請求間隔秒數 (預設 0.3)")
    s.add_argument("--limit-chats", type=int, help="每個 OA 只爬前 N 個對話串 (測試用)")
    s.add_argument("--download-media", action="store_true", help="一併下載未過期的圖片／影片／檔案")
    s.add_argument("--include-read-events", action="store_true", help="CSV 包含已讀事件")

    e = sub.add_parser("export", help="由資料包或既有原始資料重新產生 CSV")
    e.add_argument("bundle", nargs="?",
                   help="crawl_in_page.js 下載的 line_oa_bundle.json 或 line_oa_export.zip")
    e.add_argument("--out", default="line_oa_export", help="輸出資料夾 (預設 line_oa_export)")
    e.add_argument("--include-read-events", action="store_true", help="CSV 包含已讀事件")

    args = p.parse_args()
    {"doctor": cmd_doctor, "list": cmd_list, "scrape": cmd_scrape, "export": cmd_export}[args.cmd](args)


if __name__ == "__main__":
    main()
