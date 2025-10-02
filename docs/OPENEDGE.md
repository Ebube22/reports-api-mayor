# OpenEdge Integration Plan

- We prepared ABL agent stubs (openedge/mayor/agent/*.p) that call the HTTP API.
- On this machine the GUI runtime prompts (license components) prevented automated compile,
  so we parked the live agent demo. However:
  - ABL sources show how it POSTs into the FastAPI (/web/api/reports).
  - The same endpoints are consumable by PASOE (OEWebServlet) when enabled.
- Next steps (post-hackathon):
  1) Install full ABL dev components or use a licensed container image.
  2) Compile stubs with a -pf that adds OpenEdge.Core.pl + OpenEdge.Net.pl to PROPATH.
  3) Run the agent on a schedule; or expose the API to PASOE and bind a WebHandler.

This keeps the OpenEdge story intact: ABL ↔ FastAPI, and a clean migration path to PASOE.
