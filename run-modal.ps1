$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$modalExe = Join-Path $projectRoot ".venv\Scripts\modal.exe"
$scriptPath = Join-Path $projectRoot "orchestrator.py"

if (-not (Test-Path $modalExe)) {
    throw "Modal CLI not found at $modalExe. Recreate the virtual environment or reinstall modal."
}

& $modalExe run $scriptPath
