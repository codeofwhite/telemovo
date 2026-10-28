# TeleMovo

**面向仿真数据采集的沉浸式机器人遥操平台**

![TeleMovo：PICO 双手柄遥操与双臂布料仿真，带 IPPLab 水印](docs/assets/telemovo-hero.png)

TeleMovo 基于 PICO 与 WebXR，连接 VR 交互和机器人仿真，为双臂操作、柔性物体交互
及示范数据采集研究提供可扩展的遥操基础。

当前集成 Genesis 仿真后端，提供 Franka Panda 与 X5 双臂示例，支持沉浸式可视化、
双手柄控制与操作引导。

[English](README.md) · [快速开始](docs/setup.zh-CN.md) · [架构与接口](docs/architecture.md) · [参与贡献](CONTRIBUTING.md)

## 核心特性

- **沉浸式交互**：通过 PICO 浏览器提供立体视觉、头部追踪与双手柄遥操。
- **双臂控制**：相对位姿映射、夹爪控制与可视化操作引导。
- **柔性物体仿真**：基于 Genesis PBD 的布料交互场景。
- **可配置部署**：支持本机运行及远端仿真接入，独立部署 HTTPS 网关。
- **扩展与集成**：提供机器人配置与接口文档，支持后续适配开发。

## 快速开始

1. 按[安装与启动指南](docs/setup.zh-CN.md)准备运行环境及指定版本的 Genesis。
2. 根据[资产指南](docs/assets.zh-CN.md)准备机器人与衣物模型。
3. 启动所选仿真场景和网关，在 PICO 浏览器中打开对应地址。

校准、按键与交互方式见[操作指南](docs/operation.zh-CN.md)。

## 开发规划

- Episode 录制、成功失败标注与回放。
- 数据质量检查与 LeRobot 格式导出。
- 更多机器人与仿真后端适配。
- 遥操交互优化与布料操作工作流。

录制与数据集导出是基于当前遥操接口的后续扩展方向。

## 参与贡献

欢迎一起建设 TeleMovo。我们期待交互设计、机器人适配、数据工作流、文档与测试方面的
贡献。首次参与者可以从文档、安装体验或 CPU 测试开始，无需配备 VR 硬件。

[提出想法／报告问题](https://github.com/codeofwhite/telemovo/issues/new)
· [查看 Issues](https://github.com/codeofwhite/telemovo/issues)
· [贡献指南](CONTRIBUTING.md)
· [提交 PR](https://github.com/codeofwhite/telemovo/pulls)

较大改动请先通过 Issue 讨论目标、修改范围与验证方式。

## 文档导航

| 文档 | 内容 |
|---|---|
| [安装与启动](docs/setup.zh-CN.md) | 环境、部署、HTTPS 与启动命令 |
| [资产准备](docs/assets.zh-CN.md) | 模型来源、准备与导入 |
| [操作指南](docs/operation.zh-CN.md) | 校准、控制与可视化引导 |
| [架构与接口](docs/architecture.md) | 系统组件、坐标约定与通信协议 |
| [验证说明](docs/verification.zh-CN.md) | 开发检查与硬件验证 |
| [实验记录](docs/results.zh-CN.md) | 评估结果与当前验证范围 |
| [故障排查](docs/troubleshooting.zh-CN.md) | 连接、交互与仿真诊断 |

## 许可与致谢

项目整体许可证待选定。组件与资产来源见[第三方说明](THIRD_PARTY_NOTICES.md)。
TeleMovo 是独立社区项目。
