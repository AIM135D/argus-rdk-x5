# ARGUS 模型放置说明

模型文件不提交到 Git。RDK X5 默认读取：

```text
models/argus_ppe_dfl_640_rdkx5.bin
```

也可以在 `configs/runtime.yaml` 设置 `model_path`，或使用：

```bash
export ARGUS_MODEL_PATH=/path/to/compatible_model.bin
```

## 必须满足的接口

- 输入：`1×3×640×640`，RDK 运行时 NV12；
- 类别：`person`、`helmet`、`reflective_vest`；
- strides：`[8,16,32]`；
- DFL `reg_max=16`；
- 六个输出张量；
- 分类输出索引 `[0,2,4]`；
- 回归输出索引 `[1,3,5]`。

板端检查：

```bash
hrt_model_exec model_info --model_file models/argus_ppe_dfl_640_rdkx5.bin
hrt_model_exec perf --model_file models/argus_ppe_dfl_640_rdkx5.bin
```

## Release 下载

经项目所有者明确授权，三份匹配项目接口的模型已作为
[v1.0.0 Release](https://github.com/AIM135D/argus-rdk-x5/releases/tag/v1.0.0)
附件发布：

- [`argus_ppe_dfl_640.pt`](https://github.com/AIM135D/argus-rdk-x5/releases/download/v1.0.0/argus_ppe_dfl_640.pt)
- [`argus_ppe_dfl_640.onnx`](https://github.com/AIM135D/argus-rdk-x5/releases/download/v1.0.0/argus_ppe_dfl_640.onnx)
- [`argus_ppe_dfl_640_rdkx5.bin`](https://github.com/AIM135D/argus-rdk-x5/releases/download/v1.0.0/argus_ppe_dfl_640_rdkx5.bin)

这些文件仍不进入 Git 历史。模型包含训练或转换机器的绝对路径；使用者仍应自行
确认训练数据、权重和工具链许可。大小与 SHA-256 见
[`model_manifest.json`](model_manifest.json)。
