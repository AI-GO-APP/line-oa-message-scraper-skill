// LINE OA Message Scraper — 瀏覽器內抓取腳本（不需要開啟 Chrome 遠端除錯）
//
// 在使用者已登入的 Chrome 中，於 https://chat.line.biz/api/v1/me 這個 JSON 頁面執行
// （停在 API 頁面就完全不會載入聊天介面，不會觸發已讀）。只發 GET，不會送出任何訊息。
// 可由 agent 透過 Claude in Chrome 執行，也可由使用者按 F12 貼進 Console 執行。
//
// 設定（執行前先定義，全部可省略）:
//   window.__LINE_OA_CONFIG = {
//     botIds: ['U...'],      // 留空時抓網址中的 OA
//     all: false,            // true 時抓帳號下所有 CHAT 模式的 OA
//     downloadMedia: false,  // true 時一併下載未過期的圖片／影片／檔案
//     delayMs: 300,          // 每次請求間隔
//     limitChats: 0,         // 每個 OA 只抓前 N 個對話串（試跑用，0＝全部）
//     autoDownload: true,    // 完成後自動下載結果
//   };
// 進度: window.__lineOaCrawl.status 為 running / done / error，progress 為文字進度，summary() 為摘要。
// 產出: 一次下載一個檔案（避免 Chrome 擋連續自動下載）
//   downloadMedia=false → line_oa_bundle.json
//   downloadMedia=true  → line_oa_export.zip（內含 line_oa_bundle.json 與 media/）
//   交給 python line_oa_scrape.py export <檔案> 轉成 CSV。
//   失敗或被擋時可呼叫 window.__lineOaCrawl.download() 重新下載。
(() => {
  const cfg = Object.assign(
    { botIds: [], all: false, downloadMedia: false, delayMs: 300, autoDownload: true, limitChats: 0 },
    window.__LINE_OA_CONFIG || {});
  const FOLDERS = ['ALL', 'SPAM', 'DONE'];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const S = (window.__lineOaCrawl = {
    status: 'running', progress: '', requests: 0, warnings: [], bots: {},
    media: { total: 0, ok: 0, expired: 0, failed: [] }, startedAt: Date.now(),
  });

  // ── 最小 ZIP（store，不壓縮）；單一 zip 限 65,535 個檔案、4 GB ──
  const CRC_TABLE = new Uint32Array(256).map((_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc32 = buf => {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 255] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  };
  const zipEntries = [];
  const addToZip = (path, data) => zipEntries.push({ name: new TextEncoder().encode(path), data, crc: crc32(data) });
  const buildZip = () => {
    const parts = [], central = [];
    let offset = 0;
    for (const e of zipEntries) {
      const lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true);
      lh.setUint32(14, e.crc, true); lh.setUint32(18, e.data.length, true); lh.setUint32(22, e.data.length, true);
      lh.setUint16(26, e.name.length, true);
      parts.push(new Uint8Array(lh.buffer), e.name, e.data);
      const ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true);
      ch.setUint16(8, 0x0800, true); ch.setUint32(16, e.crc, true); ch.setUint32(20, e.data.length, true);
      ch.setUint32(24, e.data.length, true); ch.setUint16(28, e.name.length, true); ch.setUint32(42, offset, true);
      central.push(new Uint8Array(ch.buffer), e.name);
      offset += 30 + e.name.length + e.data.length;
    }
    const cdSize = central.reduce((a, b) => a + b.length, 0);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, zipEntries.length, true);
    end.setUint16(10, zipEntries.length, true); end.setUint32(12, cdSize, true); end.setUint32(16, offset, true);
    return new Blob([...parts, ...central, new Uint8Array(end.buffer)], { type: 'application/zip' });
  };

  const saveBlob = (blob, filename) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    (document.body || document.documentElement).appendChild(a);
    a.click();
    a.remove();
    return blob.size;
  };

  const bundleJson = () => JSON.stringify({ crawledAt: Date.now(), status: S.status, bots: S.bots });

  S.download = () => {
    if (!cfg.downloadMedia) {
      return saveBlob(new Blob([bundleJson()], { type: 'application/json' }), 'line_oa_bundle.json');
    }
    const i = zipEntries.findIndex(e => new TextDecoder().decode(e.name) === 'line_oa_bundle.json');
    if (i >= 0) zipEntries.splice(i, 1);
    addToZip('line_oa_bundle.json', new TextEncoder().encode(bundleJson()));
    return saveBlob(buildZip(), 'line_oa_export.zip');
  };

  S.summary = () => ({
    bots: Object.values(S.bots).map(b => {
      const events = Object.values(b.events).flat();
      const ts = events.map(e => e.timestamp).filter(Boolean);
      return {
        name: b.bot.name, chats: b.chats.length, contacts: b.contacts.length,
        notes: Object.values(b.notes).flat().length, tags: b.tags.length,
        emptyChats: Object.values(b.events).filter(e => !e.length).length,
        events: events.length,
        oldest: ts.length ? new Date(Math.min(...ts)).toISOString() : null,
        newest: ts.length ? new Date(Math.max(...ts)).toISOString() : null,
      };
    }),
    media: { ...S.media, failed: S.media.failed.length },
    warnings: S.warnings.length,
  });

  // 唯一的 API 出口: 只允許 /api/ 的 GET
  const get = async (path, softStatuses = []) => {
    if (!path.startsWith('/api/')) throw new Error('拒絕非 API 路徑: ' + path);
    for (let attempt = 0; attempt < 6; attempt++) {
      await sleep(cfg.delayMs);
      let r;
      try {
        r = await fetch(path, { method: 'GET', credentials: 'include', redirect: 'manual' });
      } catch (e) {
        await sleep(2000 * 2 ** attempt);
        continue;
      }
      S.requests++;
      if (r.type === 'opaqueredirect' || r.status === 401) throw new Error('登入已失效，請重新登入後再執行');
      if (r.status === 200) return { status: 200, data: await r.json() };
      if (r.status === 429 || r.status >= 500) {
        await sleep(2000 * 2 ** attempt);
        continue;
      }
      if (softStatuses.includes(r.status)) {
        S.warnings.push(`${r.status} ${path}`);
        return { status: r.status, data: await r.json().catch(() => ({})) };
      }
      throw new Error(`HTTP ${r.status} ${path}`);
    }
    throw new Error('重試多次仍失敗: ' + path);
  };

  const paged = async (path, tokenKey, onPage, softStatuses) => {
    let token = null;
    do {
      const sep = path.includes('?') ? '&' : '?';
      const res = await get(path + (token ? `${sep}${tokenKey}=${encodeURIComponent(token)}` : ''), softStatuses);
      if (res.status !== 200) return;
      onPage(res.data.list || []);
      token = res.data[tokenKey];
    } while (token);
  };

  // ── 媒體: 網址規則見 references/api.md ──
  const EXT = {
    'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp',
    'video/mp4': '.mp4', 'audio/mp4': '.m4a', 'audio/x-m4a': '.m4a', 'audio/mpeg': '.mp3',
  };
  const safeName = s => (s || '').replace(/[\\/:*?"<>|\r\n]/g, '_').trim().slice(0, 120);
  const taipeiStamp = ts => {
    const d = new Date((ts || 0) + 8 * 3600e3).toISOString();
    return d.slice(0, 10).replace(/-/g, '') + '_' + d.slice(11, 19).replace(/:/g, '');
  };
  const mediaUrl = (botId, m) => {
    const hash = m.contentHash || (m.contentProvider || {}).contentHash;
    if (!hash) return null;
    const url = `https://chat-content.line.biz/bot/${botId}/${hash}`;
    return m.type === 'file' ? `${url}/download?filename=${encodeURIComponent(m.fileName || 'file')}` : url;
  };

  const downloadMedia = async () => {
    const items = [], seen = new Set();
    for (const [botId, B] of Object.entries(S.bots)) {
      for (const [chatId, events] of Object.entries(B.events)) {
        for (const e of events) {
          const m = e.message || {};
          const url = mediaUrl(botId, m);
          if (!url || !m.id || seen.has(m.id)) continue;
          seen.add(m.id);
          if (m.expired) { S.media.expired++; continue; }
          items.push({ botId, chatId, ts: e.timestamp, m, url });
        }
      }
    }
    S.media.total = items.length;
    for (const it of items) {
      S.progress = `下載媒體 ${S.media.ok + S.media.failed.length + 1}/${items.length}`;
      await sleep(cfg.delayMs / 2);
      let r;
      try {
        r = await fetch(it.url, { method: 'GET', credentials: 'include' });
      } catch (e) {
        S.media.failed.push({ id: it.m.id, error: 'network' });
        continue;
      }
      if (!r.ok) {
        S.media.failed.push({ id: it.m.id, type: it.m.type, status: r.status });
        continue;
      }
      const data = new Uint8Array(await r.arrayBuffer());
      const name = it.m.fileName ? safeName(it.m.fileName)
        : it.m.type + (EXT[(r.headers.get('content-type') || '').split(';')[0]] || '.bin');
      addToZip(`media/${it.botId}/${it.chatId}/${taipeiStamp(it.ts)}_${it.m.id}_${name}`, data);
      S.media.ok++;
    }
  };

  (async () => {
    try {
      let bots = cfg.botIds.length ? cfg.botIds : [];
      if (cfg.all) {
        const res = await get('/api/v1/bots?limit=1000&noFilter=true');
        bots = res.data.list.filter(b => b.responseMode === 'CHAT').map(b => b.botId);
      }
      if (!bots.length) {
        const m = location.pathname.match(/U[0-9a-f]{32}/);
        if (!m) throw new Error('未指定 botIds，網址中也沒有 OA ID');
        bots = [m[0]];
      }

      for (const botId of bots) {
        const info = await get(`/api/v1/bots/${botId}?noFilter=true`, [403, 404]);
        if (info.status !== 200 || info.data.responseMode !== 'CHAT') {
          S.warnings.push(`略過 ${botId}: ${info.status !== 200 ? 'HTTP ' + info.status : '非 CHAT 模式'}`);
          continue;
        }
        const owners = await get(`/api/v1/bots/${botId}/owners`, [403]);
        const B = (S.bots[botId] = {
          bot: info.data, owners: owners.data.list || [], chats: [], members: {}, events: {},
          tags: [], contacts: [], notes: {},
        });
        // 客服資料：標籤定義、好友名單（含從未聊過天的好友）
        const tags = await get(`/api/v1/bots/${botId}/tags`, [403, 404]);
        B.tags = (tags.data && tags.data.list) || [];
        const seenContacts = new Set();
        await paged(`/api/v2/bots/${botId}/contacts?limit=100`, 'next', l => {
          for (const c of l) if (!seenContacts.has(c.contactId)) { seenContacts.add(c.contactId); B.contacts.push(c); }
          S.progress = `${B.bot.name}: 好友名單 ${B.contacts.length} 人`;
        }, [400, 403, 404]);

        const seen = new Set();
        for (const folder of FOLDERS) {
          await paged(`/api/v2/bots/${botId}/chats?folderType=${folder}&limit=25`, 'next', l => {
            for (const c of l) if (!seen.has(c.chatId)) { seen.add(c.chatId); B.chats.push(c); }
          }, [400]);
        }

        if (cfg.limitChats > 0) B.chats = B.chats.slice(0, cfg.limitChats);
        let i = 0;
        for (const c of B.chats) {
          i++;
          if (c.chatType !== 'USER') {
            const m = (B.members[c.chatId] = []);
            // 已退出的群組查不到成員，不影響訊息抓取
            await paged(`/api/v1/bots/${botId}/chats/${c.chatId}/members?limit=100`, 'next',
              l => m.push(...l), [403, 404]);
          }
          const notes = [];
          await paged(`/api/v1/bots/${botId}/chats/${c.chatId}/notes?limit=100`, 'next',
            l => notes.push(...l), [400, 403, 404]);
          if (notes.length) B.notes[c.chatId] = notes;
          const ev = (B.events[c.chatId] = []);
          await paged(`/api/v3/bots/${botId}/chats/${c.chatId}/messages`, 'backward', l => {
            ev.push(...l);
            S.progress = `${B.bot.name}: ${i}/${B.chats.length} 對話串，目前這串 ${ev.length} 則`;
          });
        }
        S.progress = `${B.bot.name}: 完成 ${B.chats.length} 個對話串`;
      }
      if (cfg.downloadMedia) await downloadMedia();
      S.status = 'done';
    } catch (e) {
      S.status = 'error';
      S.error = String(e);
    }
    S.finishedAt = Date.now();
    // 出錯也下載已取得的部分
    if (cfg.autoDownload && Object.keys(S.bots).length) S.bytes = S.download();
  })();

  return 'started';
})();
