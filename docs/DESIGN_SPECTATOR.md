# Design: the spectator / prototyping tool

Status: **designed, ready to build.** Every engine hook below cites a real line in the code as
it stands, so this is buildable against today's engine and survives the engine rewrite — the
event schema is the contract, not the engine internals.

**Never runs during training.** Recording is off by default; only the validation entry point
turns it on.

## 1. Technology: a local web app, FastAPI plus a static DOM/CSS page

Against the alternatives, on this project's specifics:

**PyQt or PySide** buys native windowing and costs a heavyweight binary dependency that must
exist on both the Windows dev box and the ARM64 DGX, a hand-rolled layout, scrolling, tooltip
and virtual-list stack, and no zero-friction remote view. Adding Qt as the project's first
declared dependency, for a debug viewer, is backwards.

**pygame** is the wrong tool. You need hover tooltips with wrapped rules text, a scrollable
virtualised log with thousands of rows, expandable JSON, bar charts of action probabilities, and
text selection. All of that is free in a browser and is weeks of work in pygame.

**A local web app** wins, and the existing prototype is already this shape so the layout idea
survives even though the code does not. Decisively: the DGX is a headless box on the network.
With a web viewer you either copy replay files to Windows and open them locally, or run the same
server on the DGX and point the browser at it. Same code, no X forwarding, no Qt over VNC.

Use **DOM and CSS, not canvas.** A Commander board is 60 to 120 permanents, which is 120 divs
with a background image — trivially fast, and you get hover, focus, `transform: rotate(90deg)`
for tapped, CSS transitions for zone moves, and portal tooltips for free. Canvas would force
reimplementing hit testing and text layout.

FastAPI rather than `file://` because the browser blocks `fetch()` on file URLs under CORS —
which is exactly why the current visualiser fails silently into its catch block. A ~120-line
server also gives you the image cache, replay enumeration, and byte-range tailing for live
validation runs.

Three new dependencies: `fastapi`, `uvicorn`, `httpx`. Already declared in `pyproject.toml`
under the `spectator` extra.

```
MTG_bot/spectator/
  events.py        # event types + SCHEMA_VERSION
  recorder.py      # ReplayRecorder: typed deltas + periodic keyframes, JSONL.gz
  hooks.py         # thin shims the engine calls; no-op when the recorder is None
  art_cache.py     # Scryfall client + sharded LRU disk cache
  server.py        # FastAPI: /api/replays, /api/replay/{id}, /art/..., /api/card/...
  static/{index.html, app.js, board.css}
  spectate.py      # CLI: run N validation games with recording on
  scripts/backfill_scryfall_ids.py
```

## 2. Replay format: typed deltas with periodic keyframes

The existing recorder writes a **complete** entity dump per move, twice, at indent 2 — about
2,400 files per game and three quarters of engine wall time. It is also structurally incapable
of showing what you asked for: it has no stack (the stack lives on the Engine, not the graph),
no legal moves, no policy, no reward, and its action field is literally the class name of the
move with no actor, no card, and no target.

So: keep the snapshot idea as a **keyframe**, and emit **typed deltas** in between. One
gzipped JSONL file per game.

```
line 0      {"rec":"header",  ...}
line 1      {"rec":"keyframe", ...}      full state at index 0
lines 2..N  {"rec":"event",    ...}      typed deltas
every 250   another keyframe
last line   {"rec":"footer",  ...}
```

Backward stepping seeks to the nearest preceding keyframe and applies forward — at most 250
delta applications of a pure JS reducer, sub-millisecond. Size for a Commander game is roughly
4 MB raw, **450 KB gzipped**; a 100-game validation batch is about 45 MB. Intern entity ids in
the header (`"e42"`) rather than repeating 36-character UUIDs, which roughly halves the file.

### Header

Carries the schema version, the git commit, a **hash of the card database** (because `card_id`
is an autoincrement rowid and a re-ingest renumbers everything — this hash is the only guard
against replaying against a different database), the **full vocabulary dump**, the seed, the
player and agent identities, the interned entity table, a per-card dictionary so the replay
renders with zero database access, and the token list.

> **Never hardcode a type id in the viewer.** All five hardcoded ids in the current
> `index.html` are wrong. The header's vocabulary dump exists precisely so that cannot happen
> again.

The per-card entry includes the parsed `effects_json` verbatim. That is how you *see* that a
burn spell has no target selector and therefore no-ops.

### Keyframe

