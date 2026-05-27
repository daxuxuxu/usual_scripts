[CmdletBinding()]
param(
    [string]$Path = (Get-Location).Path
)

function Format-Size {
    param(
        [Int64]$Bytes
    )

    if ($Bytes -ge 1TB) {
        return "{0:N2} TB" -f ($Bytes / 1TB)
    }

    if ($Bytes -ge 1GB) {
        return "{0:N2} GB" -f ($Bytes / 1GB)
    }

    if ($Bytes -ge 1MB) {
        return "{0:N2} MB" -f ($Bytes / 1MB)
    }

    if ($Bytes -ge 1KB) {
        return "{0:N2} KB" -f ($Bytes / 1KB)
    }

    return "{0} B" -f $Bytes
}

if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
    Write-Error "Path not found or is not a directory: $Path"
    exit 1
}

$directories = Get-ChildItem -LiteralPath $Path -Directory -Force -ErrorAction Stop

if (-not $directories) {
    Write-Host "No subdirectories found under $Path"
    exit 0
}

$results = foreach ($directory in $directories) {
    $sizeBytes = (Get-ChildItem -LiteralPath $directory.FullName -File -Recurse -Force -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum

    if ($null -eq $sizeBytes) {
        $sizeBytes = 0
    }

    [PSCustomObject]@{
        SizeBytes = [int64]$sizeBytes
        Size      = Format-Size -Bytes $sizeBytes
        Folder    = $directory.Name
    }
}

$results |
    Sort-Object -Property SizeBytes -Descending |
    Select-Object Size, Folder |
    Format-Table -AutoSize