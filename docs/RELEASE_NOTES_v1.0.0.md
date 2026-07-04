# ARGUS v1.0.0 — Public Research Prototype

Initial public release of the ARGUS RDK X5 + ESP32 edge-vision active safety
intervention prototype.

## Included

- online FastAPI/WebSocket dashboard mode;
- offline local-preview mode;
- three-class PPE detection post-processing contract;
- lightweight tracking, temporal risk reasoning, and multi-target arbitration;
- actuator execution state machine and serial bridge;
- ESP32 pan/tilt and buzzer firmware;
- safe example configuration with hardware disabled by default;
- RDK X5 deployment, wiring, protocol, calibration, model, and safety guides;
- hardware-free unit tests and GitHub Actions CI.

## Model assets

With explicit authorization from the project owner, these normalized model
files are attached to this release:

- `argus_ppe_dfl_640.pt`;
- `argus_ppe_dfl_640.onnx`;
- `argus_ppe_dfl_640_rdkx5.bin`.

They remain excluded from Git history. The artifacts contain embedded
build/training paths; downstream users should verify applicable dataset,
weight, and toolchain licenses. Sizes and SHA-256 checksums are recorded in
`models/model_manifest.json`.

## Safety

ARGUS is a research and engineering prototype. It does not replace a certified
industrial safety system, emergency stop, mechanical limit, guarding, or
trained human supervision.
