
# Folder
cd C:\reports-api

# README content (everything lives inside README.md)
$readme = @'
# Mayor Repairs – OpenEdge + FastAPI (GenAI-assisted)

A pragmatic tenant-repairs intake system. It accepts repair requests from web and ABL agents, auto-classifies severity and category, stores to SQLite, sends dark-themed HTML notifications and a daily email digest, and exports CSV for ops/analytics. It integrates with OpenEdge as the enterprise platform.

-------------------------------------------------------------------------------

## Problem Statement
Housing officers and FM teams receive unstructured repair requests from multiple channels. Manual triage is slow; high-risk issues (gas, damp, leaks) get buried; and teams lack a simple view across cases. We need a small, reliable intake layer to:
1) Ingest reports from web and OpenEdge ABL agents.
2) Classify and highlight critical cases automatically.
3) Notify the right team quickly and summarize daily.
4) Export data for analysis and reporting.

## Industry Context
Applies to social housing, local authorities, and facilities management where repairs are frequent, service levels matter, and legacy line-of-business systems must continue running. This project adds a sidecar service that complements existing OpenEdge applications without invasive changes.

-------------------------------------------------------------------------------

## Methodology and Design
- Start with a minimal FastAPI service that is easy to run and test locally.
- Store data in SQLite for zero-ops persistence.
- Add a tiny rules-based classifier that infers severity and category.
- Send email notifications and a daily digest via SMTP (Mailtrap recommended for dev).
- Provide a simple HTML form and REST endpoints for integrations.
- Connect an OpenEdge ABL agent that posts reports into the API. This demonstrates platform integration and gives a path to expand to full bi-directional sync later.

### High-level Flow
User or ABL Agent -> POST /web/api/reports -> SQLite
 -> Email notification and daily digest via SMTP
 -> CSV export for ops/analytics
 -> Optional HTML form at /web/form

-------------------------------------------------------------------------------

## API Endpoints and Architecture

### Main Endpoints
- POST /web/api/reports
  - Creates a report. Returns id, createdAt, severity, category, tags.
- GET /web/api/reports
  - Lists recent reports. Optional since parameter (ISO8601). Default is last 24 hours.
- GET /web/api/reports/{id}
  - Retrieve a specific report by id.
- GET /web/export/reports.csv
  - CSV export including classifier fields.
- GET /web/admin/send-digest?hours=24
  - Sends a digest email for the last N hours (default 24).
- GET /web/form
  - Simple HTML form to submit a repair report.
- Diagnostics:
  - GET /web/ping
  - GET /web/debug/db
  - GET /web/debug/mail

### Service Components
- FastAPI (Uvicorn) on 127.0.0.1:8812
- SQLite files in .\data
- SMTP via aiosmtplib (async) or smtplib fallback
- Tiny rules classifier in app.py
- Optional OpenEdge ABL agent calling HTTP POST

-------------------------------------------------------------------------------

## Challenges and Best Practices
- Windows curl alias: always call curl.exe explicitly.
- Email: confirm SMTP env vars are loaded (use /web/debug/mail).
- Ports in use: switch Uvicorn port if needed (e.g., 8813).
- Unicode in code files: keep code ASCII to avoid encoding issues in Windows terminals.
- OpenEdge PROPATH: ensure OpenEdge.Core.pl and OpenEdge.Net.pl are present in PROPATH when running ABL HTTP client.
- Keep the service stateless; persist only in SQLite; make scheduled tasks call HTTP endpoints.

-------------------------------------------------------------------------------

## Outcomes and Next Steps
Outcomes delivered:
- Working REST API with storage, classification, notifications, digest, and CSV.
- HTML form for quick manual entry.
- ABL agent example posting into the API.
- Windows Task Scheduler job for daily digest.

Next steps:
- Replace rules-based classifier with an LLM or on-prem model endpoint.
- File uploads and object storage for photos.
- Enrich with tenant/property master data from OpenEdge DB tables.
- Add operations dashboard (queues, filters, SLAs).

-------------------------------------------------------------------------------

## Setup Instructions (Windows, PowerShell)

### 1) Python and dependencies
Install Python 3.11 or later, then:

