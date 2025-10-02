# app.py — Reports API (clean single file)

from dotenv import load_dotenv
load_dotenv(override=True)

import os, io, csv, html, ssl, smtplib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import aiosqlite
from fastapi.responses import HTMLResponse
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from email.message import EmailMessage

# -----------------------------------------------------------------------------
# Paths / DB
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("REPORTS_DB", (DATA_DIR / "reports.db")))

# -----------------------------------------------------------------------------
# App
# -----------------------------------------------------------------------------
app = FastAPI(title="Reports API", version="0.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

@app.get("/web/form")
def report_form():
    return FileResponse(BASE_DIR / "static" / "form.html")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/web/ping")
async def ping():
    return {"ok": True, "pong": datetime.now(timezone.utc).isoformat()}

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class ReportIn(BaseModel):
    tenantId: str = Field(..., min_length=1, max_length=64)
    propertyId: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=4096)
    photoUrl: Optional[HttpUrl] = None
    sourceChannel: str = Field(..., min_length=1, max_length=64)

class ReportOut(ReportIn):
    id: int
    createdAt: datetime
    severity: str
    category: str
    tags: list[str] = []

# -----------------------------------------------------------------------------
# Tiny classifier
# -----------------------------------------------------------------------------
def classify(description: str) -> tuple[str, str, list[str]]:
    d = (description or "").lower()
    tags: list[str] = []
    rules = {
        "Gas/CO": ["gas leak", "smell gas", "carbon monoxide", "co leak", "co "],
        "Mould/Damp": ["mould", "mold", "damp", "black mould", "black mold"],
        "Water Leak": ["leak", "burst pipe", "flood", "dripping ceiling"],
        "Electrical": ["sparking", "socket", "short circuit", "fuse box"],
        "Heating/Hot Water": ["boiler", "no heat", "radiator", "hot water"],
        "Pests": ["rats", "mouse", "cockroach"],
        "Safety/Locks": ["broken lock", "front door", "unsafe", "security"],
        "Structural": ["crack", "structural", "subsidence", "roof tile"],
    }
    category = "Other"
    for cat, kws in rules.items():
        if any(k in d for k in kws):
            category = cat
            tags.append(cat)
            break
    high_terms = ["gas", "carbon monoxide", "co ", "child", "baby", "elderly",
                  "no heat", "leak", "flood", "sparking", "unsafe", "black mould", "black mold"]
    med_terms  = ["mould", "damp", "pest", "rats", "mouse", "cockroach"]
    severity = "Low"
    if any(k in d for k in high_terms):
        severity = "High"
    elif any(k in d for k in med_terms):
        severity = "Medium"
    return severity, category, tags

# -----------------------------------------------------------------------------
# DB bootstrap
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tenantId      TEXT NOT NULL,
              propertyId    TEXT NOT NULL,
              description   TEXT NOT NULL,
              photoUrl      TEXT,
              sourceChannel TEXT NOT NULL,
              createdAt     TEXT NOT NULL,
              severity      TEXT,
              category      TEXT,
              tags          TEXT
            )
        """)
        await db.commit()

        # Ensure new columns exist (safe even if already there)
        cur = await db.execute("PRAGMA table_info(reports)")
        cols = [row[1] for row in await cur.fetchall()]
        if "severity" not in cols:
            await db.execute("ALTER TABLE reports ADD COLUMN severity TEXT")
        if "category" not in cols:
            await db.execute("ALTER TABLE reports ADD COLUMN category TEXT")
        if "tags" not in cols:
            await db.execute("ALTER TABLE reports ADD COLUMN tags TEXT")
        await db.commit()

# -----------------------------------------------------------------------------
# SMTP / Email
# -----------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
MAIL_FROM = os.getenv("MAIL_FROM", SMTP_USER or "noreply@example.com")
MAIL_TO   = os.getenv("MAIL_TO", "")

async def send_report_email_async(r: ReportOut) -> None:
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and MAIL_TO):
        print("[email] Missing SMTP_* / MAIL_* env; skipping send.")
        return

    sev, cat, _ = classify(r.description or "")
    subj = f"[Reports] {sev} • {cat} • report {r.id} (property {r.propertyId})"

    text = (
        "New report received\n\n"
        f"Tenant:   {r.tenantId}\n"
        f"Property: {r.propertyId}\n"
        f"Source:   {r.sourceChannel}\n"
        f"Created:  {r.createdAt}\n\n"
        f"Severity: {sev}\n"
        f"Category: {cat}\n\n"
        "Description:\n"
        f"{r.description or '(none)'}\n\n"
        f"Photo: {r.photoUrl or '(none)'}\n"
        f"API link: http://127.0.0.1:8812/web/api/reports/{r.id}\n"
    )

    esc = html.escape
    html_body = f"""<!doctype html>
