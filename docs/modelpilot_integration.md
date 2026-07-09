# RDK ModelPilot 集成说明

## 为什么合并到主仓库

比赛提交时，评审和复现人员通常希望在一个仓库中看到板端代码、执行端固件、模型说明和配套工具。RDK ModelPilot 原本是独立 Windows 桌面工具，本次将其源码同步到主仓库的 `tools/rdk-modelpilot/`，用于说明自训练模型如何从 `.pt` 进入 RDK X5 可部署的 `.bin` 流程。

原独立仓库仍然保留：

```text
https://github.com/AIM135D/rdk-modelpilot
```

本次合并不是 Git submodule，也不删除、不覆盖、不强推独立仓库。主仓库中的副本用于比赛提交和离线审查。

## 与主系统的关系

主系统负责板端运行：

```text
摄像头 → RDK X5 BPU 推理 → 风险判断 → ESP32 执行控制 → Web/LLM 展示
```

RDK ModelPilot 负责模型部署前的 Windows 侧准备：

```text
.pt → ONNX → ONNX 结构检查 → OpenExplorer 量化 → Bayes-E INT8 .bin → 部署报告
```

两者的连接点是 RDK X5 `.bin` 模型和部署配置。ModelPilot 生成的模型应满足本仓库 `models/README.md` 和 `configs/model_profiles/ppe_dfl_640_rdkx5.yaml` 中记录的模型契约。

## 它不替代 RDK Studio

RDK ModelPilot 只聚焦自训练 YOLO 模型转换和部署报告生成，不提供通用 IDE、板卡烧录、远程项目管理、训练平台、数据标注或 NodeHub 发布功能。需要完整 RDK Studio 能力时，仍应使用官方工具。

## 主要解决的问题

- Windows 用户检查 WSL、Docker、Conda、OpenExplorer 和 `rdk_model_zoo` 环境。
- 调用 D-Robotics 官方 `export_monkey_patch.py` 导出适合 RDK X5 后处理的 ONNX。
- 检查 ONNX 是否为六输出 DFL 结构。
- 检查校准图片数量、亮度、分辨率和重复情况。
- 封装 OpenExplorer Docker 量化命令。
- 生成 `deploy_config.py`、`deploy_report.md` 和错误诊断信息。

## 使用入口

```powershell
cd tools\rdk-modelpilot
python -m pip install -r backend\requirements.txt
python backend\main.py

npm --prefix frontend install
npm --prefix frontend run electron:dev
```

更完整的说明见 [tools/rdk-modelpilot/README.md](../tools/rdk-modelpilot/README.md)。
