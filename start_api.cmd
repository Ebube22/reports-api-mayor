@echo off
set PORT=8812
py -3 -m uvicorn app:app --host 127.0.0.1 --port %PORT% --reload
