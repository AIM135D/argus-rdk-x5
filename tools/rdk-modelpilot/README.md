# RDK ModelPilot

Windows 一键把自训练 YOLO `.pt` 转成 RDK X5 可部署的 ONNX 与 bayes-e INT8 `.bin`。

RDK ModelPilot 是一个面向 RDK X5 用户的轻量部署助手：自动检测 Windows / WSL / Docker / OpenExplorer / rdk_model_zoo 环境，自动调用 D-Robotics 官方导出脚本，检查 ONNX 六输出 DFL 结构，封装 OpenExplorer Docker 量化编译，并生成板端部署配置与 Markdown 报告。

相比手动配置 Studio、WSL、Docker、OpenExplorer 和各种脚本参数，它更适合“我已经训练好了模型，现在只想尽快得到能上板的 `.bin`”这个场景。

## Highlights

- One-click Windows workflow for RDK X5 model conversion
- YOLO `.pt` → RDK-friendly ONNX → bayes-e INT8 `.bin`
- Auto environment check and repair scripts
- Uses D-Robotics `rdk_model_zoo` `export_monkey_patch.py` by default
- ONNX six-output DFL structure validation
- Calibration image quality report
- OpenExplorer Docker quantization wrapper
- Auto-generated `deploy_config.py`
- Auto-generated `deploy_report.md`
- Chinese / English UI
- Supports 1 to 10 detection classes in the MVP

## What It Is Not

RDK ModelPilot is not a replacement for RDK Studio. It does not try to be a general IDE, board flashing tool, remote project manager, training platform, annotation tool, AI assistant, or NodeHub publisher.

It focuses on one workflow:

```text
environment check
→ install / repair helper scripts
→ select .pt, data.yaml, calibration images
→ export ONNX with D-Robotics script
→ validate RDK X5 YOLO DFL six-output structure
→ build bayes-e INT8 .bin with OpenExplorer
→ generate deploy_config.py and deploy_report.md
```

## Supported Models

The MVP targets YOLO detection models exported through:

```text
rdk_model_zoo/samples/vision/ultralytics_yolo/x86/export_monkey_patch.py
```

Current MVP class range:

```text
1 to 10 detection classes
```

Segmentation, pose, classification, old anchor-style YOLOv5 exports, and generic Ultralytics single-output ONNX exports are not the first-stage target.

## Recommended Environment

- Windows 10 / 11
- Python 3.10+
- Git
- WSL2, default `Ubuntu-22.04`
- Docker Desktop or Docker Engine
- D-Robotics `rdk_model_zoo`
- OpenExplorer image:

```text
openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8
```

Conda / Anaconda is treated as a model export environment. If `conda` is not in PATH, the app shows it as a warning instead of a blocking Windows environment error.

## Default Paths

Defaults can be changed in the Settings page.

```json
{
  "project_dir": "D:\\RDK_ModelPilot",
  "output_dir": "D:\\RDK_ModelPilot_Output",
  "rdk_model_zoo_windows": "D:\\rdk_model_zoo-main",
  "rdk_model_zoo_wsl": "/mnt/d/rdk_model_zoo-main",
  "conda_env": "yolo",
  "wsl_distro": "Ubuntu-22.04",
  "docker_image": "openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8"
}
```

## Development

Backend:

```powershell
cd RDK-ModelPilot
python -m pip install -r backend\requirements.txt
python backend\main.py
```

Frontend:

```powershell
cd RDK-ModelPilot
npm --prefix frontend install
npm --prefix frontend run electron:dev
```

Build frontend:

```powershell
npm --prefix frontend run build
```

Package Windows folder:

```powershell
python -m PyInstaller backend\main.py --name rdk-modelpilot-backend --onefile --distpath backend_dist --workpath build\backend_pyinstaller --specpath build --clean --noconfirm
npm --prefix frontend run build
cd frontend
npx electron-builder --win dir --x64
```

## Output Layout

Each conversion creates an isolated task folder:

```text
D:\RDK_ModelPilot_Output\model_name_timestamp\
├── input\
├── onnx\
├── bin\
├── calibration\selected_images\
├── reports\
├── configs\
└── logs\
```

Key artifacts:

- `onnx/*.onnx`
- `bin/*_bayese_640x640_nv12.bin`
- `configs/deploy_config.py`
- `configs/quant_config.yaml`
- `reports/deploy_report.md`
- `reports/onnx_structure_report.md`
- `reports/calibration_report.md`
- `logs/export_onnx.log`
- `logs/checker.log`
- `logs/makertbin.log`

## Board-Side Validation

Copy artifacts to the RDK X5 board:

```bash
scp model.bin root@<RDK_X5_IP>:/userdata/model.bin
scp deploy_config.py root@<RDK_X5_IP>:/userdata/deploy_config.py
ssh root@<RDK_X5_IP>
```

Check model information:

```bash
hrt_model_exec model_info --model_file /userdata/model.bin
```

Run a quick performance check:

```bash
hrt_model_exec perf --model_file /userdata/model.bin
```

## Why Not Old YOLOv5 Anchor Postprocess

RDK X5 YOLO DFL six-output models normally use:

```text
CLS_OUTPUTS = [0, 2, 4]
BOX_OUTPUTS = [1, 3, 5]
STRIDES = [8, 16, 32]
REG = 16
```

Old YOLOv5 anchor postprocess chains such as `Yolov5PostProcess`, `Yolov5doProcess`, or legacy `libpostprocess.so` may produce no boxes, shifted boxes, wrong classes, or abnormal false positives when used with DFL six-output models.

## Why Use D-Robotics export_monkey_patch.py

Generic `ultralytics model.export()` often generates an ONNX structure that does not match RDK X5 six-output DFL postprocessing. RDK ModelPilot prioritizes the D-Robotics `rdk_model_zoo` export script so the generated ONNX is closer to the expected deployment chain.

## Roadmap

- `.pt` / ONNX / `.bin` inference result comparison
- SSH upload to RDK X5
- Board-side single-image test run
- Cross-stage consistency report
- More RDK model families

## License

MIT is recommended for open-source distribution. Add a `LICENSE` file before publishing a formal release.