Turn, phase, step, active and priority player; per-player life, mana, lands played, hand size,
poison, commander tax and commander damage; ordered zone contents including the command zone;
per-permanent state (tapped, sick, attacking, blocking, damage, counters, **printed versus
effective power/toughness**, keywords, attachments); **the stack**, which today lives outside
the graph and is therefore missing from every existing snapshot; and the continuous effects
with **the list of entities each one actually matched**. That last field is how you see that an
anthem is pumping both players' creatures.

### Events

Common envelope: monotonic index, type, **granularity level**, turn/phase/step, active and
priority player, **the index of the causing event**, and the `file:line` that emitted it. The
cause chain is what turns the log from a feed into a correctness tool.

The catalogue covers turn and step changes, untap, decisions, actions, zone changes, draws,
deckout, taps, mana, costs, stack pushes and resolutions, triggers, damage, life changes,
counters, power/toughness recomputation, attach and detach, combat declarations and damage
assignment, state-based actions, choices, rewards, and game end.

Four event types are **new and exist to expose current bugs**:

| Event | What it reveals |
|---|---|
| `trigger_missed` | The forty dead enters-the-battlefield triggers, fired on the false branch of the condition match |
| `effect_unhandled` | The 13 node types the executor cannot run — 137 selectors, 36 exiles, and the rest |
| `engine_error` | Today `execute_move` catches every rules bug into a log line and returns a string |
| `stall` | Flagged `reward_corrupt: true`, because the move cap leaves no winner and the reward function then pays −10 to **both** players |

The `combat_damage_assigned` event carries a note saying only the first blocker participates,
so the viewer *shows* the simplification instead of hiding it.

### Footer

Event and turn counts, winner and reason, a keyframe byte-offset index for seeking, timeline
markers for the scrubber, and:

```jsonc
"totals": {"errors":14, "unhandled_effects":221, "missed_triggers":40, "no_op_resolutions":63}
```

**That totals block is the single most valuable line in the file.** It turns "the bot looks
dumb" into "63 of its spells resolved as no-ops."

## 3. How it hooks into the engine today

Six edits, all additive, all gated so training pays nothing.

1. ~~**Gate the recorder.**~~ ✔ **Already done** — `Engine(graph, manual_mode, recorder=None)`
   now defaults to a `NullRecorder`.
2. **Replace the string events with typed emits.** `execute_move` already builds a list of
   event strings across nine branches and returns it, and the environment calls it **without
   capturing the return value**. The engine already knows actor, card and target at every
   branch; the information is thrown away twice over.
3. **Record the three places that never record.** `resolve_stack`, `progress_phase_and_step`
   and `check_state_based_actions` mutate the graph and emit nothing. Untap, draw, combat
   damage, cleanup discard, every trigger resolution and every creature death are currently
   invisible. These are exactly the under-the-surface events you asked for.
4. **One choke point for zone moves.** `game_graph._move_card_to_zone` is called by draw, play
   land, cast resolution, destroy, and cleanup discard. Instrument it once and every zone change
   is free.
5. **Decision info.** `Student.select_action` returns only the chosen action's log-probability.
   Return the full probability vector. Also record the **raw logits before the proactivity
   bias**, because that bias subtracts up to 10 nats from every pass action and a panel showing
   only the post-bias distribution is lying about what the model thinks.
6. **Delete `latest.json`.** It is written to a shared path, so every concurrent engine clobbers
   one global file. Live view becomes byte-range tailing of the per-game file.

## 4. Scryfall integration

### Identity resolution — offline, once, no API needed

`MTG_bot/data/M21.json` already carries `identifiers.scryfallId`, `scryfallOracleId` and `uuid`
for all 397 cards **and** all 20 tokens. A backfill script adds `scryfall_id`, `oracle_id` and
`mtgjson_uuid` columns and joins on set code plus collector number — a clean 397/397 join, since
all M21 numbers are plain integers. That fixes the stable-identity problem for the model at the
same time.

### Endpoints

| Need | Endpoint | Note |
|---|---|---|
| Metadata plus image URIs, bulk | `POST /cards/collection` | **75 identifiers per request.** 397 cards is **6 requests.** |
| By set and number | `GET /cards/{set}/{cn}` | Works straight off the existing columns if you skip the backfill |
| Image bytes | the `image_uris` URL returned above | Do **not** construct these by hand; they are documented as opaque |

**Required on every request:** a real `User-Agent` naming the app, and an `Accept` header.
Scryfall returns 429 without a user agent. Keep to roughly 10 requests per second with 50–100 ms
spacing. Downloading all 285 distinct M21 arts at 100 ms spacing takes **about 30 seconds,
once, ever.**

