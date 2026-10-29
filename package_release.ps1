<#
.SYNOPSIS
  Turns dist\WhisperOffline into files you can upload to a GitHub Release.

.DESCRIPTION
  GitHub Releases accept files up to 2 GB each, and the full app (with the
  bundled models) is roughly 7 GB. This script:
    1. zips dist\WhisperOffline into release\WhisperOffline-<version>.zip
    2. splits the zip into parts below the 2 GB limit (.zip.001, .zip.002, ...)
    3. writes "Combine-WhisperOffline.bat", which downloaders double-click to
       rebuild the zip using only built-in Windows tools
    4. writes SHA256SUMS.txt so anyone can verify their download

  Upload everything in the release\ folder to the GitHub Release.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File package_release.ps1 -Version v1.0
#>
param(
    [string]$Version = "v1.0",
    [int]$PartSizeMB = 1900
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$appDir = Join-Path $PSScriptRoot "dist\WhisperOffline"
$outDir = Join-Path $PSScriptRoot "release"
$zipName = "WhisperOffline-$Version.zip"
$zipPath = Join-Path $outDir $zipName

if (-not (Test-Path -LiteralPath (Join-Path $appDir "WhisperOffline.exe"))) {
    throw "dist\WhisperOffline\WhisperOffline.exe not found. Run build_offline_bundle_windows.bat first."
}
if (Test-Path -LiteralPath (Join-Path $appDir "gpu")) {
    throw "dist\WhisperOffline\gpu exists (probably from testing the GPU add-on). Delete it first: the add-on ships as its own download."
}

# Drop any per-machine leftovers so they don't ship in the release.
#   - first_run.py's marker, so every downloader gets first-run setup
#   - the hidden flag first_run.py puts on _internal after a test launch
Remove-Item -LiteralPath (Join-Path $appDir "_internal\.setup_done") -Force -ErrorAction SilentlyContinue
$internal = Get-Item -LiteralPath (Join-Path $appDir "_internal") -Force
$internal.Attributes = $internal.Attributes -band (-bnot [System.IO.FileAttributes]::Hidden)
Remove-Item -LiteralPath (Join-Path $appDir "processed") -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath (Join-Path $appDir "DropAudioHere") -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# Clear this script's previous output only, so a GPU add-on zip built by
# build_gpu_addon.ps1 stays in release\.
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
Get-ChildItem -LiteralPath $outDir -File | Where-Object {
    $_.Name -like "WhisperOffline-$Version.zip*" -or $_.Name -in @("Combine-WhisperOffline.bat", "SHA256SUMS.txt")
} | Remove-Item -Force

# Zip with .NET (supports files over 2 GB, unlike Compress-Archive on PowerShell 5.1).
# Keep the empty DropAudioHere folder in the zip by adding a placeholder.
foreach ($sub in @("DropAudioHere")) {
    Set-Content -LiteralPath (Join-Path $appDir "$sub\.keep") -Value "" -Encoding ascii
}
Write-Host "Zipping $appDir (this takes a while)..."
# Windows PowerShell's .NET writes zip entry paths with backslashes unless told
# otherwise; the zip format (and tools like 7-Zip) expect forward slashes.
[System.AppContext]::SetSwitch("Switch.System.IO.Compression.ZipFile.UseBackslash", $false)
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $appDir, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)

$partSize = [int64]$PartSizeMB * 1MB
$zipSize = (Get-Item -LiteralPath $zipPath).Length
$assets = @()

if ($zipSize -le $partSize) {
    Write-Host "Zip is under the size limit; no split needed."
    $assets += $zipName
} else {
    Write-Host ("Splitting {0:N1} GB zip into {1} MB parts..." -f ($zipSize / 1GB), $PartSizeMB)
    $buffer = New-Object byte[] (4MB)
    $in = [System.IO.File]::OpenRead($zipPath)
    try {
        $index = 0
        while ($in.Position -lt $in.Length) {
            $index++
            $partName = "{0}.{1:D3}" -f $zipName, $index
            $out = [System.IO.File]::Create((Join-Path $outDir $partName))
            try {
                $written = [int64]0
                while ($written -lt $partSize) {
                    $toRead = [int][Math]::Min($buffer.Length, $partSize - $written)
                    $read = $in.Read($buffer, 0, $toRead)
                    if ($read -le 0) { break }
                    $out.Write($buffer, 0, $read)
                    $written += $read
                }
            } finally {
                $out.Dispose()
            }
            $assets += $partName
        }
    } finally {
        $in.Dispose()
    }
    Remove-Item -LiteralPath $zipPath

    $copyArgs = ($assets | ForEach-Object { '"' + $_ + '"' }) -join " + "
    $combine = @"
@echo off
rem Rebuilds $zipName from its downloaded parts.
rem Put this file in the same folder as all the $zipName.### parts, then double-click it.
cd /d "%~dp0"
for %%P in ($($assets -join " ")) do (
  if not exist "%%P" (
    echo Missing part: %%P
    echo Download every $zipName.### file from the release into this folder, then try again.
    pause
    exit /b 1
  )
)
echo Combining parts into $zipName ...
copy /b $copyArgs "$zipName" >nul
if errorlevel 1 (
  echo Combining failed.
  pause
  exit /b 1
)
echo.
echo Done. Now right-click $zipName and choose "Extract All...".
echo You can delete the .### part files afterwards.
pause
"@
    $combinePath = Join-Path $outDir "Combine-WhisperOffline.bat"
    # Batch files need CRLF line endings and plain ASCII.
    [System.IO.File]::WriteAllText($combinePath, ($combine -replace "`r?`n", "`r`n"), [System.Text.Encoding]::ASCII)
    $assets += "Combine-WhisperOffline.bat"
}

foreach ($sub in @("DropAudioHere")) {
    Remove-Item -LiteralPath (Join-Path $appDir "$sub\.keep") -ErrorAction SilentlyContinue
}

# Checksums cover everything in release\, including a GPU add-on zip if present.
$sums = Get-ChildItem -LiteralPath $outDir -File | Where-Object Name -ne "SHA256SUMS.txt" | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)"
}
Set-Content -LiteralPath (Join-Path $outDir "SHA256SUMS.txt") -Value $sums -Encoding ascii

Write-Host ""
Write-Host "Release files are ready in: $outDir"
Get-ChildItem -LiteralPath $outDir | ForEach-Object { "  {0,-40} {1,8:N0} MB" -f $_.Name, ($_.Length / 1MB) }
Write-Host ""
Write-Host "Upload all of these to a new GitHub Release (tag $Version)."
