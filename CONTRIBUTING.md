# Contributing

Contributions are welcome through GitHub issues and pull requests.

## Principles

- Keep hardware, servo, buzzer, light, and LLM output disabled by default.
- Do not commit models, datasets, calibration images, videos, credentials, or private configuration.
- Preserve compatibility with Python 3.10 and the RDK X5 system runtime.
- Keep BPU/camera/ESP32 tests out of mandatory CI; provide a clear manual test record instead.
- Document GPIO, power, mechanical-limit, serial-protocol, and rollback implications for hardware changes.
- Do not describe research results as certified safety performance.

## Before opening a pull request

```bash
python3 -m compileall -q online offline tests scripts
python3 -m unittest discover -s tests -v
python3 scripts/validate_repository.py
```

Explain the tested platform, RDK image/toolchain version, model interface, and any connected hardware.