**Bulk versus per-card:** for a single-set project, per-card via the collection endpoint wins
outright — six requests against a 2 GB download you then have to parse. Bulk only becomes worth
it past roughly 5,000 enabled cards, and even then it gives metadata, not images. Rule:
**metadata from MTGJSON, which is already on disk; art from individual image GETs, cached
forever.**

### Disk cache — sized against 27.9 GB free on C:

Cache outside the repo, under `%LOCALAPPDATA%/MTG_AI/art/`, two-level sharded by the first two
hex characters of the id (Windows NTFS degrades badly on directories with tens of thousands of
entries).

| Size | Pixels | Approx bytes | 285 M21 arts | All ~30k unique arts |
|---|---|---|---|---|
| `small` | 146×204 jpg | ~12 KB | 3.4 MB | 360 MB |
| `normal` | 488×680 jpg | ~90 KB | **26 MB** | **2.7 GB** |
| `large` | 672×936 jpg | ~140 KB | 40 MB | 4.2 GB |
| `png` | 745×1040 png | ~800 KB | 230 MB | 24 GB — **never** |

Policy: `normal` is the default display size, cached with no eviction. `large` is for
hover/inspect, LRU-capped at 1,500 entries (~210 MB). `png` is fetched on demand only and never
cached — it is nine times the bytes for a corner radius you can do in CSS. Hard ceiling 4 GB,
swept on startup. Chip-density rendering uses `small`, which at 3.4 MB per set is free.

**Double-faced cards.** M21 has none, but the schema must not need changing later. Rule: if the
Scryfall object has top-level `image_uris`, use it; if it has `card_faces[]` **with per-face
`image_uris`**, the replay carries a face index. The trap: split, flip, adventure and aftermath
cards have `card_faces[]` **without** per-face images — one image, two faces. Key on the
presence of the per-face image field, never on the faces array existing.

**Tokens.** Today `create_token` fabricates an entity with a type id of 999, which is not a
vocabulary row, so a created token has no card identity at all. Two stages: now, render tokens
as a CSS card frame with a dashed border, name, power/toughness and colour bar — zero
dependency, honest, immediately correct. After the backfill, stamp a token key and map it to a
Scryfall id from the MTGJSON token list, and real art appears with no viewer change.

**Offline behaviour.** The viewer must never block on the network. Missing art renders the CSS
frame with full rules text, plus a "fetch missing art (N cards)" button. **The DGX never touches
Scryfall** — art is a viewer-machine concern only.

## 5. Layout and rendering

```
┌──────────────────────────────────────────────────────────────┬──────────────────┐
│ ▸ val_g007 · Commander · T14 Combat/Declare Blockers          │ ACTION LOG       │
│   student(seat0) vs frozen@G4200   ⚑ 3 errors  ⚑ 40 missed    │ [lvl ▾ resolution]│
├──────────────────────────────────────────────────────────────┤ [filter ⬤ Shock ×]│
│ SEAT 1  ♥33  ⌂7 ▤41 ⚰6 ⌦2  ⌘[Pack Leader ×2]                  │──────────────────│
│  ┌ lands ─────────────────────────────────────────────────┐   │ T14 ▸ Declare Atk│
│  │ [Mountain ×7 ⟲4] [Island ×3] [Temple ⟲]                │   │  ▸ decision e0   │
│  └────────────────────────────────────────────────────────┘   │    ⌁0.61 Attack  │
│  ┌ nonperm ───────────────────────────────────────────────┐   │      V +0.31     │
│  │ [Glorious Anthem] [Runed Halo ⟨Shock⟩]                 │   │  ▪ declare_attack│
│  └────────────────────────────────────────────────────────┘   │    ⚠ vigilance:  │
│  ┌ creatures ─────────────────────────────────────────────┐   │      tapped anyway│
│  │ [Cur 2/2⟲] [Bear 3/3̶2̶/̶2̶ +1/+1×1] [Angel⟨tok⟩ 4/4]      │   │      keyword_han-│
│  └────────────────────────────────────────────────────────┘   │      dlers.py:52 │
│ ═══════════════════ COMBAT BAND ══════════════════════════    │      = pass      │
│   [Cur 2/2] ──▶ [Wall 0/4]      [Bear 3/3] ──▶ ♥ Player 2     │  ▪ combat_damage │
│ ═════════════════════════════════════════════════════════     │                  │
│                    ... SEAT 0 mirrored ...                    │                  │
├──────────────────────────────────────────────────────────────┤                  │
│ ◀ ▶ ⏸  [────────●──────────────] 4170/9612   speed 1×         │                  │
└──────────────────────────────────────────────────────────────┴──────────────────┘
```

