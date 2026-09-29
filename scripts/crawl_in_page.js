// LINE OA Message Scraper — 瀏覽器內抓取腳本
//
// 在使用者已登入的 Chrome 中，於 https://chat.line.biz/api/v1/me 這個 JSON 頁面執行
// （停在 API 頁面就完全不會載入聊天介面，不會觸發已讀）。只發 GET，不會送出任何訊息。
//
// 設定: 執行前先定義 window.__LINE_OA_CONFIG = { botIds: ['U...'], delayMs: 300, autoDownload: true }
//       botIds 留空時抓網址中的 OA；all: true 時抓帳號下所有 CHAT 模式 OA。
// 進度: window.__lineOaCrawl.status 為 running / done / error，progress 為文字進度。
// 產出: 完成後自動下載 line_oa_bundle.json，交給
//       python line_oa_scrape.py export <bundle.json> 轉成 CSV。
//       也可隨時呼叫 window.__lineOaCrawl.download() 下載目前已取得的部分。
(() => {
  const cfg = Object.assign({ botIds: [], all: false, delayMs: 300, autoDownload: true },
    window.__LINE_OA_CONFIG || {});
  const FOLDERS = ['ALL', 'SPAM', 'DONE'];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const S = (window.__lineOaCrawl = {
    status: 'running', progress: '', requests: 0, warnings: [], bots: {}, startedAt: Date.now(),
  });

  S.download = () => {
    const body = JSON.stringify({ crawledAt: Date.now(), status: S.status, bots: S.bots });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([body], { type: 'application/json' }));
    a.download = 'line_oa_bundle.json';
    (document.body || document.documentElement).appendChild(a);
    a.click();
    a.remove();
    return body.length;
  };

  S.summary = () => Object.values(S.bots).map(b => {
    const events = Object.values(b.events).flat();
    const ts = events.map(e => e.timestamp).filter(Boolean);
    return {
      name: b.bot.name, chats: b.chats.length,
      emptyChats: Object.values(b.events).filter(e => !e.length).length,
      events: events.length,
      oldest: ts.length ? new Date(Math.min(...ts)).toISOString() : null,
      newest: ts.length ? new Date(Math.max(...ts)).toISOString() : null,
    };
  });

  // 唯一的網路出口: 只允許 /api/ 的 GET
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
        });

        const seen = new Set();
        for (const folder of FOLDERS) {
          await paged(`/api/v2/bots/${botId}/chats?folderType=${folder}&limit=25`, 'next', l => {
            for (const c of l) if (!seen.has(c.chatId)) { seen.add(c.chatId); B.chats.push(c); }
          }, [400]);
        }

        let i = 0;
        for (const c of B.chats) {
          i++;
          if (c.chatType !== 'USER') {
            const m = (B.members[c.chatId] = []);
            await paged(`/api/v1/bots/${botId}/chats/${c.chatId}/members?limit=100`, 'next',
              l => m.push(...l), [403, 404]);
          }
          const ev = (B.events[c.chatId] = []);
          await paged(`/api/v3/bots/${botId}/chats/${c.chatId}/messages`, 'backward', l => {
            ev.push(...l);
            S.progress = `${B.bot.name}: ${i}/${B.chats.length} 對話串，目前這串 ${ev.length} 則`;
          });
        }
        S.progress = `${B.bot.name}: 完成 ${B.chats.length} 個對話串`;
      }
      S.status = 'done';
    } catch (e) {
      S.status = 'error';
      S.error = String(e);
    }
    S.finishedAt = Date.now();
    if (cfg.autoDownload && Object.keys(S.bots).length) S.bytes = S.download();
  })();

  return 'started';
})();
