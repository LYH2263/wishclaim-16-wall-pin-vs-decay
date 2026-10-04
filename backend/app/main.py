import sqlite3
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired
from app.engines.pin import pin_allowed, project_wall, annotate_detail
from app.modules import pin as pinstore

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def ttl():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone(); c.close()
    return int(row["value"] if row else 86400)

def max_pins():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='max_pins'").fetchone(); c.close()
    try:
        return int(row["value"]) if row else 3
    except (TypeError, ValueError):
        return 3

PIN_REASON_STATUS = {"already_pinned": 409, "pin_only_open": 400, "pin_cap_exceeded": 409}

def sweep(c):
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], now())
        if rel:
            c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                      (rel["status"], None, None, None, r["id"]))

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c); c.commit()
    rows = [dict(r) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]
    pinned = set(pinstore.pinned_ids(c)); c.close()
    return project_wall(rows, pinned)

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    pinned = pinstore.is_pinned(c, wid) if r else False
    c.close()
    if not r: raise HTTPException(404, "not found")
    return annotate_detail(dict(r), pinned)

class WishIn(BaseModel):
    title: str
    note: str = ""

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    cur = c.execute("INSERT INTO wishes(title,note,status,data_quality) VALUES (?,?,?,?)",
                    (body.title, body.note, "open", "clean"))
    c.commit(); wid = cur.lastrowid; c.close(); return {"id": wid}

class ClaimIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    allowed = claim_allowed(r["status"], r["claimer"], now(), r["expires_at"])
    if not allowed["ok"]:
        c.close(); raise HTTPException(409, allowed["reason"])
    p = lock_payload(body.claimer, now(), ttl())
    c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
              (p["status"], p["claimer"], p["claimed_at"], p["expires_at"], wid))
    c.commit(); c.close(); return p

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    c.execute("UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "released"}

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "need_claim")
    c.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "fulfilled"}

@app.post("/api/wishes/{wid}/pin")
def pin_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r:
        c.close(); raise HTTPException(404, "not found")
    decision = pin_allowed(pinstore.is_pinned(c, wid), r["status"],
                           pinstore.pin_count(c), max_pins())
    if not decision["ok"]:
        c.close(); raise HTTPException(PIN_REASON_STATUS[decision["reason"]], decision["reason"])
    try:
        pinstore.pin(c, wid); c.commit()
    except sqlite3.IntegrityError:       # concurrent pin lost the race
        c.close(); raise HTTPException(409, "already_pinned")
    c.close(); return {"ok": True, "pinned": True, "id": wid}

@app.post("/api/wishes/{wid}/unpin")
def unpin_wish(wid: int):
    c = connect()
    if not c.execute("SELECT 1 FROM wishes WHERE id=?", (wid,)).fetchone():
        c.close(); raise HTTPException(404, "not found")
    removed = pinstore.unpin(c, wid); c.commit(); c.close()
    if removed == 0:
        raise HTTPException(400, "not_pinned")
    return {"ok": True, "pinned": False, "id": wid}

@app.get("/api/mine")
def mine(claimer: str):
    c = connect(); sweep(c); c.commit()
    rows = [dict(r) for r in c.execute("SELECT * FROM wishes WHERE claimer=?", (claimer,))]; c.close(); return rows

@app.get("/api/done")
def done():
    c = connect()
    rows = [dict(r) for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled'")]; c.close(); return rows

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.get("/api/rules")
def rules():
    n = max_pins()
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销后状态变为 fulfilled",
        "pin_band": "置顶愿望组成整块排在最前；置顶区与普通区内部都按新到旧排列（编号大的在前）。",
        "pin_cap": f"最多置顶 {n} 条；灰钉同样占用名额，名额满后再置顶会被拒绝（pin_cap_exceeded）。",
        "pin_grey": "已置顶愿望被认领后保留📌并在墙上变灰，名额不释放；详情页始终显示真实状态，释放后灰钉恢复正常颜色，核销后的灰钉需手动取消置顶。",
        "pin_unpin": "取消置顶立即释放名额，该愿望回到普通区中按新到旧的原位置。",
        "pin_open_only": "只有 open 状态的愿望可以置顶；对已置顶愿望重复置顶返回 already_pinned。",
    }
