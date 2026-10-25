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

& $python -m PyInstaller --noconfirm --clean --windowed `
    --name ClearCommitTeams `
    --add-data "$uiSource;ui" `
    --collect-all webview `
    --distpath dist `
    --workpath build\pyinstaller `
    --specpath build `
    --exclude-module tkinter `
    --exclude-module android `
    app_entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

Write-Host "[ClearCommit Teams] Built: dist\ClearCommitTeams\ClearCommitTeams.exe"
