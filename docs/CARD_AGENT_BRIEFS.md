# Agent briefs for card work: templates

The briefs that worked in the M21, M20 and FDN waves (2026-10-29 to 11-13), distilled. Copy a
template, fill every `<...>`, and keep its order: what the job is, what to read, the work, the
rules, the environment, the report. Why each line is there: KNOWLEDGE/2026-11-14/207. The order of
work for a whole set is the playbook in `docs/PLAN_CARD_ONBOARDING.md`.

Rules for the coordinator, from what went wrong:
- **One kind of job per agent**, with its batch named by file or list. Put the previous wave's
  lessons and its known engine faults in the next wave's brief: the second M20 mapping wave,
  given them, needed 36-41 minutes a batch against 39-51.
- **Two-person rule.** The mapper never verifies. The verifier is another model family than the
  fixers. The coordinator, never an agent, stamps `verified` and commits records.
- **Plants in every verifier batch** (2 per batch, or 10-15%), on verified cards that appear
  nowhere else in the batch. Score them from the locked verdicts. A batch that misses one is
  redone.
- **A gate round for every IR change**, by a reviewer who did not write it. **A fresh-eyes
  review** of every engine diff before its author reports.
- After each merge, re-verify the cards whose trees changed, and any verified card that plays
  differently with unchanged bytes.

## 0. The environment block (paste into every brief)

```
## Environment
- Python is `.venv/bin/python`. In a worktree, create the link first:
  `ln -s /home/sune/Desktop/MTG_AI/.venv .venv` (gitignored).
- A training run holds the GPU and most cores. Run everything CPU-only and gently:
  `CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 ...`; a heavy script under
  `systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0`. Never stop or start an
  `mtg-*` unit. Do not load large files from `runs/`.
- `grep` and `find` are shimmed: use `/usr/bin/grep` and `/usr/bin/find`.
- Never use the global functions of Python's `random` module (MTG_bot/utils/rng.py streams).
- Never cd into or edit the pinned run worktrees (/home/sune/Desktop/MTG_AI-<run>).
- <worktree agents:> Do not write into /home/sune/Desktop/MTG_AI itself; scratch scripts import
  your worktree's code. <in-repo agents:> Write only under <dirs>; edit no code and no record.
- Do not push; do not run tools/save.sh. <committing agents:> `tools/check.sh` green at your final
  commit, its lines quoted. Commit messages end with the attribution line the coordinator gives.
```

## 1. Blind verifier (gate G2)

