 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/app.py b/app.py
index 9f0ac6b507899976890d52d377252fa81fd22a1f..389be60268969458dbb7029b782ad1dfd60c0049 100644
--- a/app.py
+++ b/app.py
@@ -12,107 +12,196 @@ import aiosqlite
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
 
+
+@app.get("/web/chatbot")
+def chatbot_page():
+    return FileResponse(BASE_DIR / "static" / "chatbot.html")
+
+
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
 
+
+class ChatbotMessage(BaseModel):
+    message: str = Field(..., min_length=1, max_length=1024)
+
+
+class ChatbotReply(BaseModel):
+    reply: str
+    severity: str
+    category: str
+    suggestedActions: list[str] = Field(default_factory=list)
+
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
 
+
+def generate_chatbot_reply(message: str) -> tuple[str, str, str, list[str]]:
+    """Return a conversational reply plus severity/category context."""
+    severity, category, _ = classify(message)
+    lower_msg = (message or "").strip().lower()
+
+    greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
+    if any(lower_msg.startswith(greet) for greet in greetings):
+        reply = (
+            "Hello! I'm here to help with your housing issue. Could you tell me a little more "
+            "about the problem you're experiencing?"
+        )
+        return reply, severity, category, ["Share details about the issue"]
+
+    responses: dict[str, tuple[str, list[str]]] = {
+        "Gas/CO": (
+            "This sounds serious. If you suspect a gas or carbon monoxide leak, please leave the "
+            "property immediately and contact the emergency gas number.",
+            ["Call the emergency gas number", "Ventilate the area if safe"],
+        ),
+        "Mould/Damp": (
+            "Mould and damp can affect your health. We'll raise this with the repairs team. "
+            "Try to keep the area ventilated until someone can visit.",
+            ["Keep the area well ventilated", "Move belongings away from the damp patch"],
+        ),
+        "Water Leak": (
+            "Thanks for letting us know about the leak. If water is spreading quickly, shut off "
+            "the stop tap if you can safely reach it.",
+            ["Turn off the stop tap if safe", "Put down containers to catch drips"],
+        ),
+        "Electrical": (
+            "Electrical problems can be dangerous. Avoid using the affected sockets or switches "
+            "until an engineer attends.",
+            ["Switch off power to the affected circuit if safe", "Keep the area dry"],
+        ),
+        "Heating/Hot Water": (
+            "We'll arrange support for your heating or hot water issue. If it's very cold, use extra "
+            "layers or portable heaters if available.",
+            ["Use extra blankets or layers", "Check the boiler pressure if you know how"],
+        ),
+        "Pests": (
+            "Pest issues are unpleasant. We'll book a visit to treat the area. Keep food sealed and "
+            "the area as clean as possible in the meantime.",
+            ["Store food in sealed containers", "Clean up crumbs and spills promptly"],
+        ),
+        "Safety/Locks": (
+            "Security concerns are a priority. If you feel unsafe right now, contact the emergency "
+            "services. We'll arrange for repairs to locks or doors.",
+            ["Call emergency services if you feel unsafe", "Avoid leaving the property unattended"],
+        ),
+        "Structural": (
+            "Thanks for reporting the structural issue. We'll send a surveyor to inspect it. Please "
+            "avoid the affected area if there's any risk of falling debris.",
+            ["Keep away from the damaged area", "Move belongings away from cracks or loose parts"],
+        ),
+    }
+
+    if category in responses:
+        reply, actions = responses[category]
+    else:
+        reply = (
+            "Thank you for the information. I've logged the issue and will pass it to the housing "
+            "repairs team. If the situation becomes urgent, please call us immediately."
+        )
+        actions = ["Provide any photos if you have them", "Let us know if the problem worsens"]
+
+    if severity == "High" and category != "Gas/CO":
+        actions = ["Contact emergency services if anyone is in danger"] + actions
+
+    return reply, severity, category, actions
+
+
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
diff --git a/app.py b/app.py
index 9f0ac6b507899976890d52d377252fa81fd22a1f..389be60268969458dbb7029b782ad1dfd60c0049 100644
--- a/app.py
+++ b/app.py
@@ -243,50 +332,59 @@ def mailcheck():
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
 
+# -----------------------------------------------------------------------------
+# Chatbot API
+# -----------------------------------------------------------------------------
+@app.post("/web/api/chatbot", response_model=ChatbotReply)
+async def chatbot_endpoint(payload: ChatbotMessage):
+    reply, severity, category, actions = generate_chatbot_reply(payload.message)
+    return ChatbotReply(reply=reply, severity=severity, category=category, suggestedActions=actions)
+
+
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
 
EOF
)
