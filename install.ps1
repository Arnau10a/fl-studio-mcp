<#
.SYNOPSIS
    One-command Windows installer for fl-studio-mcp.
#>
$ErrorActionPreference = "Stop"

Write-Host "==> Checking uv installation..." -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "==> Syncing Python dependencies..." -ForegroundColor Cyan
uv sync --locked

Write-Host "==> Installing FL Studio controller & Piano Roll scripts..." -ForegroundColor Cyan
uv run python scripts/install_fl_script.py

Write-Host "==> Running diagnostics (fl-studio-mcp-doctor)..." -ForegroundColor Cyan
uv run fl-studio-mcp-doctor

$repoPath = (Get-Location).Path
$pythonPath = Join-Path $repoPath ".venv\Scripts\python.exe"
$serverPath = Join-Path $repoPath "server.py"

Write-Host ""
Write-Host "Setup complete! Add this to your MCP client config:" -ForegroundColor Green
Write-Host @"
{
  "mcpServers": {
    "fl-studio": {
      "command": "$($pythonPath -replace '\\', '\\')",
      "args": ["$($serverPath -replace '\\', '\\')"]
    }
  }
}
"@