Build the seat grid for **four seats now**, even though the engine is hardcoded to two. Seats 2
and 3 render as empty placeholders, and the multiplayer work then needs no UI rewrite.

**Command zone is first-class** — its own always-visible chip beside the life total, with the
cast tax counter next to it even though tax is unimplemented. Showing `+0` forever is itself a
finding. Note the live bug the panel will expose immediately: the deck builder shuffles and
*then* the initialiser takes the first card as the commander, so **the commander is a uniformly
random card, frequently a basic land.** You will see that in the first replay you open.

### Rendering 60+ permanents readably

Five mechanisms, in this order.

1. **Three lanes per seat: creatures, non-creature non-lands, lands.** Separating lands out
   reclaims roughly 40% of a typical Commander board immediately.
2. **Pile identical objects.** Objects that are *state-identical* — same card, tapped state,
   counters, effective power/toughness, no attachments, not in combat — collapse into one card
   with a count badge. Twelve untapped Forests become one Forest ×12. Hover fans the pile out;
   click pins it. This is the biggest win and it is exact, because state is part of the pile
   key: piling can never hide a difference.
3. **Three density tiers, auto-selected by permanent count and manually overridable.** Full art
   at 100×140 up to 25 objects per seat; compact 64×90 from 26 to 60; a 26-pixel text row above
   that. A 200-permanent board is still one screen.
4. **A combat band.** Attackers and their blockers lift out of their lanes into a horizontal
   band between the seats, with SVG arrows. Combat is where the interesting mistakes are.
5. **Attachments ride the host** as a fanned stack behind and left, never occupying their own
   slot.

### Per-card visual state

| State | Rendering |
|---|---|
| Tapped | rotate 90°, reduced frame opacity |
| Summoning sickness | animated dashed halo, desaturated |
| Damage marked | red pip bottom-right |
| +1/+1 counters | green badge top-right with the count |
| **Power/toughness modified** | box painted over the art, **printed value struck through beside it**, amber outline; the tooltip lists the contributing continuous effects by id with their filters and matched entities |
| Attached | badge plus fanned stack behind the host |
| Token | dashed border, no set symbol |
| Attacking / blocking | lifted into the combat band with an arrow |
| Commander | gold border |
| **Just changed** | 400 ms yellow flash, keyed on the event index |

**Hover** after 120 ms opens a pinnable inspect panel: large art, printed versus effective
everything, the contributing continuous effects **by id with their matched-entity lists**, the
parsed ability tree, and a collapsible raw property dump. That last one is the correctness tool.

**Log panel**, virtualised, on the right. Rows indent by cause depth, so decision → action →
trigger → resolution → state-based action reads as a tree. Level filter. Click any card anywhere
and the log filters to events touching it. Rows carrying an engine error, unhandled effect,
missed trigger, or no-op render with a warning glyph **and the emitting `file:line`** — that is
"verify correctness, not just surface" made concrete. Every row expands to raw JSON; clicking
seeks the timeline.

## 6. Step semantics

One step is **whatever the current granularity level says it is** — one slider, five detents.
Right arrow advances to the next event at or below the selected level. Because every event
carries its level at write time, this is a pure filter over one array.

| Level | One press advances to | Per Commander game | Use |
|---|---|---|---|
| **G0 turn** | the next turn | ~100 | skim a whole game in 100 presses |
| **G1 step** | the next step change | ~1,300 | "what happened in combat this turn" |
| **G2 decision** | **one agent decision and its execution** | ~1,200 | **the default** |
| **G3 resolution** | every rules event | ~9,600 | verifying correctness |
| **G4 mutation** | every property write | ~25,000 | debugging the layer system |

**Why G2 is the default rather than "a priority pass":** priority is not modelled. The
non-active player gets a decision in exactly one step per turn, and the pass action is overloaded
to mean both "resolve one stack object" and "advance the step". So "a priority pass" is not a
coherent unit here. "One agent decision" is, and it maps one-to-one onto what the model did.

| Key | Action |
|---|---|
| `→` `←` | ±1 at the current granularity |
| `Shift+→` `Shift+←` | ±1 one level **finer** — drill into what you just stepped over |
| `Ctrl+→` `Ctrl+←` | next/previous event touching the **selected entity** |
| `↑` `↓` | change granularity |
| `Space` | play/pause |
| `,` `.` | speed ÷2 / ×2, from 0.25× to as fast as it renders |
| `Home` `End` | first / last |
| `T` | next turn boundary |
| **`E`** | **next warning event — the correctness-hunting key** |
| `[` `]` | previous/next timeline marker |
| `Enter` | pin the hovered card |

