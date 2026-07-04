# 危险区域与舵机标定

## 1. 危险区域

画面坐标使用 640×360。配置项：

```json
{
  "id": 1,
  "name": "机械作业区",
  "zone": [300, 40, 520, 350],
  "risk_level": "high",
  "enabled": true,
  "require_helmet": true,
  "require_vest": true
}
```

`zone` 为 `[x1,y1,x2,y2]`。区域规则决定进入区域的人是否必须佩戴安全帽和反光衣。

先复制：

```bash
cp configs/danger_zones.example.json configs/danger_zones.runtime.json
```

## 2. 舵机标定

标定采用 3×3 图像点到 pan/tilt 的稀疏网格，再做分片双线性插值。

```bash
cp configs/servo_calibration.example.json \
  configs/servo_calibration.runtime.json
```

每个网格点包含：

```json
{"u": 320, "v": 180, "pan": 90, "tilt": 82}
```

## 3. 安全步骤

1. 保持所有硬件开关为 false；
2. 确认舵机独立供电、共地和机械限位；
3. 手工确认 90° 中位；
4. 从中间点开始，再测四边和四角；
5. 把角度写入运行时标定文件；
6. 检查 `limits` 不超过机械安全范围；
7. 空载、低速启用 `hardware_enabled` 和 `servo_enabled`；
8. 确认方向、抖动和丢失回退后，再启用蜂鸣器。

## 4. 区域固定角度

特定区域可使用固定角度覆盖：

```json
{
  "zone_overrides": {
    "1": {
      "enabled": true,
      "name": "机械作业区",
      "pan": 105,
      "tilt": 86
    }
  }
}
```

固定角度适合位置明确的区域，但仍受 `limits` 和全局 offset 限制。

## 5. 调试接口

`calibration_cli.py` 可调用 Web API 读取、保存、重载标定以及发送手动角度。
手动角度调试必须在执行器周围无人、机械限位已确认时进行。

## 6. 回退

如果方向相反、出现碰撞风险或串口异常：

1. 立即断开执行器电源；
2. 将 `hardware_enabled` 设回 false；
3. 检查 ESP32 固件方向常量、角度范围与网格；
4. 重新从中位开始标定。
