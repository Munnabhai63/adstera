"""Live Workflow Visualizer — Vuexy admin view (v2).

Drop-in files
-------------
1. admin_ui/views/live_workflow.py          (this file — view + page renderer)
2. admin_ui/assets/js/crm-workflow.js       (pan/zoom, SVG router, SSE, inspector)

Usage::

    from admin_ui.views.live_workflow import (
        render_live_workflow_view, render_workflow_dashboard_page,
    )

    fragment = render_live_workflow_view()          # embed inside a Vuexy page
    page     = render_workflow_dashboard_page()     # complete standalone page

Backend contract
----------------
GET  /api/phase4/live-workflow-stream   SSE: {node_id, status, message, data, run_id}
POST /api/phase4/workflow/trigger       {"mode": "paper"|"live", "steps": 1..10}
GET  /api/phase4/workflow/history       JSON list (or {"runs": [...]})

The controller maps backend identifiers such as ``PHASE4_DRIFT`` onto canvas
node ids through ``NODE_ALIAS`` in ``crm-workflow.js``; a ``WORKFLOW_FINISH``
event (or ``{"event": "run_complete"}``) stops the run spinner.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
VIEW_ROOT = Path(__file__).resolve().parents[1]          # admin_ui/
WORKFLOW_JS = VIEW_ROOT / "assets" / "js" / "crm-workflow.js"
WORKFLOW_JS_URL = "/crm-assets/js/crm-workflow.js"       # static mount for crm-workflow.js
INLINE_JS_DEFAULT = True                                 # inline when the asset is readable


# --------------------------------------------------------------------------
# Styles — every rule is scoped under .lwv so Vuexy core CSS is untouched
# --------------------------------------------------------------------------
WORKFLOW_CSS = r"""
.lwv{
  --bg:#0b0f19; --panel:#111827; --panel-2:#0d1420; --panel-3:#151e2e;
  --line:rgba(255,255,255,.085); --line-2:rgba(255,255,255,.14);
  --txt:#f1f5f9; --txt-2:#cbd5e1; --muted:#8a9bb2; --muted-2:#63748c;
  --cyan:#38bdf8; --green:#10b981; --amber:#f59e0b; --red:#ef4444;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--txt); font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:13px; line-height:1.5; position:relative;
}
.lwv *{box-sizing:border-box}
.lwv button,.lwv input,.lwv select{font:inherit;color:inherit}
.lwv button{cursor:pointer;border:0;background:none}
.lwv ::selection{background:rgba(56,189,248,.28);color:#fff}
.lwv ::-webkit-scrollbar{width:8px;height:8px}
.lwv ::-webkit-scrollbar-track{background:transparent}
.lwv ::-webkit-scrollbar-thumb{background:#263248;border-radius:8px;border:2px solid transparent;background-clip:content-box}

/* Component shell -------------------------------------------------------- */
.lwv-card{
  border:1px solid var(--line); border-radius:16px; overflow:hidden;
  background:linear-gradient(180deg,#101827,#0c121d);
  box-shadow:0 20px 50px -18px rgba(0,0,0,.65), inset 0 1px 0 rgba(255,255,255,.04);
}
.lwv-head{display:flex;align-items:flex-start;gap:18px;flex-wrap:wrap;padding:16px 18px;border-bottom:1px solid var(--line)}
.lwv-titleblock{min-width:240px;flex:1}
.lwv-eyebrow{display:flex;align-items:center;gap:7px;font-size:9px;letter-spacing:.13em;text-transform:uppercase;color:#71819b;font-weight:600;margin-bottom:6px}
.lwv-eyebrow i{width:14px;height:1px;background:#3a475c;display:inline-block}
.lwv-head h1,.lwv-head h2{margin:0;font-size:20px;line-height:1.15;letter-spacing:-.03em;font-weight:600;color:#f8fafc;display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.lwv-live{display:inline-flex;align-items:center;gap:5px;border:1px solid rgba(56,189,248,.22);background:rgba(56,189,248,.08);color:#a5f3fc;border-radius:99px;padding:2px 7px;font-size:8px;letter-spacing:.09em;text-transform:uppercase;font-weight:600}
.lwv-live i{width:4px;height:4px;border-radius:50%;background:var(--cyan);box-shadow:0 0 7px var(--cyan);animation:lwvPulse 2s infinite}
.lwv-sub{margin:6px 0 0;font-size:11px;color:#7f8fa6;max-width:640px;line-height:1.6}
.lwv-sub strong{color:#b8c5d6;font-weight:500}
.lwv-controls{display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.lwv-control{display:flex;flex-direction:column;gap:5px}
.lwv-control > span{font-size:8px;letter-spacing:.1em;text-transform:uppercase;color:#64748b;font-weight:600;padding-left:2px}
.lwv-seg{display:flex;gap:2px;padding:3px;background:#0b1220;border:1px solid var(--line);border-radius:9px}
.lwv-seg label{margin:0;cursor:pointer}
.lwv-seg input{position:absolute;opacity:0;pointer-events:none}
.lwv-seg span{display:inline-flex;align-items:center;gap:5px;height:27px;padding:0 9px;border-radius:6px;border:1px solid transparent;font-size:10px;color:#8494ab;white-space:nowrap;transition:.15s}
.lwv-seg input:checked + span{background:#1c2637;border-color:rgba(255,255,255,.12);color:#f1f5f9}
.lwv-seg input:focus-visible + span{outline:2px solid rgba(56,189,248,.6);outline-offset:1px}
.lwv-seg .lwv-live-opt input:checked + span{color:#fcd34d;border-color:rgba(245,158,11,.3);background:rgba(245,158,11,.1)}
.lwv-steps{height:33px;border:1px solid var(--line);background:#0b1220;border-radius:9px;padding:0 7px;font-family:var(--mono);font-size:10px;color:#cdd9e6;outline:none;min-width:66px}
.lwv-btn{height:34px;border-radius:9px;border:1px solid transparent;display:inline-flex;align-items:center;justify-content:center;gap:6px;font-size:11px;font-weight:600;padding:0 13px;transition:.16s;white-space:nowrap}
.lwv-btn.primary{background:#f8fafc;color:#0b0f19;box-shadow:0 4px 14px rgba(0,0,0,.35)}
.lwv-btn.primary:hover{background:#fff;transform:translateY(-1px)}
.lwv-btn.primary:disabled{opacity:.6;cursor:not-allowed;transform:none}
.lwv-btn.ghost{border-color:var(--line);background:#0e1623;color:#93a3b8;padding:0 10px}
.lwv-btn.ghost:hover{border-color:var(--line-2);color:#f1f5f9;background:#152031}
.lwv-spinner{width:11px;height:11px;border-radius:50%;border:1.5px solid rgba(11,15,25,.25);border-top-color:#0b0f19;display:none;animation:lwvSpin .7s linear infinite}
.lwv-btn.is-running .lwv-spinner{display:block}

/* meta strip ------------------------------------------------------------- */
.lwv-meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;padding:10px 14px;border-bottom:1px solid var(--line);background:rgba(9,14,23,.35)}
.lwv-meta div{border:1px solid rgba(255,255,255,.055);background:rgba(255,255,255,.018);border-radius:9px;padding:7px 9px;min-width:0}
.lwv-meta span{display:block;font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:#63748c;margin-bottom:2px}
.lwv-meta strong{display:flex;align-items:center;gap:5px;font-size:11px;font-weight:550;color:#e6eef7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lwv-meta strong i.dot{width:5px;height:5px;border-radius:50%;background:var(--green);box-shadow:0 0 6px rgba(16,185,129,.7);flex:none}
.lwv-meta code{font-family:var(--mono);font-size:8.5px;color:#8ba0b8;overflow:hidden;text-overflow:ellipsis}
#wf-connection{display:inline-flex;align-items:center;gap:5px}
#wf-connection i{width:5px;height:5px;border-radius:50%;background:#f59e0b;box-shadow:0 0 6px rgba(245,158,11,.7);animation:lwvPulseAmber 2s infinite}
#wf-connection[data-state="live"] i{background:var(--green);box-shadow:0 0 6px rgba(16,185,129,.7);animation-name:lwvPulse}
#wf-connection[data-state="demo"] i{background:#94a3b8;box-shadow:none;animation:none}

/* canvas toolbar --------------------------------------------------------- */
.lwv-canvasbar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--line);background:rgba(13,20,32,.55);flex-wrap:wrap}
.lwv-canvasbar .lwv-graph-title{display:flex;align-items:center;gap:7px;min-width:0}
.lwv-glyph{width:24px;height:24px;border-radius:6px;border:1px solid var(--line);background:rgba(255,255,255,.04);display:grid;place-items:center;color:#a9b8cc;flex:none}
.lwv-glyph svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.lwv-canvasbar strong{font-size:10.5px;font-weight:550;color:#e8eef6;letter-spacing:-.01em}
.lwv-canvasbar small{display:block;font-size:8px;color:#64748b}
.lwv-runbadge{margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:8px;color:#8ea0b7;border:1px solid var(--line);background:rgba(255,255,255,.02);border-radius:6px;padding:4px 7px;white-space:nowrap}
.lwv-runbadge i{width:4px;height:4px;border-radius:50%;background:var(--green);box-shadow:0 0 6px rgba(16,185,129,.7)}
.lwv-zoom{display:flex;align-items:center;gap:1px;padding:2px;border:1px solid var(--line);border-radius:8px;background:#0b1220}
.lwv-zoom button{width:24px;height:23px;border-radius:5px;display:grid;place-items:center;color:#8494aa;font-size:13px;line-height:1;transition:.14s}
.lwv-zoom button:hover{background:#1a2537;color:#fff}
.lwv-zoom .readout{min-width:42px;height:17px;line-height:17px;text-align:center;border-left:1px solid var(--line);border-right:1px solid var(--line);font-family:var(--mono);font-size:8.5px;color:#a9b8cc;padding:0 3px}
.lwv-zoom .readout:hover{color:#fff}
.lwv-iconbtn{width:29px;height:29px;border-radius:7px;border:1px solid var(--line);background:#0d1522;display:grid;place-items:center;color:#8494aa;transition:.14s}
.lwv-iconbtn:hover{color:#fff;border-color:var(--line-2)}
.lwv-iconbtn svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}

/* canvas ---------------------------------------------------------------- */
.wf-canvas{
  position:relative;height:clamp(440px,56vh,600px);min-height:420px;overflow:hidden;cursor:grab;
  touch-action:none;user-select:none;background-color:#0a0e17;
  background-image:radial-gradient(rgba(255,255,255,.09) .7px,transparent .85px),radial-gradient(ellipse 80% 70% at 50% 40%,rgba(30,41,59,.32),transparent 78%),linear-gradient(180deg,#0b1019,#090d15);
  background-size:20px 20px,100% 100%,100% 100%;
}
.wf-canvas.is-dragging{cursor:grabbing}
.wf-canvas::after{content:"";position:absolute;inset:0;pointer-events:none;box-shadow:inset 0 12px 28px -18px rgba(0,0,0,.9),inset 0 -14px 30px -22px rgba(0,0,0,.9);z-index:3}
.wf-world{position:absolute;top:0;left:0;transform-origin:0 0;will-change:transform;width:2640px;height:1000px}
#wf-layers{position:absolute;inset:0;z-index:1}
#wf-edges{position:absolute;top:0;left:0;overflow:visible;z-index:2;pointer-events:none}
#wf-nodes{position:absolute;inset:0;z-index:4}
.wf-layer{position:absolute;border:1px dashed rgba(255,255,255,.075);border-radius:16px;background:linear-gradient(165deg,rgba(255,255,255,.02),rgba(255,255,255,.004) 70%)}
.wf-layer-label{position:absolute;top:-9px;left:14px;height:18px;display:flex;align-items:center;gap:6px;padding:2px 7px;border-radius:5px;background:#0d1420;border:1px solid rgba(255,255,255,.075)}
.wf-layer-num{font-family:var(--mono);font-size:7px;color:#7d8fa7}
.wf-layer-label strong{font-size:8px;font-weight:550;letter-spacing:.09em;text-transform:uppercase;color:#9aabc0;white-space:nowrap}
.wf-layer-label em{font-style:normal;font-family:var(--mono);font-size:6.5px;color:#566880;border-left:1px solid rgba(255,255,255,.1);padding-left:6px;white-space:nowrap}

/* nodes ----------------------------------------------------------------- */
.wf-node{
  position:absolute;display:flex;flex-direction:column;padding:8px 10px 7px;border-radius:10px;
  background:linear-gradient(172deg,#151e2d,#111927 58%,#0f1622);
  border:1px solid rgba(255,255,255,.115);cursor:pointer;overflow:hidden;
  box-shadow:0 6px 16px -8px rgba(0,0,0,.7),inset 0 1px 0 rgba(255,255,255,.04);
  transition:border-color .18s,box-shadow .18s,transform .18s,opacity .2s;
}
.wf-node:hover{border-color:rgba(255,255,255,.26);transform:translateY(-1px);z-index:2}
.wf-node.is-selected{border-color:rgba(56,189,248,.8)!important;box-shadow:0 0 0 2px rgba(56,189,248,.18)!important}
.wf-node:focus-visible{outline:2px solid rgba(56,189,248,.65);outline-offset:2px}
.wf-node-head{display:flex;align-items:center;gap:5px;margin-bottom:4px}
.wf-node-icon{width:19px;height:19px;border-radius:5px;display:grid;place-items:center;flex:none;border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.045);color:#a3b3c8;font-family:var(--mono);font-size:6.5px;font-weight:600}
.wf-kind{font-family:var(--mono);font-size:6.3px;letter-spacing:.085em;text-transform:uppercase;color:#63748c;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wf-node-flag{margin-left:auto;width:12px;height:12px;border-radius:50%;display:grid;place-items:center;flex:none;border:1px solid rgba(255,255,255,.13);background:rgba(255,255,255,.025);color:#8ea0b6;position:relative;transition:.2s}
.wf-node-flag svg{width:7px;height:7px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.wf-node-title{font-size:13px;font-weight:550;letter-spacing:-.018em;line-height:1.24;color:#eef3f9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wf-node-sub{font-size:8px;color:#7385a0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
.wf-node-metric{margin-top:auto;padding-top:4px;border-top:1px solid rgba(255,255,255,.06);display:flex;align-items:center;gap:4px;font-family:var(--mono);font-size:6.9px;color:#8597ae;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-.015em}
.wf-node-metric i{width:3px;height:3px;border-radius:50%;background:#64748b;flex:none}
.wf-node-sweep{display:none;position:absolute;top:0;bottom:0;width:44%;left:-60%;pointer-events:none;background:linear-gradient(90deg,transparent,rgba(56,189,248,.1),transparent);animation:lwvSweep 1.8s ease-in-out infinite}
.wf-node[data-status="success"]{border-color:rgba(16,185,129,.52);box-shadow:0 0 0 1px rgba(16,185,129,.07),0 7px 18px -12px rgba(16,185,129,.5)}
.wf-node[data-status="success"] .wf-node-flag{background:rgba(16,185,129,.16);border-color:rgba(16,185,129,.45);color:#34d399}
.wf-node[data-status="success"] .wf-node-metric i{background:#10b981;box-shadow:0 0 5px rgba(16,185,129,.75)}
.wf-node[data-status="success"] .wf-node-metric{color:#8fb3a9}
.wf-node[data-status="processing"]{border-color:rgba(56,189,248,.8);animation:lwvNodeGlow 1.8s ease-in-out infinite}
.wf-node[data-status="processing"] .wf-node-sweep{display:block}
.wf-node[data-status="processing"] .wf-node-flag{border-color:rgba(56,189,248,.45);background:rgba(56,189,248,.12);color:#38bdf8}
.wf-node[data-status="processing"] .wf-node-flag svg{animation:lwvSpin .65s linear infinite}
.wf-node[data-status="processing"] .wf-node-metric{color:#8cc6e3}
.wf-node[data-status="processing"] .wf-node-metric i{background:#38bdf8;box-shadow:0 0 6px #38bdf8}
.wf-node[data-status="failed"]{border-color:rgba(239,68,68,.75);box-shadow:0 0 16px rgba(239,68,68,.14)}
.wf-node[data-status="failed"] .wf-node-flag{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.4);color:#f87171}
.wf-node[data-status="failed"] .wf-node-metric{color:#f0a4a4}

/* decision diamonds + action chips --------------------------------------- */
.wf-gate{background:transparent;border:0;box-shadow:none;padding:0;overflow:visible;display:grid;place-items:center}
.wf-gate:hover{transform:none;border:0}
.wf-gate .wf-gate-shape{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.wf-gate .wf-gate-shape polygon:first-child{fill:#18212f;stroke:rgba(255,255,255,.16);stroke-width:1.2;transition:.2s}
.wf-gate .wf-gate-shape .wf-gate-inner{fill:none;stroke:rgba(255,255,255,.055);stroke-width:1}
.wf-gate:hover .wf-gate-shape polygon:first-child{stroke:rgba(255,255,255,.32);fill:#1b2536}
.wf-gate-content{position:relative;z-index:1;width:70%;text-align:center;display:flex;flex-direction:column;align-items:center;gap:1px;pointer-events:none}
.wf-gate-content .wf-kind{font-size:5.8px;letter-spacing:.12em;color:#6d8098}
.wf-gate-content strong{font-size:8.4px;font-weight:550;line-height:1.22;color:#edf3fa;letter-spacing:-.01em}
.wf-gate-content small{font-size:6px;color:#6f819a;line-height:1.3}
.wf-gate-metric{font-family:var(--mono);font-size:5.6px;color:#8597ae;border-top:1px solid rgba(255,255,255,.08);padding-top:3px;margin-top:2px;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wf-gate .wf-node-flag{position:absolute;top:15%;right:11%;z-index:2;background:#101827}
.wf-gate[data-status="success"] .wf-gate-shape polygon:first-child{stroke:rgba(16,185,129,.62);fill:#12211f}
.wf-gate[data-status="success"] .wf-node-flag{background:rgba(16,185,129,.2);border-color:rgba(16,185,129,.45);color:#34d399}
.wf-gate[data-status="processing"] .wf-gate-shape polygon:first-child{stroke:rgba(56,189,248,.8);fill:#12202c}
.wf-gate[data-status="processing"] .wf-node-flag svg{animation:lwvSpin .65s linear infinite}
.wf-gate[data-status="failed"] .wf-gate-shape polygon:first-child{stroke:rgba(239,68,68,.7);fill:#211416}
.wf-action{display:flex;align-items:center;gap:7px;padding:7px 9px;border-style:dashed;border-color:rgba(148,163,184,.28);background:linear-gradient(170deg,#131b29,#0e1521)}
.wf-action .wf-action-icon{width:19px;height:19px;border-radius:5px;display:grid;place-items:center;flex:none;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.03);color:#8092aa}
.wf-action .wf-action-icon svg{width:10px;height:10px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.wf-action-body{min-width:0}
.wf-action strong{display:block;font-size:8.6px;font-weight:550;color:#dfe8f2;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wf-action span{display:block;font-size:6.4px;color:#6b7d96;margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wf-action-metric{display:block;font-style:normal;font-family:var(--mono);font-size:5.8px;color:#7d8ea6;margin-top:3px;padding-top:3px;border-top:1px solid rgba(255,255,255,.07);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wf-action[data-status="success"] .wf-action-metric{color:#86d9c0}
.wf-action[data-status="processing"] .wf-action-metric{color:#8cc6e3}
.wf-action[data-status="success"]{border-style:solid;border-color:rgba(16,185,129,.45);background:#0f1f1e}
.wf-action[data-status="success"] .wf-action-icon{color:#34d399;border-color:rgba(16,185,129,.3)}

/* edges ----------------------------------------------------------------- */
.wf-edge .wf-line{fill:none;stroke:rgba(148,163,184,.28);stroke-width:1.35;stroke-dasharray:4 5;stroke-linecap:round;transition:stroke .2s}
.wf-edge .wf-flow{fill:none;stroke:transparent;stroke-width:2.8;stroke-linecap:round}
.wf-edge .wf-pulse{fill:#7dd3fc;opacity:0;filter:drop-shadow(0 0 3px rgba(56,189,248,.95))}
.wf-edge .wf-edge-end{fill:rgba(148,163,184,.45)}
.wf-edge.is-dashed .wf-line{stroke-dasharray:3 5;stroke:rgba(148,163,184,.22)}
.wf-edge[data-state="active"] .wf-line{stroke:rgba(56,189,248,.38);stroke-dasharray:none;stroke-width:1.55}
.wf-edge[data-state="active"] .wf-flow{stroke:rgba(56,189,248,.95);stroke-dasharray:5 22;animation:lwvFlow .62s linear infinite}
.wf-edge[data-state="active"] .wf-pulse{opacity:1}
.wf-edge[data-state="active"] .wf-edge-end{fill:#7dd3fc}
.wf-edge[data-state="success"] .wf-line{stroke:rgba(16,185,129,.62);stroke-dasharray:none;stroke-width:1.75}
.wf-edge[data-state="success"] .wf-edge-end{fill:rgba(52,211,153,.8)}
.wf-edge[data-state="failed"] .wf-line{stroke:rgba(239,68,68,.78);stroke-width:1.85;stroke-dasharray:6 4}
.wf-edge.is-dashed[data-state="success"] .wf-line{stroke-dasharray:3 5;stroke:rgba(16,185,129,.55)}
.wf-edge.is-dashed[data-state="active"] .wf-line{stroke-dasharray:3 5;stroke:rgba(56,189,248,.4)}
.wf-branch-chip rect{fill:#0b1220;stroke:rgba(148,163,184,.24)}
.wf-branch-chip text{fill:#93a4bb;font-family:var(--mono);font-size:9px;letter-spacing:.05em;font-weight:500}

/* overlays --------------------------------------------------------------- */
.wf-canvas-hint{position:absolute;bottom:45px;left:11px;z-index:6;display:flex;align-items:center;gap:7px;background:rgba(9,14,23,.8);border:1px solid var(--line);border-radius:6px;padding:4px 8px;font-size:8.5px;color:#7c8da5;pointer-events:none;backdrop-filter:blur(10px)}
.wf-canvas-hint b{color:#a8b7cb;font-weight:500}
.wf-canvas-hint i{width:1px;height:9px;background:rgba(255,255,255,.12);display:inline-block}
.wf-legend{position:absolute;left:11px;bottom:10px;z-index:6;display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:rgba(9,14,23,.82);border:1px solid var(--line);border-radius:7px;padding:6px 9px;backdrop-filter:blur(10px)}
.wf-legend span{display:inline-flex;align-items:center;gap:5px;font-size:7.5px;color:#7f90a7;white-space:nowrap}
.wf-legend i{display:inline-block;width:14px;height:0;border-top:1.5px dashed rgba(148,163,184,.6)}
.wf-legend i.active{border-top:2px solid var(--cyan);box-shadow:0 0 5px rgba(56,189,248,.5)}
.wf-legend i.success{border-top:2px solid var(--green)}
.wf-legend i.failed{border-top:2px solid var(--red);border-top-style:dashed}
.wf-legend i.loop{border-top:1.5px dotted rgba(148,163,184,.75)}
.wf-minimap-wrap{position:absolute;right:11px;bottom:10px;z-index:6;width:174px;padding:6px;border-radius:9px;border:1px solid var(--line);background:rgba(8,13,21,.9);backdrop-filter:blur(12px);box-shadow:0 8px 22px rgba(0,0,0,.45)}
.wf-minimap-wrap .wm-head{display:flex;justify-content:space-between;padding:0 2px 4px;font-size:7px;letter-spacing:.07em;text-transform:uppercase;color:#5f7087;font-family:var(--mono)}
#wf-minimap{width:100%;height:60px;display:block;background:rgba(255,255,255,.017);border-radius:4px;cursor:crosshair;overflow:hidden}
.wf-mini-node{fill:#31415a}
.wf-mini-node.done{fill:#256b58}
.wf-mini-vp{fill:rgba(56,189,248,.08);stroke:rgba(56,189,248,.7);stroke-width:2}

/* node inspector --------------------------------------------------------- */
.wf-inspector{position:fixed;inset:0;z-index:90;pointer-events:none;visibility:hidden}
.wf-inspector.is-open{visibility:visible;pointer-events:auto}
.wf-inspector-scrim{position:absolute;inset:0;background:rgba(4,7,13,.5);backdrop-filter:blur(2px);opacity:0;transition:opacity .25s}
.wf-inspector.is-open .wf-inspector-scrim{opacity:1}
.wf-inspector-panel{
  position:absolute;top:0;right:0;bottom:0;width:352px;max-width:94vw;display:flex;flex-direction:column;
  background:linear-gradient(180deg,#0f1724,#0a101a);border-left:1px solid var(--line-2);
  box-shadow:-24px 0 60px rgba(0,0,0,.55);transform:translateX(103%);transition:transform .3s cubic-bezier(.32,.72,0,1);
}
.wf-inspector.is-open .wf-inspector-panel{transform:translateX(0)}
.wf-inspector-panel > header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;border-bottom:1px solid var(--line);flex:none}
.wf-insp-eyebrow{font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:#74849b;font-weight:600}
.wf-insp-close{width:24px;height:24px;border-radius:6px;border:1px solid var(--line);background:rgba(255,255,255,.03);display:grid;place-items:center;color:#8495ab;transition:.15s}
.wf-insp-close:hover{color:#fff;background:rgba(255,255,255,.07)}
.wf-insp-close svg{width:11px;height:11px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round}
.wf-insp-body{flex:1;overflow-y:auto;padding:14px}
.wf-insp-hero h3{margin:0;font-size:14px;font-weight:600;letter-spacing:-.02em;color:#f4f8fc;line-height:1.3}
.wf-insp-hero p{margin:4px 0 8px;font-size:9.5px;color:#7f90a7;line-height:1.5}
.wf-insp-badges{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:14px}
.wf-pill{display:inline-flex;align-items:center;gap:4px;height:19px;padding:0 7px;border-radius:4px;font-family:var(--mono);font-size:7.5px;color:#95a6bc;border:1px solid var(--line);background:rgba(255,255,255,.03)}
.wf-pill-success{color:#6ee7b7;border-color:rgba(16,185,129,.26);background:rgba(16,185,129,.09)}
.wf-pill-processing{color:#7dd3fc;border-color:rgba(56,189,248,.26);background:rgba(56,189,248,.09)}
.wf-pill-failed{color:#fca5a5;border-color:rgba(239,68,68,.26);background:rgba(239,68,68,.09)}
.wf-insp-body section{margin-bottom:14px}
.wf-insp-body h4{margin:0 0 6px;font-size:8px;letter-spacing:.11em;text-transform:uppercase;color:#65768d;font-weight:600;display:flex;align-items:center;gap:6px}
.wf-insp-body h4 em{font-style:normal;font-family:var(--mono);font-size:7px;letter-spacing:0;color:#4f6076;text-transform:none;margin-left:auto}
.wf-insp-metric{display:flex;align-items:center;gap:7px;border:1px solid rgba(16,185,129,.2);background:rgba(16,185,129,.05);border-radius:8px;padding:8px 10px;font-family:var(--mono);font-size:9px;color:#8bd9c3}
.wf-insp-metric i{width:5px;height:5px;border-radius:50%;background:#10b981;box-shadow:0 0 6px rgba(16,185,129,.7);flex:none}
.wf-insp-list{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.wf-insp-list li{display:flex;align-items:center;gap:7px;padding:6px 8px;font-size:9px;color:#93a4ba;border-bottom:1px solid rgba(255,255,255,.045);line-height:1.4}
.wf-insp-list li:last-child{border-bottom:0}
.wf-insp-list .dir{font-family:var(--mono);font-size:6px;letter-spacing:.06em;padding:2px 4px;border-radius:3px;border:1px solid;flex:none}
.wf-insp-list .dir.in{color:#7dd3fc;border-color:rgba(56,189,248,.24);background:rgba(56,189,248,.07)}
.wf-insp-list .dir.out{color:#c4b5fd;border-color:rgba(167,139,250,.22);background:rgba(167,139,250,.07)}
.wf-insp-empty{margin:0;font-size:8.5px;color:#5f7087;font-style:italic;padding:7px 9px;border:1px dashed var(--line);border-radius:8px}
.wf-json{margin:0;background:#070c14;border:1px solid var(--line);border-radius:8px;padding:9px 10px;font-family:var(--mono);font-size:8.5px;line-height:1.75;color:#8fa3bb;overflow:auto;max-height:220px;white-space:pre-wrap;word-break:break-word}
.wf-json .jk{color:#7dd3fc}
.wf-json .js{color:#86efac}
.wf-json .jn{color:#fcd34d}
.wf-json .jb{color:#f0abfc}
.wf-inspector-panel > footer{flex:none;display:flex;gap:7px;padding:10px 14px;border-top:1px solid var(--line);background:rgba(8,13,21,.55)}
.wf-insp-btn{flex:1;height:29px;border-radius:7px;background:#f1f5f9;color:#0b0f19;font-size:9.5px;font-weight:600;display:flex;align-items:center;justify-content:center;transition:.15s}
.wf-insp-btn:hover{background:#fff}
.wf-insp-btn.ghost{background:#141d2b;border:1px solid var(--line-2);color:#c6d3e2;font-weight:500}
.wf-insp-btn.ghost:hover{background:#1c283a;color:#fff}

/* event stream ----------------------------------------------------------- */
.lwv-stream{border-top:1px solid var(--line);background:#090e17}
.lwv-stream-head{height:36px;display:flex;align-items:center;gap:9px;padding:0 12px;border-bottom:1px solid rgba(255,255,255,.055);background:rgba(13,19,30,.95)}
.lwv-stream-head .term{width:20px;height:20px;border-radius:5px;border:1px solid var(--line);background:rgba(255,255,255,.04);display:grid;place-items:center;color:#91a2b8;flex:none}
.lwv-stream-head .term svg{width:11px;height:11px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.lwv-stream-head strong{font-size:9.5px;font-weight:550;color:#d4dfea;white-space:nowrap}
.lwv-sse{display:inline-flex;align-items:center;gap:4px;font-family:var(--mono);font-size:6.5px;font-weight:600;letter-spacing:.08em;color:#6ee7b7;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.22);padding:2px 5px;border-radius:4px;flex:none}
.lwv-sse i{width:3.5px;height:3.5px;border-radius:50%;background:#34d399;box-shadow:0 0 5px #10b981;animation:lwvPulse 2s infinite}
.lwv-endpoint{font-family:var(--mono);font-size:7.5px;color:#526176;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lwv-stream-head .actions{margin-left:auto;display:flex;align-items:center;gap:7px;flex:none}
.lwv-stream-head label{display:inline-flex;align-items:center;gap:5px;font-size:8px;color:#7b8ca2;cursor:pointer;white-space:nowrap}
.lwv-switch{position:relative;display:inline-block;width:22px;height:12px;flex:none}
.lwv-switch input{opacity:0;width:0;height:0;position:absolute}
.lwv-switch .track{position:absolute;inset:0;background:#263248;border-radius:99px;transition:.2s}
.lwv-switch .track:after{content:"";position:absolute;left:2px;top:2px;width:8px;height:8px;border-radius:50%;background:#8fa1b7;transition:.2s}
.lwv-switch input:checked + .track{background:rgba(16,185,129,.32)}
.lwv-switch input:checked + .track:after{transform:translateX(10px);background:#6ee7b7}
.lwv-stream-btn{height:22px;padding:0 7px;border-radius:5px;font-size:8px;color:#8495ab;border:1px solid transparent;display:inline-flex;align-items:center;gap:4px}
.lwv-stream-btn:hover{background:rgba(255,255,255,.05);color:#e2e8f0;border-color:var(--line)}
#wf-event-log{height:126px;overflow-y:auto;padding:4px 0 6px;scroll-behavior:smooth}
.wf-stream-row{display:flex;align-items:flex-start;gap:8px;padding:3.5px 12px;font-family:var(--mono);font-size:8px;line-height:1.55;border-left:2px solid transparent}
.wf-stream-row:hover{background:rgba(255,255,255,.025)}
.wf-time{color:#495a70;flex:none;padding-top:1px}
.wf-log-dot{width:4px;height:4px;border-radius:50%;background:#526178;flex:none;margin-top:5px}
.wf-stream-row.ok .wf-log-dot{background:#10b981;box-shadow:0 0 4px rgba(16,185,129,.5)}
.wf-stream-row.warn .wf-log-dot{background:#f59e0b}
.wf-stream-row.err .wf-log-dot{background:#ef4444}
.wf-stream-row.run .wf-log-dot{background:#38bdf8;box-shadow:0 0 5px rgba(56,189,248,.6)}
.wf-tag{flex:none;min-width:96px;max-width:96px;font-size:7.5px;color:#8fa1b9;border:1px solid rgba(255,255,255,.075);background:rgba(255,255,255,.025);border-radius:3px;padding:0 4px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wf-stream-row.run .wf-tag{color:#7dd3fc;border-color:rgba(56,189,248,.18);background:rgba(56,189,248,.06)}
.wf-stream-row.ok .wf-tag{color:#86d9c0;border-color:rgba(16,185,129,.16);background:rgba(16,185,129,.045)}
.wf-stream-row.err .wf-tag{color:#fca5a5;border-color:rgba(239,68,68,.2);background:rgba(239,68,68,.06)}
.wf-msg{color:#8a9bb2;min-width:0;word-break:break-word}
.lwv-foot{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:9px 14px;font-size:8px;color:#5d6d84;border-top:1px solid var(--line);background:rgba(8,13,21,.4)}
.lwv-foot span{display:inline-flex;align-items:center;gap:6px}
.lwv-foot i{width:4px;height:4px;border-radius:50%;background:var(--green);box-shadow:0 0 5px rgba(16,185,129,.65)}
.lwv-foot .mono{font-family:var(--mono)}

/* history --------------------------------------------------------------- */
.lwv-history{border-top:1px solid var(--line);background:#0a101a;padding:10px 14px;display:none}
.lwv-history.is-open{display:block}
.lwv-history table{width:100%;border-collapse:collapse;font-size:9px}
.lwv-history th{text-align:left;font-size:7px;letter-spacing:.09em;text-transform:uppercase;color:#5f7087;padding:4px 6px}
.lwv-history td{padding:5px 6px;border-top:1px solid var(--line);color:#b6c4d5;font-family:var(--mono);font-size:8px}
.lwv-history .wf-empty{text-align:center;color:#63748c;font-family:Inter,sans-serif}

@keyframes lwvFlow{to{stroke-dashoffset:-27}}
@keyframes lwvPulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.45)}70%{box-shadow:0 0 0 6px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
@keyframes lwvPulseAmber{0%{box-shadow:0 0 0 0 rgba(245,158,11,.45)}70%{box-shadow:0 0 0 6px rgba(245,158,11,0)}100%{box-shadow:0 0 0 0 rgba(245,158,11,0)}}
@keyframes lwvSpin{to{transform:rotate(360deg)}}
@keyframes lwvSweep{0%{left:-60%}100%{left:118%}}
@keyframes lwvNodeGlow{0%,100%{box-shadow:0 0 14px rgba(56,189,248,.17),0 0 0 1px rgba(56,189,248,.13)}50%{box-shadow:0 0 24px rgba(56,189,248,.3),0 0 0 1px rgba(56,189,248,.22)}}

@media (max-width:1100px){
  .lwv-meta{grid-template-columns:repeat(2,minmax(0,1fr))}
  .lwv-controls{width:100%;justify-content:flex-start}
  .lwv-controls .lwv-btn.primary{margin-left:auto}
}
@media (max-width:720px){
  .lwv-head{padding:13px}
  .lwv-head h1,.lwv-head h2{font-size:18px}
  .lwv-controls{gap:6px}
  .lwv-btn.primary{width:100%;margin-left:0!important;order:9}
  .lwv-meta{grid-template-columns:repeat(2,minmax(0,1fr));padding:8px 10px}
  .wf-canvas{height:440px;min-height:380px}
  .wf-canvas-hint{display:none}
  .wf-minimap-wrap{display:none}
  .wf-legend{gap:6px;padding:5px 7px}
  .wf-legend span{font-size:7px}
  .lwv-endpoint{display:none}
  .lwv-runbadge{display:none}
  .wf-tag{min-width:80px;max-width:80px}
  #wf-event-log{height:112px}
  .wf-inspector-panel{width:100%;max-width:100%}
  .lwv-history td:nth-child(4),.lwv-history th:nth-child(4){display:none}
}
@media (prefers-reduced-motion:reduce){
  .lwv *,.lwv *::before,.lwv *::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}
}
"""


# --------------------------------------------------------------------------
# Markup — IDs consumed by admin_ui/assets/js/crm-workflow.js
# --------------------------------------------------------------------------
WORKFLOW_MARKUP = r"""
<div class="lwv" id="live-workflow-visualizer">
  <div class="lwv-card">

    <header class="lwv-head">
      <div class="lwv-titleblock">
        <div class="lwv-eyebrow"><span>Phase 4</span><i></i><span>Revenue automation</span></div>
        <h1>Live workflow <span class="lwv-live"><i></i>Live</span></h1>
        <p class="lwv-sub">Four-layer orchestration for <strong>rechargekar.com</strong> — content &amp; SEO, the device farm, the AI decision core and central HQ telemetry, streamed over SSE.</p>
      </div>
      <div class="lwv-controls">
        <div class="lwv-control">
          <span>Execution mode</span>
          <div class="lwv-seg" role="radiogroup" aria-label="Execution mode">
            <label><input type="radio" name="wfMode" value="paper"><span>Paper (simulated)</span></label>
            <label class="lwv-live-opt"><input type="radio" name="wfMode" value="live" checked><span>Live touch (Phone)</span></label>
          </div>
        </div>
        <div class="lwv-control">
          <span>Steps</span>
          <select class="lwv-steps" id="wfSteps" aria-label="Steps per run">
            <option value="1">1 step</option>
            <option value="3" selected>3 steps</option>
            <option value="5">5 steps</option>
            <option value="10">10 steps</option>
          </select>
        </div>
        <button class="lwv-btn primary" type="button" id="wfTriggerRunBtn">
          <span class="lwv-spinner" aria-hidden="true"></span><span data-btn-label>Start pipeline run</span>
        </button>
        <button class="lwv-btn ghost" type="button" id="wfResetBtn">Reset nodes</button>
        <button class="lwv-btn ghost" type="button" id="wfHistoryBtn" title="GET /api/phase4/workflow/history">History</button>
      </div>
    </header>

    <div class="lwv-meta">
      <div><span>Pipeline state</span><strong><i class="dot"></i><em id="wf-run-state" style="font-style:normal">Operational</em></strong></div>
      <div><span>Active run</span><strong><code id="wf-run-id">#1284</code></strong></div>
      <div>
        <span>SSE channel</span>
        <strong id="wf-connection" data-state="demo"><i></i><code id="wf-connection-state" data-conn-label>Live simulation</code></strong>
      </div>
      <div><span>Nodes / layers</span><strong>25 <code>· 4 layers</code></strong></div>
    </div>

    <div class="lwv-canvasbar">
      <div class="lwv-graph-title">
        <span class="lwv-glyph" aria-hidden="true"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="6" height="6" rx="1.4"/><rect x="15" y="15" width="6" height="6" rx="1.4"/><path d="M9 6h5a3 3 0 013 3v6"/><path d="M6 9v3a3 3 0 003 3h6"/></svg></span>
              <div><strong>Pipeline topology</strong><small>25 nodes · 27 connections · drag to pan, scroll to zoom, click for telemetry</small></div>
      </div>
      <span class="lwv-runbadge"><i></i>RUN <span id="wf-run-badge-id">#1284</span></span>
      <div class="lwv-zoom">
        <button type="button" id="wfZoomOut" aria-label="Zoom out">−</button>
        <button type="button" class="readout" id="wfZoomReadout" title="Reset to 100%">100%</button>
        <button type="button" id="wfZoomIn" aria-label="Zoom in">+</button>
      </div>
      <button type="button" class="lwv-iconbtn" id="wfZoomReset" aria-label="Reset zoom to 1:1" title="Reset 1:1">
        <svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
      </button>
      <button type="button" class="lwv-iconbtn" id="wfFitBtn" aria-label="Fit graph to view" title="Fit to view">
        <svg viewBox="0 0 24 24"><path d="M4 9h5V4M20 15h-5v5M15 9V4h5M9 20v-5H4"/></svg>
      </button>
    </div>

    <div class="wf-canvas" id="wf-stage" role="application" aria-label="Workflow graph. Drag to pan and scroll to zoom.">
      <div class="wf-world" id="wf-world">
        <div id="wf-layers"></div>
        <svg id="wf-edges" width="2640" height="1000" viewBox="0 0 2640 1000" aria-hidden="true"></svg>
        <div id="wf-nodes"></div>
      </div>
      <div class="wf-canvas-hint">Drag to pan <i></i> Scroll to zoom <i></i> Click a node for telemetry</div>
      <div class="wf-legend">
        <span><i></i>Idle</span><span><i class="active"></i>Data flow</span><span><i class="success"></i>Success</span>
        <span><i class="failed"></i>Error</span><span><i class="loop"></i>Feedback / skip</span>
      </div>
      <div class="wf-minimap-wrap">
        <div class="wm-head"><span>Minimap</span><span>4L · 25N</span></div>
        <svg id="wf-minimap" viewBox="0 0 2640 1000" aria-label="Workflow minimap"></svg>
      </div>
    </div>

    <section class="lwv-stream" aria-label="Live event stream">
      <div class="lwv-stream-head">
        <span class="term" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m4 17 6-6-6-6"/><path d="M12 19h8"/></svg></span>
        <strong>Event stream</strong>
        <span class="lwv-sse"><i></i>LIVE</span>
        <span class="lwv-endpoint">GET /api/phase4/live-workflow-stream</span>
        <div class="actions">
          <label for="wfAutoScroll">Auto-scroll</label>
          <span class="lwv-switch"><input type="checkbox" id="wfAutoScroll" checked><span class="track"></span></span>
          <button type="button" class="lwv-stream-btn" id="wfClearLog">Clear</button>
        </div>
      </div>
      <div id="wf-event-log" role="log" aria-live="polite"></div>
    </section>

    <section class="lwv-history" id="wf-history-panel" aria-label="Workflow run history">
      <table>
        <thead><tr><th>Run</th><th>Mode</th><th>Steps</th><th>Started</th></tr></thead>
        <tbody id="wf-history-list"><tr><td colspan="4" class="wf-empty">Press History to fetch GET /api/phase4/workflow/history</td></tr></tbody>
      </table>
    </section>

    <footer class="lwv-foot">
      <span><i></i>Central HQ tunnel active · last event <span class="mono" id="wf-last-event">just now</span></span>
      <span class="mono">phase3.db · SQLite WAL · PHASE4_DRIFT watchdog</span>
    </footer>
  </div>
  <!-- .wf-inspector drawer is injected here by crm-workflow.js -->
</div>
"""


@lru_cache(maxsize=1)
def _workflow_js_source() -> str:
    """Return the controller source when the asset sits next to this view."""
    try:
        return WORKFLOW_JS.read_text(encoding="utf-8")
    except OSError:
        return ""


def _script_tag() -> str:
    """Inline the controller when available, otherwise reference the static mount."""
    inline = os.environ.get("CRM_WORKFLOW_INLINE_JS", "1" if INLINE_JS_DEFAULT else "0") not in {"0", "false", "False"}
    source = _workflow_js_source() if inline else ""
    if source:
        return "<script>\n" + source + "\n</script>"
    return '<script src="' + WORKFLOW_JS_URL + '" defer></script>'


def render_live_workflow_view(*, active: bool = False, wrapped: bool = True) -> str:
    """Return the complete, drop-in Live Workflow Visualizer HTML fragment.

    Includes its own scoped ``<style>`` block and (by default) inlines the
    adjacent ``crm-workflow.js`` controller so the view works with no build step.
    Set ``CRM_WORKFLOW_INLINE_JS=0`` to emit a ``<script src>`` tag instead.
    """
    view_cls = "crm-view active" if active else "crm-view"
    inner = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
        "<style>\n" + WORKFLOW_CSS + "\n</style>\n"
        + WORKFLOW_MARKUP
        + "\n" + _script_tag() + "\n"
    )
    if wrapped:
        return f'<section id="view-workflow-live" class="{view_cls}" data-crm-view-container="workflow-live">\n{inner}\n</section>'
    return inner


def render_workflow_dashboard_page(title: str = "Live Workflow · Phase 4 Operations") -> str:
    """Return a complete standalone HTML document containing the component."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html,body{{margin:0;padding:0;background:#0b0f19;color:#f1f5f9}}
  body{{
    min-height:100vh;
    font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    background-image:radial-gradient(900px 520px at 12% -8%,rgba(56,189,248,.06),transparent 65%),
                     radial-gradient(700px 460px at 96% -10%,rgba(148,163,184,.055),transparent 60%);
    background-attachment:fixed;
  }}
  .lwv-page{{max-width:1660px;margin:0 auto;padding:24px 22px 32px}}
  .lwv-crumb{{display:flex;align-items:center;gap:8px;font-size:11px;color:#7e8da5;margin-bottom:14px;flex-wrap:wrap}}
  .lwv-crumb a{{color:#8b9bb4;text-decoration:none}}
  .lwv-crumb a:hover{{color:#e2e8f0}}
  .lwv-crumb .now{{color:#e2e8f0}}
  .lwv-crumb .chip{{font-family:'JetBrains Mono',monospace;font-size:8px;color:#8ea0b8;border:1px solid rgba(255,255,255,.11);padding:2px 6px;border-radius:5px}}
  @media (max-width:720px){{.lwv-page{{padding:14px 10px 22px}}}}
</style>
</head>
<body>
<div class="lwv-page">
    <nav class="lwv-crumb" aria-label="Breadcrumb">
      <a href="#">Operations</a><span>/</span><a href="#">Automation</a><span>/</span><span class="now">Live workflow</span><span class="chip">v4.3.0</span>
    </nav>
    {render_live_workflow_view(wrapped=False)}
</div>
</body>
</html>
"""


__all__ = [
    "render_live_workflow_view",
    "render_workflow_dashboard_page",
    "WORKFLOW_CSS",
    "WORKFLOW_MARKUP",
    "WORKFLOW_JS_URL",
]
