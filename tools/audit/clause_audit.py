#!/usr/bin/env python3
"""T5-B — persisted clause-level ZERO-LOSS audit of the 305 golden M21 trees.

Replaces the ad-hoc probe (/tmp/opencode/clause/, 50 unclassified residuals,
keyword-list false positives). For every golden tree: load the compiled tree
JSON + the card's oracle text (MTG_bot/data/M21.json via the engine's own
ingest pool loader), decompose the text into clauses (deterministic
line / bullet / sentence / semicolon splits; parenthesised reminder text is
stripped), and try to MAP each clause to a tree component by

  (a) verb / keyword match   — regex on the clause vs engine Verb+Keyword vocab
  (b) numeric literals       — explicit quantities vs tree number fields
  (c) zone / shape tokens    — ZoneKind / structural-tag / cost-shape probes.

Unmapped clauses are RESIDUALS and get the owner taxonomy (§50 charter, §11
significance criterion):

  COVERED                   clause mapped to >=1 component (mechanism+evidence)
  BOILERPLATE-NOTSIGNIFICANT deterministic rules-prose patterns (§11: cannot
                            alter legal options or outcomes)
  NOT-ENCODED               an engine atom COULD express it but the tree lacks
                            it; evidence = targeted grep of compiler.py +
                            templates*.py -> file:symbol, or 'no-template'
  MISSING-ENCODING          the tree carries the verb but the clause did not
                            map fully (quantity/parameter mismatch, or verb
                            present yet unmatched) — human-review flag, the
                            nearest tree node is shown
  MISSING-EXPRESSIVENESS    no engine verb/keyword candidate fits the clause
                            at all; evidence names the missing concept

Deterministic, no LLM. Run: python tools/audit/clause_audit.py
Writes tools/audit/clause_audit_v1.json and prints the summary table.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "MTG_bot" / "core" / "golden" / "M21"
POOL_FILE = ROOT / "MTG_bot" / "data" / "M21.json"
COMPILER_DIR = ROOT / "MTG_bot" / "core" / "compiler"
OUT_PATH = ROOT / "tools" / "audit" / "clause_audit_v1.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from MTG_bot.core.ability_tree import Keyword, Verb  # vocab of record
from MTG_bot.core.compiler.ingest import ingest_pool  # oracle text, canon parser

VERB_NAMES = frozenset(v.name for v in Verb)
KEYWORD_NAMES = frozenset(k.name for k in Keyword)

# keyword display words -> enum name (longest phrase wins on multi-word keys)
KW_WORDS = {
    "vigilance": "VIGILANCE",
    "reach": "REACH",
    "trample": "TRAMPLE",
    "flying": "FLYING",
    "haste": "HASTE",
    "deathtouch": "DEATHTOUCH",
    "first strike": "FIRST_STRIKE",
    "double strike": "DOUBLE_STRIKE",
    "lifelink": "LIFELINK",
    "hexproof": "HEXPROOF",
    "indestructible": "INDESTRUCTIBLE",
    "menace": "MENACE",
    "defender": "DEFENDER",
    "flash": "FLASH",
    "protection": "PROTECTION",
    "prowess": "PROWESS",
    "enchant": "ENCHANT",
    "equip": "EQUIP",
    "scry": "SCRY",
    "mill": "MILL",
}

WORD_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

# ---------------------------------------------------------------- clause split
_REMINDER = re.compile(r"\([^)]*\)")
_LOYALTY = re.compile(r"^\[[+\u2212-]?\d+\]:\s*")


def _alpha_len(s: str) -> int:
    return len(re.sub(r"[^A-Za-z]", "", s))


def kw_only_names(clause: str) -> list[str] | None:
    """A pure keyword-reminder line ('Vigilance, reach, trample', 'Flash.',
    'Enchant creature') -> the enum names, else None."""
    core = clause.strip().rstrip(".").lower()
    words = re.split(r",\s+|\s+", core)
    names, i = [], 0
    while i < len(words):
        if i + 1 < len(words) and f"{words[i]} {words[i + 1]}" in KW_WORDS:
            names.append(KW_WORDS[f"{words[i]} {words[i + 1]}"])
            i += 2
        elif words[i] in (
            "creature",
            "creatures",
            "permanent",
            "land",
            "artifact",
            "enchantment",
            "auras",
        ):
            i += 1  # 'Enchant creature' target word
        elif words[i] in KW_WORDS:
            names.append(KW_WORDS[words[i]])
            i += 1
        else:
            return None
        # trailing commas
    return names or None


def split_clauses(text: str) -> list[str]:
    """Deterministic oracle-text decomposition: strip parenthesised reminder
    text, split line -> bullet -> sentence/semicolon. Keeps loyalty-ability
    bodies (prefix '[+1]:' stripped), keeps '{T}: ...' cost prefixes intact."""
    text = _REMINDER.sub(" ", text or "")
    out: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("\u2022"):
            line = line[1:].strip()
        line = _LOYALTY.sub("", line)
        if not line:
            continue
        for part in re.split(r"(?<=[.;])\s+", line):
            part = part.strip()
            if not part:
                continue
            if _alpha_len(part) >= 6 or kw_only_names(part):
                out.append(part)
    return out


# ------------------------------------------------------------------- rule set
# (regex on clause, mechanism, any-of token probes). Token probes:
#   V:NAME verb   KW:NAME keyword   Z:NAME zone-kind   T:Tag structural tag
#   S:raw  substring in the compact tree JSON
RULES: list[tuple[str, str, list[str]]] = [
    # --- triggers / windows (map by shape; inner effects also map separately)
    (r"^(?:when|whenever)\b", "shape", ["T:TriggeredAbility"]),
    (
        r"^at the beginning of|^at the start of|^during\b",
        "shape",
        ["T:TriggeredAbility"],
    ),
    (
        r"\b(?:dies|died|enters|entering|leaves|left) (?:the battlefield)?\b",
        "shape",
        ["T:TriggeredAbility", "T:ZoneChangeEvent"],
    ),
    (
        r"\b(?:dealt (?:combat )?damage|becomes? (?:blocked|unblocked|tapped|blocked))\b",
        "shape",
        ["T:TriggeredAbility", "T:CombatDamageEvent", "S:Event"],
    ),
    (r"\bactivate only as a sorcery\b", "shape", ["S:ActivationWindow"]),
    (
        r"\bactivat\w+ only if\b",
        "shape",
        ["S:ActivationCondition", "S:condition", "T:ActivationCondition"],
    ),
    (
        r"\b(?:costs|cost) \{?\d*\{?[0-9WUBRGX]*\}?\}? less to activate\b",
        "shape",
        ["S:CostDeltaReduce", "S:CostModifier"],
    ),
    (
        r"\bcosts\b.*\bless to cast\b",
        "shape",
        ["S:CostDeltaReduce", "S:CostModifier", "S:CostReduction"],
    ),
    # --- replacement / modifier prose
    (
        r"\bwould\b.*\binstead\b|\bif one or more\b.*counters\b",
        "shape",
        ["T:ReplacementAbility"],
    ),
    (r"\binstead\b", "shape", ["T:ReplacementAbility"]),
    (
        r"\btriggers?\b.*\ban additional time\b",
        "shape",
        ["S:ADDITIONAL", "S:additional", "S:AdditionalTrigger"],
    ),
    # --- keyword lines / grants
    (
        r"^(?:creatures?|permanents?|this creature|it)\b.*\b(?:have|has|gains?)\b",
        "keyword-grant",
        [],
    ),  # resolved by embedded-keyword scan below
    (r"\b(?:any time you could cast an instant)\b", "keyword", ["KW:FLASH", "S:Flash"]),
    (r"\benchant \b", "keyword", ["KW:ENCHANT"]),
    (r"\bequip \{|^equip\b", "keyword", ["KW:EQUIP"]),
    (r"\bhexproof\b", "keyword", ["KW:HEXPROOF"]),
    (r"\bindestructible\b", "keyword", ["KW:INDESTRUCTIBLE"]),
    (r"\bprotection from\b", "keyword", ["KW:PROTECTION"]),
    (
        r"\b(?:first|double) strike\b",
        "keyword",
        ["KW:FIRST_STRIKE", "KW:DOUBLE_STRIKE"],
    ),
    (
        r"\b(?:vigilance|trample|flying|reach|haste|deathtouch|lifelink|menace)\b",
        "keyword",
        [],
    ),  # resolved by embedded-keyword scan
    # --- combat mandates / restrictions
    (r"\battack(?:s|ing)?\b.*\bif able\b", "verb", ["V:MANDATE_ATTACK"]),
    (r"\bblock(?:s|ing|ed)?\b.*\bif able\b", "verb", ["V:MANDATE_BLOCK"]),
    (
        r"\bcan.?t (?:block|attack)\b|\bcan.?t be blocked\b|\bcan block only\b|\bcan attack only\b",
        "verb",
        ["V:PREVENT_EFFECT", "S:PREVENT", "T:DeclareBlockersEvent"],
    ),
    (
        r"\bcannot\b|\bcan.?t\b|\bdoesn.?t untap\b|\bdon.?t untap\b",
        "shape",
        ["S:PREVENT", "T:FNot", "V:PREVENT_EFFECT"],
    ),
    # --- verbs
    (r"\bdestroys?\b|\bdestroyed\b", "verb", ["V:DESTROY"]),
    (r"\bsacrific(?:es|e|ing)\b", "verb", ["V:SACRIFICE", "S:CostSacrifice"]),
    (r"\bexiles?\b|\bexiled\b", "verb", ["V:EXILE", "V:MOVE_ZONE"]),
    (r"\bmills?\b|\bmilled\b", "verb", ["V:MOVE_ZONE", "V:MILL"]),
    (r"\bdraws?\b|\bdrew\b|\bdrawing\b", "verb", ["V:DRAW"]),
    (
        r"\bdiscards?\b|\bdiscarded\b|\bdiscarding\b",
        "verb",
        ["V:DISCARD", "V:MOVE_ZONE"],
    ),
    (
        r"\bcounter target\b|\bcounter (?:that|the|another)\b",
        "verb",
        ["V:COUNTER_SPELL"],
    ),
    (
        r"\b(?:puts?|put)\b.*\bcounter",
        "verb",
        ["V:PUT_COUNTER", "S:CounterKind", "V:REMOVE_COUNTER"],
    ),
    (r"\bremoves?\b.*\bcounters?\b", "verb", ["V:REMOVE_COUNTER", "V:PUT_COUNTER"]),
    (
        r"\bdouble the number of\b.*\bcounters\b",
        "verb",
        ["V:PUT_COUNTER", "S:double", "S:DOUBLE"],
    ),
    (
        r"[-+][\dX]/\+?-?[\dX]|\bgets? [-+][\dX]/\+?-?[\dX]|\bget [-+][\dX]/\+?-?[\dX]",
        "verb",
        ["V:MODIFY_PT", "S:PtDelta", "V:SET_PT"],
    ),
    (r"\bpower is equal to\b|\btoughness is equal to\b", "verb", ["V:SET_PT"]),
    (r"\bgain(?:s|ed)?\b.*\blife\b|\byou gain \d+\b", "verb", ["V:GAIN_LIFE"]),
    (r"\blos(?:es|e|ing)\b.*\blife\b", "verb", ["V:LOSE_LIFE"]),
    (
        r"\bdeals?\b.*\bdamage\b|\bdamage\b.*\bdealt\b|\bdamage equal to\b",
        "verb",
        ["V:DEAL_DAMAGE"],
    ),
    (
        r"\bcreates?\b.*\btoken|\bcreates?\b.*\bcopy\b|\bputs? .{0,40}token.{0,25}battlefield\b",
        "verb",
        ["V:CREATE_TOKEN"],
    ),
    (
        r"\bsearch(?:es)?\b.*\b(?:library|graveyard|hand|exile)\b|\bsearch(?:es)?\b (?:an? )?(?:target )?(?:opponent|player|your|any)",
        "verb",
        ["V:SEARCH"],
    ),
    (r"\bshuffles?\b", "verb", ["V:SHUFFLE"]),
    (r"\bscri(?:es|y)\b", "verb", ["V:SCRY"]),
    (r"\btaps?\b(?!.*untapped)|\bbecomes? tapped\b", "verb", ["V:TAP", "S:CostTap"]),
    (r"\buntaps?\b", "verb", ["V:UNTAP", "V:TAP", "S:CostTap"]),
    (r"\breveals?\b|\brevealing\b", "verb", ["V:REVEAL", "V:LOOK_AT"]),
    (r"\blook(?:s|ing)? at\b", "verb", ["V:LOOK_AT", "V:REVEAL"]),
    (r"\battach(?:es|ed|ing)?\b|\bequip\b", "verb", ["V:ATTACH", "KW:EQUIP"]),
    (r"\bfights?\b|\bfighting\b", "verb", ["V:FIGHT"]),
    (
        r"\bgain(?:s|ed)? control\b|\byou control enchanted\b",
        "verb",
        ["V:GAIN_CONTROL"],
    ),
    (r"\bextra turn|\ban extra turn\b", "verb", ["V:EXTRA_TURN"]),
    (r"\bend(?:s|ing)? the turn\b", "verb", ["V:END_TURN"]),
    (r"\bphas(?:e|es|ing) out\b", "verb", ["V:PHASE_OUT", "V:PHASE_IN"]),
    (r"\blos(?:e|es|ing) the game\b", "verb", ["V:LOSE_GAME"]),
    (
        r"\bflip a coin\b|\bwin the flip\b|\blose the flip\b",
        "verb",
        ["V:FLIP_COIN", "S:FLIP_WON"],
    ),
    (
        r"\bgets? an? emblem\b|\byou get an emblem\b",
        "verb",
        ["V:GET_EMBLEM", "S:emblem"],
    ),
    (
        r"\badd(?:s|ing)?\b.*\bmana\b|\bmana of any (?:one )?color\b|\badds? [^.]*\{[0-9WUBRG]\}",
        "verb",
        ["V:ADD_MANA"],
    ),
    (
        r"\b(?:may\s+)?(?:take|play) (?:an? )?additional? land",
        "verb",
        ["V:ADD_LAND_PLAY", "V:CAST"],
    ),
    (
        r"\bspend (?:this|that) mana only\b|\bspend mana as though\b",
        "verb",
        ["V:MANA_POLICY", "S:MANA_POLICY"],
    ),
    (
        r"\bassign its combat damage as though\b",
        "verb",
        ["V:DAMAGE_ASSIGN_POLICY", "V:GRANT_ABILITY"],
    ),
    (
        r"\bactivate\b.*\bwhenever you wish\b",
        "verb",
        ["V:GRANT_ACTIVATION", "S:GRANT_ACTIVATION"],
    ),
    (r"\bcopies?\b|\bcopy of\b", "verb", ["V:COPY"]),
    (
        r"\bname a (?:nonland )?card|\bchoose (?:a )?(?:a )?card name\b|\bchoose a name\b|\bname(?:d)? \w+ card\b",
        "verb",
        ["V:CHOOSE_NAME"],
    ),
    (
        r"\bcasts?\b|\bplay(?:ing)?\b|\bmay cast\b",
        "verb",
        ["V:CAST", "T:SpellAbility", "S:CAST"],
    ),
    (
        r"\b(?:lose|loses)\b.*\bability\b|\bloses all abilities\b",
        "verb",
        ["V:LOSE_ABILITY", "S:LOSE_ABILITY"],
    ),
    # --- grant / type prose
    (
        r"\b(?:is|becomes?|are) a[n]? \b|\bin addition to its other types\b|\bgains? .{0,30}abilit(?:y|ies)\b|\b(?:has|have) (?:all |any )?[^.]{0,40}abilit(?:y|ies)\b",
        "shape",
        ["V:GRANT_ABILITY", "V:GRANT_TYPE", "S:GRANT"],
    ),
    (r"\buntil end of turn\b", "shape", ["S:Eot", "S:EOT", "S:duration", "S:Duration"]),
    # --- zone moves (target/zone shapes)
    (
        r"\b(?:return|returns|put|puts)\b.*\b(?:to|into|onto)\b.*\b(?:hands?|librar(?:y|ies)|graveyards?|battlefield|exile)\b",
        "shape",
        ["V:MOVE_ZONE", "Z:HAND", "Z:GRAVEYARD", "Z:BATTLEFIELD"],
    ),
    (
        r"\bon (?:the )?(?:top|bottom)\b|\bto (?:the )?(?:top|bottom)\b",
        "shape",
        ["V:MOVE_ZONE", "Z:LIBRARY", "S:position"],
    ),
    (
        r"\b(?:put|puts)\b.*\bonto the battlefield\b",
        "shape",
        ["V:MOVE_ZONE", "V:CREATE_TOKEN", "Z:BATTLEFIELD"],
    ),
    # --- decision / option prose
    (
        r"\bchoose\b|\bchoose any number\b|\bof your choice\b",
        "shape",
        ["S:Choose", "S:CHOOSE", "T:Choose", "V:CHOOSE"],
    ),
    (
        r"\byou may\b|\bmay (?:choose|target|have|put|exile|cast)\b",
        "shape",
        ["S:Optional", "T:OptionalEffect", "S:optional"],
    ),
    (
        r"\bfor each\b|\bthat many\b|\bequal to the number of\b|\bplus one\b",
        "shape",
        ["S:QProp", "S:QAgg", "S:QBin", "S:QCount"],
    ),
    # --- ETB static states
    (
        r"\benters\b.*\btapped\b|\benter the battlefield tapped\b",
        "shape",
        ["T:EtBState", "S:tapped"],
    ),
    (
        r"\benters\b.*\bwith\b.*\bcounter",
        "shape",
        ["T:EtBState", "S:initial_counters", "S:CounterKind"],
    ),
    # --- costs (activation prefix fallbacks)
    (r"\{T\}[:,}]", "shape", ["S:CostTap", "T:ActivatedAbility"]),
    (
        r"\bpay \d+ life\b|\bpaying \d+ life\b",
        "shape",
        ["S:CostLife", "V:LOSE_LIFE", "S:Cost"],
    ),
    (r"\bactivat\w+:|^.{0,60}:", "shape", ["T:ActivatedAbility", "T:Cost"]),
]

# deterministic §11 boilerplate: rules prose that cannot alter legal options
BOILERPLATE: list[tuple[str, str]] = [
    ("rules-note", r"^(?:play|remember|note|game rule)\b"),
    ("rules-note", r"\bgame rules? (?:apply|notes?)\b"),
    ("flavor", r"^[A-Z][a-z]+ (?:is a|was a) .{0,40}\.$"),
]

# MISSING-EXPRESSIVENESS concept names (checked when no verb candidate fits)
CONCEPTS: list[tuple[str, str]] = [
    (r"\bround(?:s|ed)? (?:up|down)\b", "rounding-policy (half-value round-up)"),
    (
        r"\b(?:loses?|loses?) half\b|\bhalf (?:their|your|the) life\b",
        "half-of-value quantity (QHalf)",
    ),
    (r"\btriggers?\b.*\ban additional time\b", "additional-trigger-count"),
    (
        r"\b(?:that (?:ability|spell|creature)?|each)\b.*\b(?:copies?|copy)\b",
        "copy-count modifier",
    ),
]

_STOP = set(
    "the a an and or of to that this those these with from your their "
    "you they it its are was were will not can have has had you're "
    "each other another target creature creatures player players".split()
)


# ------------------------------------------------------------------ tree view
class Tree:
    """Compact serialised view + number census of one golden tree."""

    def __init__(self, record: dict) -> None:
        self.record = record
        self.dump = json.dumps(record, separators=(",", ":"))
        self.numbers: set[int] = set()
        self._collect_numbers(record)

    def _collect_numbers(self, x) -> None:
        if isinstance(x, dict):
            tag = x.get("tag") or ""
            if not str(tag).startswith("Cost"):  # mana costs are not effect amounts
                for k in ("value", "count", "quantity"):
                    v = x.get(k)
                    if isinstance(v, int):
                        self.numbers.add(v)
                v = x.get("amount")
                if isinstance(v, int):
                    self.numbers.add(v)
            if x.get("loyalty") is not None:
                self.numbers.add(int(x["loyalty"]))
            ic = x.get("initial_counters")
            if isinstance(ic, dict):
                self.numbers.update(int(n) for n in ic.values())
            for v in x.values():
                self._collect_numbers(v)
        elif isinstance(x, list):
            for v in x:
                self._collect_numbers(v)

    def has(self, probe: str) -> bool:
        if probe.startswith("V:"):
            return f'"name":"{probe[2:]}","tag":"Verb"' in self.dump
        if probe.startswith("KW:"):
            return f'"name":"{probe[3:]}","tag":"Keyword"' in self.dump
        if probe.startswith("Z:"):
            return f'"name":"{probe[2:]}","tag":"ZoneKind"' in self.dump
        if probe.startswith("T:"):
            return f'"tag":"{probe[2:]}"' in self.dump
        if probe.startswith("S:"):
            return probe[2:] in self.dump
        raise ValueError(probe)

    def node_around(self, probe: str) -> str:
        name = probe.split(":", 1)[1]
        i = self.dump.find(name)
        if i < 0:
            return f"<{probe} not found>"
        lo = max(0, i - 150)
        return self.dump[lo : i + 150]


# ------------------------------------------------------------- compiler grep
_site_cache: list[tuple[str, str]] | None = None
_verb_site_cache: dict[str, str] | None = None


def _compiler_sources() -> list[tuple[str, str]]:
    """(stem, source) for compiler.py first, then templates*.py."""
    global _site_cache
    if _site_cache is None:
        srcs = []
        files = [COMPILER_DIR / "compiler.py"] + sorted(
            COMPILER_DIR.glob("templates*.py")
        )
        for f in files:
            if f.is_file():
                srcs.append((f.name, f.read_text(encoding="utf-8")))
        _site_cache = srcs
    return _site_cache


def _enclosing_symbol(lines: list[str], idx: int) -> str:
    for j in range(idx, -1, -1):
        m = re.match(r"\s*(?:def|class)\s+(\w+)", lines[j])
        if m:
            return m.group(1)
    return "<module>"


def verb_site(verb: str) -> str:
    """Where the compiler emits Verb.<verb>; first hit wins, else no-template."""
    global _verb_site_cache
    if _verb_site_cache is None:
        _verb_site_cache = {}
    if verb in _verb_site_cache:
        return _verb_site_cache[verb]
    site = "no-template"
    for fname, src in _compiler_sources():
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if f"Verb.{verb}" in line or f'"{verb}"' in line:
                site = f"{fname}::{_enclosing_symbol(lines, i)}"
                break
        if site != "no-template":
            break
    _verb_site_cache[verb] = site
    return site


def grep_clause(clause: str) -> str:
    """Targeted grep of compiler sources for distinctive clause words;
    returns file:symbol of the first hit or 'no-template'."""
    words = [w for w in re.findall(r"[a-z]{5,}", clause.lower()) if w not in _STOP]
    for w in words[:3]:
        rx = re.compile(w)
        for fname, src in _compiler_sources():
            lines = src.splitlines()
            for i, line in enumerate(lines):
                if rx.search(line) and not line.lstrip().startswith("#"):
                    return f"{fname}::{_enclosing_symbol(lines, i)} (grep '{w}')"
    return "no-template"


# -------------------------------------------------------------- quantity axis
_QTY_PATTERNS = [
    r"\blos(?:es|e|ing) (\w+|\d+) life\b",
    r"\bgain(?:s|ed)? (\w+|\d+) life\b",
    r"\bpay (\d+) life\b",
    r"\bdeals? (\w+|\d+) (?:damage|combat damage)\b",
    r"\bscri(?:es|y) (\w+|\d+)\b",
    r"\bdraw(?:s|ing)? (\w+|\d+) cards\b",
    r"\bmills? (\w+|\d+) cards\b",
]


def clause_quantities(clause: str) -> list[int]:
    """Explicit EFFECT quantities in a clause; X / 'that much' / 'half' /
    'equal to' yield nothing (no fixed number to cross-check)."""
    low = clause.lower()
    if re.search(r"\bX\b|that much|half|equal to|how many", clause) or "=X" in low:
        return []
    out = []
    for pat in _QTY_PATTERNS:
        for m in re.finditer(pat, low):
            tok = m.group(1)
            n = int(tok) if tok.isdigit() else WORD_NUM.get(tok)
            if n is not None:
                out.append(n)
    return out


# ---------------------------------------------------------------- classification
def embedded_keywords(clause: str) -> list[str]:
    low = clause.lower()
    return sorted(
        {name for word, name in KW_WORDS.items() if re.search(rf"\b{word}\b", low)}
    )


def candidate_verbs(clause: str) -> set[str]:
    """Engine verbs a clause COULD map to (rules that text-match, ignoring
    tree presence)."""
    out: set[str] = set()
    for rx, _mech, tokens in RULES:
        if re.search(rx, clause, re.I):
            for t in tokens:
                if t.startswith("V:"):
                    out.add(t[2:])
    for kw in embedded_keywords(clause):
        out.add(kw)  # keyword enums are also engine atoms
    return {v for v in out if v in VERB_NAMES or v in KEYWORD_NAMES}


def audit_card(name: str, oracle: str, tree: Tree) -> dict:
    mapped, residuals = [], []
    for clause in split_clauses(oracle):
        hit = None  # (mechanism, evidence)
        # (a) keyword-only reminder lines -> keyword atoms
        names = kw_only_names(clause)
        if names:
            if all(tree.has(f"KW:{n}") for n in names):
                mapped.append(
                    {
                        "text": clause,
                        "mechanism": "keyword",
                        "evidence": "KW:" + ",".join(names),
                    }
                )
                continue
        for rx, mech, tokens in RULES:
            if not re.search(rx, clause, re.I):
                continue
            if tokens:
                matched = [t for t in tokens if tree.has(t)]
                if matched:
                    hit = (mech, matched[0])
                    break
            elif mech == "keyword-grant":
                kws = embedded_keywords(clause)
                found = [f"KW:{k}" for k in kws if tree.has(f"KW:{k}")]
                if found:
                    hit = ("keyword", found[0])
                    break
        # embedded keyword fallback for plain keyword-word clauses
        if hit is None:
            kws = [f"KW:{k}" for k in embedded_keywords(clause) if tree.has(f"KW:{k}")]
            if kws and re.search(r"\b(?:have|has|gains?|gain)\b", clause, re.I):
                hit = ("keyword", kws[0])
        # (c) zone-shape-only clause (e.g. zone-mention with no verb)
        if hit is None:
            for rx, mech, toks in [
                (
                    r"\b(?:to|into|from) (?:your|the|their|its) (hand|library|graveyard|exile)\b",
                    "shape",
                    {
                        "hand": "Z:HAND",
                        "library": "Z:LIBRARY",
                        "graveyard": "Z:GRAVEYARD",
                        "exile": "Z:EXILE",
                    },
                ),
            ]:
                m = re.search(rx, clause, re.I)
                if m:
                    probe = toks[m.group(1).lower()]
                    if tree.has(probe):
                        hit = (mech, probe)
                    break
        # (b) numeric axis: clause quantity present in tree numbers
        if hit is None:
            qty = clause_quantities(clause)
            if (
                qty
                and all(q in tree.numbers for q in qty)
                and re.search(r"\b(?:life|damage|cards?|counter|point)", clause, re.I)
            ):
                hit = ("numeric", f"numbers={sorted(qty)} in tree")

        if hit:
            # MISSING-ENCODING parameter guard: clause quantities all present?
            qty = clause_quantities(clause)
            missing_q = [q for q in qty if q not in tree.numbers]
            if missing_q:
                residuals.append(
                    {
                        "text": clause,
                        "class": "MISSING-ENCODING",
                        "evidence": (
                            f"mapped {hit[1]} but quantity {missing_q} not "
                            f"in tree numbers (param mismatch); node: "
                            f"{tree.node_around(hit[1])[:220]}"
                        ),
                    }
                )
            else:
                mapped.append({"text": clause, "mechanism": hit[0], "evidence": hit[1]})
            continue

        # ---------------- residual taxonomy
        low = clause
        bp = next((tag for tag, rx in BOILERPLATE if re.match(rx, low, re.I)), None)
        if bp:
            residuals.append(
                {
                    "text": clause,
                    "class": "BOILERPLATE-NOTSIGNIFICANT",
                    "evidence": f"boilerplate pattern '{bp}'",
                }
            )
            continue
        cands = candidate_verbs(clause)
        if cands:
            in_tree = sorted(
                c for c in cands if tree.has(f"V:{c}") or tree.has(f"KW:{c}")
            )
            if in_tree:
                residuals.append(
                    {
                        "text": clause,
                        "class": "MISSING-ENCODING",
                        "evidence": (
                            f"atom {in_tree} present in tree but clause "
                            f"did not map (human review); node: "
                            f"{tree.node_around(f'V:{in_tree[0]}')[:220]}"
                        ),
                    }
                )
            else:
                cites = ", ".join(
                    f"{v}->{verb_site(v)}"
                    if verb_site(v) != "no-template"
                    else f"{v}->no-template"
                    for v in sorted(cands)[:4]
                )
                residuals.append(
                    {
                        "text": clause,
                        "class": "NOT-ENCODED",
                        "evidence": (
                            f"engine atom exists ({sorted(cands)[:4]}), "
                            f"tree lacks it; compiler sites: {cites}; "
                            f"grep: {grep_clause(clause)}"
                        ),
                    }
                )
            continue
        concept = next((c for rx, c in CONCEPTS if re.search(rx, low, re.I)), None)
        if concept is None:
            words = [w for w in re.findall(r"[a-zA-Z]+", low) if w not in _STOP]
            concept = (
                "unmapped-operation (" + (words[0] if words else clause[:20]) + ")"
            )
        residuals.append(
            {
                "text": clause,
                "class": "MISSING-EXPRESSIVENESS",
                "evidence": (
                    f"no engine Verb/Keyword candidate fits; missing "
                    f"concept: {concept}; grep: {grep_clause(clause)}"
                ),
            }
        )
    return {
        "card": name,
        "clauses": len(mapped) + len(residuals),
        "mapped": len(mapped),
        "mapped_clauses": mapped,
        "residuals": residuals,
    }


# ------------------------------------------------------------------------ build
def load_pool():
    """oracle_id -> oracle text lines, via the engine's canonical ingest."""
    raw = ingest_pool(POOL_FILE)
    out = {}
    for oid, rc in raw.items():
        out[oid] = (rc.identity.name, "\n".join(rc.sentences))
    return out