<html>
  <body style="margin:0;padding:24px;background:#0b0f14;color:#e5e7eb;font-family:Segoe UI,Arial,Roboto,Inter,Helvetica,sans-serif;">
    <div style="max-width:720px;margin:0 auto;background:#111827;border:1px solid #1f2937;border-radius:12px;overflow:hidden;">
      <div style="display:flex;align-items:center;gap:12px;padding:16px 20px;background:#0b1220;border-bottom:1px solid #1f2937;">
        <div style="width:36px;height:36px;border-radius:8px;background:#1f2937;display:flex;align-items:center;justify-content:center;color:#93c5fd;font-weight:700">T</div>
        <div>
          <div style="color:#e5e7eb;font-weight:600">Tenant repairs – new report</div>
          <div style="color:#9ca3af;font-size:12px;">{esc(str(r.createdAt))}</div>
        </div>
      </div>
      <div style="padding:20px 22px">
        <div style="display:flex;gap:8px;margin-bottom:12px;">
          <span style="background:{'#ef444433' if sev=='High' else ('#f59e0b33' if sev=='Medium' else '#10b98133')};color:{'#fecaca' if sev=='High' else ('#fef3c7' if sev=='Medium' else '#d1fae5')};padding:4px 10px;border-radius:999px;font-size:12px;">Severity: {esc(sev)}</span>
          <span style="background:#334155;color:#cbd5e1;padding:4px 10px;border-radius:999px;font-size:12px;">{esc(cat)}</span>
        </div>
        <table style="width:100%;border-collapse:separate;border-spacing:0 8px;color:#e5e7eb">
          <tr><td style="width:140px;color:#9ca3af">Tenant</td><td>{esc(r.tenantId)}</td></tr>
          <tr><td style="width:140px;color:#9ca3af">Property</td><td>{esc(r.propertyId)}</td></tr>
          <tr><td style="width:140px;color:#9ca3af">Source</td><td>{esc(r.sourceChannel)}</td></tr>
        </table>
        <div style="margin:16px 0 6px;color:#9ca3af;font-size:13px;">Description</div>
        <div style="white-space:pre-wrap;background:#0b1220;border:1px solid #1f2937;border-radius:10px;padding:12px 14px;color:#d1d5db;">
          {esc(r.description or '(none)')}
        </div>
        <div style="margin:16px 0 6px;color:#9ca3af;font-size:13px;">Photo URL</div>
        <div><a style="color:#93c5fd" href="{esc(r.photoUrl or '#')}">{esc(r.photoUrl or '(none)')}</a></div>
        <div style="margin-top:18px">
          <a href="http://127.0.0.1:8812/web/api/reports/{esc(str(r.id))}"
             style="display:inline-block;background:#2563eb;color:white;text-decoration:none;padding:10px 14px;border-radius:8px;">
            View in API
          </a>
        </div>
      </div>
    </div>
    <div style="max-width:720px;margin:12px auto;text-align:center;color:#6b7280;font-size:12px;">
      Internal demo email via Mailtrap Sandbox
    </div>
  </body>
