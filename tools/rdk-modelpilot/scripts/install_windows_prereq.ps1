# RDK ModelPilot Windows prerequisite helper
# Run as Administrator when prompted by the application.
$ErrorActionPreference = "Stop"
Write-Host "Enabling WSL and Virtual Machine Platform..."
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
wsl --set-default-version 2
Write-Host "If Ubuntu is missing, install it with:"
Write-Host "  wsl --install -d Ubuntu-22.04"
Write-Host "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ or via winget:"
Write-Host "  winget install Docker.DockerDesktop"
Write-Host "A Windows restart may be required."
