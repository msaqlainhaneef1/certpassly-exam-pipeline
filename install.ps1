# Create a venv, install this skill, check system tools, run the regression tests.
# Run from PowerShell:  Set-ExecutionPolicy -Scope Process Bypass; .\install.ps1
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Py = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
if (-not (Test-Path '.venv')) {
  Write-Host "Creating virtualenv at $Root\.venv"
  & $Py -m venv .venv
}
$Activate = Join-Path $Root '.venv\Scripts\Activate.ps1'
. $Activate
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
Write-Host ""
Write-Host "System tools:"
$missing = $false
foreach ($c in @('pdftohtml','pdftoppm','pdftotext')) {
  if (Get-Command $c -ErrorAction SilentlyContinue) {
    Write-Host "  ok  $c"
  } else {
    Write-Host "  MISSING  $c  (poppler)"
    $missing = $true
  }
}
if (Get-Command tesseract -ErrorAction SilentlyContinue) {
  Write-Host "  ok  tesseract (optional)"
} else {
  Write-Host "  note  tesseract not found (optional; used for image-only questions)"
}
if ($missing) {
  Write-Host ""
  Write-Host "Install poppler for Windows and add its Library\bin folder to PATH."
  Write-Host "A common option is the poppler-windows release, then restart PowerShell."
  Write-Host "tesseract is optional: https://github.com/UB-Mannheim/tesseract/wiki"
}
Write-Host ""
Write-Host "Running tests (offline). The full gold-package regression runs only when"
Write-Host "CERTPASSLY_GOLD points at a cached workspace, or when that default path exists."
python -m unittest discover -s tests -v
Write-Host ""
Write-Host "Installed. Try:  certpassly-pipeline --help"
Write-Host "Full pipeline (needs reference/ and config/):  pip install -e .  or set CERTPASSLY_SKILL_ROOT=$Root"
