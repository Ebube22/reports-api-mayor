@echo off
REM send last 24h digest; suppress console output
"%SystemRoot%\System32\curl.exe" --noproxy "*" -sS "http://127.0.0.1:8812/web/admin/send-digest?hours=24" >NUL