```powershell
cd C:\reports-api
pip install fastapi uvicorn aiosqlite aiosmtplib python-dotenv

### 2) .env configuration

Create C:\reports-api.env with SMTP settings. Mailtrap Sandbox example:

SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=2525
SMTP_USER=YOUR_MAILTRAP_USER
SMTP_PASS=YOUR_MAILTRAP_PASS
MAIL_FROM=reports-bot@example.test
MAIL_TO=repairs-team@example.test

# Optional custom DB file path
# REPORTS_DB=C:\reports-api\data\reports.db

### 3. Run the API
py -3 -m uvicorn app:app --host 127.0.0.1 --port 8812 --reload

### 4.Quick tests
# Ping
& "$env:SystemRoot\System32\curl.exe" --noproxy "*" -i "http://127.0.0.1:8812/web/ping"

# Create a report
$req="$env:TEMP\req.json"
'{"tenantId":"T0007","propertyId":"P0123","description":"Black mould around bedroom window; child coughing","photoUrl":"https://example.com/mould.jpg","sourceChannel":"web"}' | Set-Content -Encoding ASCII -Path $req
& "$env:SystemRoot\System32\curl.exe" --noproxy "*" -i -H "Content-Type: application/json" --data-binary "@$req" "http://127.0.0.1:8812/web/api/reports"

# List recent (default: 24h)
& "$env:SystemRoot\System32\curl.exe" --noproxy "*" -i "http://127.0.0.1:8812/web/api/reports"

# Fetch by id (replace N)
& "$env:SystemRoot\System32\curl.exe" --noproxy "*" -i "http://127.0.0.1:8812/web/api/reports/N"

# CSV export
& "$env:SystemRoot\System32\curl.exe" --noproxy "*" -i "http://127.0.0.1:8812/web/export/reports.csv"

# Test email
& "$env:SystemRoot\System32\curl.exe" --noproxy "*" -i "http://127.0.0.1:8812/web/test-mail"

# Daily digest (24h)
& "$env:SystemRoot\System32\curl.exe" --noproxy "*" -i "http://127.0.0.1:8812/web/admin/send-digest?hours=24"

### 5.Schedule Digest(Optional)
$job = 'C:\reports-api\jobs'
New-Item -ItemType Directory -Force $job | Out-Null
@'
@echo off
"%SystemRoot%\System32\curl.exe" --noproxy "*" -sS "http://127.0.0.1:8812/web/admin/send-digest?hours=24" >NUL
'@ | Set-Content -Path "$job\send_digest.cmd" -Encoding ASCII
schtasks /Create /SC DAILY /ST 08:30 /TN "ReportsAPI Digest" /TR "C:\reports-api\jobs\send_digest.cmd" /F


OpenEdge (ABL) Integration

Minimal ABL program to POST a report into the API:
/* syncReports.p */
USING OpenEdge.Net.HTTP.* FROM PROPATH.
USING OpenEdge.Core.* FROM PROPATH.
USING Progress.Json.ObjectModel.* FROM PROPATH.

DEFINE VARIABLE oCli AS IHttpClient     NO-UNDO.
DEFINE VARIABLE oReq AS IHttpRequest    NO-UNDO.
DEFINE VARIABLE oRes AS IHttpResponse   NO-UNDO.
DEFINE VARIABLE oJ   AS JsonObject      NO-UNDO.

oCli = ClientBuilder:Build():Client.
oJ = NEW JsonObject().
oJ:Add("tenantId",     "T0007").
oJ:Add("propertyId",   "P0123").
oJ:Add("description",  "ABL agent test message").
oJ:Add("photoUrl",     "https://example.com/photo.jpg").
oJ:Add("sourceChannel","abl-agent").

oReq = RequestBuilder:Post("http://127.0.0.1:8812/web/api/reports")
       :ContentType("application/json")
       :Entity(oJ)
       :Request.

oRes = oCli:Execute(oReq).
MESSAGE "Status:" oRes:StatusCode SKIP "Body:" oRes:Entity:GetJsonText()
    VIEW-AS ALERT-BOX INFO.

Ensure PROPATH includes:

%DLC%\gui

%DLC%\tty

%DLC%\gui\OpenEdge.Core.pl

%DLC%\gui\netlib\OpenEdge.Net.pl

The folder that contains syncReports.p

Run from Windows:
$env:PROPATH = "$env:DLC\gui;$env:DLC\tty;$env:DLC\gui\OpenEdge.Core.pl;$env:DLC\gui\netlib\OpenEdge.Net.pl;C:\OpenEdge\WRK\oepas1\openedge\mayor\agent"
& "$env:DLC\bin\prowin.exe" -b -p "C:\OpenEdge\WRK\oepas1\openedge\mayor\agent\syncReports.p"

Troubleshooting

If PowerShell opens its own curl alias, call curl.exe explicitly.

If /web/test-mail returns 500, check /web/debug/mail and your .env values.

If port is in use, change Uvicorn port in the run command.

If ABL HTTP compile errors appear, verify PROPATH contains OpenEdge.Core.pl and OpenEdge.Net.pl.

If SQLite errors appear on startup, delete data\reports.db and let the API recreate it.