</html>"""

    try:
        import aiosmtplib
        await aiosmtplib.send(
            message=EmailMessageFrom(text, html_body, MAIL_FROM, MAIL_TO, subj),
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=True,
            username=SMTP_USER,
            password=SMTP_PASS,
            timeout=20,
        )
        print(f"[email] sent report {r.id} to {MAIL_TO}")
    except Exception as e:
        # Fallback to smtplib if aiosmtplib not available
        try:
            msg = EmailMessage()
            msg["Subject"] = subj
            msg["From"] = MAIL_FROM or SMTP_USER
            msg["To"] = MAIL_TO
            msg.set_content(text)
            msg.add_alternative(html_body, subtype="html")
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
            print(f"[email-fb] sent report {r.id} to {MAIL_TO}")
        except Exception as e2:
            print(f"[email] failed: {e2}")

def EmailMessageFrom(text: str, html_body: str, sender: str, to: str, subject: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    return msg

@app.get("/web/_mailcheck")
def mailcheck():
    return {
        "host": SMTP_HOST,
        "port": SMTP_PORT,
        "user_set": bool(SMTP_USER),
        "pass_set": bool(SMTP_PASS),
        "from": MAIL_FROM,
        "to": MAIL_TO
    }

@app.get("/web/test-mail")
async def test_mail():
    fake = ReportOut(
        id=999,
        tenantId="T0007",
        propertyId="P0123",
        description="Test message",
        photoUrl=None,
        sourceChannel="test",
        createdAt=datetime.now(timezone.utc),
        severity="Low",
        category="Other",
        tags=[]
    )
    await send_report_email_async(fake)
    return {"ok": True}

# -----------------------------------------------------------------------------
# Core API
# -----------------------------------------------------------------------------
@app.post("/web/api/reports", response_model=ReportOut)
async def create_report(r: ReportIn, background_tasks: BackgroundTasks):
    created = datetime.now(timezone.utc).isoformat()
    severity, category, tags = classify(r.description)
    tags_csv = ",".join(tags)

    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        cur = await db.execute(
            """INSERT INTO reports
               (tenantId,propertyId,description,photoUrl,sourceChannel,createdAt,
                severity,category,tags)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                r.tenantId, r.propertyId, r.description,
                (str(r.photoUrl) if r.photoUrl else None),
                r.sourceChannel, created, severity, category, tags_csv
            )
        )
        await db.commit()
        rid = cur.lastrowid

    out = ReportOut(
        id=rid, createdAt=datetime.fromisoformat(created),
        severity=severity, category=category, tags=tags, **r.model_dump()
    )

    # send email without delaying the HTTP response
    background_tasks.add_task(send_report_email_async, out)
    return out

@app.get("/web/api/reports/{rid}", response_model=ReportOut)
async def get_report(rid: int):
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        db.row_factory = aiosqlite.Row
        row = await db.execute_fetchone("SELECT * FROM reports WHERE id = ?", (rid,))
    if not row:
        raise HTTPException(status_code=404, detail="Not Found")
    d = dict(row)
    d["createdAt"] = datetime.fromisoformat(d["createdAt"])
    d["tags"] = d.get("tags", "") .split(",") if d.get("tags") else []
    return ReportOut(**d)

@app.get("/web/api/reports", response_model=List[ReportOut])
async def list_reports(since: datetime | None = Query(None, description="UTC timestamp. If omitted: last 24h")):
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=1)
    iso = since.isoformat()

    out: list[ReportOut] = []
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reports WHERE createdAt > ? ORDER BY id ASC", (iso,)
        ) as cur:
            async for r in cur:
                d = dict(r)
                d["createdAt"] = datetime.fromisoformat(d["createdAt"])
                d["tags"] = d.get("tags", "") .split(",") if d.get("tags") else []
                out.append(ReportOut(**d))
    return out

# -----------------------------------------------------------------------------
# CSV export + Daily digest
# -----------------------------------------------------------------------------
async def _fetch_reports(since_iso: str | None = None, until_iso: str | None = None) -> list[dict]:
    where, params = [], []
    if since_iso:
        where.append("createdAt >= ?")
        params.append(since_iso)
    if until_iso:
        where.append("createdAt < ?")
        params.append(until_iso)

    sql = ("SELECT id, tenantId, propertyId, description, photoUrl, sourceChannel, createdAt "
           "FROM reports")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY createdAt DESC"

    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(sql, tuple(params))
    return [dict(r) for r in rows]

@app.get("/web/export/reports.csv")
async def export_reports_csv(since: str | None = None, until: str | None = None):
    rows = await _fetch_reports(since, until)

    def _iter_csv():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id","tenantId","propertyId","sourceChannel","severity","category","description","photoUrl","createdAt"])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in rows:
            sev, cat, _ = classify(r["description"])
            w.writerow([r["id"], r["tenantId"], r["propertyId"], r["sourceChannel"], sev, cat, r["description"], r["photoUrl"] or "", r["createdAt"]])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    headers = {"Content-Disposition": f'attachment; filename="reports_{ts}.csv"'}
    return StreamingResponse(_iter_csv(), media_type="text/csv", headers=headers)

