"""Fetch real Scryfall card images for the replay viewer (14g validation infra).

Two target sets, written to ``MTG_bot/assets/card_images/<oracle_id>.jpg``:

1. the 305 goldens — every ``oracle_id`` in :func:`ingest_pool` (the exact
   key set every golden/executor object uses), sourced from the paginated
   ``cards/search?q=set:m21 unique=prints include_extras=true`` feed;
2. the tokens the executor synthesizes — every ``TokenSpec`` name in the
   compiled pool, stored under the SAME synthetic id the world gives a
   token instance (:func:`executor.verbs.token_oracle_id`), looked up
   with ``q=type:token!"<name>"`` because M21's token cards ship under a
   separate Scryfall set and are not in the ``set:m21`` page.

Etiquette: one page/GET at a time, ``~0.1s`` sleep between image GETs
(Scryfall asks for ≥0.1s), an honest identifying User-Agent, and the API
``ttl`` param is not needed because we cache on disk. Resumable: an
existing non-empty file is skipped, so re-running only fills gaps.

Report at the end: N downloaded / N already present / N missing (with
names). Nothing is silently skipped — a card with no sourceable image
just stays absent and the viewer renders a placeholder.

Run::

    .venv/bin/python tools/fetch_card_images.py            # fetch
    .venv/bin/python tools/fetch_card_images.py --check    # verify only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ASSET_DIR = REPO / "MTG_bot" / "assets" / "card_images"
DATA = REPO / "MTG_bot" / "data" / "M21.json"
API = "https://api.scryfall.com"
USER_AGENT = "MTG_AI-replay-audit/1.0 (local validation tool; contact: none)"
SLEEP = 0.1  # Scryfall developer etiquette: at least one tenth of a second


def _get(url: str, accept: str = "application/json") -> Any:
    # Scryfall REQUIRES both User-Agent and Accept headers on every API call.
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _image_of(card: dict) -> str | None:
    uris = card.get("image_uris") or (
        (card.get("card_faces") or [{}])[0].get("image_uris")
    )
    return uris.get("normal") if uris else None


def golden_ids() -> dict[str, str]:
    """oracle_id -> name for the 305 goldens (the ingest key set)."""
    from MTG_bot.core.compiler.ingest import ingest_pool

    raw = ingest_pool(DATA)
    return {oid: rec.identity.name for oid, rec in raw.items()}


def token_names() -> list[str]:
    """Every TokenSpec name the compiled pool can synthesize."""
    from MTG_bot.core.ability_tree import Atom, TokenSpec, walk
    from MTG_bot.core.executor.games import get_supply

    names: set[str] = set()
    supply = get_supply("all")
    for res in supply.pool.results.values():
        for node in walk(res.card):
            if isinstance(node, Atom):
                for _role, value in node.args.pairs:
                    if isinstance(value, TokenSpec):
                        names.add(value.name)
    return sorted(names)


def scryfall_search_pages(query: str) -> list[dict]:
    """All pages of a search with prints collapsed and extras included."""
    url = f"{API}/cards/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "unique": "prints",
            "include_extras": "true",
            "order": "name",
        }
    )
    cards: list[dict] = []
    while url:
        page = _get(url)
        cards.extend(page.get("data", []))
        url = page.get("next_page") or ""
        time.sleep(SLEEP)
    return cards


def build_image_map() -> dict[str, tuple[str, str]]:
    """oracle_id -> (image_url, display_name) for both target sets."""
    wanted = golden_ids()
    image_map: dict[str, tuple[str, str]] = {}
    for card in scryfall_search_pages("set:m21"):
        oid = card.get("oracle_id")
        uri = _image_of(card)
        if oid and uri and oid in wanted and oid not in image_map:
            image_map[oid] = (uri, card.get("name", wanted[oid]))
    missing = {oid: name for oid, name in wanted.items() if oid not in image_map}
    for oid, name in sorted(missing.items()):
        # one targeted lookup per straggler (quoted so commas are safe)
        try:
            found = scryfall_search_pages(f'"{name}"')
        except urllib.error.URLError:
            continue
        for card in found:
            if card.get("oracle_id") == oid and (uri := _image_of(card)):
                image_map[oid] = (uri, name)
                break
    # tokens: stored under the executor's synthetic token oracle id
    from MTG_bot.core.executor.verbs import token_oracle_id

    for name in token_names():
        tid = token_oracle_id(name)
        try:
            found = scryfall_search_pages(f'type:token "{name}"')
        except urllib.error.URLError:
            continue
        for card in found:
            if card.get("name") == name and (uri := _image_of(card)):
                image_map[tid] = (uri, f"{name} (token)")
                break
    return image_map


def download(image_map: dict[str, tuple[str, str]], check_only: bool) -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    wanted = golden_ids()
    got = skipped = 0
    missing: list[str] = []
    for oid, (uri, name) in sorted(image_map.items(), key=lambda kv: kv[1][1]):
        path = ASSET_DIR / f"{oid}.jpg"
        if path.exists() and path.stat().st_size > 0:
            skipped += 1
            continue
        if check_only:
            missing.append(name)
            continue
        try:
            req = urllib.request.Request(
                uri,
                headers={"User-Agent": USER_AGENT, "Accept": "image/jpeg"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                blob = resp.read()
        except (urllib.error.URLError, OSError) as error:
            print(f"  fetch fail {name}: {error}")
            missing.append(name)
            continue
        if blob[:2] != b"\xff\xd8":  # not a JPEG — do not poison the cache
            missing.append(name)
            continue
        path.write_bytes(blob)
        got += 1
        time.sleep(SLEEP)
    # goldens that never even produced a URL are missing too
    sourced = {oid for oid in image_map if oid in wanted}
    missing += [name for oid, name in wanted.items() if oid not in sourced]
    print(
        f"card images: {got} downloaded, {skipped} already present, "
        f"{len(missing)} missing"
    )
    for name in sorted(set(missing)):
        print(f"  MISSING: {name}")
    return 0 if not missing else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Scryfall images for the replay viewer"
    )
    parser.add_argument(
        "--check", action="store_true", help="report coverage, download nothing"
    )
    args = parser.parse_args(argv)
    return download(build_image_map(), args.check)


if __name__ == "__main__":
    raise SystemExit(main())
