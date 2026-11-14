# Evidence for KNOWLEDGE/2026-11-14/207 (card-onboarding lessons)

Each script prints the numbers its section of the note quotes. Run the repo ones from the repository
root with `.venv/bin/python -I <script>`; the rest read local inputs that are not in git (session
transcripts, the coordinator's answer keys in the session scratchpad of 2026-11-05 to 11-13), so they
document where a number came from rather than reproduce it elsewhere.

| Script | Inputs | Numbers (note section) |
|---|---|---|
| `ledger.py` | itself: one row per fault, from KNOWLEDGE 173-177, 184, 201-206 and the gate log | the fault classes, where made and caught, escapes (§1) |
| `rounds.py <out.json>` | the answer keys, verdicts and apply logs of the ten blind rounds since 2026-11-05 | plants caught, real WRONG, G3 survivors by operator (§1, §2) |
| `agents.py <transcript> <out.json>`, `subagents.py <subagents dir> <out.json>` | the session transcript and its agents' transcripts (emails scrubbed) | the briefs, reports and follow-up messages (§2, docs/CARD_AGENT_BRIEFS.md) |
| `active.py <subagents dir>` | the agents' transcripts | active agent-minutes and output tokens per phase (§4) |
| `githist.py <worktree>` | `git log` of `MTG_bot/data/cards` | re-maps, re-stamps, first stamps per day (§2, §5.4) |
| `dupver.py <worktree>` | the card records | cards verified in two or three home sets (§2) |
| `reuse.py <out.json>` | the 19 sets and the records | reprints of verified cards, slot near-reuse (§4) |
| `lintscan.py <sets> <n>` | the 19 sets and the records | lint findings on verified and unverified cards (§5.1) |
| `plantlint.py` | the answer keys | the plants the lints flag (§5.1) |
| `reprint_dry.py <scratch dir>` | the 16 other sets and the records; writes records only under the scratch dir | the dry run of `verify --reprint-of` (§4) |
