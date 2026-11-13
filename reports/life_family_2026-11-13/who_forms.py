"""Which LIFE_TOTAL_GE `who` forms build on one checkout (ontology gate round 8, M1): the reviewed
head 0be3db11 (a git archive) builds six, the branch YOU only. Output in gate8_runs.txt.

    who_forms.py <checkout>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core import ability_tree as at
from MTG_bot.core.test_executor_binding import referent_sel

forms = [at.ControllerRef.TARGET_PLAYER, at.ControllerRef.TARGET_OPPONENT, at.ControllerRef.YOU,
         at.ControllerRef.OPPONENT, *[referent_sel(r) for r in
                                      ("target", "event", "result", "source", "controller")]]
built = []
for who in forms:
    try:
        at.FAtom(at.FAtomPred.LIFE_TOTAL_GE, who=who, count=at.QConst(10))
    except ValueError:
        continue
    built.append(getattr(who, "name", None) or f"referent {who.referent}")
print(ROOT.name, "builds:", built)
