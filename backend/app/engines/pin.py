"""Pure pin domain logic: cap gate, wall ordering projection, detail annotation.

No DB access, no clock — unit-tested directly like engines.claim_lock.
"""


def pin_allowed(already_pinned, status, pin_count, max_pins):
    """Decide whether a pin action is allowed. Analogous to claim_allowed.

    Precedence: already_pinned BEFORE pin_only_open so re-pinning a grey pin
    reports already_pinned instead of the misleading pin_only_open.
    """
    if already_pinned:
        return {"ok": False, "reason": "already_pinned"}
    if status != "open":
        return {"ok": False, "reason": "pin_only_open"}
    if pin_count >= max_pins:
        return {"ok": False, "reason": "pin_cap_exceeded"}
    return {"ok": True, "reason": ""}


def project_wall(rows, pinned_ids):
    """Annotate rows with a pinned bool and project the wall order.

    The whole pinned band comes first; id DESC (newer first — the existing
    decay order) WITHIN each band. Input dicts are copied, never mutated.
    Unpinning moves a wish straight back to its natural slot in the rest band.
    """
    annotated = [dict(r, pinned=(r["id"] in pinned_ids)) for r in rows]
    pinned = sorted((r for r in annotated if r["pinned"]), key=lambda r: r["id"], reverse=True)
    rest = sorted((r for r in annotated if not r["pinned"]), key=lambda r: r["id"], reverse=True)
    return pinned + rest


def annotate_detail(row, pinned):
    """True-status detail view: copy the row verbatim and only add the pin flag."""
    return dict(row, pinned=pinned)
