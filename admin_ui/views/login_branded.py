"""
admin_ui/views/login_branded.py — Adsterra Fleet branded sign-in page.

Standalone renderer for /crm/login. Zero external requests, zero images,
all graphics are inline SVG or CSS gradients. System fonts only.

Public API
----------
    render_login_branded(profile: dict, error_msg: str = "") -> str

Compatible drop-in replacement for admin_ui.views.login.render_login_view
(which stays on disk, untouched).
"""
from __future__ import annotations

import html
from typing import Any

__all__ = ["render_login_branded"]


def _esc(value: Any) -> str:
    """Escape for HTML text and attribute contexts."""
    return html.escape(str(value or ""), quote=True)


_CSS = r"""
*,*::before,*::after{box-sizing:border-box}

:root{
  --void:#03060D;
  --deep:#050B16;
  --navy:#0A1628;
  --line:#17304C;
  --line-2:#0F2338;

  --accent:#2E5BFF;
  --accent-hi:#5C86FF;
  --cyan:#28E0F0;
  --violet:#7A5CFF;

  --white:#FFFFFF;
  --text:#EAF0FA;
  --muted:#7E93AE;
  --muted-2:#5E7490;

  --danger:#FF6B5E;
  --danger-bg:rgba(255,107,94,.08);
  --danger-br:rgba(255,107,94,.32);

  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}

html,body{height:100%}
body{
  margin:0;
  font-family:var(--font);
  background:var(--void);
  color:var(--text);
  -webkit-font-smoothing:antialiased;
  overflow-x:hidden;
}

.bg{position:fixed;inset:0;z-index:0;overflow:hidden;pointer-events:none}
.bg-base{
  position:absolute;inset:0;
  background:
    radial-gradient(ellipse 120% 80% at 50% -10%, #0B1F3A 0%, transparent 60%),
    radial-gradient(ellipse 80% 60% at 15% 100%, #08182C 0%, transparent 65%),
    linear-gradient(180deg,#050B16 0%,#03060D 55%,#02040A 100%);
}
.bg-floor{
  position:absolute;left:-40%;right:-40%;bottom:-14%;height:78%;
  transform:perspective(700px) rotateX(76deg);
  transform-origin:50% 100%;
  background-image:
    linear-gradient(to right, rgba(46,91,255,.22) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(46,91,255,.22) 1px, transparent 1px);
  background-size:56px 56px;
  -webkit-mask-image:linear-gradient(to top, #000 0%, rgba(0,0,0,.5) 42%, transparent 78%);
          mask-image:linear-gradient(to top, #000 0%, rgba(0,0,0,.5) 42%, transparent 78%);
  opacity:.5;
}
.orb{position:absolute;border-radius:50%;pointer-events:none}
.orb-a{
  width:620px;height:620px;left:-180px;top:-220px;
  background:radial-gradient(circle, rgba(46,91,255,.28) 0%, rgba(46,91,255,.06) 40%, transparent 68%);
  animation:float-a 22s ease-in-out infinite;
}
.orb-b{
  width:520px;height:520px;right:-160px;bottom:-120px;
  background:radial-gradient(circle, rgba(40,224,240,.14) 0%, rgba(40,224,240,.03) 42%, transparent 70%);
  animation:float-b 26s ease-in-out infinite;
}
@keyframes float-a{0%,100%{transform:translate3d(0,0,0)}50%{transform:translate3d(40px,30px,0)}}
@keyframes float-b{0%,100%{transform:translate3d(0,0,0)}50%{transform:translate3d(-36px,-26px,0)}}

.shell{
  position:relative;z-index:1;
  display:grid;
  grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);
  min-height:100vh;min-height:100dvh;
}

.brand{
  position:relative;display:flex;flex-direction:column;
  padding:36px 48px 28px;min-width:0;
}
.brand-top{display:flex;align-items:center;gap:12px;flex:0 0 auto}
.mark{width:31px;height:31px;flex:0 0 31px;display:block;
  filter:drop-shadow(0 0 10px rgba(46,91,255,.55))}
.wordmark{
  font-size:11.5px;font-weight:650;letter-spacing:.20em;
  text-transform:uppercase;color:#fff;
  text-shadow:0 0 18px rgba(92,134,255,.4);
}
.wordmark-sep{width:1px;height:14px;background:var(--line);margin:0 2px}
.wordmark-sub{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted-2)}

.brand-body{
  flex:1 1 auto;display:flex;flex-direction:column;justify-content:center;
  padding:20px 0 8px;min-width:0;
}

.eyebrow{
  margin:0 0 14px;display:inline-flex;align-items:center;gap:9px;
  font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;
  color:#8FA6C4;
}
.eyebrow .dot{
  width:5px;height:5px;border-radius:50%;background:var(--cyan);
  box-shadow:0 0 0 3px rgba(40,224,240,.14), 0 0 14px rgba(40,224,240,.9);
}

h1{
  margin:0;max-width:520px;
  font-size:clamp(29px,3.1vw,44px);
  font-weight:600;line-height:1.05;letter-spacing:-.028em;
  color:#fff;text-shadow:0 0 42px rgba(46,91,255,.26);
}
h1 em{font-style:normal;color:#56708F}

.lede{
  margin:14px 0 0;max-width:46ch;
  font-size:14px;line-height:1.6;color:#8FA3BD;letter-spacing:-.003em;
}

/* ---------- pipeline ---------- */
.pipeline-wrap{
  margin:22px 0 6px;
  max-width:560px;
  flex:0 0 auto;
  perspective:1200px;
}
.pipeline{
  position:relative;
  width:100%;
  height:340px;
  transform-style:preserve-3d;
  transition:transform .35s cubic-bezier(.22,.61,.36,1);
  will-change:transform;
}
.wires{
  position:absolute;inset:0;
  width:100%;height:100%;
  overflow:visible;
  pointer-events:none;
}
.wire-path{fill:none;stroke-width:1.4;stroke-linecap:round}
.wire-base{stroke:rgba(70,110,190,.42)}
.wire-lit{stroke:url(#grad-wire);filter:url(#w-glow)}
.wire-charge{
  fill:none;
  stroke:#EAF8FF;
  stroke-width:2.1;
  stroke-linecap:round;
  stroke-dasharray:16 460;
  filter:url(#w-glow-bright);
}
.charge-l{animation:flow-l 3.4s linear infinite}
.charge-r{animation:flow-r 3.4s linear infinite}
@keyframes flow-l{from{stroke-dashoffset:476}to{stroke-dashoffset:0}}
@keyframes flow-r{from{stroke-dashoffset:0}to{stroke-dashoffset:-476}}

.hub{
  position:absolute;
  left:50%;top:50%;
  width:96px;height:96px;
  margin:-48px 0 0 -48px;
  border-radius:50%;
  background:
    radial-gradient(circle at 38% 32%, #FFFFFF 0%, #B9CEFF 16%, #5C86FF 44%, #2E5BFF 66%, #0B1D42 100%);
  box-shadow:
    0 0 0 6px rgba(46,91,255,.10),
    0 0 34px rgba(92,134,255,.95),
    0 0 90px rgba(46,91,255,.55),
    0 0 160px rgba(40,224,240,.20);
  animation:orb-breathe 6s ease-in-out infinite;
}
@keyframes orb-breathe{
  0%,100%{box-shadow:0 0 0 6px rgba(46,91,255,.10),0 0 34px rgba(92,134,255,.95),0 0 90px rgba(46,91,255,.55),0 0 160px rgba(40,224,240,.20)}
  50%    {box-shadow:0 0 0 10px rgba(46,91,255,.14),0 0 46px rgba(92,134,255,1),0 0 120px rgba(46,91,255,.7),0 0 200px rgba(40,224,240,.28)}
}

.hub-ring{position:absolute;left:50%;top:50%;border-radius:50%;pointer-events:none}
.ring-1{
  width:150px;height:150px;margin:-75px 0 0 -75px;
  border:1px solid rgba(92,134,255,.30);
  animation:ring-pop 6s ease-in-out infinite;
}
.ring-2{
  width:196px;height:196px;margin:-98px 0 0 -98px;
  border:1px dashed rgba(40,224,240,.24);
  animation:spin 26s linear infinite;
}
.ring-3{
  width:248px;height:248px;margin:-124px 0 0 -124px;
  border:1px solid rgba(46,91,255,.14);
}
@keyframes ring-pop{0%,100%{transform:scale(.96);opacity:.4}50%{transform:scale(1.05);opacity:.9}}
@keyframes spin{to{transform:rotate(360deg)}}

.spark{
  position:absolute;
  width:3px;height:3px;border-radius:50%;
  background:#CFE4FF;
  box-shadow:0 0 8px rgba(180,215,255,.95);
  animation:twinkle 4.5s ease-in-out infinite;
}
@keyframes twinkle{0%,100%{opacity:.15}50%{opacity:.95}}

.node-card{
  position:absolute;
  display:flex;align-items:center;gap:9px;
  width:158px;
  padding:9px 11px;
  border-radius:11px;
  border:1px solid rgba(60,102,180,.55);
  background:linear-gradient(150deg, rgba(17,36,68,.92) 0%, rgba(8,17,32,.86) 100%);
  box-shadow:
    0 1px 0 rgba(255,255,255,.05) inset,
    0 10px 28px -16px rgba(0,0,0,1),
    0 0 20px -8px rgba(46,91,255,.5);
  backdrop-filter:blur(8px);
  -webkit-backdrop-filter:blur(8px);
  transform:translateY(-50%);
  transition:border-color .25s ease, box-shadow .25s ease;
}
.node-card:hover{
  border-color:rgba(92,140,240,.95);
  box-shadow:
    0 1px 0 rgba(255,255,255,.07) inset,
    0 0 30px -4px rgba(46,91,255,.8);
}
.node-card .ico{
  flex:0 0 26px;width:26px;height:26px;
  display:grid;place-items:center;
  border-radius:7px;
  border:1px solid rgba(92,134,255,.42);
  background:rgba(46,91,255,.13);
  box-shadow:0 0 14px -4px rgba(46,91,255,.9);
}
.node-card .ico svg{width:13px;height:13px;stroke:#9FBEFF;fill:none;
  stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.node-card .lbl{
  font-size:11px;font-weight:550;letter-spacing:.005em;
  color:#D6E3F5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.node-card .lbl small{
  display:block;font-size:9.5px;font-weight:400;letter-spacing:.01em;
  color:#6F86A3;margin-top:1px;
}

.nl1{left:0;top:13.5%}
.nl2{left:0;top:35.3%}
.nl3{left:0;top:64.7%}
.nl4{left:0;top:86.5%}
.nr1{right:0;top:13.5%}
.nr2{right:0;top:35.3%}
.nr3{right:0;top:64.7%}
.nr4{right:0;top:86.5%}

.brand-foot{
  margin:14px 0 0;padding-top:13px;
  border-top:1px solid var(--line-2);
  display:flex;gap:20px;flex-wrap:wrap;align-items:center;
  font-size:10px;letter-spacing:.10em;text-transform:uppercase;color:#5E7490;
  flex:0 0 auto;
}
.brand-foot span{white-space:nowrap}

/* ---------- sign-in ---------- */
.panel{
  position:relative;
  display:flex;align-items:center;justify-content:center;
  padding:44px;min-width:0;
}
.panel::before{
  content:"";position:absolute;left:0;top:8%;bottom:8%;width:1px;
  background:linear-gradient(to bottom, transparent, rgba(46,91,255,.42) 30%, rgba(40,224,240,.3) 70%, transparent);
  box-shadow:0 0 18px rgba(46,91,255,.45);
}

.card{
  position:relative;
  width:100%;max-width:378px;
  padding:34px 32px 30px;
  border-radius:18px;
  border:1px solid rgba(56,102,180,.55);
  background:linear-gradient(165deg, rgba(15,33,60,.92) 0%, rgba(6,13,25,.94) 100%);
  box-shadow:
    0 0 0 1px rgba(46,91,255,.10),
    0 0 60px -12px rgba(46,91,255,.40),
    0 30px 80px -30px rgba(0,0,0,1),
    inset 0 1px 0 rgba(255,255,255,.06);
  backdrop-filter:blur(14px) saturate(120%);
  -webkit-backdrop-filter:blur(14px) saturate(120%);
}
.card::before{
  content:"";position:absolute;left:24px;right:24px;top:-1px;height:1px;
  background:linear-gradient(90deg, transparent, rgba(92,134,255,.9), var(--cyan), rgba(92,134,255,.9), transparent);
  box-shadow:0 0 16px rgba(92,134,255,.75);
  border-radius:2px;
}

.card h2{
  margin:0;font-size:22px;font-weight:600;letter-spacing:-.018em;color:#fff;
  text-shadow:0 0 24px rgba(92,134,255,.32);
}
.card-sub{margin:6px 0 26px;font-size:13px;color:var(--muted);letter-spacing:-.003em}

.field{margin-bottom:16px}
.field label{
  display:block;margin-bottom:7px;
  font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
  color:#8CA2BE;
}
.input-wrap{position:relative;display:block}

.input{
  width:100%;height:44px;padding:0 13px;
  font-family:inherit;font-size:14px;color:var(--text);
  background:rgba(4,10,20,.86);
  border:1px solid rgba(40,78,132,.9);
  border-radius:7px;outline:none;
  transition:border-color .16s ease, box-shadow .16s ease, background .16s ease;
  -webkit-appearance:none;appearance:none;
}
.input::placeholder{color:#4E6280}
.input:hover{border-color:rgba(58,104,170,1)}
.input:focus{
  background:rgba(6,14,28,.96);
  border-color:var(--accent-hi);
  box-shadow:0 0 0 3px rgba(46,91,255,.18), 0 0 26px -4px rgba(46,91,255,.6);
}
.input:focus-visible{outline:2px solid var(--cyan);outline-offset:1px}
input[type="password"].input{padding-right:58px}

.reveal{
  position:absolute;right:5px;top:5px;height:34px;padding:0 11px;
  border:0;border-radius:5px;background:transparent;color:var(--muted);
  font-family:inherit;font-size:10.5px;font-weight:600;
  letter-spacing:.08em;text-transform:uppercase;cursor:pointer;
  transition:color .15s ease, background .15s ease;
}
.reveal:hover{color:#CFE0F5;background:rgba(46,91,255,.14)}
.reveal:focus-visible{outline:2px solid var(--cyan);outline-offset:-2px}

.row{display:flex;align-items:center;gap:12px;margin:4px 0 22px}
.remember{
  display:inline-flex;align-items:center;gap:8px;
  font-size:12px;color:var(--muted);cursor:pointer;user-select:none;
}
.remember input{width:14px;height:14px;margin:0;accent-color:var(--accent);cursor:pointer}

.btn{
  width:100%;height:44px;border:0;border-radius:7px;
  background:linear-gradient(180deg, #3D68FF 0%, #2450E8 100%);
  color:#fff;font-family:inherit;font-size:14px;font-weight:600;
  cursor:pointer;
  box-shadow:0 0 0 1px rgba(92,134,255,.5) inset, 0 8px 26px -8px rgba(46,91,255,.9);
  transition:transform .07s ease, box-shadow .2s ease, filter .2s ease;
  -webkit-appearance:none;appearance:none;
}
.btn:hover{filter:brightness(1.1);box-shadow:0 0 0 1px rgba(150,180,255,.7) inset, 0 10px 34px -6px rgba(46,91,255,1)}
.btn:active{transform:translateY(1px)}
.btn:focus-visible{outline:2px solid var(--cyan);outline-offset:2px}
.btn[disabled]{opacity:.5;cursor:not-allowed;filter:none;transform:none}

.alert{
  display:flex;gap:9px;align-items:flex-start;
  margin:0 0 18px;padding:10px 12px;
  border:1px solid var(--danger-br);border-radius:7px;
  background:var(--danger-bg);
  font-size:12px;line-height:1.5;color:var(--danger);
}
.alert svg{flex:0 0 14px;margin-top:1px}

.panel-foot{
  position:absolute;bottom:20px;left:0;right:0;text-align:center;
  font-size:10px;color:#3F5268;letter-spacing:.04em;
}

@media (max-width:1180px){
  .node-card{width:142px;padding:8px 10px}
  .node-card .lbl{font-size:10.5px}
  .node-card .lbl small{font-size:9px}
}

@media (max-width:1080px){
  .shell{grid-template-columns:minmax(0,1fr)}
  .brand{padding:30px 26px 8px}
  .brand-body{padding:16px 0 4px}
  .pipeline{height:320px}
  .pipeline-wrap{max-width:560px;margin-left:auto;margin-right:auto}
  .panel{padding:26px 20px 62px}
  .panel::before{display:none}
  .panel-foot{position:static;margin-top:34px}
}

@media (max-width:640px){
  .brand{padding:22px 16px 6px}
  .panel{padding:18px 14px 50px}
  .card{padding:26px 20px 24px;border-radius:14px}
  .card h2{font-size:19px}
  .pipeline{height:300px}
  .node-card{width:124px;padding:7px 8px;gap:7px}
  .node-card .ico{flex:0 0 22px;width:22px;height:22px}
  .node-card .ico svg{width:11px;height:11px}
  .node-card .lbl{font-size:9.5px}
  .node-card .lbl small{display:none}
  .hub{width:74px;height:74px;margin:-37px 0 0 -37px}
  .ring-1{width:118px;height:118px;margin:-59px 0 0 -59px}
  .ring-2{width:152px;height:152px;margin:-76px 0 0 -76px}
  .ring-3{width:196px;height:196px;margin:-98px 0 0 -98px}
  .brand-foot{gap:12px;font-size:9px}
}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none !important;transition:none !important}
}
"""

