# ARGUS PPE DFL 640 Model Card

## Intended use

The model contract supports PPE-aware observation in the ARGUS RDK X5 research
prototype. It detects people, helmets, and reflective vests. Its outputs feed
tracking and risk reasoning; detections alone do not directly command hardware.

## Interface

| Field | Value |
|---|---|
| Input | `1×3×640×640` |
| RDK input format | NV12 |
| Classes | `person`, `helmet`, `reflective_vest` |
| Strides | `8`, `16`, `32` |
| DFL reg max | `16` |
| Output count | `6` |
| Class outputs | `0`, `2`, `4` |
| Regression outputs | `1`, `3`, `5` |
| Post-processing | sigmoid, DFL softmax, dist2bbox, class-aware NMS |

## Discovered artifacts

Three candidate artifacts were found next to the final project archive:

- a PyTorch checkpoint;
- an ONNX export;
- a Bayes-E 640×640 NV12 binary.

Their byte sizes and SHA-256 hashes are preserved in `model_manifest.json`.
Strings and metadata confirm the expected three classes and RDK model shape.

## Publication status

Published as normalized assets on the GitHub `v1.0.0` release after explicit
authorization from the project owner. The artifacts remain excluded from Git
history. They contain embedded training/build paths, so downstream users must
still verify that their use complies with the applicable dataset, weight, and
toolchain licenses.

## Limitations

- No public evaluation dataset or metrics accompany this repository.
- Quantization can change accuracy.
- PPE association is performed by downstream geometry and tracking logic.
- Performance must be validated on the target camera, environment, and RDK X5.
- The model and ARGUS must not be treated as a certified safety control.
