$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run launch.bat once, or: python -m venv .venv"
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ClearCommit Teams] Installing build dependency: pyinstaller"
    & $python -m pip install --disable-pip-version-check -r requirements-dev.txt pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }
}

$uiSource = (Get-Item -LiteralPath "ui").FullName

# Live capture is the point of the app, so the audio runtime is collected
# explicitly rather than left to import-graph luck: sounddevice loads
# PortAudio as a DLL at runtime (not a module), and PyAudioWPatch's binary
# extension plus its data folder are easy for the analyser to miss.
& $python -m PyInstaller --noconfirm --clean --windowed `
    --name ClearCommitTeams `
    --add-data "$uiSource;ui" `
    --collect-all webview `
    --collect-all sounddevice `
    --collect-data _sounddevice_data `
    --collect-all pyaudiowpatch `
    --hidden-import sounddevice `
    --hidden-import pyaudiowpatch `
    --hidden-import numpy `
    --hidden-import groq `
    --hidden-import dotenv `
    --distpath dist `
    --workpath build\pyinstaller `
    --specpath build `
    --exclude-module tkinter `
    --exclude-module android `
    app_entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

# The packaged app reads provider keys from a .env next to the exe (see
# app._env_candidates). Copy the checkout's file so the build boots with
# transcription configured instead of failing at the first poll.
$envSource = Join-Path (Get-Location) ".env"
$distDir = Join-Path (Get-Location) "dist\ClearCommitTeams"
if (Test-Path -LiteralPath $envSource) {
    Copy-Item -LiteralPath $envSource -Destination (Join-Path $distDir ".env") -Force
    Write-Host "[ClearCommit Teams] Copied .env next to the exe."
} else {
    Write-Warning "[ClearCommit Teams] No .env found; the build will have no GROQ_API_KEY (live capture will not transcribe)."
}

# Prove the frozen bundle actually carries the audio runtime before shipping.
& $python -c "import sounddevice, pyaudiowpatch; print('audio runtime ok', sounddevice.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Audio runtime is missing from the environment." }

Write-Host "[ClearCommit Teams] Built: dist\ClearCommitTeams\ClearCommitTeams.exe"
