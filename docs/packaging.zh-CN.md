# 本次项目整理说明

整理日期：2026-10-28。新项目名 TeleMovo，来源为原独立 PBD 实验仓库的
`74c41fd` 快照及当时保存的接触补丁。原仓库、远端实验目录与运行环境没有被修改。
新项目使用独立 Git 历史，不把旧历史中携带的第三方 OBJ／URDF 带入发布历史。

## 文件与行为变化

| 文件 | 原先 → 整理后；原因与接口影响 |
|---|---|
| `simulation/live.py` | 从实验目录复制；配置默认指向 `configs/franka`，通过配置解析器取得资产绝对路径；WebSocket 协议、物理与控制循环保留 |
| `simulation/teleop_control.py` | 保留原场景构建、控制、支撑检查；仅把缺补丁错误改为指向本项目说明；未改变抓取方法或材料 |
| `simulation/robot_profiles.py` | 原样复制两种模型的关节／工具／底座定义；未修改几何 |
| `simulation/material_validation.py` | 从实验目录复制，配置入口改为新配置目录及资产路径解析；历史诊断 profile 行为保留 |
| `simulation/export_garment.py` | 固定服务器源／布局／输出路径 → 必填 CLI 参数；USD 依赖延迟至导出时加载，`--help` 无需 USD；输出拒绝覆盖旧目录 |
| `simulation/configuration.py` | 新增机器人一致性、控制频率整除检查及相对路径解析；缺资源明确报错 |
| `simulation/benchmark.py` | 旧独立场景测速不复制；新测速复用当前 `build()` 和控制配置，避免用旧摩擦／桌面／出生高度混测；CLI 明确模式、时长和新输出目录 |
| `viewer/gateway.py` | 固定 IP、外部证书目录与上游端口 → CLI 参数，默认环回地址；删除导入模块时创建 outputs 目录的副作用；状态／控制协议不变 |
| `viewer/index.html` | 使用 TeleMovo 标题，移除原服务器 IP 的两个固定入口，说明机器人取决于所连网关 |
| `viewer/viewer.js` | 标题改为 TeleMovo；坐标计算、渲染、控制、指南保持原样 |
| `configs/franka/*.json` | 复制现有参数；资产改用仓库相对路径，显式标识机器人类型 |
| `configs/x5/*.json` | 同上；保留 X5 的 40cm 平台与初始关节姿态 |
| `scripts/launch.py` | 新增明确解释器、GPU、IP、TLS 和 SSH 入口；启动仿真前校验资产与补丁；支持无副作用 dry-run；不自动安装或启动远端仿真 |
| `scripts/start-simulation.sh` / `start-gateway.sh` | 使用脚本自身位置解析根目录；转交 Python 启动器，不依赖原服务器路径 |
| `scripts/apply_contact_patch.py` | 新增原文件／补丁／结果哈希检查与隔离复制；拒绝未知源和已存在目标 |
| `scripts/import_assets.py` | 新增用户自备模型、衣物导入；先核对关键文件哈希，再复制到忽略目录；不下载资产 |
| `scripts/check_project.py` | 新增 CPU 检查总入口；语法、文档链接、单元测试、方向和启动计划 |
| `patches/manifest.json` | 固定 Genesis 提交、原文件／补丁／结果哈希 |
| `patches/genesis-contact-v4.patch` | 纳入原先在忽略 outputs 中的完整原版→v4 补丁，仅规范文件路径头 |
| `patches/upstream-contact.py.txt` | 纳入未修改的原文件作为离线补丁复现夹具；不导入或执行它 |
| `patches/licenses/Genesis-Apache-2.0.txt` | 保存已读取的上游许可文本 |
| `assets/sources.json` | 模型与衣物来源、哈希和历史材料溯源；移除原机器绝对路径，不携带网格 |
| `requirements/*.txt` | 区分仿真、网关、CPU 测试、可选 USD 导出和录像依赖；不宣称完整跨系统锁定 |
| `.env.example` / `.gitignore` | 环境占位示例与本地资产、证书、输出、缓存、运行时隔离副本排除规则 |
| `tests/test_core.py` | 配置、输入控制、支撑边界、补丁重建测试 |
| `tests/coordinates.test.cjs` | 直接执行实际 viewer 的纯数学函数，测试 108 组方向映射与竖直朝向拒绝 |
| `.github/workflows/checks.yml` | 新增 Python 3.12／Node 22 的无 GPU 检查；尚未在 GitHub 执行 |
| `README.md` / `README.zh-CN.md` | 新项目入口、功能、启动步骤和实验限制；不沿用旧 5.1 Docker 说明作为主入口 |
| `docs/setup.zh-CN.md` | 现有依赖、补丁、同机／远端、证书、停止与输出 |
| `docs/assets.zh-CN.md` | 外部资源、哈希、导入／导出与模型差异 |
| `docs/operation.zh-CN.md` | Grip／Trigger、方向、重锚定、旋转和台边指南 |
| `docs/architecture.md` | 模块职责、坐标、GSV2 状态协议和适配边界 |
| `docs/results.zh-CN.md` / `results-summary.json` | 带原报告哈希的历史证据摘要，保留失败抓取与绝对姿态误差 |
| `docs/troubleshooting.zh-CN.md` | 页面、无响应、性能、接触故障与 CloudXR 路径区别 |
| `docs/verification.zh-CN.md` | 区分本轮 CPU 验证和仍需硬件执行的验证 |
| `THIRD_PARTY_NOTICES.md` / `CONTRIBUTING.md` | 来源、贡献入口、当前许可证待所有者选择的事实 |

## 删除与未纳入范围

没有删除原项目文件。新副本去掉机器专属绝对路径、固定 IP 网页入口和网关导入时的目录
创建。没有携带旧 Docker 启动脚本，因为它依赖仓库外 RoboDojo 代码与本地镜像，不能作为
Genesis 的可复现入口。没有复制大模型、录像、日志、证书、私钥或数据工作台。

## 本轮验证与剩余事项

- 本机执行 CPU 检查，7 项 unittest 与 108 组坐标映射通过；文档链接、Python／JSON、JS、
  Shell 语法及本机／SSH dry-run 通过。
- 用已有网关解释器检查 `--help`，核对网关 websockets 17.2；远端只读核对 Genesis、
  模型和可选依赖元数据，没有启动仿真。
- 原接触文件经补丁精确重建既有结果哈希，证明纳入的是完整补丁；不证明物理效果已经改善。
- 没有安装依赖、重测 GPU／VR、测端到端延迟或完成空白机器安装。
- Git 空白检查在补丁文件的 5 个空上下文行提示尾随空格；单个空格是 unified diff
  的上下文标记，保留以确保完整补丁与哈希一致。其余文件的暂存空白检查通过。
- 项目许可证、公开／私有属性和 GitHub 目标仍待所有者决定；未配置远端或推送。