def build() -> dict:
    pool = load_pool()
    per_card = []
    for f in sorted(GOLDEN_DIR.glob("*.json")):
        record = json.loads(f.read_text())
        oid = record["oracle_id"]
        name, oracle = pool.get(oid, (record["name"], record.get("oracle_text") or ""))
        per_card.append(audit_card(name, oracle, Tree(record)))
    per_card.sort(key=lambda c: c["card"])

    class_counts: Counter[str] = Counter()
    total_clauses = total_mapped = 0
    for c in per_card:
        total_clauses += c["clauses"]
        total_mapped += c["mapped"]
        for r in c["residuals"]:
            class_counts[r["class"]] += 1
    classes = [
        "BOILERPLATE-NOTSIGNIFICANT",
        "NOT-ENCODED",
        "MISSING-ENCODING",
        "MISSING-EXPRESSIVENESS",
    ]
    return {
        "meta": {
            "tool": "clause_audit v1",
            "golden_trees": len(per_card),
            "oracle_source": str(POOL_FILE.relative_to(ROOT)) + " via ingest_pool",
            "vocab": {"verbs": len(VERB_NAMES), "keywords": len(KEYWORD_NAMES)},
        },
        "summary": {
            "clauses": total_clauses,
            "mapped": total_mapped,
            "coverage_pct": round(100.0 * total_mapped / max(total_clauses, 1), 2),
            "residuals": sum(class_counts.values()),
            "class_counts": {k: class_counts.get(k, 0) for k in classes},
        },
        "per_card": per_card,
    }


def main() -> dict:
    report = build()
    OUT_PATH.write_text(json.dumps(report, indent=1))
    s = report["summary"]
    print(
        f"CLAUSE AUDIT v1 — {report['meta']['golden_trees']} golden trees, "
        f"{s['clauses']} clauses, {s['mapped']} mapped "
        f"({s['coverage_pct']}% zero-loss), {s['residuals']} residuals"
    )
    print(f"{'class':34} {'count':>6}")
    for k, v in s["class_counts"].items():
        print(f"{k:34} {v:>6}")
    for cls in ("NOT-ENCODED", "MISSING-EXPRESSIVENESS", "MISSING-ENCODING"):
        rows = [
            (c["card"], r)
            for c in report["per_card"]
            for r in c["residuals"]
            if r["class"] == cls
        ]
        if rows:
            print(f"\n== {cls} ({len(rows)})")
            for card, r in rows:
                print(f"  [{card}] {r['text'][:90]}")
                print(f"      {r['evidence'][:180]}")
    return report


if __name__ == "__main__":
    main()
