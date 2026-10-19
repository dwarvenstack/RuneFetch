/**
 * RuneFetch WebSocket client — ws://127.0.0.1:8770
 *
 * Handles:
 *   - Auto-reconnect with back-off (max 8 s)
 *   - Token injection on every outgoing command
 *   - Event routing to registered listeners
 */

class WsClient {
  constructor(port = 8770) {
    this._port    = port;
    this._token   = '';
    this._ws      = null;
    this._ready   = false;
    this._queue   = [];          // commands buffered before connect
    this._backoff = 500;
    this._listeners = {};        // event → [callback]
    this._pendingResolvers = {}; // action → [{resolve, reject}]
    this._reconnectTimer = null;
    this._destroyed = false;
  }

  /** Connect and get token from the native Api, then open socket. */
  async init() {
    try {
      const tokens = await window.pywebview.api.get_tokens();
      this._token = tokens.ui_token || '';
      const port = Number(tokens.ui_port);
      if (Number.isInteger(port) && port > 0 && port <= 65535) this._port = port;
    } catch (e) {
      console.warn('[ws] pywebview not ready, retrying…');
      await _sleep(300);
      return this.init();
    }
    this._connect();
  }

  _connect() {
    if (this._destroyed) return;
    const url = `ws://127.0.0.1:${this._port}`;
    try {
      this._ws = new WebSocket(url);
    } catch (e) {
      this._scheduleReconnect();
      return;
    }

    this._ws.onopen = () => {
      this._ready   = true;
      this._backoff = 500;
      console.info('[ws] connected');
      this.emit('_connected', {});
      // Flush buffered commands
      const q = this._queue.splice(0);
      for (const msg of q) this._ws.send(msg);
    };

    this._ws.onmessage = (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch { return; }

      // Command response: { ok, error, ... }
      if ('ok' in data) {
        const resolvers = this._pendingResolvers['_next'];
        if (resolvers && resolvers.length) {
          const { resolve, reject } = resolvers.shift();
          if (data.ok) resolve(data); else reject(new Error(data.error || 'error'));
          if (!resolvers.length) delete this._pendingResolvers['_next'];
        }
        return;
      }

      // Server event: { event, data }
      if (data.event) {
        this.emit(data.event, data.data);
      }
    };

    this._ws.onclose = () => {
      this._ready = false;
      this.emit('_disconnected', {});
      this._scheduleReconnect();
    };

    this._ws.onerror = () => {
      // onclose fires after onerror; just suppress console noise
    };
  }

  _scheduleReconnect() {
    if (this._destroyed) return;
    clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => {
      console.info('[ws] reconnecting…');
      this._connect();
    }, this._backoff);
    this._backoff = Math.min(this._backoff * 1.5, 8000);
  }

  destroy() {
    this._destroyed = true;
    clearTimeout(this._reconnectTimer);
    if (this._ws) this._ws.close();
  }

  /** Send a command; returns a Promise that resolves with the response. */
  send(action, payload = {}) {
    const msg = JSON.stringify({ token: this._token, action, ...payload });

    return new Promise((resolve, reject) => {
      if (!this._pendingResolvers['_next']) this._pendingResolvers['_next'] = [];
      this._pendingResolvers['_next'].push({ resolve, reject });

      if (this._ready && this._ws.readyState === WebSocket.OPEN) {
        this._ws.send(msg);
      } else {
        this._queue.push(msg);
      }
    });
  }

  /** Fire-and-forget (no response needed). */
  fire(action, payload = {}) {
    this.send(action, payload).catch(() => {});
  }

  /** Register an event listener. */
  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
  }

  off(event, fn) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter(f => f !== fn);
  }

  emit(event, data) {
    (this._listeners[event] || []).forEach(fn => { try { fn(data); } catch (e) { console.error(e); } });
  }
}

function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

export const ws = new WsClient(8770);
