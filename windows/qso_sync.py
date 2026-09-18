"""Compare contact contents, independently of each computer's local bookkeeping."""
import copy
from shared_log import normalize

LOCAL_FIELDS = frozenset({'id', 'APP_HAMNAVIGATOR_ID', 'APP_HAMNAVIGATOR_NATIVE_ORIGINAL', 'APP_HAMNAVIGATOR_SHARED'})
MISSING = object()


def canonical(value):
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    return normalize({k: v for k, v in value.items() if k not in LOCAL_FIELDS and v is not None and str(v).strip() != ''})


def contact_merge(local, remote, base=MISSING):
    """Three-way field merge; old caches/first connection use a lossless union.

    A missing field in legacy exports is not evidence of an intentional deletion.
    Once a canonical baseline exists, explicit later field removals are supported.
    Different non-empty values for the same changed field still require a choice.
    """
    local, remote = canonical(local), canonical(remote)
    if not isinstance(local, dict) or not isinstance(remote, dict):
        return None, ['kontakt']
    previous = canonical(base) if isinstance(base, dict) else None
    merged, conflicts = {}, []
    for field in sorted(local.keys() | remote.keys() | (previous.keys() if previous else set())):
        left, right = local.get(field, MISSING), remote.get(field, MISSING)
        old = previous.get(field, MISSING) if previous is not None else MISSING
        if left == right:
            value = left
        elif previous is not None and left == old:
            value = right
        elif previous is not None and right == old:
            value = left
        elif previous is None and left is MISSING:
            value = right
        elif previous is None and right is MISSING:
            value = left
        else:
            conflicts.append(field)
            continue
        if value is not MISSING:
            merged[field] = copy.deepcopy(value)
    return merged, conflicts


def canonical_objects(values):
    return {key: canonical(value) if key.startswith('qso/') else copy.deepcopy(value) for key, value in values.items()}
