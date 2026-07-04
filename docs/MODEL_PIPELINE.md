# 模型转换与后处理

## 1. 目标接口

```text
输入：1×3×640×640
运行时格式：NV12
类别：person、helmet、reflective_vest
strides：[8,16,32]
DFL reg_max：16
输出：6 个张量
分类：[0,2,4]
回归：[1,3,5]
```

完整机器可读配置见：

```text
configs/model_profiles/ppe_dfl_640_rdkx5.yaml
```

## 2. 主机环境

推荐 Windows 10/11 + WSL2 Ubuntu 22.04 或 x86 Linux、Python 3.10、
Conda 环境 `rdk_yolo`、Docker、D-Robotics `rdk_model_zoo` 和镜像：

```text
openexplorer/ai_toolchain_ubuntu_20_x5_cpu:v1.2.8
```

Python 侧使用 `ultralytics`、`torch`、`torchvision`、`onnx`、
`onnxruntime`、`numpy`、`opencv-python`、`scipy`、`pyyaml`。

## 3. 转换流程

```text
.pt
→ export_monkey_patch.py
→ ONNX 检查
→ hb_mapper checker
→ 校准图片
→ hb_mapper makertbin
→ Bayes-E INT8 .bin
→ RDK X5 部署
```

`export_monkey_patch.py` 和具体 mapper YAML 应来自与目标 RDK 工具链版本匹配的
D-Robotics 示例。不要把训练数据或校准图片提交到本仓库。

## 4. ONNX 检查

确认：

- 输入尺寸固定为 640×640；
- 类别顺序与代码一致；
- 检测头导出为六个原始特征张量，而不是端到端 NMS 输出；
- 三尺度分类通道为 3；
- 三尺度回归通道为 `4 × 16 = 64`。

## 5. Bayes-E 编译

使用 `hb_mapper checker` 检查算子、输入格式和量化配置，再用具有代表性的
校准图像运行 `hb_mapper makertbin`。校准数据必须由模型提供方合法准备，
不得从公开仓库下载未经授权的现场图像。

## 6. 板端验证

```bash
hrt_model_exec model_info --model_file your_model.bin
hrt_model_exec perf --model_file your_model.bin
```

程序启动时还会检查输出数量与形状；不匹配时直接报错。

## 7. 后处理

1. 分类 logits 与原始阈值比较，再执行 sigmoid；
2. 回归张量按四个边和 16 个离散桶重排；
3. 对 DFL 桶执行 softmax 并求期望距离；
4. 按 stride 将距离转换为边界框；
5. 去除 letterbox 偏移并映射回原图；
6. 按类别执行 NMS；
7. 将 helmet/vest 空间关联到 person；
8. 交给跟踪、风险引擎和目标仲裁器。

## 8. 当前模型发布决策

本机发现的 `.pt`、`.onnx`、Bayes-E `.bin` 与该接口相符，但文件内嵌训练或
转换机器的绝对路径，训练数据再分发授权也未能确认。为避免泄露环境信息或传播
来源不明模型，公开 Release 不包含模型。文件摘要记录在
`models/model_manifest.json`。