_L = {
    "brand": '<rect x="3" y="5.2" width="26" height="5.2" rx="2.6" fill="#1B3352"/>'
             '<rect x="3" y="13" width="26" height="5.2" rx="2.6" fill="#25456B"/>'
             '<rect x="3" y="20.8" width="16" height="5.2" rx="2.6" fill="url(#mk)"/>'
             '<circle cx="25.2" cy="23.4" r="1.7" fill="#28E0F0"/>',
    "wallet": '<rect x="2" y="3.5" width="12" height="9" rx="1.6"/><path d="M2 6.2h12"/>',
    "spark": '<path d="M8 2.2l1.5 3.5 3.5 1.5-3.5 1.5L8 12.2 6.5 8.7 3 7.2l3.5-1.5z"/>',
    "bars": '<path d="M2.6 12.4V8.2M6.4 12.4V5.4M10.2 12.4V9M14 12.4V3.6"/>',
    "lead": '<circle cx="6" cy="5.6" r="2.3"/><path d="M2.4 13c0-2 1.6-3.4 3.6-3.4S9.6 11 9.6 13"/>'
            '<path d="M11 4.2a2.2 2.2 0 0 1 0 4.3M12.4 13c0-1.5-.5-2.6-1.4-3.2"/>',
    "board": '<rect x="2" y="3" width="12" height="10" rx="1.6"/><path d="M5 6.6h6M5 9.4h4"/>',
    "doc": '<path d="M3.4 2.6h6.2l3 3v7.8H3.4z"/><path d="M9.4 2.6v3.2h3.2"/>',
    "search": '<circle cx="7" cy="7" r="4.2"/><path d="M10.2 10.2 13.6 13.6"/>',
    "chart": '<path d="M3 13.4V9.6M6.6 13.4V6.8M10.2 13.4V8.4M13.8 13.4V4.2"/>'
             '<path d="M2 2.6v10.8h12"/>',
}

