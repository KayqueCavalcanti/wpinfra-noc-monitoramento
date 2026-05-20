/**
 * WP Infra NOC — Dashboard Controller
 *
 * Estrutura de dados central (por que cada uma):
 *
 *   state.targets  dict id→config     O(1) lookup ao receber WS message
 *   state.results  dict id→result     O(1) update e leitura para summary
 *   state.history  dict id→[{ms,st}]  O(1) push; O(k) para sparkline (k≤20)
 *   dom.cards      dict id→element    O(1) update de DOM sem varrer lista
 *
 * Fluxo de dados:
 *   /api/targets → cria cards
 *   /api/history → pré-carrega sparklines
 *   /api/status  → estado inicial dos cards
 *   WebSocket    → atualizações em tempo real
 */

const NOC = (() => {

  /* ── Constantes ───────────────────────────────────────────── */
  const MAX_HISTORY  = 20;
  const MAX_LOG_ROWS = 150;
  const TOAST_TTL_MS = 9000;
  const TS_UPDATE_MS = 15000;

  /* ── Estado ───────────────────────────────────────────────── */
  const state = {
    targets:  {},
    results:  {},
    history:  {},
    logCount: 0,
    ws:       null,
  };

  /* ── Cache de elementos DOM — O(1) por target_id ─────────── */
  const dom = {
    cards:   {},
    clock:   null,
    wsDot:   null,
    wsLabel: null,
    grid:    null,
    logBody: null,
    logMeta: null,
    toasts:  null,
    stats: { total: null, online: null, offline: null, degraded: null, avgLat: null },
  };

  /* ── Ponto de entrada ─────────────────────────────────────── */
  async function init() {
    _cacheDom();
    _startClock();
    _startRelativeTsUpdater();
    await _loadData();
  }

  function _cacheDom() {
    dom.clock    = document.getElementById('clock');
    dom.wsDot    = document.getElementById('wsDot');
    dom.wsLabel  = document.getElementById('wsLabel');
    dom.grid     = document.getElementById('grid');
    dom.logBody  = document.getElementById('logBody');
    dom.logMeta  = document.getElementById('logMeta');
    dom.toasts   = document.getElementById('toastContainer');
    dom.stats.total    = document.getElementById('statTotal');
    dom.stats.online   = document.getElementById('statOnline');
    dom.stats.offline  = document.getElementById('statOffline');
    dom.stats.degraded = document.getElementById('statDegraded');
    dom.stats.avgLat   = document.getElementById('statAvgLat');
  }

  function _startClock() {
    const tick = () => {
      dom.clock.textContent = new Date().toLocaleTimeString('pt-BR', { hour12: false });
    };
    tick();
    setInterval(tick, 1000);
  }

  function _startRelativeTsUpdater() {
    setInterval(() => {
      Object.entries(state.results).forEach(([id, r]) => {
        const el = document.getElementById(`ts-${id}`);
        if (el) el.textContent = _relativeTime(r.timestamp);
      });
    }, TS_UPDATE_MS);
  }

  /* ── Carga inicial ────────────────────────────────────────── */
  async function _loadData() {
    try {
      const tRes  = await fetch('/api/targets');
      const tData = await tRes.json();
      tData.targets.forEach(t => {
        state.targets[t.id] = t;
        _createCard(t);
      });

      const [hRes, sRes, lRes] = await Promise.all([
        fetch('/api/history'),
        fetch('/api/status'),
        fetch('/api/logs?n=80'),
      ]);
      const hData = await hRes.json();
      const sData = await sRes.json();
      const lData = await lRes.json();

      Object.entries(hData).forEach(([id, entries]) => {
        state.history[id] = entries.map(e => ({ ms: e.response_time_ms, status: e.status }));
      });

      sData.targets.forEach(r => _applyResult(r, false));
      lData.logs.forEach(entry => _addLogRow(entry, false));

      _connectWebSocket();
    } catch (err) {
      console.error('[NOC] Falha na carga inicial:', err);
    }
  }

  /* ─────────────────────────────────────────────────────────── */
  /* CARD                                                        */
  /* ─────────────────────────────────────────────────────────── */

  function _createCard(target) {
    const port = target.port ? `:${target.port}` : '';

    const card = document.createElement('div');
    card.className = 'card status-unknown';
    card.id = `card-${target.id}`;

    /*
     * Layout do card (hierarquia visual intencional):
     *   1. [branch]              [tipo]   ← contexto, peso mínimo
     *   2. Nome do ativo                  ← identidade, peso máximo
     *   3. Endereço IP/host              ← detalhe técnico
     *   4. [● STATUS]     [latência ms]  ← estado + métrica hero
     *   5. [sparkline]                   ← histórico visual
     *   ─────────────────────────────────
     *   6. [uptime %]      [há Ns]       ← meta, peso mínimo
     */
    card.innerHTML = `
      <div class="card-header">
        <span class="card-branch">${_esc(target.branch)}</span>
        <span class="card-type">${_esc(target.monitor_type)}</span>
      </div>
      <div class="card-name">${_esc(target.name)}</div>
      <div class="card-host">${_esc(target.host)}${_esc(port)}</div>
      <div class="card-row">
        <div class="card-status">
          <span class="status-dot"></span>
          <span class="status-label" id="sl-${target.id}">AGUARDANDO</span>
        </div>
        <span class="card-latency" id="lat-${target.id}">—</span>
      </div>
      <div class="sparkline-wrap" id="spark-${target.id}"></div>
      <div class="card-footer">
        <span class="uptime-text" id="up-${target.id}"></span>
        <span class="card-time"   id="ts-${target.id}" title="">—</span>
      </div>
    `;

    dom.cards[target.id] = card;
    dom.grid.appendChild(card);
  }

  /* Aplica um resultado ao card — O(1): todas as operações são lookups de dict */
  function _applyResult(result, animate = true) {
    const card = dom.cards[result.target_id];
    if (!card) return;

    const prev = state.results[result.target_id];

    _pushHistory(result.target_id, result);
    state.results[result.target_id] = result;

    /* Status class */
    card.classList.remove('status-online', 'status-offline', 'status-degraded', 'status-unknown');
    card.classList.add(`status-${result.status.toLowerCase()}`);

    /* Flash + toast ao mudar status em tempo real */
    if (animate && prev && prev.status !== result.status) {
      card.classList.remove('flash');
      void card.offsetWidth;
      card.classList.add('flash');
      if (result.status === 'OFFLINE' || result.status === 'DEGRADED') {
        _showToast(state.targets[result.target_id], result);
      }
    }

    /* Status label */
    const sl = document.getElementById(`sl-${result.target_id}`);
    if (sl) sl.textContent = result.status;

    /* Latência */
    const lat = document.getElementById(`lat-${result.target_id}`);
    if (lat) {
      lat.textContent = result.response_time_ms != null
        ? `${result.response_time_ms} ms`
        : '—';
    }

    /* Timestamp relativo */
    const ts = document.getElementById(`ts-${result.target_id}`);
    if (ts) {
      ts.textContent = _relativeTime(result.timestamp);
      ts.title = new Date(result.timestamp).toLocaleTimeString('pt-BR', { hour12: false });
    }

    /* Sparkline */
    const sparkEl = document.getElementById(`spark-${result.target_id}`);
    if (sparkEl) {
      sparkEl.innerHTML = _buildSparkline(result.target_id, result.status) || '';
    }

    /* Uptime */
    const upEl = document.getElementById(`up-${result.target_id}`);
    if (upEl) {
      const pct = _calcUptime(result.target_id);
      if (pct !== null) {
        upEl.textContent = `${pct}%`;
        upEl.className = 'uptime-text ' +
          (pct >= 95 ? 'uptime-high' : pct >= 80 ? 'uptime-medium' : 'uptime-low');
      } else {
        upEl.textContent = '';
        upEl.className = 'uptime-text';
      }
    }

    _updateSummary();
  }

  /* ─────────────────────────────────────────────────────────── */
  /* SPARKLINE  (SVG puro, sem bibliotecas)                      */
  /* ─────────────────────────────────────────────────────────── */

  /**
   * Constrói SVG de sparkline com gradient fill, grid e ponto vivo.
   *
   * Big-O: O(k) onde k = len(history[id]) ≤ MAX_HISTORY.
   * Como MAX_HISTORY é constante (20), é efetivamente O(1) em escala.
   *
   * CSS vars não funcionam em atributos SVG em todos os browsers —
   * por isso usamos valores hex hardcoded por status.
   */
  function _buildSparkline(targetId, currentStatus) {
    const h = state.history[targetId] || [];
    const valid = h.filter(e => e.ms != null);
    if (valid.length < 2) return '';

    const values = valid.map(e => e.ms);
    const W = 240, H = 56, padY = 8;
    const minV  = Math.min(...values);
    const maxV  = Math.max(...values);
    const range = (maxV - minV) || 1;

    /* Y invertido: latência maior = ponto mais alto visualmente */
    const pts = values.map((v, i) => [
      Math.round((i / (values.length - 1)) * W),
      Math.round(H - padY - ((v - minV) / range) * (H - padY * 2)),
    ]);

    const [lastX, lastY] = pts[pts.length - 1];
    const linePoints = pts.map(([x, y]) => `${x},${y}`).join(' ');
    const areaD =
      `M${pts[0][0]},${H} L${pts[0][0]},${pts[0][1]} ` +
      pts.slice(1).map(([x, y]) => `L${x},${y}`).join(' ') +
      ` L${lastX},${H} Z`;

    const colorMap = {
      ONLINE:   '#5fa868',
      OFFLINE:  '#a85f5f',
      DEGRADED: '#a8925f',
      UNKNOWN:  '#444444',
    };
    const color  = colorMap[currentStatus] || colorMap.UNKNOWN;
    const gradId = `sg${targetId.replace(/[^a-z0-9]/gi, '')}`;

    /* Linhas de referência horizontais (grid) em 25%, 50%, 75% */
    const refLines = [0.25, 0.50, 0.75].map(frac => {
      const ry = Math.round(H - padY - frac * (H - padY * 2));
      const op = frac === 0.50 ? '0.07' : '0.03';
      return `<line x1="0" y1="${ry}" x2="${W}" y2="${ry}" stroke="#E6E6E6" stroke-opacity="${op}" stroke-width="0.8"/>`;
    }).join('');

    /* Ponto vivo: pulsa quando ONLINE, estático nos demais */
    const liveDot = currentStatus === 'ONLINE'
      ? `<circle cx="${lastX}" cy="${lastY}" r="2.5" fill="${color}" opacity="0.9">
           <animate attributeName="r"       values="2.5;4.5;2.5" dur="2.2s" repeatCount="indefinite"/>
           <animate attributeName="opacity" values="0.9;0.15;0.9" dur="2.2s" repeatCount="indefinite"/>
         </circle>`
      : `<circle cx="${lastX}" cy="${lastY}" r="2" fill="${color}" opacity="0.6"/>`;

    return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="56" preserveAspectRatio="none">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="${color}" stop-opacity="0.32"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      ${refLines}
      <path d="${areaD}" fill="url(#${gradId})"/>
      <polyline points="${linePoints}" fill="none" stroke="${color}"
        stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
      ${liveDot}
    </svg>`;
  }

  /* ─────────────────────────────────────────────────────────── */
  /* ANALYTICS                                                   */
  /* ─────────────────────────────────────────────────────────── */

  function _pushHistory(targetId, result) {
    if (!state.history[targetId]) state.history[targetId] = [];
    state.history[targetId].push({ ms: result.response_time_ms, status: result.status });
    if (state.history[targetId].length > MAX_HISTORY) state.history[targetId].shift();
  }

  /**
   * Uptime % dos últimos N checks.
   * ONLINE e DEGRADED = disponível (host responde, mesmo que lento).
   * O(k) onde k ≤ MAX_HISTORY.
   */
  function _calcUptime(targetId) {
    const h = state.history[targetId] || [];
    if (h.length === 0) return null;
    const ok = h.filter(e => e.status === 'ONLINE' || e.status === 'DEGRADED').length;
    return Math.round((ok / h.length) * 100);
  }

  /* ─── Summary bar ───────────────────────────────────────────── */
  function _updateSummary() {
    const results  = Object.values(state.results);
    const online   = results.filter(r => r.status === 'ONLINE').length;
    const offline  = results.filter(r => r.status === 'OFFLINE').length;
    const degraded = results.filter(r => r.status === 'DEGRADED').length;

    const lats = results.map(r => r.response_time_ms).filter(v => v != null);
    const avg  = lats.length
      ? Math.round(lats.reduce((a, b) => a + b, 0) / lats.length)
      : null;

    dom.stats.total.textContent    = results.length || '--';
    dom.stats.online.textContent   = online;
    dom.stats.offline.textContent  = offline;
    dom.stats.degraded.textContent = degraded;
    dom.stats.avgLat.textContent   = avg != null ? `${avg} ms` : '--';
  }

  /* ─────────────────────────────────────────────────────────── */
  /* TOAST                                                       */
  /* ─────────────────────────────────────────────────────────── */

  function _showToast(target, result) {
    if (!target) return;
    const time  = new Date(result.timestamp).toLocaleTimeString('pt-BR', { hour12: false });
    const toast = document.createElement('div');
    toast.className = `toast toast-${result.status.toLowerCase()}`;
    toast.innerHTML = `
      <span class="toast-dot"></span>
      <div class="toast-body">
        <span class="toast-title">${_esc(result.status)}</span>
        <span class="toast-msg">${_esc(target.branch)} — ${_esc(target.name)}</span>
        <span class="toast-time">${_esc(target.host)} · ${time}</span>
      </div>
      <button class="toast-close" aria-label="Fechar">×</button>
    `;
    toast.querySelector('.toast-close').addEventListener('click', () => _dismissToast(toast));
    dom.toasts.prepend(toast);
    setTimeout(() => _dismissToast(toast), TOAST_TTL_MS);
  }

  function _dismissToast(toast) {
    if (!toast.isConnected) return;
    toast.classList.add('exiting');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
  }

  /* ─────────────────────────────────────────────────────────── */
  /* LOG                                                         */
  /* ─────────────────────────────────────────────────────────── */

  function _addLogRow(entry, animate = true) {
    const target = state.targets[entry.target_id] || {};
    const time   = new Date(entry.timestamp).toLocaleTimeString('pt-BR', { hour12: false });
    const lat    = entry.response_time_ms != null ? `${entry.response_time_ms} ms` : '—';
    const msg    = entry.error_message || '—';

    const tr = document.createElement('tr');
    if (animate) tr.classList.add('new-row');

    tr.innerHTML = `
      <td>${time}</td>
      <td>${_esc(target.branch || entry.target_id)}</td>
      <td>${_esc(target.name   || entry.target_id)}</td>
      <td>${_esc(target.host   || '—')}</td>
      <td><span class="log-status ${entry.status}">${_esc(entry.status)}</span></td>
      <td>${_esc(lat)}</td>
      <td class="log-msg" title="${_esc(msg)}">${_esc(msg)}</td>
    `;

    dom.logBody.prepend(tr);
    state.logCount++;
    while (dom.logBody.rows.length > MAX_LOG_ROWS) dom.logBody.deleteRow(dom.logBody.rows.length - 1);
    dom.logMeta.textContent = `${state.logCount} evento${state.logCount !== 1 ? 's' : ''}`;
  }

  /* ─────────────────────────────────────────────────────────── */
  /* WEBSOCKET                                                   */
  /* ─────────────────────────────────────────────────────────── */

  function _connectWebSocket() {
    const ws = new WebSocket(`ws://${window.location.host}/ws`);
    state.ws = ws;

    ws.onopen = () => {
      dom.wsDot.className     = 'ws-dot connected';
      dom.wsLabel.textContent = 'CONECTADO';
    };
    ws.onclose = () => {
      dom.wsDot.className     = 'ws-dot disconnected';
      dom.wsLabel.textContent = 'RECONECTANDO';
      setTimeout(_connectWebSocket, 5000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === 'monitor_result') {
          _applyResult(msg.data, true);
          _addLogRow(msg.data, true);
        }
      } catch (err) {
        console.error('[NOC] Mensagem WS inválida:', err);
      }
    };
  }

  /* ─────────────────────────────────────────────────────────── */
  /* UTILIDADES                                                  */
  /* ─────────────────────────────────────────────────────────── */

  /**
   * Tempo relativo contextual — mais útil operacionalmente do que HH:MM:SS
   * porque comunica urgência diretamente ("há 30s" vs "14:05:42").
   */
  function _relativeTime(isoString) {
    const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
    if (diff < 5)    return 'agora';
    if (diff < 60)   return `há ${diff}s`;
    if (diff < 3600) return `há ${Math.floor(diff / 60)}min`;
    return `há ${Math.floor(diff / 3600)}h`;
  }

  /** Escapa HTML — previne XSS ao inserir dados externos no DOM. */
  function _esc(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return { init };
})();

document.addEventListener('DOMContentLoaded', () => NOC.init());
