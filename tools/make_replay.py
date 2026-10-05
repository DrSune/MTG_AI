"""Build a single self-contained replay HTML from one traced game (14g).

Runs ONE seed/pool game with the games.py trace on, then inlines the trace
JSON + the goldens' rules text into ``reports/replays/replay_s<seed>.html``.
The viewer is vanilla HTML+JS with NO build chain and no network deps —
card images load from the local assets dir via a relative path
(computed at build time, overridable with ``--img-base``), so the file
opens over ``file://`` straight from the repo checkout.

Response-window-arc journal kinds get dedicated rendering (VIEWER batch,
2026-10-05): WINDOW_OPEN / WINDOW_PASS render as a highlighted response
panel (who was asked, what they held, what they did), COUNTER / KICKBACK
as inline event cards, LIFE_LOST / TARGETING as distinct event rows.
STALL_BREAK renders too (emitter landed 2026-10-05/11, sibling batch):
the viewer matches it BY KIND STRING, so it stays correct across the
commit boundary either way, and unknown kinds keep the old generic
event row, so nothing ever renders blank.
The pre-existing row renderers (turn / action / decision / generic
event) are byte-styled exactly as before; the views are computed at
BUILD time in :func:`enrich_view` and attached as ``entry["view"]``.

Run::

    .venv/bin/python tools/make_replay.py --seed 7 --pool engine
"""

from __future__ import annotations

import argparse
import ast
import html as html_mod
import json
import os
import re
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


# --------------------------------------------------------------------------
# Build-time views for the response-window-arc journal kinds (VIEWER batch).
# The trace's event rows carry ``data`` as the Python str-repr of the
# journal tuple (games.py dumps with default=str), e.g.::
#
#   WINDOW_OPEN   "(('PASS', 'card:112'),)"        subject "X (card:2)"
#   WINDOW_OPEN   "(('PASS', 'card:117@card:20'),)"  subject "None" (combat)
#   COUNTER       "()"                             cause "Cancel (card:112)"
#   KICKBACK      "('PAY',)"                       answer PAY/PASS/UNPAYABLE
#   LIFE_LOST     "(3,)"                           subject "player:0"
#   TARGETING     "(Handle(namespace='card', index=10), Handle(namespace=
#                  'player', index=0))"            verb TARGET / ONE_OF / REST
#
# Every builder is defensive: an unparseable shape leaves NO view, and the
# JS falls back to the old generic event row — a malformed/unknown feed can
# never blank the log.
# --------------------------------------------------------------------------

_TAG_NAME_RE = re.compile(r"^(.*) \((card:\d+)\)$")
_PLAYER_RE = re.compile(r"player\D*(\d+)")
_TARGET_PLAYER_RE = re.compile(r"namespace='player', index=(\d+)")
_WINDOW_LOOKAHEAD = 300  # journal rows scanned for the window's outcome
# STALL_BREAK: the emitter landed 2026-10-05/11 (KIND_STALL_BREAK in
# executor/events.py: subject None, cause the seat, data (repeat_rounds,))
# but the viewer still matches BY KIND STRING, which held across the
# commit boundary of the sibling batch.
KIND_STALL_BREAK = "STALL_BREAK"


def _esc(text: object) -> str:
    return html_mod.escape(str(text), quote=False)


def _data_tuple(text: object) -> tuple | None:
    """``"(('PASS', 'card:112'),)"`` -> the tuple, or None if unparseable."""
    if isinstance(text, tuple | list):
        return tuple(text)
    if not isinstance(text, str):
        return None
    try:
        val = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    return val if isinstance(val, tuple) else None


def _seat(text: object) -> str:
    match = _PLAYER_RE.search(str(text))
    return "P" + match.group(1) if match else str(text)


def _card_names(entries: list[dict]) -> dict[str, str]:
    """``card:N`` handle -> card name, harvested from the trace itself
    (subjects/causes arrive pre-formatted as ``"Name (card:N)"`` by
    games.py's game_name; action entries carry handle + name)."""
    names: dict[str, str] = {}
    for e in entries:
        for field in ("subject", "cause"):
            match = _TAG_NAME_RE.match(str(e.get(field) or ""))
            if match:
                names.setdefault(match.group(2), match.group(1))
        if e.get("type") == "action" and e.get("card") and e.get("handle"):
            names.setdefault(str(e["handle"]), str(e["card"]))
    return names