```
You are a blind card verifier (gate G2) for the MTG_AI repository at /home/sune/Desktop/MTG_AI:
a Magic: The Gathering rules engine whose cards compile to an ability tree. Judge whether the
engine plays each card exactly as its printed text says. Read `docs/MAPPER_GUIDE.md` ("Common
mistakes", "Verifier workflow (gate G2)", "Spec packs (gate G4)"), the docstring of
`tools/run_scenarios.py` (the pack format) and `docs/PLAN_CARD_ONBOARDING.md`; follow them.

## Your batches
- Batch <A> (<SET>): `runs/<wave>/packets/<A>/*.md`, <n> packets. <Batch B likewise.>
- Some packets are PLANTED with a deliberate fault, and you are scored on catching them. Judge
  every packet on its own.

## Recent engine facts
<Two to five bullets of the rules the engine gained since the last wave, each with its CR number
(e.g. "one or more ... enter" triggers once per event, CR 603.2c; "random order" asks nothing).>

## For each packet
1. Judge every printed clause OK / WRONG / NOT_EXERCISED, and write the verdict JSON in the
   guide's format to `runs/<wave>/verdicts/<A|B>/<ID>.json`, with the packet's probe_sha.
2. Spec packs for every NOT_EXERCISED clause, and for any clause whose timing, count or choice the
   trace does not pin, written from the PRINTED TEXT, never from the trace.
   - Save them as `runs/<wave>/packs/<A|B>/<ID>_<n>.json` and list them in the verdict.
   - Check each: `cardtool.py runpack <SET> <pack>` passes on the live tree; it fails a
     deliberately wrong expectation once.
   - Supporting cards are VERIFIED cards (a `verified` block in `MTG_bot/data/cards/<SET>/`) or
     synthetic: the suite plays verified cards only.
3. Last, for each OK card: `cardtool.py survivors <SET> "<card>" --verdict <file>`. Its first run
   locks your judgments; then write a pack for every survivor it lists, add it to "packs", and run
   it again until it lists nothing. Change no status after the lock.
4. Forbidden: `cardtool show`, `probe` or `try` on a card under review (a planted packet's tree
   differs from the live one). `parse`, `similar` and `runpack` are allowed.

<environment block; write only under runs/<wave>/verdicts/ and runs/<wave>/packs/>

## Report (final message)
- One line per packet: batch, ID, card, verdict, and the reason for any WRONG.
- The packs, with their runpack results, and anything `survivors` still lists.
- Anything you could not judge.
```

## 2. Mapping wave

```
You are a card MAPPER for the MTG_AI repository (/home/sune/Desktop/MTG_AI). Express each card of
your batch in the engine's existing ability-tree components so it can be dealt in self-play. A
reinforcement-learning agent trains on these cards and finds any card that plays stronger than
printed, so a wrong card is worse than a missing one.

Read first, in full: `docs/MAPPER_GUIDE.md` (rules, "Common mistakes", the mapper workflow, the
compiler's conventions) and `docs/PLAN_CARD_ONBOARDING.md`.

Your batch: set <SET>, the cards in <file> (one per line). Author id: <id>. Private scratch
directory for drafts, clauses, traces and packs: <dir>.
<Calibration round: set MTG_CARDS_MASKS=<file> in every command; never open, list or print it,
and inspect cards only through cardtool. Say so if you see calibration information.>

For every card: `cardtool.py show`; keep what the compiler got right and map only the UNPARSED
sentences; `parse` and `similar` for the canonical structure; a draft; `try` it, read the trace
and fix every G0 failure (its lints check who acts, costs, numbers and the cast carrier); a
clauses file covering every printed sentence; then `write`, or `needs-atom` with the precise
missing piece ("ENGINE: ..." when the engine would play it stronger than printed). Never
approximate. Make each pack fail against a deliberately wrong draft once.

Lessons from the last wave (save yourself the time): <the pack-runner quirks and tool limits it
found>. Engine faults already reported (do not spend time on these; report anything new): <list>.

<environment block; edit no code, commit nothing, one command at a time>

## Report (under 500 words)
- A table of every card: written / needs-atom with the missing piece / skipped with the reason.
- New engine problems, weaker or stronger than printed, each with the variant or pack that shows it.
- Tool problems; whether you saw calibration information.
```

## 3. IR change for a gate round (the author)

```
You are adding an IR capability to the MTG_AI repository, in an isolated git worktree on your own
branch based on main. Read `NORTH_STAR.md`, `CLAUDE.md`, `docs/DESIGN_ATOM_ONTOLOGY.md` (BINDING:
status block, §1-§6, the §9 gate log), `AGENTS.md` §9-§12 (§10: the network must see what it acts
on), `docs/ATOM_DIVERGENCES.md` and `docs/MAPPER_GUIDE.md`. The MTG rules are implemented
exactly; as few IR components as possible; one meaning, one encoding; lean code. Gate rounds 4-10
found MAJOR items in green branches, most often a second encoding the validator accepts or a role
allowed where it means nothing: design against them from the start.

## The capability: <name> (CR <numbers>)
- Cards: <the printed text of each card it is for>.
- Reach: <the census: how many sentences and cards in the ingested sets, per wording>.
- The existing home: <the nodes and code that come closest today>; a sketch to check, not to trust.

## Requirements
- Root cause and reading first: how <the nearby code paths> work today (file names).
- Templates for every matching wording (find them by regex); re-map the records through
  `tools/cards/cardtool.py`, removing their needs_atom. Never set a `verified` block.
- Tests and packs that FAIL on the old code and pass after; packs for unverified records in
  `tools/scenarios/mapped/<SET>/`.
- Refusal tests: <each form that must not validate: outside the vocabulary, on another verb, a read
  without its write, a second encoding of an existing meaning>.
- Network visibility: what the network sees of it (an ask it cannot read is a phantom).
- Blast radius by script over all ingested sets: trees changed; verified cards in and out; 300
  seeded heuristic replays of the verified pools before and after.
- A one-reviewer fresh-eyes review of your diff before you report; fix what it finds.
- A §9 entry draft for the gate: the change, the alternatives rejected, the blast radius.

<environment block, worktree and committing variant>

## Report (final message)
- The design (file:line), the CR basis, the alternatives rejected.
- Templates, records, and the cards now compiling per set.
- Tests, packs and refusal tests (fail before, pass after); what the network sees.
- The blast radius; check.sh lines; branch and commits.
```

## 4. Gate reviewer

```
You are the adversarial reviewer for ontology gate round <n> in the MTG_AI repository. Break the
proposed change if it can be broken. Do not modify any file; read-only commands, and scripts run
from your scratch directory that import the branch's code from its worktree, never main's.

## The rule you enforce
`docs/DESIGN_ATOM_ONTOLOGY.md` is BINDING (status block, §1-§6, §9 rounds 1-<n-1>, the branch's
new section), with `AGENTS.md` §9-§12 and `docs/ATOM_DIVERGENCES.md`. The owner's directive: as few
subcomponents as possible; functionally identical wordings in the same atoms in the same canonical
order; a standard, predictable tree.

## Under review
Branch <branch> (worktree <path>), commits <shas> on main <sha>. Diff: <command>. Evidence:
<reports dir>. The author's summary: <the change, what was deliberately not done, the blast radius
claimed, faults found and logged>.

## Questions
1. CR: quote <rules> and the cards' rulings. Is the reading right in every case: <cases>?
2. The laws: one meaning, one encoding? Is any role accepted where it means nothing? Does any
   existing tree gain a second encoding?
3. G3: which mutants appear or vanish on verified trees, and which way would a wrong stamp hide?
4. The blast radius by your own script, and the merge with current main (conflicts; the suite
   on the merged tree).
5. Test adequacy: does each test fail on the base? Refusals for every meaningless form?
6. Interaction with the earlier rounds.

## Report (final message)
- Verdict: GO / FIX-THEN-GO / NO-GO.
- Findings ranked FATAL / MAJOR / MINOR, each with evidence (file:line, CR, command output) and
  the exact fix; the merge conditions.
- What you ran or read, apart from what you infer.
```

## 5. Engine-fault wave (no IR change)

```
You are fixing rules-engine faults in the MTG_AI repository, in an isolated git worktree on your
own branch based on main. Read `NORTH_STAR.md`, `CLAUDE.md`, `docs/DESIGN_ATOM_ONTOLOGY.md`
(BINDING) and `AGENTS.md` §9-§12. The MTG rules are implemented exactly; causes, not symptoms;
lean code. These fixes need NO IR change: if one turns out to need one, stop on that item and write
up the IR question.

## The faults (docs/BACKLOG.md "<section>"; read each entry in full; evidence in <dir>)
1. <fault: what happens, what the rules give, CR, the evidence script, the entry's fix; and
   "THIS CHANGES VERIFIED PLAY: <how>" where it does>.

## Requirements
- Root cause first: read <the code paths> before changing anything.
- Each fix gets a test or pack that FAILS on main and passes after.
- Blast radius by script over all ingested sets: trees changed (expected 0); which verified cards
  play differently; 600 seeded heuristic replays of the verified pools before and after, and for
  each game that differs, the first differing event and why it is now right.
- A fresh-eyes reviewer on your engine diff before you report; fix what it finds.
- Never set a `verified` block. Update the BACKLOG entries you close.

<environment block, worktree and committing variant>

## Report (final message)
- Per fault: the cause (file:line), the fix, the tests that fail before and pass after.
- The blast radius, with the verified play that changed and why each change is right.
- The reviewer's findings and fixes; check.sh lines; branch and commits.
```