def _render_digest_html(rows: list[dict], since_dt: datetime, until_dt: datetime) -> tuple[str, str]:
    title = f"Reports digest: {len(rows)} new"
    subject = f"[Reports] {title}"
    period = f"{since_dt.isoformat()} – {until_dt.isoformat()}"

    if not rows:
        html_body = f"""
        <div style="font-family:Segoe UI,Arial,sans-serif;padding:16px;background:#0b1016;color:#e6edf3">
          <h2 style="margin:0 0 8px 0">Reports digest</h2>
          <div style="opacity:.7;font-size:12px;margin-bottom:16px">{html.escape(period)}</div>
          <p>No new reports in this period.</p>
        </div>
        """
        return subject, html_body

    rows_html = []
    for r in rows:
        sev, cat, _ = classify(r["description"])
        desc = html.escape(r["description"])
        photo = html.escape(r.get("photoUrl") or "")
        rows_html.append(f"""
          <tr>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{r['id']}</td>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{html.escape(r['tenantId'])}</td>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{html.escape(r['propertyId'])}</td>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{html.escape(cat)}</td>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{html.escape(sev)}</td>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{desc}</td>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{f'<a href="{photo}">photo</a>' if photo else ''}</td>
            <td style="padding:8px;border-bottom:1px solid #2b2f36">{html.escape(r['createdAt'])}</td>
          </tr>
        """)

    html_body = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;padding:16px;background:#0b1016;color:#e6edf3">
      <h2 style="margin:0 0 8px 0">{html.escape(title)}</h2>
      <div style="opacity:.7;font-size:12px;margin-bottom:16px">{html.escape(period)}</div>
      <table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;
             background:#0f1520;color:#e6edf3">
        <thead>
          <tr style="background:#141b27">
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">ID</th>
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">Tenant</th>
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">Property</th>
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">Category</th>
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">Severity</th>
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">Description</th>
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">Photo</th>
            <th style="text-align:left;padding:8px;border-bottom:1px solid #2b2f36">Created</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
    </div>
    """
    return subject, html_body

async def _send_digest_email(rows: list[dict], since_dt: datetime, until_dt: datetime) -> None:
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS and MAIL_TO):
        print("[digest] Missing SMTP_* / MAIL_* env; skipping send.")
        return

    subject, html_body = _render_digest_html(rows, since_dt, until_dt)

    # Build one message we can send via aiosmtplib or smtplib
    msg = EmailMessage()
    msg["From"] = MAIL_FROM or SMTP_USER
    msg["To"] = MAIL_TO
    msg["Subject"] = subject
    msg.set_content("See HTML version.")
    msg.add_alternative(html_body, subtype="html")

    try:
        import aiosmtplib
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=int(SMTP_PORT),
            start_tls=True,
            username=SMTP_USER,
            password=SMTP_PASS,
            timeout=20,
        )
    except Exception as e1:
        # fallback to smtplib
        import traceback
        print("[digest] aiosmtplib failed, falling back:", e1)
        try:
            with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT), timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        except Exception as e2:
            print("[digest] smtplib failed:", traceback.format_exc())
            raise
    print(f"[digest] sent {len(rows)} items to {MAIL_TO}")


@app.get("/web/admin/send-digest")
async def send_digest(hours: int = 24):
    try:
        until_dt = datetime.now(timezone.utc)
        since_dt = until_dt - timedelta(hours=hours)
        rows = await _fetch_reports(since_dt.isoformat(), until_dt.isoformat())
        await _send_digest_email(rows, since_dt, until_dt)
        return {"ok": True, "count": len(rows), "since": since_dt.isoformat(), "until": until_dt.isoformat()}
    except Exception as e:
        import traceback
        print("[digest] failed:\n", traceback.format_exc())
        # Surface the reason instead of a generic 500
        raise HTTPException(status_code=500, detail=f"Digest failed: {e}")

@app.get("/web/admin/digest-preview", response_class=HTMLResponse)
async def digest_preview(hours: int = 24):
    """Render the digest HTML in the browser without sending email."""
    until_dt = datetime.now(timezone.utc)
    since_dt = until_dt - timedelta(hours=hours)
    rows = await _fetch_reports(since_dt.isoformat(), until_dt.isoformat())
    _, html_body = _render_digest_html(rows, since_dt, until_dt)
    return HTMLResponse(html_body)


# -----------------------------------------------------------------------------
# Debug
# -----------------------------------------------------------------------------
@app.get("/web/debug/db")
async def db_info():
    p = DB_PATH
    size = Path(p).stat().st_size if Path(p).exists() else 0
    async with aiosqlite.connect(DB_PATH.as_posix()) as db:
        cur = await db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='reports'")
        has_table = (await cur.fetchone())[0] == 1
        total = 0
        if has_table:
            cur = await db.execute("SELECT COUNT(*) FROM reports")
            total = (await cur.fetchone())[0]
    return {"db": str(p), "exists": Path(p).exists(), "bytes": size, "hasReportsTable": has_table, "count": total}
