@echo off
REM Build NQ-KLine.exe on Windows (needs Python 3.10+ on PATH)
python -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt || exit /b 1
pyinstaller --noconfirm --clean --onefile --windowed --name NQ-KLine ^
  --add-data "nqkline\static;nqkline\static" ^
  --collect-submodules webview ^
  --collect-all databento ^
  --collect-submodules anthropic ^
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan.on ^
  run.py || exit /b 1
echo.
echo Done: dist\NQ-KLine.exe
