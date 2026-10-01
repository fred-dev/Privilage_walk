// Shared helpers for the Privilege Walk pages: resilient fetch, safe
// storage, and a poller that survives sleep, tab switches and dropped wifi.
(function () {
  async function api(url, opts) {
    opts = opts || {};
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), opts.timeout || 8000);
    const headers = Object.assign({}, opts.headers || {});
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    try {
      const res = await fetch(url, {
        method: opts.method || 'GET',
        headers: headers,
        body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        signal: ctrl.signal,
        credentials: 'same-origin',
        cache: 'no-store'
      });
      let data = {};
      try { data = await res.json(); } catch (e) { /* non-JSON body */ }
      return { ok: res.ok, status: res.status, data: data, network: false };
    } catch (e) {
      return { ok: false, status: 0, data: {}, network: true };
    } finally {
      clearTimeout(timer);
    }
  }

  const store = {
    get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode */ } },
    del(key) { try { localStorage.removeItem(key); } catch (e) { /* ignore */ } }
  };

  // Calls fn() repeatedly. fn returns true on success. Never overlaps calls,
  // backs off on failure, slows down while hidden, and fires immediately when
  // the device wakes up, the tab becomes visible, or the network comes back.
  function poller(fn, baseMs, hiddenMs) {
    let timer = null, running = false, stopped = false, failures = 0;
    async function run() {
      if (running || stopped) return;
      running = true;
      clearTimeout(timer);
      let ok = false;
      try { ok = await fn(); } catch (e) { ok = false; }
      running = false;
      failures = ok ? 0 : failures + 1;
      if (stopped) return;
      const base = document.hidden ? hiddenMs : baseMs;
      const delay = ok ? base : Math.min(base * Math.pow(1.6, failures), 10000);
      timer = setTimeout(run, delay + Math.random() * 400);
    }
    const kick = () => { if (!stopped) run(); };
    document.addEventListener('visibilitychange', () => { if (!document.hidden) kick(); });
    window.addEventListener('online', kick);
    window.addEventListener('focus', kick);
    window.addEventListener('pageshow', kick);
    setTimeout(run, 0);
    return {
      kick: kick,
      stop() { stopped = true; clearTimeout(timer); },
      get failures() { return failures; }
    };
  }

  // Keep the screen on while the walk is running (supported browsers only).
  let wakeLock = null, wantWake = false;
  async function keepAwake(on) {
    wantWake = on;
    if (!('wakeLock' in navigator)) return;
    try {
      if (on && !wakeLock && !document.hidden) {
        wakeLock = await navigator.wakeLock.request('screen');
        wakeLock.addEventListener('release', () => { wakeLock = null; });
      } else if (!on && wakeLock) {
        await wakeLock.release();
        wakeLock = null;
      }
    } catch (e) { /* not allowed right now; retried on next visibility */ }
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && wantWake) keepAwake(true); });

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  window.PW = { api: api, store: store, poller: poller, keepAwake: keepAwake, el: el };
})();