# (css class, icon key, label, sub-label)
_LEFT = [
    ("nl1", "wallet", "Adsterra", "Banner vault"),
    ("nl2", "spark", "AutoPublish", "Generation"),
    ("nl3", "bars", "Search Console", "Property sync"),
    ("nl4", "lead", "Lead log", "CPL &amp; CPA"),
]
_RIGHT = [
    ("nr1", "board", "Placements", "Live banners"),
    ("nr2", "doc", "Articles", "Published"),
    ("nr3", "search", "Rankings", "Tracked pages"),
    ("nr4", "chart", "Reports", "Weekly digest"),
]

# (y of the card centre, wire path d)  — geometry of the 560x340 viewBox
_WIRES = [
    (46,  "M162 46 C 210 46, 196 170, 234 170"),
    (120, "M162 120 C 210 120, 196 170, 234 170"),
    (220, "M162 220 C 210 220, 196 170, 234 170"),
    (294, "M162 294 C 210 294, 196 170, 234 170"),
]
_WIRES_R = [
    (46,  "M326 170 C 366 170, 350 46, 398 46"),
    (120, "M326 170 C 366 170, 350 120, 398 120"),
    (220, "M326 170 C 366 170, 350 220, 398 220"),
    (294, "M326 170 C 366 170, 350 294, 398 294"),
]
_SPARKS = [
    ("47%", "14%", "0s"),
    ("54%", "26%", "1.1s"),
    ("43%", "78%", "2.2s"),
    ("57%", "72%", ".7s"),
    ("38%", "50%", "3.1s"),
]


