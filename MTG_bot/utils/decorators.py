import time
from functools import wraps
import json
import os

DEBUG = True  # set False in training hot loops

def timed(name=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not DEBUG:
                return fn(*args, **kwargs)
            t0 = time.perf_counter()
            res = fn(*args, **kwargs)
            dt = (time.perf_counter() - t0) * 1e3
            print(f"[TIMER] {name or fn.__name__}: {dt:.3f} ms")
            return res
        return wrapper
    return deco

def with_human_names(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        res = fn(*args, **kwargs)
        # only for debugging: map ids -> names in returned structure for printing
        if not DEBUG:
            return res

        # Load the mapping from the JSON file
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        mapping_path = os.path.join(project_root, 'MTG_bot', 'rule_engine', 'id_to_name_mapping.json')
        with open(mapping_path, 'r') as f:
            id_to_name = json.load(f)

        # example: if res contains 'entity_ids', attach 'entity_names'
        if isinstance(res, dict) and 'entity_ids' in res:
            ids = res['entity_ids']
            # map vectorized
            if hasattr(ids, 'tolist'):
                id_list = ids.tolist()
            else:
                id_list = ids
            res['entity_names'] = [[id_to_name.get(str(i), 'UNK') if i>=0 else None for i in row] for row in id_list]
        return res
    return wrapper


