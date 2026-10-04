from app.engines.pin import pin_allowed, project_wall, annotate_detail

N = 3


def test_cap_boundary():
    assert pin_allowed(False, "open", 2, N)["ok"] is True
    r = pin_allowed(False, "open", 3, N)
    assert r["ok"] is False and r["reason"] == "pin_cap_exceeded"
    r = pin_allowed(False, "open", 4, N)
    assert r["ok"] is False and r["reason"] == "pin_cap_exceeded"


def test_only_open_can_pin():
    for s in ("claimed", "released", "fulfilled"):
        r = pin_allowed(False, s, 0, N)
        assert r["ok"] is False and r["reason"] == "pin_only_open"


def test_already_pinned_takes_precedence():
    r = pin_allowed(True, "claimed", 0, N)
    assert r["ok"] is False and r["reason"] == "already_pinned"
    r = pin_allowed(True, "open", N, N)
    assert r["ok"] is False and r["reason"] == "already_pinned"


def _row(i, status="open"):
    return {"id": i, "status": status}


def test_project_pinned_band_first_id_desc_within_bands():
    rows = [_row(1), _row(2), _row(3), _row(4), _row(5)]
    out = project_wall(rows, {1, 4})
    assert [r["id"] for r in out] == [4, 1, 5, 3, 2]
    assert [r["pinned"] for r in out] == [True, True, False, False, False]


def test_unpin_returns_to_decay_slot():
    rows = [_row(1), _row(2), _row(3), _row(4)]
    pinned = project_wall(rows, {1, 4})
    assert [r["id"] for r in pinned] == [4, 1, 3, 2]
    after = project_wall(rows, {4})
    assert [r["id"] for r in after] == [4, 3, 2, 1]


def test_grey_pin_stays_on_top():
    rows = [_row(1), _row(9, "claimed")]
    out = project_wall(rows, {9})
    assert [r["id"] for r in out] == [9, 1]
    assert out[0]["pinned"] is True and out[0]["status"] == "claimed"


def test_projection_does_not_mutate_inputs():
    rows = [_row(1)]
    project_wall(rows, {1})
    assert "pinned" not in rows[0]
    out = project_wall(rows, set())
    assert out[0]["pinned"] is False
    assert out[0] is not rows[0]


def test_annotate_detail_keeps_true_status():
    d = annotate_detail({"id": 1, "status": "claimed", "claimer": "bob"}, True)
    assert d == {"id": 1, "status": "claimed", "claimer": "bob", "pinned": True}
