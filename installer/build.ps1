# Builds dist\MeshCoreDesktop\ (PyInstaller) and dist\MeshCoreDesktop-Setup-<ver>.exe (Inno Setup).
# Requirements: the project's .venv with requirements-dev.txt installed, and Inno Setup 6.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

& $py -m PyInstaller --noconfirm --clean --windowed --name MeshCoreDesktop `
    --icon (Join-Path $root "mcd\app.ico") `
    --add-data ((Join-Path $root "mcd\app.ico") + ";mcd") `
    --add-data ((Join-Path $root "mcd\help_pl.md") + ";mcd") `
    --add-data ((Join-Path $root "mcd\help_en.md") + ";mcd") `
    --collect-all winrt --collect-submodules bleak --collect-submodules meshcore `
    --distpath (Join-Path $root "dist") --workpath (Join-Path $root "build") --specpath (Join-Path $root "build") `
    (Join-Path $root "meshcore_desktop.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }
& $iscc (Join-Path $PSScriptRoot "setup.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
