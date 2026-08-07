$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Cli = Join-Path $ProjectRoot '.venv\Scripts\magibu-toolcall.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Create .venv and install .[dev] before verification.'
}
if (-not (Test-Path -LiteralPath $Cli)) {
    throw 'Install the magibu-toolcall project in editable mode before verification.'
}

& $Python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Cli registry validate (Join-Path $ProjectRoot 'registry\registry.jsonl')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Cli dataset validate (Join-Path $ProjectRoot 'tests\fixtures\dataset\valid_single_tool.json')
exit $LASTEXITCODE