Backward stepping is real state reconstruction, not an undo log. The viewer keeps an LRU of
about 64 materialised states, so scrubbing back and forth over a turn is instant.

**Live tail:** the recorder flushes each line; the viewer polls for new bytes and appends. A
follow toggle pins the playhead to the newest event. This replaces the shared `latest.json` that
every concurrent engine clobbers. Validation games only, never training.

## 7. Showing *why* the agent acted

The decision event carries the chosen index, **how it was chosen** (argmax, sample, or
exploration override), the exploration rate, the proactivity bias, the value estimate, the policy
entropy, the number of reasoning passes, and the full menu with **both** post-bias and raw
probabilities and logits — plus **what was filtered out of the menu before the model saw it**,
and a hash of the menu.

Five things that makes visible which nothing currently can:

1. **Biased versus raw probabilities.** The proactivity bias mutates logits in place by up to 10
   nats before the softmax. Showing only the post-bias distribution makes the agent look decisive
   when it is being shoved.
2. **How the action was chosen.** At an exploration rate of 0.31 with a floor of 0.15, roughly a
   third of all actions are uniform random and the probabilities are decoration. The panel must
   say `RANDOM (ε=0.31)` in red across the bar chart, or you will spend hours judging the
   intelligence of a coin flip.
3. **What was withheld.** The training loop curates the menu — dropping repeats, subsampling mana
   abilities, removing pass actions — before the model sees it. That is the difference between
   "the bot never blocks" and "blocks were filtered out".
4. **Menu-hash mismatch.** The environment calls `get_legal_moves()` *again* and indexes into
   that fresh list, while the engine builds some choice menus with `random.sample`. If the
   executed action does not equal the scored one, paint the row red. This is a real,
   currently-invisible correctness hazard.
5. **Untrained heads.** 54.4M of 315.7M parameters get zero gradient. Render plan steps beyond
   the first in grey with an "untrained" tag rather than presenting random output as reasoning.

The reward event decomposes the total into its thirteen named terms, and states the **shaping
versus outcome split** on every row. With +1.0 per cast against a ±10 terminal, a 200-step game
accrues more shaping than outcome, and the log should say so. Also mark the case where the
opponent's move ends the game: the loss reward is computed and then discarded with no transition
appended, so **the student almost never sees a loss.**

Three charts under the timeline: the **value trace** across the game with life overlaid and the
top-20 largest value jumps jumpable (those are the moments the model was surprised);
**cumulative reward stacked by term** (if the shaping band dwarfs the outcome band, the picture
is the argument); and **policy entropy** per decision (collapse to zero is mode collapse, pinned
at the maximum means the model is not discriminating).

## 8. Gaps to close, cheapest first

**A. Attachments do not exist.** The vocabulary has controlled-by, tapped, attacking, blocking,
has-ability and is-in-zone, but **no attachment relationship**, and there is no aura or equipment
attachment logic anywhere. Design the badge now; it costs nothing and emits nothing until the
edge exists.

**B. Nothing is seeded.** The spectate CLI must seed the global random module before constructing
anything and record the seed in the header. Two residual non-determinisms survive even then:
entity ids come from `uuid4()`, and zone-change triggers iterate set differences of UUIDs so
multi-permanent trigger ordering is hash-dependent. Replays are therefore watchable and
self-contained but **not bit-reproducible against a re-run**. Say so in the header rather than
letting someone discover it at 2 a.m.

**C. Blocking decisions are attributed to the wrong player.** Legal-move generation temporarily
overwrites the active player id and restores it in a `finally`, and the training loop then works
out who acted from the *restored* value. Take the acting player from the engine's decision player
at generation time, or the log will confidently attribute the opponent's blocks to the student.

**D. `execute_move` swallows exceptions** into a log line and returns an error string. Emit a
typed error event with the traceback and count them in the footer. That counter will probably be
the most-read number in the tool.

**E. The stall trip corrupts rewards.** It leaves no winner, so the reward function returns −1.0
to *both* players while the training loop separately scores the same game as a draw. Flag it.

## Build order

1. ~~Gate the recorder~~ ✔ done — a prerequisite for anything, including training throughput.
2. `events.py`, `recorder.py`, and the five engine hook points.
3. `backfill_scryfall_ids.py` and `art_cache.py` — 30 seconds of network, once.
4. `server.py` and the static viewer: board, hover, transport, log.
5. The decision panel, which needs the one-line change to return the probability vector.

**Steps 1 and 2 alone, with the log panel and no art at all, already answer "is the engine doing
what I think it is doing", which is the question that currently has no answer.**
