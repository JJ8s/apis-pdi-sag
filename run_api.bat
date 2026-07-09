@echo off
python -m uvicorn api_server:app --host 0.0.0.0 --port 8090 --reload
pause
