# RDK X5 部署指南

## 1. 环境边界

ARGUS 分成主机侧模型转换与 RDK X5 板端运行两部分。`.pt` 到 Bayes-E
INT8 `.bin` 的转换建议在 Windows 10/11 + WSL2 Ubuntu 22.04 或 x86
Linux 完成；macOS 不保证能够运行 X5 编译工具链。

### 主机侧模型转换依赖

- Windows 10/11 或 x86 Linux；
- WSL2 Ubuntu 22.04；
- Python 3.10；
- Conda 环境 `rdk_yolo`；
- Docker；
- D-Robotics `rdk_model_zoo`；
- `openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8`；
- `ultralytics`、`torch`、`torchvision`；
- `onnx`、`onnxruntime`；
- `numpy`、`opencv-python`、`scipy`、`pyyaml`。

### RDK X5 板端依赖

- Ubuntu 22.04；
- Python 3.10；
- RDK X5 BPU Runtime；
- `hobot_dnn` / `pyeasy_dnn`；
- `hrt_model_exec`；
- OpenCV、NumPy、SciPy；
- FastAPI、Uvicorn、WebSocket、pyserial；
- USB 或 MIPI 摄像头支持。

`hobot_dnn`、BPU Runtime 和 `hrt_model_exec` 主要由 RDK X5 系统环境提供。
不要用通用 PyPI 包替代板卡系统组件。

## 2. 获取代码

```bash
git clone https://github.com/AIM135D/argus-rdk-x5.git
cd argus-rdk-x5
```

## 3. 准备配置

```bash
cp configs/runtime.example.yaml configs/runtime.yaml
cp configs/danger_zones.example.json configs/danger_zones.runtime.json
cp configs/servo_calibration.example.json configs/servo_calibration.runtime.json
```

第一次启动保持：

```yaml
hardware_enabled: false
servo_enabled: false
buzzer_enabled: false
light_enabled: false
llm_bridge_enabled: false
host: 127.0.0.1
```

## 4. 放置并检查模型

模型默认位置：

```text
models/argus_ppe_dfl_640_rdkx5.bin
```

板端检查：

```bash
hrt_model_exec model_info \
  --model_file models/argus_ppe_dfl_640_rdkx5.bin

hrt_model_exec perf \
  --model_file models/argus_ppe_dfl_640_rdkx5.bin
```

检查结果应与 [模型流水线](MODEL_PIPELINE.md) 中的 640×640 NV12、
三类别和六输出约束一致。

## 5. 安装 Python 依赖

建议先使用 RDK 镜像自带的 OpenCV/NumPy；缺少的通用依赖再通过 pip 安装：

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

如果 pip 尝试替换板端 OpenCV 或 NumPy 并与 `hobot_dnn` 冲突，应恢复板卡系统包，
再仅安装 FastAPI、Uvicorn、PyYAML 和 pyserial。

## 6. 无硬件启动

```bash
./online/check_system.sh
./online/start.sh
```

在板卡本机打开：

```text
http://127.0.0.1:8000
```

需要受信任局域网访问时，将 `host` 显式改为 `0.0.0.0`，并通过防火墙限制来源。
该 Web 服务不包含公网身份认证。

## 7. 启用 ESP32

完成 [接线](HARDWARE_AND_WIRING.md)、[串口协议](SERIAL_PROTOCOL.md) 和
[标定](CALIBRATION.md) 后，再修改：

```yaml
hardware_enabled: true
servo_enabled: true
buzzer_enabled: true
esp32_port: /dev/ttyUSB0
esp32_protocol: A
```

不要在启动脚本中自动执行 `sudo chmod 666`。应通过 udev 规则或把运行用户加入正确的
串口组来授予最小权限。

## 8. 离线预览

```bash
./offline/start.sh
```

离线目录保留 OpenCV 本地预览路径；仍需要 RDK X5 BPU Runtime 和兼容模型。

## 9. 常见错误

- `ARGUS model not found`：检查模型位置或设置 `ARGUS_MODEL_PATH`；
- `hobot_dnn unavailable`：确认板卡镜像和 BPU Runtime，而不是普通桌面 Python；
- 串口不可用：检查设备节点、用户组、线缆与 ESP32 串口监视器；
- 输出形状不匹配：模型不是当前 3 类、DFL16、六输出配置；
- 浏览器无法访问：检查 `host`、端口、防火墙，并确认只在受信任网络开放。
