[CmdletBinding()]
param(
    [string]$Path = (Get-Location).Path
)

$scriptPath = Join-Path -Path $PSScriptRoot -ChildPath "folder-sizes.ps1"

if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    Write-Error "Script not found: $scriptPath"
    exit 1
}

& $scriptPath -Path $Path