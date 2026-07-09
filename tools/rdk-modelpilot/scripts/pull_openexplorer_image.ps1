# RDK ModelPilot OpenExplorer image pull
$ErrorActionPreference = "Stop"
docker pull openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8
docker run --rm openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8 hb_mapper --help