def _wires_svg() -> str:
    """Build the pipeline wire layer (8 curves + 8 travelling charges)."""
    parts: list[str] = []
    delays = ["0s", ".55s", "1.1s", "1.65s"]
    for i, (_y, d) in enumerate(_WIRES):
        parts.append(f'<path class="wire-path wire-base" d="{d}"/>')
        parts.append(f'<path class="wire-path wire-lit" stroke="url(#grad-wire)" d="{d}"/>')
        parts.append(
            f'<path class="wire-charge charge-l" style="animation-delay:{delays[i]}" d="{d}"/>'
        )
    rdelays = [".3s", ".85s", "1.4s", "1.95s"]
    for i, (_y, d) in enumerate(_WIRES_R):
        parts.append(f'<path class="wire-path wire-base" d="{d}"/>')
        parts.append(f'<path class="wire-path wire-lit" stroke="url(#grad-wire-rev)" d="{d}"/>')
        parts.append(
            f'<path class="wire-charge charge-r" style="animation-delay:{rdelays[i]}" d="{d}"/>'
        )
    return "".join(parts)


def _cards() -> str:
    """Build the eight integration cards."""
    out: list[str] = []
    for group in (_LEFT, _RIGHT):
        for cls, icon, label, sub in group:
            out.append(
                f'<div class="node-card {cls}">'
                f'<span class="ico"><svg viewBox="0 0 16 16" aria-hidden="true">{_L[icon]}</svg></span>'
                f'<span class="lbl">{label}<small>{sub}</small></span>'
                f"</div>"
            )
    return "".join(out)


