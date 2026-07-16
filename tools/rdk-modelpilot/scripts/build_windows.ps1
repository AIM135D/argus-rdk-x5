$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$config = Get-Content -Raw -Encoding UTF8 (Join-Path $projectRoot "config.json") | ConvertFrom-Json

$condaCandidates = @()
$condaCommand = Get-Command conda -ErrorAction SilentlyContinue
if ($condaCommand) {
    $condaCandidates += $condaCommand.Source
}
$condaCandidates += @(
    "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
    "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
    "C:\ProgramData\anaconda3\Scripts\conda.exe",
    "D:\ANACONDA\Scripts\conda.exe",
    "D:\Anaconda3\Scripts\conda.exe",
    "D:\Miniconda3\Scripts\conda.exe"
)
$conda = $condaCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $conda) {
    throw "Conda/Anaconda was not found. Install it or add conda to PATH."
}

$envList = (& $conda env list --json | ConvertFrom-Json).envs
$envPath = $envList | Where-Object { (Split-Path $_ -Leaf) -eq $config.conda_env } | Select-Object -First 1
if (-not $envPath) {
    throw "Conda environment '$($config.conda_env)' was not found."
}
$python = Join-Path $envPath "python.exe"
$dllDir = Join-Path $envPath "Library\bin"

Push-Location $projectRoot
try {
    & $python -m pip install -r "backend\requirements.txt" pyinstaller

    $pyInstallerArgs = @(
        "-m", "PyInstaller", "backend\main.py",
        "--name", "rdk-modelpilot-backend",
        "--onefile",
        "--distpath", "backend_dist",
        "--workpath", "build\backend_pyinstaller",
        "--specpath", "build",
        "--clean",
        "--noconfirm"
    )
    foreach ($dll in @("libexpat.dll", "liblzma.dll", "libbz2.dll", "ffi.dll")) {
        $dllPath = Join-Path $dllDir $dll
        if (-not (Test-Path -LiteralPath $dllPath)) {
            throw "Required Conda runtime DLL is missing: $dllPath"
        }
        $pyInstallerArgs += @("--add-binary", "$dllPath;.")
    }
    & $python @pyInstallerArgs

    & npm.cmd --prefix frontend ci
    & npm.cmd --prefix frontend run package:win

    $portable = Get-ChildItem -LiteralPath "frontend\release" -Filter "RDK ModelPilot*.exe" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $portable) {
        throw "Electron portable executable was not generated."
    }
    Copy-Item -LiteralPath $portable.FullName -Destination (Join-Path $projectRoot "RDK ModelPilot.exe") -Force
    Write-Host "Built: $(Join-Path $projectRoot 'RDK ModelPilot.exe')"
}
finally {
    Pop-Location
}
