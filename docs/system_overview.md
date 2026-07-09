# 系统总览

本仓库是一个面向 RDK X5 的竞赛原型，目标是把自训练 PPE 检测模型、边缘推理、风险判断、执行端控制、Web 可视化和模型部署工具整理成一个可复现的开源工程。

## 组成

- RDK X5 主系统：`online/` 与 `offline/`。
- ESP32 执行端：`firmware/esp32/`。
- 模型与部署说明：`models/`、`docs/MODEL_PIPELINE.md`。
- Windows 模型部署工具：`tools/rdk-modelpilot/`。
- 配置与基础检查：`configs/`、`tests/`、`scripts/`。

## 数据流

```text
固定摄像头
→ RDK X5 BPU PPE 推理
→ 后处理与 PPE-person 关联
→ 跨帧状态维护
→ 危险区域规则与风险评分
→ 多目标仲裁
→ 串口协议
→ ESP32
→ 舵机 / 蜂鸣器 / 灯光字段
```

在线模式还会把画面、状态、事件和 LLM 建议推送到浏览器。LLM 只做异步解释和建议，不参与实时执行链路的阻塞决策。

## 默认安全策略

`configs/runtime.example.yaml` 中硬件、舵机、蜂鸣器、灯光和 LLM 桥接默认关闭。首次部署时建议先完成摄像头和模型验证，再逐步启用串口和执行端。
