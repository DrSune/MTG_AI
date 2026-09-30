"""Build a single self-contained replay HTML from one traced game (14g).

Runs ONE seed/pool game with the games.py trace on, then inlines the trace
JSON + the goldens' rules text into ``reports/replays/replay_s<seed>.html``.
The viewer is vanilla HTML+JS with NO build chain and no network deps —
card images load from the local assets dir via a relative path
(computed at build time, overridable with ``--img-base``), so the file
opens over ``file://`` straight from the repo checkout.

Run::

    .venv/bin/python tools/make_replay.py --seed 7 --pool engine
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import get_supply, play_game

DATA = REPO / "MTG_bot" / "data" / "M21.json"
ASSET_DIR = REPO / "MTG_bot" / "assets" / "card_images"
DEFAULT_OUT = REPO / "reports" / "replays"


def card_text_map() -> dict[str, dict[str, str]]:
    """oracle_id -> {name, type_line, text} from the M21 golden dump
    (the raw Scryfall set file keeps the human rules text the compiled
    CardRecord drops)."""
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for card in raw["data"]["cards"]:
        oid = (card.get("identifiers") or {}).get("scryfallOracleId")
        if not oid:
            continue
        out.setdefault(
            oid,
            {
                "name": card.get("name", ""),
                "type_line": card.get("type", ""),
                "text": card.get("text") or card.get("originalText") or "",
            },
        )
    return out


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MTG replay — seed __SEED__ pool __POOL__</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font:13px/1.4 system-ui,sans-serif; background:#14161a; color:#ddd; }
  header { display:flex; gap:18px; align-items:center; padding:6px 12px;
           background:#1e2126; border-bottom:1px solid #333; flex-wrap:wrap; }
  header b { color:#9cf; } header .det { color:#7a7; font-size:11px; }
  #controls { display:flex; gap:8px; align-items:center; padding:6px 12px; background:#191c21; }
  #scrub { flex:1; }
  button { background:#2b303a; color:#ddd; border:1px solid #444; border-radius:4px;
           padding:3px 10px; cursor:pointer; }
  #layout { display:grid; grid-template-columns: 210px 1fr 210px 340px; gap:6px;
            padding:6px; height:calc(100vh - 108px); }
  .sidecol { overflow-y:auto; }
  .panel { background:#1b1e23; border:1px solid #2c2f36; border-radius:6px;
           padding:6px; margin-bottom:6px; }
  .panel h3 { margin:0 0 4px; font-size:11px; color:#8fa; text-transform:uppercase; }
  #center { display:flex; flex-direction:column; gap:6px; overflow-y:auto; }
  .bfrow { min-height:118px; }
  .tiles { display:flex; flex-wrap:wrap; gap:6px; }
  .tile { position:relative; width:76px; cursor:pointer; }
  .tile img { width:76px; height:106px; object-fit:cover; border-radius:5px;
              border:1px solid #555; background:#222; display:block; }
  .tile.tapped img { transform:rotate(90deg); }
  .tile .pt { position:absolute; right:2px; bottom:2px; background:#000c;
              padding:0 4px; border-radius:3px; font-size:11px; color:#fd8; }
  .tile .ct { position:absolute; left:2px; top:2px; background:#070c;
              padding:0 4px; border-radius:3px; font-size:10px; color:#8f8; }
  .tile .nm { font-size:9px; text-align:center; overflow:hidden;
              white-space:nowrap; text-overflow:ellipsis; }
  .missing { width:76px; height:106px; border:1px dashed #666; border-radius:5px;
             display:flex; align-items:center; justify-content:center;
             font-size:9px; color:#777; text-align:center; overflow:hidden; }
  #log { overflow-y:auto; background:#1b1e23; border:1px solid #2c2f36;
         border-radius:6px; padding:6px; }
  .row { padding:2px 4px; border-bottom:1px solid #26292f; cursor:pointer; font-size:12px; }
  .row.sel { background:#2a3345; }
  .row.decision { background:#232b1e; border-left:3px solid #7a4; }
  .row.action { border-left:3px solid #48a; }
  .row.event { color:#999; }
  .vocab { background:#463; color:#efe; border-radius:3px; padding:0 4px;
           font-size:10px; margin-right:4px; }
  .chosen { color:#9f9; font-weight:bold; }
  .alts { color:#888; }
  #stackpanel .st { background:#232536; margin:2px 0; padding:2px 5px;
                    border-radius:4px; cursor:pointer; }
  #popup { position:fixed; inset:0; background:#000a; display:none;
           align-items:center; justify-content:center; z-index:9; }
  #popup .card { background:#1e2126; border:1px solid #555; border-radius:8px;
                 padding:14px; max-width:460px; display:flex; gap:14px; }
  #popup img { width:240px; height:336px; object-fit:cover; border-radius:8px; }
  #popup .txt { max-width:190px; font-size:12px; }
  .hand .tile, .zone .tile { width:56px; }
  .hand .tile img, .zone .tile img { width:56px; height:78px; }
  .hand .tile .nm, .zone .tile .nm { width:56px; }
</style>
</head>
<body>
<header id="top"></header>
<div id="controls">
  <button id="play">&#9654; play</button>
  <button id="prev">&#9664;</button>
  <button id="next">&#9654;</button>
  <input id="scrub" type="range" min="0" max="0" value="0">
  <span id="pos"></span>
</div>
<div id="layout">
  <div class="sidecol" id="left"></div>
  <div id="center"></div>
  <div class="sidecol" id="right"></div>
  <div id="log"></div>
</div>
<div id="popup" onclick="this.style.display='none'"><div class="card" onclick="event.stopPropagation()">
  <div id="pimg"></div><div class="txt"><h2 id="pname" style="margin:0 0 4px"></h2>
  <div id="ptype" style="color:#8fa;margin-bottom:6px"></div>
  <div id="ptext"></div></div></div></div>
<script id="trace-data" type="application/json">__TRACE__</script>
<script>
const DATA = JSON.parse(document.getElementById('trace-data').textContent);
const IMG_BASE = "__IMG_BASE__";
let idx = 0, timer = null;

function imgTag(oid, name, cls) {
  const src = IMG_BASE + '/' + oid + '.jpg';
  return '<img loading="lazy" src="' + src + '" alt="' + name + '" ' +
         'onerror="this.outerHTML=\\'<div class=missing>" + name + '</div>\\'">';
}
function tile(c, cls) {
  let b = '<div class="tile ' + (cls||'') + (c.tapped?' tapped':'') + '" ' +
          'onclick="popup(\\'' + c.oracle_id + '\\',\\'' + c.name.replace(/'/g,'') + '\\')">';
  b += imgTag(c.oracle_id, c.name.replace(/'/g,''));
  if (c.pt) b += '<span class="pt">' + c.pt + '</span>';
  const cs = Object.entries(c.counters||{}).map(([k,v]) => v+' '+k).join(' ');
  if (cs) b += '<span class="ct">' + cs + '</span>';
  b += '<div class="nm">' + c.name + '</div></div>';
  return b;
}
function zoneTiles(cards) {
  return '<div class="tiles">' + (cards.map(c=>tile(c,'hand')).join('') || '<i>empty</i>') + '</div>';
}
function zoneNames(names) {
  if (!names.length) return '<i>empty</i>';
  const counts = {};
  names.forEach(n => counts[n] = (counts[n]||0)+1);
  return Object.entries(counts).map(([n,k]) => n + (k>1 ? ' ×'+k : '')).join(', ');
}
function snap() {
  for (let i = Math.min(idx, DATA.entries.length-1); i >= 0; i--)
    if (DATA.entries[i].snapshot) return DATA.entries[i].snapshot;
  return DATA.final_snapshot;
}
function render() {
  const s = snap();
  const e = DATA.entries[Math.min(idx, DATA.entries.length-1)];
  document.getElementById('top').innerHTML =
    '<b>seed ' + DATA.seed + '</b><span>pool ' + DATA.pool + '</span>' +
    '<span>turn <b>' + s.turn + '</b> phase <b>' + (s.phase||'-') + '</b></span>' +
    s.players.map(p => '<span>P' + p.seat + ' life <b>' + p.life + '</b></span>').join('') +
    '<span class="det">deterministic: ' + DATA.determinism + '</span>';
  // battlefield rows (top = opponent)
  const c = [...s.players].reverse().map(p =>
    '<div class="panel bfrow"><h3>P' + p.seat + ' battlefield (' + p.battlefield.length + ')</h3>' +
    '<div class="tiles">' + (p.battlefield.map(x=>tile(x)).join('') || '<i>empty</i>') + '</div></div>');
  // stack vertical LIFO (top of stack first)
  const st = [...s.stack].reverse().map(f =>
    '<div class="st" onclick="popup(\\'' + (s.players.flatMap(p=>p.battlefield.concat(p.hand))
      .find(x=>x.handle===f.handle)||{}).oracle_id + '\\',\\'' + f.name + '\\')">' + f.name +
    (f.x!=null ? ' <span class=pt>X='+f.x+'</span>':'') +
    (f.targets.length ? ' &rarr; ' + f.targets.join(', ') : '') + '</div>');
  c.push('<div class="panel" id="stackpanel"><h3>stack (top first, LIFO)</h3>' +
         (st.join('') || '<i>empty</i>') + '</div>');
  document.getElementById('center').innerHTML = c.join('');
  // side columns per player: left = P0, right = P1
  const col = p =>
    '<div class="panel hand"><h3>P' + p.seat + ' hand — revealed (' + p.hand.length + ')</h3>' +
      zoneTiles(p.hand) + '</div>' +
    '<div class="panel zone"><h3>P' + p.seat + ' graveyard</h3>' + zoneNames(p.graveyard) + '</div>' +
    '<div class="panel zone"><h3>P' + p.seat + ' exile</h3>' + zoneNames(p.exile) + '</div>' +
    '<div class="panel"><h3>P' + p.seat + ' library</h3>' + p.library + ' cards</div>';
  document.getElementById('left').innerHTML = s.players[0] ? col(s.players[0]) : '';
  document.getElementById('right').innerHTML = s.players[1] ? col(s.players[1]) : '';
  renderLog();
  document.getElementById('scrub').value = idx;
  document.getElementById('pos').textContent = idx + 1 + ' / ' + DATA.entries.length;
}
function renderLog() {
  const log = document.getElementById('log');
  let html = '';
  DATA.entries.forEach((e, i) => {
    if (e.type === 'turn') html += '<div class="row' + (i===idx?' sel':'') + '" data-i="' + i +
      '">— T' + e.turn + ' P' + e.seat + ' ' + (e.phase||'') + '</div>';
    else if (e.type === 'action') html += '<div class="row action' + (i===idx?' sel':'') +
      '" data-i="' + i + '">T' + e.turn + ' P' + e.seat + ' <b>' + e.kind + '</b> ' + e.card +
      (e.target_names && e.target_names.length ? ' &rarr; ' + e.target_names.join(', ') : '') +
      (e.detail ? ' <span class=alts>(' + e.detail + ')</span>' : '') + '</div>';
    else if (e.type === 'decision') {
      const alts = e.candidates.filter(x => x !== e.answer).join(', ');
      html += '<div class="row decision' + (i===idx?' sel':'') + '" data-i="' + i + '">' +
        '<span class="vocab">' + e.what + '</span>' +
        '<span class="chosen">&#9654; ' + e.answer + '</span> ' +
        '<span class="alts">| alt: ' + (alts || 'none') + '</span></div>';
    } else if (e.type === 'event') html += '<div class="row event' + (i===idx?' sel':'') +
      '" data-i="' + i + '">' + e.kind + (e.verb ? ' [' + e.verb + ']' : '') +
      ' ' + e.subject + (e.data && e.data !== '()' ? ' ' + e.data : '') + '</div>';
  });
  log.innerHTML = html;
  log.querySelectorAll('.row').forEach(r =>
    r.onclick = () => { idx = +r.dataset.i; render(); });
  const sel = log.querySelector('.sel');
  if (sel) sel.scrollIntoView({block:'nearest'});
}
function popup(oid, name) {
  const info = (DATA.card_text || {})[oid] || {name: name, type_line: '', text: '(token / no golden text)'};
  document.getElementById('pimg').innerHTML = (oid && oid !== 'undefined') ?
    imgTag(oid, info.name) : '<div class=missing>' + name + '</div>';
  document.getElementById('pname').textContent = info.name || name;
  document.getElementById('ptype').textContent = info.type_line || '';
  document.getElementById('ptext').textContent = info.text || '';
  document.getElementById('popup').style.display = 'flex';
}
function go(d) { idx = Math.max(0, Math.min(DATA.entries.length-1, idx + d)); render(); }
document.getElementById('play').onclick = () => {
  if (timer) { clearInterval(timer); timer = null; return; }
  timer = setInterval(() => { if (idx >= DATA.entries.length-1) go(0); else go(1); }, 500);
};
document.getElementById('next').onclick = () => go(1);
document.getElementById('prev').onclick = () => go(-1);
document.getElementById('scrub').max = DATA.entries.length - 1;
document.getElementById('scrub').oninput = ev => { idx = +ev.target.value; render(); };
window.onkeydown = ev => {
  if (ev.key === 'ArrowRight') go(1);
  else if (ev.key === 'ArrowLeft') go(-1);
  else if (ev.key === ' ') { ev.preventDefault(); document.getElementById('play').click(); }
  else if (ev.key === 'Escape') document.getElementById('popup').style.display = 'none';
};
render();
</script>
</body>
</html>
"""