def _pretty(token: str, names: dict[str, str]) -> str:
    """``"card:112"`` -> ``"Cancel (card:112)"``; ``"card:a@card:b"`` ->
    ``"A &rarr; B"``; anything unrecognised passes through untouched."""
    if "@" in token:
        caster, _, target = token.partition("@")
        return f"{_pretty(caster, names)} &#8594; {_pretty(target, names)}"
    if token in names:
        return f"{names[token]} ({token})"
    return token


def _full(token: str, names: dict[str, str]) -> str:
    """A vocab token -> the same string a journal subject would carry, so
    held cards can be matched against later CAST/COUNTER subject rows."""
    return f"{names[token]} ({token})" if token in names else token


def _held(vocab: tuple, names: dict[str, str]) -> list[str]:
    return [_pretty(t, names) for t in vocab if t != "PASS"]


def enrich_view(payload: dict) -> None:
    """Attach ``entry["view"] = {cls, html[, did]}`` to the window-arc
    event rows. Kinds without a builder (and malformed shapes) are left
    view-less and render through the old generic event branch."""
    entries = payload.get("entries") or []
    names = _card_names(entries)

    def base(e: dict, cls: str, inner: str) -> dict:
        return {"cls": cls, "html": inner, "kind": e.get("kind", "")}

    def window_open(e: dict) -> dict | None:
        vocab = _data_tuple(e.get("data"))
        if not vocab or not isinstance(vocab[0], tuple):
            return None
        combat = e.get("verb") == "COMBAT_WINDOW"
        spell = "&laquo;combat window&raquo;" if combat else _esc(e.get("subject"))
        held = _held(vocab[0], names)
        chips = "".join(f'<span class="chip">{h}</span>' for h in held)
        did = '<span class="did">acted (see the rows below)</span>'
        view = base(
            e,
            "window",
            f"&#9670; RESPONSE WINDOW &mdash; {spell} &mdash; asked "
            f"<b>{_seat(e.get('cause'))}</b> &middot; held: {chips}",
        )
        view["did"] = did
        view["_held_full"] = [
            _full(t.partition("@")[0], names) for t in vocab[0] if t != "PASS"
        ]
        return view

    def window_pass(e: dict) -> dict | None:
        spell = (
            "&laquo;combat window&raquo;"
            if e.get("verb") == "COMBAT_WINDOW"
            else _esc(e.get("subject"))
        )
        return base(
            e,
            "windowpass",
            f"&#8211; {_seat(e.get('cause'))} passed on {spell}",
        )

    def counter(e: dict) -> dict:
        return base(
            e,
            "counter",
            f"&#10006; <b>COUNTERED</b> {_esc(e.get('subject'))} by "
            f"<b>{_esc(e.get('cause'))}</b>",
        )

    def kickback(e: dict) -> dict | None:
        vocab = _data_tuple(e.get("data"))
        if not vocab:
            return None
        answer = str(vocab[0])
        cls = "pay" if answer == "PAY" else "nopay"
        verb = "spell LIVES" if answer == "PAY" else "spell is COUNTERED"
        return base(
            e,
            "kickback",
            f"&#8617; unless-cost on {_esc(e.get('subject'))} (counter "
            f'{_esc(e.get("cause"))}): payer <span class="{cls}">{_esc(answer)}'
            f"</span> &mdash; {verb}",
        )

    def life_lost(e: dict) -> dict | None:
        vocab = _data_tuple(e.get("data"))
        if not vocab:
            return None
        return base(
            e,
            "life",
            f"&darr; {_seat(e.get('subject'))} LOST <b>{_esc(vocab[0])}</b> "
            f"life (not damage) &mdash; {_esc(e.get('cause'))}",
        )

    def targeting(e: dict) -> dict:
        verb = e.get("verb")
        actor = "?"
        match = _TARGET_PLAYER_RE.search(str(e.get("data")))
        if match:
            actor = "P" + match.group(1)
        if verb in ("ONE_OF", "REST"):  # partition audit rows (NOT designations)
            label = "chosen (ONE_OF)" if verb == "ONE_OF" else "left in pool (REST)"
            return base(
                e,
                "targeting partition",
                f"&#9673; partition {label}: {_esc(e.get('subject'))} "
                f"&mdash; {_esc(e.get('cause'))} [{actor}]",
            )
        return base(
            e,
            "targeting",
            f"&#9678; TARGET: <b>{_esc(e.get('subject'))}</b> designated by "
            f"{_esc(e.get('cause'))} [{actor}]",
        )

    def stall_break(e: dict) -> dict:
        # Emitter landed 2026-10-05/11 (events.py KIND_STALL_BREAK):
        # subject None, cause the seat, data (repeat_rounds,). Still
        # matched BY KIND STRING and shape-tolerant: an unparseable
        # payload falls back to the raw witness string.
        rounds = _data_tuple(e.get("data"))
        detail = (
            f"after <b>{_esc(rounds[0])}</b> repeat rounds"
            if rounds
            else str(e.get("data") or "")
        )
        subject = str(e.get("subject") or "")
        subject = "" if subject in ("None", "") else f" {_esc(subject)}"
        return base(
            e,
            "stall",
            f"&#9208; <b>STALL BREAK</b> T{e.get('turn', '?')} "
            f"{_seat(e.get('cause'))}{subject} {detail}",
        )

    builders = {
        "WINDOW_OPEN": window_open,
        "WINDOW_PASS": window_pass,
        "COUNTER": counter,
        "KICKBACK": kickback,
        "LIFE_LOST": life_lost,
        "TARGETING": targeting,
        KIND_STALL_BREAK: stall_break,
    }
    for entry in entries:
        if entry.get("type") != "event":
            continue
        build = builders.get(str(entry.get("kind")))
        if build is None:
            continue
        try:
            view = build(entry)
        except (
            AttributeError,
            IndexError,
            KeyError,
            SyntaxError,
            TypeError,
            ValueError,
            re.error,
        ):  # a broken/unknown feed must never blank the log
            continue
        if view:
            entry["view"] = view

    # Second pass: annotate each WINDOW_OPEN with what the seat actually
    # DID, read off the following rows (pass row for the same seat/spell,
    # a CAST event for a held card, or a COUNTER flag for the framed spell).
    for i, entry in enumerate(entries):
        view = entry.get("view")
        if not view or view["cls"] != "window":
            continue
        subject = str(entry.get("subject"))
        seat_cause = str(entry.get("cause"))
        did = '<span class="did">acted (see the rows below)</span>'
        picked_target = ""
        for later in entries[i + 1 : i + 1 + _WINDOW_LOOKAHEAD]:
            if (
                later.get("kind") == "WINDOW_OPEN"
                and str(later.get("subject")) == subject
            ):
                break
            if (
                later.get("kind") == "WINDOW_PASS"
                and str(later.get("subject")) == subject
                and str(later.get("cause")) == seat_cause
            ):
                did = '<span class="did">PASSED</span>'
                break
            if later.get("kind") == "COUNTER" and str(later.get("subject")) == subject:
                did = (
                    '<span class="did">COUNTERED &mdash; see the &#10006; card'
                    " below</span>"
                )
                break
            if later.get("kind") == "TARGETING" and str(later.get("cause")) in view.get(
                "_held_full", []
            ):
                picked_target = str(later.get("subject"))
            if later.get("kind") == "CAST" and str(later.get("subject")) in view.get(
                "_held_full", []
            ):
                arrow = f" &#8594; {_esc(picked_target)}" if picked_target else ""
                did = (
                    f'<span class="did">CAST {_esc(later.get("subject"))}{arrow}</span>'
                )
                break
        view["html"] += " &mdash; " + did
        view.pop("did", None)
        view.pop("_held_full", None)


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
  /* response-window-arc kinds (VIEWER batch 2026-10-05) */
  .row.window { background:#241f33; border-left:3px solid #c9a227; }
  .row.window .chip { background:#3a3357; color:#dcd; border-radius:3px;
                      padding:0 4px; font-size:10px; margin:0 2px; }
  .row.window .did { color:#fc6; font-weight:bold; }
  .row.windowpass { background:#201d29; border-left:3px solid #665a78;
                    color:#a99; padding-left:16px; }
  .row.counter { background:#3a1d24; border-left:3px solid #d33; }
  .row.kickback { background:#33270f; border-left:3px solid #e93; }
  .row.kickback .pay { color:#8f8; font-weight:bold; }
  .row.kickback .nopay { color:#faa; font-weight:bold; }
  .row.life { border-left:3px solid #a33; color:#faa; }
  .row.targeting { border-left:3px solid #39a; color:#9cf; }
  .row.targeting.partition { border-left-color:#367; color:#8ab; opacity:.8; }
  .row.stall { background:#332c10; border-left:3px solid #fc3; }
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
    } else if (e.type === 'event' && e.view) html += '<div class="row ' + e.view.cls +
      (i===idx?' sel':'') + '" data-i="' + i + '">' + e.view.html + '</div>';
    else if (e.type === 'event') html += '<div class="row event' + (i===idx?' sel':'') +
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
    enrich_view(payload)
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
