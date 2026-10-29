<#
.SYNOPSIS
  Builds the optional NVIDIA GPU add-on for Whisper Offline.

.DESCRIPTION
  The add-on is a "gpu" folder that users move into their WhisperOffline
  folder. When the app finds it and an NVIDIA GPU with a working driver, it
  runs Whisper on the GPU; otherwise it keeps using the CPU.

  The folder holds NVIDIA's cuBLAS 12 and cuDNN 8.9.7 runtime libraries (the
  versions CTranslate2 4.3.1 was built for), zlibwapi.dll that cuDNN loads
  on Windows, a README and the license files.

  Needs internet and the whisper-offline-build Conda environment. The NVIDIA
  wheels (about 1.1 GB) come from PyPI, pinned by hash in
  packaging\gpu-addon-requirements.txt.

  Output: release\WhisperOffline-GPU-addon-<version>.zip (about 1 GB), and an
  updated release\SHA256SUMS.txt.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File build_gpu_addon.ps1 -Version v1.0
#>
param(
    [string]$Version = "v1.0"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
# Windows PowerShell's .NET writes zip entry paths with backslashes unless told
# otherwise; the zip format (and tools like 7-Zip) expect forward slashes.
[System.AppContext]::SetSwitch("Switch.System.IO.Compression.ZipFile.UseBackslash", $false)
Add-Type -AssemblyName System.IO.Compression.FileSystem

$envName = "whisper-offline-build"
$wheelDir = Join-Path $PSScriptRoot "build\gpu-wheels"
$stage = Join-Path $PSScriptRoot "build\gpu-addon"
$gpuDir = Join-Path $stage "gpu"
$licenseDir = Join-Path $gpuDir "licenses"
$outDir = Join-Path $PSScriptRoot "release"
$zipName = "WhisperOffline-GPU-addon-$Version.zip"
$zipPath = Join-Path $outDir $zipName

# DLLs taken from each wheel. CTranslate2 needs cublas64_12.dll (which loads
# cublasLt64_12.dll) and cudnn64_8.dll, which loads cuDNN's *_infer libraries.
# The *_train libraries are only needed for training, so they are left out.
$wanted = [ordered]@{
    "nvidia_cublas_cu12" = @("cublas64_12.dll", "cublasLt64_12.dll")
    "nvidia_cudnn_cu12"  = @("cudnn64_8.dll", "cudnn_ops_infer64_8.dll", "cudnn_cnn_infer64_8.dll", "cudnn_adv_infer64_8.dll")
}

$conda = Get-Command conda -ErrorAction SilentlyContinue
if (-not $conda -and $env:CONDA_EXE) { $conda = Get-Command $env:CONDA_EXE }
if (-not $conda) { throw "Conda not found. Install Miniconda, or run this from an Anaconda/Miniconda PowerShell." }

function Invoke-EnvPython([string[]]$PythonArgs) {
    $output = & $conda run -n $envName python @PythonArgs
    if ($LASTEXITCODE) { throw "python $($PythonArgs -join ' ') failed in the $envName environment." }
    return $output
}

Write-Host "Downloading NVIDIA libraries (pinned by hash)..."
Invoke-EnvPython @("-m", "pip", "download", "-r", "packaging\gpu-addon-requirements.txt",
    "--require-hashes", "--no-deps", "--only-binary=:all:", "-d", $wheelDir, "--progress-bar", "off") | Out-Null

if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Path $licenseDir -Force | Out-Null

foreach ($package in $wanted.Keys) {
    $wheel = Get-ChildItem -LiteralPath $wheelDir -Filter "$package-*.whl" | Select-Object -First 1
    if (-not $wheel) { throw "No $package wheel in $wheelDir." }
    Write-Host "Extracting from $($wheel.Name)..."
    $zip = [System.IO.Compression.ZipFile]::OpenRead($wheel.FullName)
    try {
        foreach ($dll in $wanted[$package]) {
            $entry = $zip.Entries | Where-Object { $_.Name -eq $dll } | Select-Object -First 1
            if (-not $entry) { throw "$dll not found in $($wheel.Name)." }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $gpuDir $dll), $true)
        }
        $license = $zip.Entries | Where-Object { $_.FullName -match '\.dist-info/License\.txt$' } | Select-Object -First 1
        if (-not $license) { throw "No License.txt in $($wheel.Name)." }
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($license, (Join-Path $licenseDir "NVIDIA-$($package -replace '_', '-')-License.txt"), $true)
    } finally {
        $zip.Dispose()
    }
}

# zlibwapi.dll and its license come from the conda-forge zlib-wapi package in
# the build environment (see environment_offline.yml).
$prefix = (Invoke-EnvPython @("-c", "import sys; print(sys.prefix)") | Select-Object -Last 1).Trim()
$zlib = Join-Path $prefix "Library\bin\zlibwapi.dll"
if (-not (Test-Path -LiteralPath $zlib)) {
    throw "zlibwapi.dll not found in $prefix. Update the environment: conda env update -n $envName -f environment_offline.yml"
}
Copy-Item -LiteralPath $zlib -Destination $gpuDir
$zlibMeta = Get-ChildItem -LiteralPath (Join-Path $prefix "conda-meta") -Filter "libzlib-wapi-*.json" | Select-Object -First 1
$zlibPkgDir = (Get-Content -LiteralPath $zlibMeta.FullName -Raw | ConvertFrom-Json).extracted_package_dir
Copy-Item -LiteralPath (Join-Path $zlibPkgDir "info\licenses\LICENSE") -Destination (Join-Path $licenseDir "zlib-LICENSE.txt")

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "packaging\README_GPU.txt") -Destination $gpuDir
$versions = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "packaging\gpu-addon-requirements.txt") |
    Where-Object { $_ -match '^nvidia-' } | ForEach-Object { ($_ -split ' ')[0] }) -join ", "
Set-Content -LiteralPath (Join-Path $gpuDir "addon-version.txt") -Encoding ascii -Value @(
    "Whisper Offline GPU add-on $Version",
    "Contents: $versions, zlib-wapi"
)

New-Item -ItemType Directory -Path $outDir -Force | Out-Null
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Write-Host "Zipping the add-on (this takes a few minutes)..."
# Zip root is the gpu\ folder itself, so users can drag it straight out.
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $stage, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)

$size = (Get-Item -LiteralPath $zipPath).Length
if ($size -ge 2GB) { throw "$zipName is $([math]::Round($size / 1GB, 2)) GB, over GitHub's 2 GB per-file limit." }

# Refresh checksums for everything in release\, including the main app parts.
$sums = Get-ChildItem -LiteralPath $outDir -File | Where-Object Name -ne "SHA256SUMS.txt" | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)"
}
Set-Content -LiteralPath (Join-Path $outDir "SHA256SUMS.txt") -Value $sums -Encoding ascii

Write-Host ""
Write-Host ("GPU add-on ready: {0} ({1:N0} MB)" -f $zipPath, ($size / 1MB))
Write-Host "Upload it to the same GitHub Release as the main app, along with the updated SHA256SUMS.txt."
