# 110 — WAS_KICKED permanent lane: entry-provenance semantics (blink-stale caveat closed) — note transcribed by orchestrator (author's file lost to a parallel-write race the same day)

Date: 2026-10-19. Closes the /100-registered blink staleness caveat. Semantics (owner-ruling law):
"was kicked" is a property of HOW THE SPELL WAS CAST — a permanent that left and re-entered is a NEW
object that was never cast ⇒ WAS_KICKED False for the new object's entering-replacement (gated
EtBState must NOT re-apply counters) AND for later permanent-lane reads.

Implementation (author report, executor/quantity.py): WAS_KICKED branch splits by judged-handle
zone. Battlefield ⇒ `_permanent_was_kicked()` entry-provenance read: LAST battlefield-entry
ZONE_CHANGE row's journalled from_state + CAST-row pairing (`cast_clock > stack_in_clock`; pairing
rejects put-on-stack/copy artifacts); entry from stack ⇒ that cast's kicked flag; entry from ANY
other zone ⇒ False. SPELL/TRIGGER lanes keep the unchanged turn-window CAST read (byte-identical
behavior, regression-pinned). NO journal payload extension — fingerprint bytes unchanged
(ReplayDeterminismTest green).

Evidence: PermanentKickerBlinkTest 5 tests (control True; un-kicked sibling False falsifier; blink
return False + no counter re-apply (4 stay 4, would be 8 pre-fix); put-from-hand False/0;
turn-boundary independence). Pack: Nullpriest of Oblivion is the ONLY compiled ZNR card with a
gated (WAS_KICKED) MOVE_ZONE GY→battlefield trigger — `znr_nullpriest_blink_kick.json` exercises
the full loop (kicker ask → GY target → kicked return with EtBState counter → blink → gate False →
no re-apply). Packs 405/405; core 2636 + 36 subtests; pyright 0; ruff Δ0.

Census: exile-return-to-battlefield = 0 ZNR cards (primitive-level proof stands); 7 graveyard-return
cards, Nullpriest is the only gated one. Author also flagged a 'Requiem Angel trigger duplication'
attribute to the smoke fuzz — VERIFIED FALSE (absent from the smoke ledger); dropped.

Housekeeping: the author's original file was lost — KNOWLEDGE parallel sessions raced on this exact
number (claim-by-commit law in force); orchestrator re-created it from the author's verbatim report.
If the author's copy resurfaces, theirs supersedes on content, this header stays as the incident pin.