def _sparks() -> str:
    return "".join(
        f'<i class="spark" style="left:{x};top:{y};animation-delay:{d}" aria-hidden="true"></i>'
        for x, y, d in _SPARKS
    )


def render_login_branded(
    profile: dict[str, Any] | None = None,
    error_msg: str = "",
    next_url: str = "",
) -> str:
    """Render the branded sign-in page.

    Parameters
    ----------
    profile : operator profile dict (from profile_auth.load_profile()).
              Used only to pre-fill the email field.
    error_msg : non-empty -> the inline alert block is rendered.
    next_url : optional post-login destination; forwarded as a hidden field.
    """
    profile = profile or {}
    has_password = bool(profile.get("has_password"))
    email_value = "" if not has_password else _esc(profile.get("email") or "")
    safe_err = _esc(error_msg)
    safe_next = _esc(next_url)

    alert_html = ""
    if safe_err:
        alert_html = (
            '<div class="alert" role="alert">'
            '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true">'
            '<circle cx="10" cy="10" r="7.4" stroke="#FF6B5E" stroke-width="1.5"/>'
            '<path d="M10 6.2v4.4M10 13.4h.01" stroke="#FF6B5E" stroke-width="1.5" '
            'stroke-linecap="round"/></svg>'
            f"<span>{safe_err}</span></div>"
        )

    next_html = (
        f'<input type="hidden" name="next" value="{safe_next}">' if safe_next else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="color-scheme" content="dark">
<title>Sign in — Adsterra Fleet</title>
<style>{_CSS}</style>
</head>
<body>

<div class="bg" aria-hidden="true">
  <div class="bg-base"></div>
  <div class="bg-floor"></div>
  <div class="orb orb-a"></div>
  <div class="orb orb-b"></div>
</div>

<div class="shell">

  <section class="brand">

    <header class="brand-top">
      <svg class="mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="mk" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#7FA4FF"/>
            <stop offset="1" stop-color="#2E5BFF"/>
          </linearGradient>
        </defs>
        {_L["brand"]}
      </svg>
      <span class="wordmark">Adsterra Fleet</span>
      <span class="wordmark-sep"></span>
      <span class="wordmark-sub">Control Plane</span>
    </header>

    <div class="brand-body">

      <p class="eyebrow"><span class="dot"></span>Publisher operations</p>

      <h1>Every domain.<br><em>One console.</em></h1>

      <p class="lede">
        Content generation, monetization and search performance for the
        entire publisher network — reviewed and released from the same place.
      </p>

      <div class="pipeline-wrap">
        <div class="pipeline" id="pipeline">

          <svg class="wires" viewBox="0 0 560 340" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="grad-wire" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stop-color="#2E5BFF" stop-opacity=".22"/>
                <stop offset=".55" stop-color="#5C86FF" stop-opacity=".70"/>
                <stop offset="1" stop-color="#28E0F0" stop-opacity=".95"/>
              </linearGradient>
              <linearGradient id="grad-wire-rev" x1="1" y1="0" x2="0" y2="0">
                <stop offset="0" stop-color="#2E5BFF" stop-opacity=".22"/>
                <stop offset=".55" stop-color="#5C86FF" stop-opacity=".70"/>
                <stop offset="1" stop-color="#28E0F0" stop-opacity=".95"/>
              </linearGradient>
              <filter id="w-glow" x="-40%" y="-60%" width="180%" height="220%">
                <feGaussianBlur stdDeviation="2.2" result="b"/>
                <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
              <filter id="w-glow-bright" x="-60%" y="-120%" width="220%" height="340%">
                <feGaussianBlur stdDeviation="2.6" result="b"/>
                <feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
            </defs>
            <g stroke-linecap="round">{_wires_svg()}</g>
          </svg>

          <div class="hub-ring ring-3" aria-hidden="true"></div>
          <div class="hub-ring ring-2" aria-hidden="true"></div>
          <div class="hub-ring ring-1" aria-hidden="true"></div>
          <div class="hub" aria-hidden="true"></div>

          {_sparks()}
          {_cards()}

        </div>
      </div>

    </div>

    <footer class="brand-foot">
      <span>Content</span>
      <span>Monetization</span>
      <span>Search</span>
    </footer>

  </section>

  <section class="panel">

    <form class="card" method="post" action="/api/auth/login" autocomplete="on" novalidate>

      <h2>Sign in</h2>
      <p class="card-sub">Operator access only</p>

      {alert_html}

      <div class="field">
        <label for="email">Email address</label>
        <span class="input-wrap">
          <input class="input" id="email" name="email" type="email"
                 required autofocus spellcheck="false"
                 autocomplete="username"
                 placeholder="you@company.com"
                 value="{email_value}">
        </span>
      </div>

      <div class="field">
        <label for="password">Password</label>
        <span class="input-wrap">
          <input class="input" id="password" name="password" type="password"
                 required autocomplete="current-password"
                 placeholder="Enter your password">
          <button class="reveal" type="button" id="reveal"
                  aria-label="Show password" aria-pressed="false">Show</button>
        </span>
      </div>

      <div class="row">
        <label class="remember">
          <input type="checkbox" name="remember" value="1" checked>
          Keep me signed in
        </label>
      </div>

      {next_html}
      <button class="btn" type="submit">Sign in</button>

    </form>

    <p class="panel-foot">Adsterra Fleet · Operator Console</p>

  </section>

</div>

<script>
(function () {{
  "use strict";

  var btn = document.getElementById("reveal");
  var pwd = document.getElementById("password");
  if (btn && pwd) {{
    btn.addEventListener("click", function () {{
      var shown = pwd.type === "text";
      pwd.type = shown ? "password" : "text";
      btn.textContent = shown ? "Show" : "Hide";
      btn.setAttribute("aria-pressed", String(!shown));
      btn.setAttribute("aria-label", shown ? "Show password" : "Hide password");
      pwd.focus({{ preventScroll: true }});
    }});
  }}

  var wrap = document.querySelector(".pipeline-wrap");
  var stage = document.getElementById("pipeline");
  var reduce = window.matchMedia &&
               window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (wrap && stage && !reduce && window.requestAnimationFrame) {{
    var raf = 0, tx = 0, ty = 0;

    function apply() {{
      raf = 0;
      stage.style.transform =
        "rotateY(" + (tx * 7).toFixed(2) + "deg) rotateX(" + (-ty * 6).toFixed(2) + "deg)";
    }}

    wrap.addEventListener("pointermove", function (e) {{
      var r = wrap.getBoundingClientRect();
      tx = (e.clientX - r.left) / r.width - 0.5;
      ty = (e.clientY - r.top) / r.height - 0.5;
      if (!raf) raf = window.requestAnimationFrame(apply);
    }});

    wrap.addEventListener("pointerleave", function () {{
      stage.style.transform = "";
    }});
  }}
}})();
</script>

</body>
</html>"""
