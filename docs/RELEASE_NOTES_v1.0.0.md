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

No model files are attached. The discovered `.pt`, `.onnx`, and Bayes-E `.bin`
match the documented interface, but contain embedded build/training paths and
their training-data redistribution rights could not be confirmed. See
`models/model_manifest.json`.

## Safety

ARGUS is a research and engineering prototype. It does not replace a certified
industrial safety system, emergency stop, mechanical limit, guarding, or
trained human supervision.
