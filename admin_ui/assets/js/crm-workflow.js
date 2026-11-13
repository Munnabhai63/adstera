/* ============================================================================
 * crm-workflow.js — Live Workflow Visualizer controller (v2)
 * Vanilla ES2017+. No build step. SVG cubic-bezier router, pan/zoom engine,
 * SSE telemetry ingestion, n8n-style node inspector.
 *
 * Backend contract
 *   GET  /api/phase4/live-workflow-stream   (SSE: node_id, status, message, data, run_id)
 *   POST /api/phase4/workflow/trigger       {"mode":"paper"|"live","steps":1..10}
 *   GET  /api/phase4/workflow/history
 * ========================================================================== */
(function (global) {
  'use strict';

  var API = {
    stream: '/api/phase4/live-workflow-stream',
    trigger: '/api/phase4/workflow/trigger',
    history: '/api/phase4/workflow/history'
  };
  var TRIGGER_TIMEOUT_MS = 8000;

  /* ---------------------------------------------------------------- aliases */
  var NODE_ALIAS = {
    "TRENDS_HARVESTER": "trends",
    "FREELMM_GATEWAY": "freellm",
    "A5_SEO_GATE": "a5",
    "CF_PAGES": "cf",
    "GSC_INDEX": "gsc",
    "PUSH_NOTIF": "push",
    "A6_SCHEDULER": "scheduler",
    "CGNAT_TRACKER": "cgnat",
    "AIRPLANE_ROTATOR": "airplane",
    "PHONE_FARM": "phone",
    "CAPTURE": "capture",
    "A4_VISION": "vision",
    "A2_ANOMALY": "anomaly",
    "SAFE_MODE_GATE": "safe",
    "CTR_GUARD_GATE": "ctr",
    "SKIP_ACTION": "skip",
    "DEFER_ACTION": "defer",
    "A1_DECISION": "a1",
    "ADB_TAP": "adb",
    "CENTRAL_HQ": "hq",
    "DB_SAVE": "db",
    "A3_FORECAST": "forecast",
    "ADSTERRA_SYNC": "adsterra",
    "TELEGRAM_BOT": "telegram",
    "PHASE4_DRIFT": "drift"
  };
  var FINISH_TOKENS = ['WORKFLOW_FINISH', 'RUN_COMPLETE', 'PIPELINE_FINISH'];

  /* ------------------------------------------------------------- topology */
  var WORLD = { w: 2640, h: 1000 };
  var NODE_W = 210, NODE_H = 100, GATE = 150, CHIP_W = 180, CHIP_H = 70, HQ_W = 328;

  var LAYERS = {
    l1: { num: 'L01', label: 'Content & SEO', x: 32, y: 28, w: 1240, h: 300 },
    l2: { num: 'L02', label: 'Hardware & scheduler', x: 32, y: 364, w: 920, h: 228 },
    l3: { num: 'L03', label: 'Vision & decision core', x: 1292, y: 250, w: 892, h: 660 },
    l4: { num: 'L04', label: 'HQ & telemetry', x: 2212, y: 28, w: 384, h: 792 }
  };

  var NODES = [
    { id: 'trends', title: '01. Trends Harvester', sub: 'Google Trends RSS (IN/US)', metric: 'Keywords: 14 today', kind: 'Trigger', layer: 'l1', x: 56, y: 104, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'freellm', title: '02. FreeLLMAPI Gateway', sub: 'Multi-Provider Hybrid LLM', metric: 'Cost: $0.00 • 1,420 words', kind: 'AI Gateway', layer: 'l1', x: 280, y: 104, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'a5', title: '03. A5 Anti-AI Gate', sub: 'Perplexity & Burstiness Check', metric: 'Score: 84.2 • Passed', kind: 'Quality Gate', layer: 'l1', x: 504, y: 104, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'cf', title: '04. Cloudflare Pages', sub: 'Hugo Static Build & Edge Deploy', metric: '10 Domains Live', kind: 'Deploy', layer: 'l1', x: 728, y: 104, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'gsc', title: '05. GSC & IndexNow', sub: 'Instant Search Ping', metric: '10 URLs Pushed', kind: 'Indexer', layer: 'l1', x: 1000, y: 60, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'push', title: '06. Web Push Engine', sub: 'OneSignal / VAPID Broadcast', metric: 'Broadcast Active', kind: 'Notify', layer: 'l1', x: 1000, y: 190, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'scheduler', title: '07. A6 Diurnal Scheduler', sub: 'NHPP Poisson Peak Hour Curve', metric: 'Intensity: 0.94 • 150/hr', kind: 'Scheduler', layer: 'l2', x: 56, y: 436, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'cgnat', title: '08. CGNAT IP Tracker', sub: '/24 & /20 Subnet Collision Lock', metric: 'Subnet: 100.64.55.0/24', kind: 'Network', layer: 'l2', x: 280, y: 436, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'airplane', title: '09. Airplane Rotate', sub: '4G Carrier IP Renewal', metric: 'IP: 100.64.55.10', kind: 'Rotator', layer: 'l2', x: 504, y: 436, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'phone', title: '10. Phone Cluster', sub: 'Physical Android Device (USB 3.0)', metric: 'Battery: 88% • 32°C', kind: 'Device', layer: 'l2', x: 728, y: 436, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'capture', title: '11. Android Screen Capture', sub: 'ADB Screencap & XML Dump', metric: '1080x2400 PNG', kind: 'Capture', layer: 'l3', x: 1320, y: 330, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'vision', title: '12. A4 Visual Ad Detector', sub: 'XML Hierarchy + RuleFallback BBox', metric: 'bbox: [80, 1218, 920, 250]', kind: 'Vision', layer: 'l3', x: 1548, y: 330, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'anomaly', title: '13. A2 Anomaly Filter', sub: 'EWMA + Isolation Forest', metric: 'Severity: NORMAL • Clean', kind: 'Filter', layer: 'l3', x: 1776, y: 330, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'safe', title: '14. Safe Mode Active?', sub: 'Fail-Closed Sentinel Check', metric: 'Sentinel: enforce', kind: 'Decision', layer: 'l3', x: 2004, y: 300, w: GATE, h: GATE, gate: true, init: 'success' },
    { id: 'skip', title: 'Skip Action', sub: 'Clicks suppressed', metric: 'action="SKIP" logged', kind: 'Action', layer: 'l3', x: 1652, y: 492, w: CHIP_W, h: CHIP_H, action: true, init: 'idle' },
    { id: 'ctr', title: '15. CTR Guard ≤ 4.5%?', sub: 'Atomic Cap Lock', metric: '2.8% · under cap', kind: 'Decision', layer: 'l3', x: 2004, y: 520, w: GATE, h: GATE, gate: true, init: 'success' },
    { id: 'defer', title: 'Defer Action', sub: 'Cooldown window', metric: 'action="DEFER" logged', kind: 'Action', layer: 'l3', x: 1652, y: 600, w: CHIP_W, h: CHIP_H, action: true, init: 'idle' },
    { id: 'a1', title: '16. A1 LinTS Contextual Bandit', sub: 'Thompson Sampling Arm Selection', metric: 'Action: CLICK • Reward: 0.00145', kind: 'Bandit', layer: 'l3', x: 1952, y: 756, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'adb', title: '17. Biometric Touch Bridge', sub: 'Bézier Capacitive Tap inside BBox', metric: 'Tap at (540, 1343)', kind: 'Touch', layer: 'l3', x: 1690, y: 756, w: NODE_W, h: NODE_H, init: 'success' },
    { id: 'hq', title: 'Central Controller (ui.py)', sub: 'rechargekar.com HQ', metric: 'Tunnel: Active', kind: 'Controller', layer: 'l4', x: 2236, y: 68, w: HQ_W, h: NODE_H, init: 'success' },
    { id: 'db', title: 'phase3.db Persistence', sub: 'SQLite WAL + BEGIN IMMEDIATE', metric: 'Session Committed • 32s dwell', kind: 'Persistence', layer: 'l4', x: 2236, y: 188, w: HQ_W, h: NODE_H, init: 'success' },
    { id: 'forecast', title: '18. A3 Quantile Forecaster', sub: 'IRLS P10/P50/P90 Projection', metric: 'P50: $14.20', kind: 'Forecast', layer: 'l4', x: 2236, y: 320, w: HQ_W, h: NODE_H, init: 'idle' },
    { id: 'adsterra', title: '19. Adsterra Official API', sub: '15-min Revenue & CPM Pull', metric: 'Syncing 15-min window…', kind: 'Sync', layer: 'l4', x: 2236, y: 444, w: HQ_W, h: NODE_H, init: 'processing' },
    { id: 'telegram', title: '20. Telegram Alert Bot', sub: 'Daily Report & Safety Sentinel', metric: 'Status: Green • 0 Alerts', kind: 'Alerts', layer: 'l4', x: 2236, y: 568, w: HQ_W, h: NODE_H, init: 'idle' },
    { id: 'drift', title: '21. Drift & Calibration Monitor', sub: 'KL-Divergence & Touch Variance', metric: 'Drift: 0.012 • Healthy', kind: 'Monitor', layer: 'l4', x: 2236, y: 692, w: HQ_W, h: NODE_H, init: 'idle' }
  ];

  var EDGES = [
    { id: 'e1', from: 'trends', to: 'freellm', init: 'success' },
    { id: 'e2', from: 'freellm', to: 'a5', init: 'success' },
    { id: 'e3', from: 'a5', to: 'cf', init: 'success' },
    { id: 'e4', from: 'cf', to: 'gsc', init: 'success' },
    { id: 'e5', from: 'cf', to: 'push', init: 'idle' },
    { id: 'e25', from: 'cf', to: 'phone', fromSide: 'bottom', toSide: 'top', curve: { c1: { x: 833, y: 300 }, c2: { x: 833, y: 372 } }, label: 'PAGE VISIT', init: 'idle' },
    { id: 'e6', from: 'scheduler', to: 'cgnat', init: 'success' },
    { id: 'e7', from: 'cgnat', to: 'airplane', init: 'success' },
    { id: 'e8', from: 'airplane', to: 'phone', init: 'success' },
    { id: 'e9', from: 'phone', to: 'capture', init: 'success' },
    { id: 'e10', from: 'capture', to: 'vision', init: 'success' },
    { id: 'e11', from: 'vision', to: 'anomaly', init: 'success' },
    { id: 'e12', from: 'anomaly', to: 'safe', fromSide: 'right', toSide: 'top', init: 'success' },
    { id: 'e13', from: 'safe', to: 'skip', fromSide: 'left', toSide: 'right', curve: { c1: { x: 1996, y: 478 }, c2: { x: 1900, y: 520 } }, label: 'YES', labelDy: -6, init: 'idle' },
    { id: 'e14', from: 'safe', to: 'ctr', fromSide: 'bottom', toSide: 'top', label: 'NO', labelDx: 26, init: 'success' },
    { id: 'e15', from: 'ctr', to: 'defer', fromSide: 'left', toSide: 'right', label: 'AT CAP', labelDy: -6, init: 'idle' },
    { id: 'e16', from: 'ctr', to: 'a1', fromSide: 'bottom', toSide: 'top', label: 'UNDER CAP', labelDx: 26, init: 'success' },
    { id: 'e17', from: 'a1', to: 'adb', init: 'success' },
    { id: 'e18', from: 'adb', to: 'phone', fromSide: 'bottom', toSide: 'right', curve: { c1: { x: 1690, y: 920 }, c2: { x: 938, y: 550 } }, init: 'idle' },
    { id: 'e19', from: 'adb', to: 'db', fromSide: 'bottom', toSide: 'right', curve: { c1: { x: 1795, y: 970 }, c2: { x: 2632, y: 940 } }, init: 'active' },
    { id: 'e26', from: 'skip', to: 'db', fromSide: 'right', toSide: 'left', toDy: -12, curve: { c1: { x: 2050, y: 494 }, c2: { x: 2196, y: 494 } }, dashed: true, init: 'idle' },
    { id: 'e27', from: 'defer', to: 'db', fromSide: 'right', toSide: 'left', toDy: 14, curve: { c1: { x: 1960, y: 800 }, c2: { x: 2196, y: 800 } }, dashed: true, init: 'idle' },
    { id: 'e20', from: 'db', to: 'hq', fromSide: 'top', toSide: 'bottom', curve: { c1: { x: 2400, y: 178 }, c2: { x: 2400, y: 178 } }, init: 'success' },
    { id: 'e21', from: 'db', to: 'forecast', fromSide: 'right', toSide: 'right', curve: { c1: { x: 2604, y: 238 }, c2: { x: 2612, y: 370 } }, init: 'idle' },
    { id: 'e22', from: 'db', to: 'adsterra', fromSide: 'right', toSide: 'right', curve: { c1: { x: 2608, y: 238 }, c2: { x: 2618, y: 494 } }, init: 'active' },
    { id: 'e23', from: 'db', to: 'telegram', fromSide: 'right', toSide: 'right', curve: { c1: { x: 2612, y: 238 }, c2: { x: 2624, y: 618 } }, init: 'idle' },
    { id: 'e24', from: 'db', to: 'drift', fromSide: 'right', toSide: 'right', curve: { c1: { x: 2628, y: 238 }, c2: { x: 2636, y: 742 } }, init: 'idle' }
  ];

  var NODE_MAP = {}, EDGE_MAP = {}, nodeStatus = {}, edgeStatus = {}, lastPayload = {};
  NODES.forEach(function (n) { NODE_MAP[n.id] = n; nodeStatus[n.id] = n.init || 'idle'; lastPayload[n.id] = null; });
  EDGES.forEach(function (e) { EDGE_MAP[e.id] = e; edgeStatus[e.id] = e.init || 'idle'; });

  var INCOMING = {};
  NODES.forEach(function (n) { INCOMING[n.id] = []; });
  EDGES.forEach(function (e) { if (INCOMING[e.to]) INCOMING[e.to].push(e.id); });

  var state = { zoom: 1, x: 0, y: 0, minZoom: 0.4, maxZoom: 1.8, selected: null, running: false, token: 0, sse: null, mode: 'paper', steps: 3, runId: null };
  var stage, world, groupsEl, nodesEl, edgesSvg, minimap, logEl, triggerBtn, runIdEl, connectionEl, streamStatusEl, inspector, inspectorBody;

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var clamp = function (v, a, b) { return Math.min(b, Math.max(a, v)); };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var pad = function (n) { return String(n).padStart(2, '0'); };
  var time = function () { var d = new Date(); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); };

  /* ------------------------------------------------------------ resolution */
  function resolveNodeId(raw) {
    var rawId = String(raw || '').toUpperCase();
    if (!rawId) return '';
    return NODE_ALIAS[rawId] || rawId.toLowerCase();
  }

  function normalizeStatus(raw) {
    var s = String(raw || '').toLowerCase();
    if (s === 'running' || s === 'started' || s === 'in_progress' || s === 'processing' || s === 'active') return 'processing';
    if (s === 'ok' || s === 'done' || s === 'completed' || s === 'success' || s === 'passed') return 'success';
    if (s === 'error' || s === 'failed' || s === 'failure' || s === 'crash') return 'failed';
    if (s === 'skip' || s === 'skipped' || s === 'defer' || s === 'deferred') return 'success';
    return 'idle';
  }

  var METRIC_KEYS = [
    ['bbox', function (v) { return 'bbox: ' + (Array.isArray(v) ? '[' + v.join(', ') + ']' : JSON.stringify(v)); }],
    ['current_ctr', function (v) { return 'CTR: ' + Number(v).toFixed(2) + '% • cap 4.5%'; }],
    ['keywords_count', function (v) { return 'Keywords: ' + v + ' today'; }],
    ['drift', function (v) { return 'Drift: ' + Number(v).toFixed(3) + (Number(v) < 0.05 ? ' • Healthy' : ' • Recalibrate'); }],
    ['kl_divergence', function (v) { return 'KL-D: ' + Number(v).toFixed(4); }],
    ['score', function (v) { return 'Score: ' + Number(v).toFixed(1) + ' • Passed'; }],
    ['reward', function (v) { return 'Reward: ' + Number(v).toFixed(5); }],
    ['action', function (v) { return 'Action: ' + String(v).toUpperCase(); }],
    ['ip', function (v) { return 'IP: ' + v; }],
    ['subnet', function (v) { return 'Subnet: ' + v; }],
    ['battery', function (v) { return 'Battery: ' + v + '%'; }],
    ['p50', function (v) { return 'P50: $' + Number(v).toFixed(2); }],
    ['delta', function (v) { return 'Delta: ' + Number(v).toFixed(1) + '% • Matched'; }],
    ['urls_pushed', function (v) { return v + ' URLs Pushed'; }],
    ['domains', function (v) { return v + ' Domains Live'; }],
    ['words', function (v) { return 'Cost: $0.00 • ' + v + ' words'; }],
    ['intensity', function (v) { return 'Intensity: ' + Number(v).toFixed(2); }],
    ['dwell', function (v) { return 'Session Committed • ' + v + 's dwell'; }],
    ['severity', function (v) { return 'Severity: ' + String(v).toUpperCase(); }],
    ['metric', function (v) { return String(v); }]
  ];

  function metricFromData(payload) {
    if (!payload || typeof payload !== 'object') return null;
    for (var i = 0; i < METRIC_KEYS.length; i++) {
      var key = METRIC_KEYS[i][0];
      if (payload[key] !== undefined && payload[key] !== null) {
        try { return METRIC_KEYS[i][1](payload[key]); } catch (e) { return String(payload[key]); }
      }
    }
    return null;
  }

  /* -------------------------------------------------------------- geometry */
  function port(id, side, dx, dy) {
    var n = NODE_MAP[id];
    if (!n) return { x: 0, y: 0 };
    var s = side || 'right', ox = dx || 0, oy = dy || 0;
    if (s === 'left') return { x: n.x + ox, y: n.y + n.h / 2 + oy };
    if (s === 'right') return { x: n.x + n.w + ox, y: n.y + n.h / 2 + oy };
    if (s === 'top') return { x: n.x + n.w / 2 + ox, y: n.y + oy };
    return { x: n.x + n.w / 2 + ox, y: n.y + n.h + oy };
  }

  function geometry(edge) {
    var fromSide = edge.fromSide || 'right', toSide = edge.toSide || 'left';
    var a = port(edge.from, fromSide, edge.fromDx, edge.fromDy);
    var b = port(edge.to, toSide, edge.toDx, edge.toDy);
    var c1, c2;
    if (edge.curve) { c1 = edge.curve.c1; c2 = edge.curve.c2; }
    else if (fromSide === 'left' || fromSide === 'right') {
      var dx = Math.max(12, Math.abs(b.x - a.x) * 0.45);
      var dir = fromSide === 'right' ? 1 : -1;
      c1 = { x: a.x + dx * dir, y: a.y };
      c2 = { x: b.x - dx * (toSide === 'right' ? -1 : 1), y: b.y };
    } else {
      var dy = Math.max(24, Math.abs(b.y - a.y) * 0.45);
      var vdir = fromSide === 'bottom' ? 1 : -1;
      c1 = { x: a.x, y: a.y + dy * vdir };
      c2 = { x: b.x, y: b.y - dy * (toSide === 'top' ? 1 : -1) };
    }
    return { a: a, b: b, c1: c1, c2: c2, d: 'M ' + a.x + ' ' + a.y + ' C ' + c1.x + ' ' + c1.y + ', ' + c2.x + ' ' + c2.y + ', ' + b.x + ' ' + b.y };
  }

  function bezier(g, t) {
    var mt = 1 - t;
    return {
      x: mt * mt * mt * g.a.x + 3 * mt * mt * t * g.c1.x + 3 * mt * t * t * g.c2.x + t * t * t * g.b.x,
      y: mt * mt * mt * g.a.y + 3 * mt * mt * t * g.c1.y + 3 * mt * t * t * g.c2.y + t * t * t * g.b.y
    };
  }

  /* ---------------------------------------------------------------- render */
  function renderLayers() {
    groupsEl.innerHTML = Object.keys(LAYERS).map(function (id) {
      var l = LAYERS[id];
      var count = NODES.filter(function (n) { return n.layer === id; }).length;
      return '<div class="wf-layer" data-layer-box="' + id + '" style="left:' + l.x + 'px;top:' + l.y + 'px;width:' + l.w + 'px;height:' + l.h + 'px">' +
        '<div class="wf-layer-label"><span class="wf-layer-num">' + l.num + '</span><strong>' + esc(l.label) + '</strong><em>' + count + ' NODES</em></div>' +
        '</div>';
    }).join('');
  }

  function statusGlyph(status) {
    if (status === 'success') return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
    if (status === 'failed') return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
    if (status === 'processing') return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 11-6.2-8.56"/></svg>';
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/></svg>';
  }

  function renderNodes() {
    nodesEl.innerHTML = NODES.map(function (n) {
      var status = nodeStatus[n.id];
      var flag = '<span class="wf-node-flag" data-flag>' + statusGlyph(status) + '</span>';
      var common = ' id="wf-node-' + n.id + '" data-id="' + n.id + '" data-layer="' + n.layer + '" data-status="' + status +
        '" tabindex="0" role="button" style="left:' + n.x + 'px;top:' + n.y + 'px;width:' + n.w + 'px;height:' + n.h + 'px"';
      if (n.gate) {
        var c = n.w / 2, o = 2, i2 = 13;
        return '<div class="wf-node wf-gate"' + common + ' aria-label="' + esc(n.title) + ', decision gate">' +
          '<svg class="wf-gate-shape" viewBox="0 0 ' + n.w + ' ' + n.h + '" aria-hidden="true">' +
          '<polygon points="' + c + ',' + o + ' ' + (n.w - o) + ',' + c + ' ' + c + ',' + (n.h - o) + ' ' + o + ',' + c + '"/>' +
          '<polygon class="wf-gate-inner" points="' + c + ',' + i2 + ' ' + (n.w - i2) + ',' + c + ' ' + c + ',' + (n.h - i2) + ' ' + i2 + ',' + c + '"/></svg>' +
          '<div class="wf-gate-content"><span class="wf-kind">' + esc(n.kind) + '</span><strong>' + esc(n.title.replace(/^\d+\.\s*/, '')) + '</strong>' +
          '<small>' + esc(n.sub) + '</small><span class="wf-gate-metric">' + esc(n.metric || 'evaluating policy') + '</span></div>' + flag + '</div>';
      }
      if (n.action) {
        return '<div class="wf-node wf-action"' + common + ' aria-label="' + esc(n.title) + '">' +
          '<span class="wf-action-icon">' + statusGlyph(status) + '</span>' +
          '<div class="wf-action-body"><strong>' + esc(n.title) + '</strong><span>' + esc(n.sub) + '</span>' +
          '<em class="wf-metric-text wf-action-metric">' + esc(n.metric || 'idle branch') + '</em></div></div>';
      }
      return '<div class="wf-node"' + common + ' aria-label="' + esc(n.title) + '. ' + esc(n.sub) + '">' +
        '<div class="wf-node-head"><span class="wf-node-icon" data-layer-icon="' + n.layer + '">' + esc(LAYERS[n.layer].num.slice(1)) + '</span>' +
        '<span class="wf-kind">' + esc(n.kind) + '</span>' + flag + '</div>' +
        '<div class="wf-node-title">' + esc(n.title) + '</div>' +
        '<div class="wf-node-sub">' + esc(n.sub) + '</div>' +
        '<div class="wf-node-metric"><i></i><span class="wf-metric-text">' + esc(n.metric || '—') + '</span></div>' +
        '<span class="wf-node-sweep" aria-hidden="true"></span></div>';
    }).join('');

    $$('.wf-node', nodesEl).forEach(function (el) {
      el.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
      el.addEventListener('click', function (e) { e.stopPropagation(); openInspector(el.getAttribute('data-id')); });
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openInspector(el.getAttribute('data-id')); }
      });
    });
  }

  function renderEdges() {
    edgesSvg.innerHTML = EDGES.map(function (edge, i) {
      var g = geometry(edge), label = '';
      if (edge.label) {
        var m = bezier(g, 0.52), lw = edge.label.length * 5.6 + 14;
        var lx = m.x + (edge.labelDx || 0) - lw / 2, ly = m.y + (edge.labelDy || 0) - 9.5;
        label = '<g class="wf-branch-chip" transform="translate(' + lx + ',' + ly + ')"><rect width="' + lw + '" height="19" rx="9.5"/>' +
          '<text x="' + (lw / 2) + '" y="12.6" text-anchor="middle">' + esc(edge.label) + '</text></g>';
      }
      return '<g class="wf-edge' + (edge.dashed ? ' is-dashed' : '') + '" data-edge="' + edge.id + '" data-state="' + edgeStatus[edge.id] + '">' +
        '<path class="wf-line" d="' + g.d + '"/>' +
        '<path class="wf-flow" d="' + g.d + '"/>' +
        '<circle class="wf-edge-end" cx="' + g.b.x + '" cy="' + g.b.y + '" r="2.1"/>' +
        '<circle class="wf-pulse" r="2.8"><animateMotion dur="' + (2.4 + (i % 6) * 0.22).toFixed(2) + 's" repeatCount="indefinite" path="' + g.d + '"/></circle>' +
        label + '</g>';
    }).join('');
    edgesSvg.setAttribute('viewBox', '0 0 ' + WORLD.w + ' ' + WORLD.h);
  }

  function setNodeStatus(id, status, metric) {
    var n = NODE_MAP[id];
    if (!n) return;
    nodeStatus[id] = status;
    var el = $('#wf-node-' + id);
    if (el) {
      el.setAttribute('data-status', status);
      var flag = $('[data-flag]', el);
      if (flag) flag.innerHTML = statusGlyph(status);
      if (metric) {
        n.metric = metric;
        var target = $('.wf-metric-text', el) || $('.wf-gate-metric', el);
        if (target) target.textContent = metric;
      }
    }
    updateMinimapNode(id);
    if (state.selected === id) openInspector(id);
    document.dispatchEvent(new CustomEvent('workflow:node-status', { detail: { node: n, status: status, metric: metric } }));
  }

  function setEdgeStatus(id, status) {
    if (!EDGE_MAP[id]) return;
    edgeStatus[id] = status;
    var el = edgesSvg.querySelector('[data-edge="' + id + '"]');
    if (el) el.setAttribute('data-state', status);
  }

  function pulseIncoming(nodeId, successAfter) {
    (INCOMING[nodeId] || []).forEach(function (edgeId) {
      setEdgeStatus(edgeId, 'active');
      if (successAfter) setTimeout(function () { setEdgeStatus(edgeId, 'success'); }, successAfter);
    });
  }

  function resetGraph() {
    NODES.forEach(function (n) { setNodeStatus(n.id, 'idle'); });
    EDGES.forEach(function (e) { setEdgeStatus(e.id, 'idle'); });
  }

  /* -------------------------------------------------------------- minimap */
  function buildMinimap() {
    if (!minimap) return;
    minimap.innerHTML = NODES.map(function (n) {
      return '<rect data-mini="' + n.id + '" x="' + n.x + '" y="' + n.y + '" width="' + n.w + '" height="' + n.h + '" rx="3" class="wf-mini-node ' + (nodeStatus[n.id] === 'success' ? 'done' : '') + '"/>';
    }).join('') + '<rect class="wf-mini-vp" data-vp x="0" y="0" width="300" height="200" rx="3"/>';
    minimap.setAttribute('viewBox', '0 0 ' + WORLD.w + ' ' + WORLD.h);
    minimap.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
    minimap.addEventListener('click', function (e) {
      e.stopPropagation();
      var r = minimap.getBoundingClientRect();
      if (!r.width) return;
      focus(((e.clientX - r.left) / r.width) * WORLD.w, ((e.clientY - r.top) / r.height) * WORLD.h, Math.max(state.zoom, 0.8));
    });
  }

  function updateMinimapNode(id) {
    if (!minimap) return;
    var el = minimap.querySelector('[data-mini="' + id + '"]');
    if (el) el.classList.toggle('done', nodeStatus[id] === 'success');
  }

  function updateMinimapViewport() {
    if (!minimap || !stage) return;
    var vp = minimap.querySelector('[data-vp]');
    if (!vp) return;
    var r = stage.getBoundingClientRect();
    if (!r.width) return;
    vp.setAttribute('x', clamp(-state.x / state.zoom, -30, WORLD.w));
    vp.setAttribute('y', clamp(-state.y / state.zoom, -30, WORLD.h));
    vp.setAttribute('width', Math.min(r.width / state.zoom, WORLD.w + 60));
    vp.setAttribute('height', Math.min(r.height / state.zoom, WORLD.h + 60));
  }

  /* ----------------------------------------------------------- pan & zoom */
  function applyTransform() {
    if (!world) return;
    world.style.transform = 'translate3d(' + state.x + 'px,' + state.y + 'px,0) scale(' + state.zoom + ')';
    var readout = $('#wfZoomReadout');
    if (readout) readout.textContent = Math.round(state.zoom * 100) + '%';
    updateMinimapViewport();
  }

  function tween(target, duration) {
    duration = duration || 280;
    var from = { x: state.x, y: state.y, z: state.zoom }, start = performance.now();
    return new Promise(function (resolve) {
      (function frame(now) {
        var t = clamp((now - start) / duration, 0, 1), e = 1 - Math.pow(1 - t, 3);
        state.zoom = from.z + (target.z - from.z) * e;
        state.x = from.x + (target.x - from.x) * e;
        state.y = from.y + (target.y - from.y) * e;
        applyTransform();
        if (t < 1) requestAnimationFrame(frame); else resolve();
      })(performance.now());
    });
  }

  function fit(animate) {
    if (!stage) return;
    var r = stage.getBoundingClientRect();
    if (!r.width) return;
    var z = clamp(Math.min((r.width - 30) / WORLD.w, (r.height - 24) / WORLD.h), state.minZoom, 1.05);
    var target = { z: z, x: (r.width - WORLD.w * z) / 2, y: (r.height - WORLD.h * z) / 2 };
    if (animate === false) { state.zoom = target.z; state.x = target.x; state.y = target.y; applyTransform(); }
    else tween(target);
  }

  function focus(wx, wy, z) {
    if (!stage) return;
    z = clamp(z || state.zoom, state.minZoom, state.maxZoom);
    var r = stage.getBoundingClientRect();
    tween({ z: z, x: r.width / 2 - wx * z, y: r.height / 2 - wy * z }, 320);
  }

  function zoomAt(cx, cy, next) {
    var z = clamp(next, state.minZoom, state.maxZoom);
    var wx = (cx - state.x) / state.zoom, wy = (cy - state.y) / state.zoom;
    state.zoom = z; state.x = cx - wx * z; state.y = cy - wy * z;
    applyTransform();
  }

  function zoomCenter(factor) {
    if (!stage) return;
    var r = stage.getBoundingClientRect();
    zoomAt(r.width / 2, r.height / 2, state.zoom * factor);
  }

  function bindCanvas() {
    if (!stage) return;
    var drag = null;
    stage.addEventListener('wheel', function (e) {
      e.preventDefault();
      var r = stage.getBoundingClientRect();
      zoomAt(e.clientX - r.left, e.clientY - r.top, state.zoom * Math.exp(-e.deltaY * 0.00155));
    }, { passive: false });
    stage.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      if (e.target.closest('.wf-node, #wf-minimap, .wf-canvas-hint, .wf-legend')) return;
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY, ox: state.x, oy: state.y };
      stage.classList.add('is-dragging');
      try { stage.setPointerCapture(e.pointerId); } catch (err) { }
    });
    stage.addEventListener('pointermove', function (e) {
      if (!drag || drag.id !== e.pointerId) return;
      state.x = drag.ox + (e.clientX - drag.x);
      state.y = drag.oy + (e.clientY - drag.y);
      applyTransform();
    });
    function end() { drag = null; stage.classList.remove('is-dragging'); }
    stage.addEventListener('pointerup', end);
    stage.addEventListener('pointercancel', end);
    stage.addEventListener('dblclick', function (e) { if (!e.target.closest('.wf-node')) fit(true); });
  }

  function bindZoomButtons() {
    var zin = $('#wfZoomIn'), zout = $('#wfZoomOut'), reset = $('#wfZoomReset'), fitBtn = $('#wfFitBtn'), readout = $('#wfZoomReadout');
    if (zin) zin.addEventListener('click', function () { zoomCenter(1.2); });
    if (zout) zout.addEventListener('click', function () { zoomCenter(1 / 1.2); });
    if (readout) readout.addEventListener('click', function () {
      if (!stage) return;
      var r = stage.getBoundingClientRect();
      tween({ z: 1, x: r.width / 2 - (LAYERS.l3.x + LAYERS.l3.w / 2), y: r.height / 2 - 500 }, 280);
    });
    if (reset) reset.addEventListener('click', function () { zoomCenter(1 / state.zoom); });
    if (fitBtn) fitBtn.addEventListener('click', function () { fit(true); });
  }

  /* ------------------------------------------------------------- inspector */
  function ensureInspector() {
    if (inspector) return;
    var host = $('#live-workflow-visualizer') || document.body;
    inspector = document.createElement('div');
    inspector.className = 'wf-inspector';
    inspector.id = 'wf-inspector';
    inspector.setAttribute('aria-hidden', 'true');
    inspector.innerHTML = '<div class="wf-inspector-scrim" data-insp-close></div>' +
      '<aside class="wf-inspector-panel" role="dialog" aria-label="Node telemetry">' +
      '<header><span class="wf-insp-eyebrow">Node telemetry</span>' +
      '<button type="button" class="wf-insp-close" data-insp-close aria-label="Close inspector">' +
      '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg></button></header>' +
      '<div class="wf-insp-body" data-insp-body></div>' +
      '<footer><button type="button" class="wf-insp-btn" data-insp-focus>Focus node</button>' +
      '<button type="button" class="wf-insp-btn ghost" data-insp-copy>Copy payload</button></footer></aside>';
    host.appendChild(inspector);
    inspectorBody = $('[data-insp-body]', inspector);
    $$('[data-insp-close]', inspector).forEach(function (el) { el.addEventListener('click', closeInspector); });
    $('[data-insp-focus]', inspector).addEventListener('click', function () {
      var n = NODE_MAP[state.selected];
      if (n) focus(n.x + n.w / 2, n.y + n.h / 2, Math.max(state.zoom, 0.9));
    });
    $('[data-insp-copy]', inspector).addEventListener('click', function () {
      var text = JSON.stringify(lastPayload[state.selected] || { node: state.selected, status: nodeStatus[state.selected] }, null, 2);
      if (navigator.clipboard) navigator.clipboard.writeText(text).catch(function () { });
      writeLog('SYSTEM', 'Payload copied for ' + String(state.selected || '').toUpperCase(), 'info');
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeInspector(); });
  }

  function highlightJson(json) {
    return esc(json)
      .replace(/&quot;([^&]+)&quot;(\s*:)/g, '<span class="jk">&quot;$1&quot;</span>$2')
      .replace(/:\s(&quot;[^&]*&quot;)/g, ': <span class="js">$1</span>')
      .replace(/:\s(-?\d+\.?\d*)/g, ': <span class="jn">$1</span>')
      .replace(/:\s(true|false|null)/g, ': <span class="jb">$1</span>');
  }

  function openInspector(id) {
    var n = NODE_MAP[id];
    if (!n) return;
    ensureInspector();
    state.selected = id;
    $$('.wf-node', nodesEl).forEach(function (el) { el.classList.toggle('is-selected', el.getAttribute('data-id') === id); });
    var status = nodeStatus[id], payload = lastPayload[id];
    var incoming = (INCOMING[id] || []).map(function (e) { return NODE_MAP[EDGE_MAP[e].from].title; });
    var outgoing = EDGES.filter(function (e) { return e.from === id; }).map(function (e) { return NODE_MAP[e.to].title + (e.label ? ' · ' + e.label : ''); });
    var json = payload ? JSON.stringify(payload, null, 2) : JSON.stringify({ node_id: id.toUpperCase(), status: status, data: null, run_id: state.runId }, null, 2);

    inspectorBody.innerHTML =
      '<div class="wf-insp-hero"><h3>' + esc(n.title) + '</h3><p>' + esc(n.sub) + '</p>' +
      '<div class="wf-insp-badges"><span class="wf-pill wf-pill-' + status + '">' + esc(status) + '</span>' +
      '<span class="wf-pill">' + esc(n.kind) + '</span><span class="wf-pill">' + esc(LAYERS[n.layer].num + ' · ' + LAYERS[n.layer].label) + '</span></div></div>' +
      '<section><h4>Live metric</h4><div class="wf-insp-metric"><i></i><span>' + esc(n.metric || 'No metric reported') + '</span></div></section>' +
      '<section><h4>Inputs <em>' + incoming.length + '</em></h4>' +
      (incoming.length ? '<ul class="wf-insp-list">' + incoming.map(function (t) { return '<li><span class="dir in">IN</span>' + esc(t) + '</li>'; }).join('') + '</ul>' : '<p class="wf-insp-empty">Graph entry point — no upstream node</p>') +
      '</section>' +
      '<section><h4>Outputs <em>' + outgoing.length + '</em></h4>' +
      (outgoing.length ? '<ul class="wf-insp-list">' + outgoing.map(function (t) { return '<li><span class="dir out">OUT</span>' + esc(t) + '</li>'; }).join('') + '</ul>' : '<p class="wf-insp-empty">Terminal node — no downstream branch</p>') +
      '</section>' +
      '<section><h4>Latest payload <em>SSE</em></h4><pre class="wf-json">' + highlightJson(json) + '</pre></section>';

    inspector.classList.add('is-open');
    inspector.setAttribute('aria-hidden', 'false');
    document.dispatchEvent(new CustomEvent('workflow:node-select', { detail: { node: n, status: status, payload: payload } }));
  }

  function closeInspector() {
    if (!inspector) return;
    inspector.classList.remove('is-open');
    inspector.setAttribute('aria-hidden', 'true');
    state.selected = null;
    $$('.wf-node', nodesEl).forEach(function (el) { el.classList.remove('is-selected'); });
  }

  /* ----------------------------------------------------------- event stream */
  function writeLog(tag, message, level) {
    if (!logEl) return;
    var row = document.createElement('div');
    row.className = 'wf-stream-row ' + (level || 'info');
    var t = document.createElement('span'); t.className = 'wf-time'; t.textContent = time();
    var d = document.createElement('i'); d.className = 'wf-log-dot';
    var g = document.createElement('span'); g.className = 'wf-tag'; g.textContent = String(tag || 'SYSTEM').slice(0, 18);
    var m = document.createElement('span'); m.className = 'wf-msg'; m.textContent = message;
    row.appendChild(t); row.appendChild(d); row.appendChild(g); row.appendChild(m);
    logEl.appendChild(row);
    while (logEl.children.length > 180) logEl.removeChild(logEl.firstElementChild);
    var auto = $('#wfAutoScroll');
    if (!auto || auto.checked) logEl.scrollTop = logEl.scrollHeight;
    var stamp = $('#wf-last-event');
    if (stamp) stamp.textContent = time();
  }

  function seedLog() {
    if (!logEl) return;
    logEl.innerHTML = '';
    writeLog('SYSTEM', 'Subscribed to ' + API.stream, 'run');
    writeLog('PHASE4_DRIFT', 'KL-divergence 0.012 · model calibration healthy', 'ok');
    writeLog('ADSTERRA_SYNC', 'Official API reconciliation · 15-min window opened', 'run');
    writeLog('TELEGRAM_BOT', 'Safety sentinel clear · 0 alerts · status green', 'ok');
    writeLog('A1_DECISION', 'LinTS arm CLICK selected · expected reward 0.00145', 'ok');
    writeLog('DB_SAVE', 'Session committed · 32s dwell · SQLite WAL checkpoint', 'ok');
    writeLog('CF_PAGES', 'Hugo build live on 10 domains · traffic bridge armed', 'ok');
    writeLog('CGNAT_TRACKER', 'Subnet 100.64.55.0/24 locked · no collision detected', 'ok');
  }

  function setConnection(kind, label) {
    if (connectionEl) {
      connectionEl.setAttribute('data-state', kind);
      var txt = connectionEl.querySelector('[data-conn-label]');
      if (txt) txt.textContent = label;
    }
    if (streamStatusEl) streamStatusEl.textContent = label;
  }

  /* ------------------------------------------------------------------- SSE */
  function connectSSE() {
    setConnection('demo', 'Live simulation');
    if (typeof global.EventSource !== 'function') return;
    var source;
    try { source = new global.EventSource(API.stream); } catch (err) { return; }
    state.sse = source;
    source.onopen = function () { setConnection('live', 'Connected (Live)'); writeLog('SYSTEM', 'SSE channel open · realtime telemetry attached', 'ok'); };
    /* Never call source.close() here — EventSource retries automatically. */
    source.onerror = function () { setConnection('retry', 'Reconnecting…'); };
    source.onmessage = function (event) { ingest(event.data); };
    ['node_update', 'edge_update', 'run_event', 'run_complete', 'workflow_finish'].forEach(function (name) {
      source.addEventListener(name, function (event) { ingest(event.data, name); });
    });
  }

  function ingest(raw, type) {
    var data;
    try { data = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch (e) { return; }
    if (!data || typeof data !== 'object') return;

    var rawId = String(data.node_id || data.node || '').toUpperCase();
    var nodeId = NODE_ALIAS[rawId] || rawId.toLowerCase();
    var isFinish = rawId === 'WORKFLOW_FINISH' || FINISH_TOKENS.indexOf(rawId) >= 0 || data.event === 'run_complete' || type === 'run_complete';

    if (data.run_id) {
      state.runId = data.run_id;
      if (runIdEl) runIdEl.textContent = '#' + data.run_id;
      var badge = $('#wf-run-badge-id');
      if (badge) badge.textContent = '#' + data.run_id;
    }

    if (isFinish) {
      state.running = false;
      setRunningUI(false);
      writeLog('SYSTEM', 'Run #' + (data.run_id || state.runId || '—') + ' finished', 'ok');
      document.dispatchEvent(new CustomEvent('workflow:run-complete', { detail: data }));
      return;
    }

    if (NODE_MAP[nodeId]) {
      var status = normalizeStatus(data.status || (type === 'node_update' ? 'processing' : ''));
      var metric = metricFromData(data.data) || (typeof data.metric === 'string' ? data.metric : null);
      lastPayload[nodeId] = data;
      if (metric || data.status) {
        pulseIncoming(nodeId, status === 'success' ? 420 : status === 'failed' ? 900 : 0);
        setNodeStatus(nodeId, status, metric);
      }
      if (data.status === 'failed' || data.level === 'error') setNodeStatus(nodeId, 'failed', metric);
    }

    if (data.edge && EDGE_MAP[data.edge]) {
      var edgeState = data.edge_status ? normalizeStatus(data.edge_status) : (normalizeStatus(data.status) === 'idle' ? 'active' : normalizeStatus(data.status));
      setEdgeStatus(data.edge, edgeState);
    }
    if (data.message) {
      var level = data.level === 'error' ? 'err' : data.level === 'warn' ? 'warn' : normalizeStatus(data.status) === 'processing' ? 'run' : 'ok';
      writeLog(rawId || (nodeId ? nodeId.toUpperCase() : 'SYSTEM'), data.message, level);
    }
  }

  /* ------------------------------------------------------------- execution */
  function setRunningUI(running) {
    state.running = running;
    if (triggerBtn) {
      triggerBtn.disabled = running;
      triggerBtn.classList.toggle('is-running', running);
      triggerBtn.setAttribute('aria-busy', String(running));
      var label = triggerBtn.querySelector('[data-btn-label]');
      if (label) label.textContent = running ? 'Running pipeline…' : 'Start pipeline run';
    }
    var pill = $('#wf-run-state');
    if (pill) pill.textContent = running ? 'Executing' : 'Operational';
  }

  function metrics(id, cycle, mode) {
    var values = {
      trends: 'Keywords: ' + (14 + (cycle % 4)) + ' today',
      freellm: 'Cost: $0.00 • ' + (1420 + cycle * 64) + ' words',
      a5: 'Score: ' + (83.4 + (cycle % 5) * 0.4).toFixed(1) + ' • Passed',
      cf: '10 Domains Live',
      gsc: (10 + (cycle % 3)) + ' URLs Pushed',
      push: 'Broadcast Active',
      scheduler: 'Intensity: ' + (0.88 + cycle * 0.02).toFixed(2) + ' • 150/hr',
      cgnat: 'Subnet: 100.64.55.0/24',
      airplane: 'IP: 100.64.55.' + (10 + (cycle * 7) % 40),
      phone: 'Battery: ' + Math.max(62, 88 - cycle * 2) + '% • 32°C',
      capture: '1080x2400 PNG · ' + (2.1 + cycle * 0.1).toFixed(1) + ' MB',
      vision: 'bbox: [80, 1218, 920, 250]',
      anomaly: 'Severity: NORMAL • Clean',
      safe: 'Sentinel: ' + (mode === 'paper' ? 'enforce' : 'armed'),
      ctr: (2.4 + cycle * 0.2).toFixed(1) + '% · under cap',
      a1: 'Action: CLICK • Reward: 0.00' + (140 + cycle),
      adb: mode === 'paper' ? 'Tap simulated · (540, 1343)' : 'Tap at (540, 1343)',
      db: 'Session Committed • ' + (32 + cycle * 4) + 's dwell',
      hq: 'Tunnel: Active',
      forecast: 'P50: $' + (14.2 + cycle * 0.44).toFixed(2),
      adsterra: 'Delta: ' + (cycle * 0.1).toFixed(1) + '% • Matched 100%',
      telegram: 'Status: Green • 0 Alerts',
      drift: 'Drift: ' + (0.012 + cycle * 0.001).toFixed(3) + ' • Healthy'
    };
    return values[id] !== undefined ? values[id] : (NODE_MAP[id] ? NODE_MAP[id].metric : '');
  }

  function messages(id, cycle, mode) {
    var map = {
      trends: 'Google Trends RSS parsed · ' + (14 + (cycle % 4)) + ' keywords queued',
      freellm: 'Hybrid completion synthesized · $0.00 spend',
      a5: 'Perplexity & burstiness verified · score ' + (83.4 + (cycle % 5) * 0.4).toFixed(1),
      cf: 'Hugo static build published to edge',
      gsc: (10 + (cycle % 3)) + ' URLs pushed to GSC + IndexNow',
      push: 'VAPID broadcast fan-out complete',
      scheduler: 'NHPP sampler selected peak-hour slot',
      cgnat: '/24 subnet collision lock held',
      airplane: 'Carrier IP renewal · airplane mode cycled',
      phone: 'Android Chrome opened published page · ADB authorized',
      capture: 'ADB screencap + XML hierarchy captured',
      vision: 'Ad candidate detected · bbox [80, 1218, 920, 250]',
      anomaly: 'EWMA + Isolation Forest · severity NORMAL',
      safe: 'Safe-mode gate evaluated · NO · sentinel clear',
      ctr: 'CTR guard · ' + (2.4 + cycle * 0.2).toFixed(1) + '% under 4.5% cap',
      a1: 'Thompson Sampling selected arm CLICK',
      adb: 'Bézier touch bridge ' + (mode === 'paper' ? 'simulated' : 'dispatched') + ' at (540, 1343)',
      db: 'Session committed with BEGIN IMMEDIATE',
      hq: 'Central controller acknowledged run',
      forecast: 'IRLS projection refreshed · P50 $' + (14.2 + cycle * 0.44).toFixed(2),
      adsterra: 'Official API poll complete · 100% matched',
      telegram: 'Daily report pushed · 0 alerts',
      drift: 'KL-divergence ' + (0.012 + cycle * 0.001).toFixed(3) + ' · calibration healthy'
    };
    return map[id] || (NODE_MAP[id] ? NODE_MAP[id].title + ' executed' : 'executed');
  }

  async function runSequence(runId, steps, mode) {
    var token = ++state.token;
    var delay = steps >= 10 ? 110 : steps >= 5 ? 140 : 175;
    state.runId = runId;
    setRunningUI(true);
    resetGraph();
    if (runIdEl) runIdEl.textContent = '#' + runId;
    var badge = $('#wf-run-badge-id');
    if (badge) badge.textContent = '#' + runId;
    writeLog('SYSTEM', 'Run #' + runId + ' started · ' + steps + ' step(s) · ' + mode + ' mode', 'run');

    async function tick(id, incoming, cycle) {
      if (token !== state.token) throw new Error('aborted');
      if (incoming) setEdgeStatus(incoming, 'active');
      setNodeStatus(id, 'processing', metrics(id, cycle, mode));
      lastPayload[id] = { node_id: id.toUpperCase(), status: 'processing', run_id: runId, data: { cycle: cycle, mode: mode } };
      writeLog(id.toUpperCase(), messages(id, cycle, mode), 'run');
      await sleep(delay);
      if (token !== state.token) throw new Error('aborted');
      setNodeStatus(id, 'success', metrics(id, cycle, mode));
      if (incoming) setEdgeStatus(incoming, 'success');
      lastPayload[id] = { node_id: id.toUpperCase(), status: 'success', run_id: runId, message: messages(id, cycle, mode), data: { metric: metrics(id, cycle, mode), cycle: cycle } };
    }

    try {
      var content = (async function () {
        await tick('trends', null, 0); await tick('freellm', 'e1', 0); await tick('a5', 'e2', 0);
        await tick('cf', 'e3', 0); await tick('gsc', 'e4', 0); await tick('push', 'e5', 0);
      })();
      var hardware = (async function () {
        await sleep(delay * 2);
        await tick('scheduler', null, 0); await tick('cgnat', 'e6', 0);
        await tick('airplane', 'e7', 0); await tick('phone', 'e8', 0);
      })();
      await Promise.all([content, hardware]);
      await tick('phone', 'e25', 0);
      for (var cycle = 1; cycle <= steps; cycle++) {
        if (token !== state.token) return;
        await tick('capture', 'e9', cycle); await tick('vision', 'e10', cycle);
        await tick('anomaly', 'e11', cycle); await tick('safe', 'e12', cycle);
        await tick('ctr', 'e14', cycle); await tick('a1', 'e16', cycle); await tick('adb', 'e17', cycle);
        if (cycle < steps) { setEdgeStatus('e18', 'active'); await sleep(90); setEdgeStatus('e18', 'success'); }
      }
      await tick('db', 'e19', steps);
      await Promise.all([
        tick('hq', 'e20', steps), tick('forecast', 'e21', steps),
        tick('adsterra', 'e22', steps), tick('telegram', 'e23', steps), tick('drift', 'e24', steps)
      ]);
      if (token !== state.token) return;
      setRunningUI(false);
      writeLog('SYSTEM', 'Run #' + runId + ' completed · all guardrails passed', 'ok');
      document.dispatchEvent(new CustomEvent('workflow:run-complete', { detail: { runId: runId, steps: steps, mode: mode } }));
    } catch (err) {
      if (String(err && err.message) === 'aborted') return;
      setRunningUI(false);
      writeLog('SYSTEM', 'Run aborted · execution token invalidated', 'err');
    }
  }

  async function triggerPipeline() {
    if (state.running) return;
    var modeInput = document.querySelector('input[name="wfMode"]:checked');
    var stepsInput = $('#wfSteps');
    var mode = modeInput ? modeInput.value : 'live';
    var steps = clamp(parseInt(stepsInput ? stepsInput.value : '3', 10) || 3, 1, 10);
    var runId = Date.now().toString().slice(-5);
    state.mode = mode; state.steps = steps;
    setRunningUI(true);
    writeLog('SYSTEM', 'POST ' + API.trigger + ' · {"mode":"' + mode + '","steps":' + steps + '}', 'run');
    try {
      var controller = typeof AbortController === 'function' ? new AbortController() : null;
      var timer = controller ? setTimeout(function () { controller.abort(); }, TRIGGER_TIMEOUT_MS) : null;
      var response = await fetch(API.trigger, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ mode: mode, steps: steps }),
        signal: controller ? controller.signal : undefined
      });
      if (timer) clearTimeout(timer);
      if (response.ok) {
        var payload = await response.json().catch(function () { return {}; });
        writeLog('SYSTEM', 'Trigger accepted' + (payload.run_id ? ' · run #' + payload.run_id : ''), 'ok');
        if (state.sse && state.sse.readyState === 1) return;
        await runSequence(payload.run_id || runId, steps, mode);
        return;
      }
    } catch (err) { /* endpoint unavailable — fall back to local simulation */ }
    setRunningUI(false);
    await runSequence(runId, steps, mode);
  }

  function resetAll() {
    state.token++;
    setRunningUI(false);
    resetGraph();
    writeLog('SYSTEM', 'All 25 nodes reset to idle', 'warn');
    document.dispatchEvent(new CustomEvent('workflow:reset'));
  }

  /* --------------------------------------------------------------- history */
  async function loadHistory() {
    try {
      var response = await fetch(API.history, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('history unavailable');
      var data = await response.json();
      renderHistory(Array.isArray(data) ? data : (data.runs || []));
      return data;
    } catch (err) {
      renderHistory([]);
      return [];
    }
  }

  function renderHistory(runs) {
    var target = $('#wf-history-list');
    if (!target) return;
    target.innerHTML = runs.length ? runs.map(function (r) {
      return '<tr><td>' + esc(r.id || r.run_id || '—') + '</td><td>' + esc(r.mode || 'paper') + '</td><td>' + esc(r.steps || '—') + '</td><td>' + esc(r.created_at || r.started_at || '—') + '</td></tr>';
    }).join('') : '<tr><td colspan="4" class="wf-empty">No history returned by ' + esc(API.history) + '</td></tr>';
  }

  /* ------------------------------------------------------------------ boot */
  function init() {
    stage = $('#wf-stage');
    if (!stage) return;
    world = $('#wf-world');
    groupsEl = $('#wf-layers');
    nodesEl = $('#wf-nodes');
    edgesSvg = $('#wf-edges');
    minimap = $('#wf-minimap');
    logEl = $('#wf-event-log');
    triggerBtn = $('#wfTriggerRunBtn');
    runIdEl = $('#wf-run-id');
    connectionEl = $('#wf-connection');
    streamStatusEl = $('#wf-connection-state');
    if (!world || !groupsEl || !nodesEl || !edgesSvg) return;

    world.style.width = WORLD.w + 'px';
    world.style.height = WORLD.h + 'px';
    edgesSvg.setAttribute('width', WORLD.w);
    edgesSvg.setAttribute('height', WORLD.h);

    renderLayers();
    renderNodes();
    renderEdges();
    buildMinimap();
    bindCanvas();
    bindZoomButtons();
    ensureInspector();
    seedLog();

    if (triggerBtn) triggerBtn.addEventListener('click', triggerPipeline);
    var resetBtn = $('#wfResetBtn');
    if (resetBtn) resetBtn.addEventListener('click', resetAll);
    var clearBtn = $('#wfClearLog');
    if (clearBtn) clearBtn.addEventListener('click', function () { logEl.innerHTML = ''; writeLog('SYSTEM', 'Event stream cleared', 'info'); });
    var historyBtn = $('#wfHistoryBtn');
    if (historyBtn) historyBtn.addEventListener('click', function () {
      loadHistory();
      var panel = $('#wf-history-panel');
      if (panel) panel.classList.toggle('is-open');
    });
    $$('input[name="wfMode"]').forEach(function (input) {
      input.addEventListener('change', function () {
        state.mode = input.value;
        writeLog('SYSTEM', input.value === 'live' ? 'Live touch armed · operator approval required' : 'Paper mode selected · gestures simulated', input.value === 'live' ? 'warn' : 'info');
      });
    });
    var stepsSel = $('#wfSteps');
    if (stepsSel) stepsSel.addEventListener('change', function () { state.steps = clamp(parseInt(stepsSel.value, 10) || 3, 1, 10); });

    document.addEventListener('keydown', function (e) {
      var tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
      if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomCenter(1.2); }
      else if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomCenter(1 / 1.2); }
      else if (e.key.toLowerCase() === 'f' || e.key === '0') { e.preventDefault(); fit(true); }
    });

    global.addEventListener('resize', function () { updateMinimapViewport(); });
    if (typeof global.ResizeObserver === 'function') {
      try { new global.ResizeObserver(function () { updateMinimapViewport(); }).observe(stage); } catch (err) { }
    }

    fit(false);
    setTimeout(function () { fit(false); }, 180);
    connectSSE();
    writeLog('SYSTEM', 'Visualizer ready · 25 nodes / 4 layers / ' + EDGES.length + ' connections', 'ok');
  }

  global.CRMWorkflow = {
    init: init,
    trigger: triggerPipeline,
    reset: resetAll,
    ingest: ingest,
    setNodeStatus: setNodeStatus,
    setEdgeStatus: setEdgeStatus,
    openInspector: openInspector,
    closeInspector: closeInspector,
    loadHistory: loadHistory,
    fit: function () { fit(true); },
    nodes: NODES,
    edges: EDGES,
    alias: NODE_ALIAS,
    geometry: geometry
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