def build_html(trace: dict, img_base: str) -> str:
    payload = dict(trace)
    payload["card_text"] = card_text_map()
    blob = json.dumps(payload, default=str).replace("</", "<\\/")
    return (
        HTML_TEMPLATE.replace("__SEED__", str(trace["seed"]))
        .replace("__POOL__", str(trace["pool"]))
        .replace("__IMG_BASE__", img_base)
        .replace("__TRACE__", blob)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a self-contained replay HTML for one game"
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--pool", default="engine", choices=("all", "engine", "castable")
    )
    parser.add_argument("--deck-pairs-seed", type=int, default=1409)
    parser.add_argument("--turns", type=int, default=60)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--img-base",
        default=None,
        help="relative image base; default = relpath from out-dir to "
        "MTG_bot/assets/card_images",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    supply = get_supply(args.pool)
    trace_path = out_dir / f"game_{args.pool}_s{args.seed}.json"
    play_game(
        args.seed,
        args.pool,
        args.deck_pairs_seed,
        args.turns,
        supply=supply,
        trace_path=trace_path,
    )
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    img_base = args.img_base or os.path.relpath(ASSET_DIR.resolve(), out_dir.resolve())
    html = build_html(trace, img_base)
    out = out_dir / f"replay_s{args.seed}.html"
    out.write_text(html, encoding="utf-8")
    print(
        f"replay: {out}  ({out.stat().st_size // 1024} KB, "
        f"{len(trace['entries'])} entries, "
        f"{sum(1 for e in trace['entries'] if e.get('type') == 'action')} actions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
