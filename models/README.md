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

## 为什么公开 Release 不包含模型

整理时找到一组 `.pt`、`.onnx` 和 Bayes-E `.bin`，接口与项目匹配。但这些文件
包含训练或转换机器的绝对路径，训练数据的来源和模型再分发授权也无法从文件本身
确认。因此本仓库只发布模型接口、摘要和转换方法，不发布二进制。

如果你拥有可公开模型，请先确认训练数据、权重和工具链许可，再按以下名称发布：

```text
argus_ppe_dfl_640.pt
argus_ppe_dfl_640.onnx
argus_ppe_dfl_640_rdkx5.bin
```

不要使用 Git LFS；模型应作为 GitHub Release 附件发布。
