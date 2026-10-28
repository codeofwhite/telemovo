# 验证与复现

## 无 GPU 检查

在有 NumPy、Node.js、Bash 和系统 `patch` 命令的开发环境执行：

```bash
python3 -B scripts/check_project.py
```

检查脚本解析所有项目 Python／JSON、核对文档相对链接，运行 unittest、浏览器坐标
测试、JS／Shell 语法和两个机器人启动计划。它不导入 Genesis、不申请 GPU、不连接网络，
也不生成 TLS 证书。测试只在临时目录写验证夹具，`-B` 避免生成 Python 字节码。
CI 使用 Python 3.12、Node 22；测试依赖见 `requirements/test.txt`。

重点检查：

- 机器人配置与关节数、资源路径、控制步长一致；错误配置明确失败。
- 平台悬边与 5mm 支撑容差的边界。
- 控制输入的所有者、序列、非法数值、模式切换和重置前松 Grip 要求。
- 实际 viewer 中的纯坐标函数在 108 组头部姿态／手柄方向条件下映射正确，竖直朝向明确拒绝。
- 原版接触文件经补丁后精确匹配历史已验证哈希，源文件不变，未知版本拒绝。

## 仿真控制自检（需 GPU，手工执行）

按安装、资产与补丁说明准备后运行：

```bash
bash scripts/start-simulation.sh --robot franka --self-test \
  --python /path/to/sim-env/bin/python
```

换成 `--robot x5` 检查 X5。自检会实际运动机器人并重置衣物；不要与正在使用的 PICO
会话或未保存的实验共享同一进程。检查 `diagnostics.json` 的最终 status 与各项原始值。
仅代表当前测试协议通过，仍需手动检验碰撞、任务可达性与真实操作体验。

## 物理／渲染计时（需 GPU，手工执行）

保持同一配置，在已应用补丁的环境中指定独立包父目录、GPU 和新输出目录：

```bash
PYTHONPATH=/path/to/isolated/genesis-contact CUDA_VISIBLE_DEVICES=0 EGL_DEVICE_ID=0 \
  /path/to/sim-env/bin/python -B simulation/benchmark.py \
  --config-dir configs/franka --mode physics --seconds 15 --output outputs/bench-franka-physics-001
```

换 `--mode render` 加入每四步一次的 640×480 服务端诊断相机；这不是 PICO 渲染配置。
选择 X5 时改为 `--config-dir configs/x5`。代码复用当前 `build()` 和持位控制，避免旧
基准中不同的摩擦、出生高度或桌面让结果失去可比性。每步 CUDA 同步，结果应注明这是
同步计时，不能直接当作 live 异步物理循环的速度。

## 材料／接触验证（需 GPU，手工执行）

保留了 `simulation/material_validation.py` 的历史诊断选项：`--profile`、`--grasp-only`、
`--contact-probe`、`--record-video`、摩擦与 bend 对照等。先查看其 `--help`，再选择
明确的实验配置。它会按所选 profile 覆盖部分材料参数；**不能将这些结果当作默认配置
不变的性能对照**。原生录像使用 imageio／视频编码环境，已观察的可选依赖版本列在
`requirements/validation.txt`，未包含在核心网关依赖中。
每次使用新的 `--tag`；输出需逐项检查 gates，不仅看脚本是否 complete。

## 实际 PICO 验证（需头显，手工执行）

依次验证双眼、转头、探身、左右对应、松 Grip 重锚定、上下／前后／左右、夹爪开合、
旋转锁定与自由旋转、断连保持、重连释放和重置。记录头显型号、浏览器、网络、GPU
负载、版本哈希及操作者反馈；需要延迟结论时另做时钟／画面同步测量。

本次项目整理只执行 CPU 检查、路径与依赖元数据核验和补丁复现。没有重测 GPU、PICO
或物理夹持。迁移到新目录后的完整硬件启动仍待验证。
