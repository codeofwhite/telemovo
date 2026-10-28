# 环境、启动与停止

本文命令供操作者按需执行。整理项目时没有执行安装命令，也没有启动 GPU 或 PICO 服务。
假设终端当前目录为仓库根目录；先用 `pwd` 确认。示例中的路径与 IP 必须替换。

## 1. 经过验证的环境与固定源版本

历史实验使用 Linux、单张 RTX 5090、Genesis 源码提交
`9727f6e857d8ea6951a30fd761bc489c82e224ec`，元数据版本为 1.3.1；
PyTorch `2.11.0+cu128`、NumPy `2.3.5`、仿真端 websockets `17.0.1`；本机网关为 websockets `17.2`。
八卡服务器上只选用了一张卡，未测试多卡物理加速。它是一次实际环境记录，
并非所有系统的通用兼容矩阵。该源码依赖 quadrants；不要替换成旧版 Taichi Genesis。

仿真环境、网关环境可以分开。先选择适配本机驱动的现有 GPU PyTorch 环境。
以下是明确选定解释器后的安装步骤；不要把占位路径原样复制：

```bash
git clone https://github.com/Genesis-Embodied-AI/genesis-world.git /path/to/genesis-world
git -C /path/to/genesis-world checkout 9727f6e857d8ea6951a30fd761bc489c82e224ec
/path/to/sim-env/bin/python -m pip install -e /path/to/genesis-world
/path/to/sim-env/bin/python -m pip install -r requirements/simulation.txt
/path/to/gateway-env/bin/python -m pip install -r requirements/gateway.txt
```

源码安装会解析其依赖，不能把它描述为完全锁定的离线环境。`requirements/simulation.txt`
只固定直接使用的 NumPy 与 websockets；PyTorch GPU wheel 与驱动由部署环境提供。
没有验证在一台空白机器上完整重装。仅安装同名 `genesis-world==1.3.1` 不能代替固定源提交。

## 2. 外部资产与独立补丁

先按[资产准备](assets.zh-CN.md)导入所需机器人和衣物。配置文件中的相对路径是相对于
`configs/franka/` 或 `configs/x5/` 解析，不取决于 shell 当前目录。缺资产会明确报错。

```bash
python3 -B scripts/apply_contact_patch.py --source /path/to/genesis-world/genesis
```

输出默认为 `.runtime/genesis-contact/genesis`，它是上游包的独立复制。脚本先检查上游
接触文件与补丁哈希，再零模糊应用补丁，最后核对结果哈希。源版本不匹配或目标已存在时
直接报错；不会修改安装包、覆盖未知目标或自动换版本。运行仿真时将独立包的父目录放到
`PYTHONPATH` 前端。

## 3. 配置本机环境

可直接使用启动参数，也可以复制 `.env.example` 为被 Git 忽略的 `.env`，编辑后显式执行
`source .env`。脚本不会自动加载任意 `.env`。常用变量：

| 变量 | 意义／默认值 |
|---|---|
| `TELEMOVO_SIM_PYTHON` | 仿真解释器；默认启动器当前 Python |
| `TELEMOVO_GATEWAY_PYTHON` | 网关解释器；默认启动器当前 Python |
| `TELEMOVO_GPU` | `CUDA_VISIBLE_DEVICES`；默认 `0`，只指定一张卡 |
| `TELEMOVO_EGL_DEVICE` | EGL 设备索引；默认 `0`，与本机驱动枚举核对 |
| `TELEMOVO_GENESIS_PATH` | 独立 Genesis 包父目录；默认 `.runtime/genesis-contact` |
| `TELEMOVO_BIND` | HTTPS 绑定地址；默认 `127.0.0.1`，PICO 使用服务器局域网 IP |
| `TELEMOVO_CERT` / `TELEMOVO_KEY` | 证书与私钥；默认 `.local/tls/server.crt` / `server.key` |
| `TELEMOVO_SSH_HOST` | 可选 SSH 主机别名；未设置则直接连接同机仿真 |

原实验的显存限制不作为本项目默认配置；启动前应自行确认空闲 GPU 和显存。
启动器不会停止其他人的进程、自动换卡或重启现有仿真。

## 4. HTTPS 与 PICO

WebXR 需要浏览器认可的安全上下文。优先使用头显信任的证书，且证书 SAN 包含访问 IP
或主机名。私钥放到忽略目录或项目外，不能提交。

实验室可以生成自签证书（需已有 OpenSSL；以下会创建本地文件）：

```bash
mkdir -p .local/tls
openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
  -keyout .local/tls/server.key -out .local/tls/server.crt \
  -subj '/CN=YOUR_LAN_IP' -addext 'subjectAltName=IP:YOUR_LAN_IP'
chmod 600 .local/tls/server.key
```

不同浏览器对自签证书的行为不同；确认页面可访问并不保证 `navigator.xr` 已可用。
历史 PICO 环境可在测试证书提示后继续，但正式复现应检查浏览器的信任设置与 WebXR 能力。
服务器与 PICO 应在互通的局域网；同 SSID 不代表不存在访客隔离。

## 5. 同机启动

先检查命令，不启动：

```bash
bash scripts/start-simulation.sh --robot franka --teleop --dry-run
bash scripts/start-gateway.sh --robot franka --bind YOUR_LAN_IP --dry-run
```

终端一启动仿真：

```bash
bash scripts/start-simulation.sh --robot franka --teleop \
  --python /path/to/sim-env/bin/python --seconds 1800
```

终端二启动网关：

```bash
bash scripts/start-gateway.sh --robot franka --bind YOUR_LAN_IP \
  --python /path/to/gateway-env/bin/python \
  --cert /path/to/server.crt --key /path/to/server.key
```

先访问 `https://YOUR_LAN_IP:8444/health`，然后在 PICO 打开
`https://YOUR_LAN_IP:8444/?teleop=1`。只读查看使用 `/`；仿真不带 `--teleop`
时也保持只读。仅打开遥操网页不会绕过服务端只读设置。

X5 将两条命令都改成 `--robot x5`，网页端口为 `8445`。不需要同时运行两个场景。
默认仿真端口分别为 Franka `9740`、X5 `9742`，只监听 `127.0.0.1`。

## 6. 远端仿真、本地网关

在 GPU 服务器准备同一份 TeleMovo、依赖、资产、独立补丁，在远端终端运行上述仿真命令。
在 PICO 所在局域网的网关机器运行：

```bash
bash scripts/start-gateway.sh --robot franka --bind YOUR_LAN_IP \
  --ssh-host YOUR_EXISTING_SSH_ALIAS --python /path/to/gateway-env/bin/python \
  --cert /path/to/server.crt --key /path/to/server.key
```

启动器建立本地 `9741→远端9740`（Franka）或 `9743→远端9742`（X5）的环回隧道。
需要先配置已知主机与 SSH 认证；使用 `BatchMode` 和严格主机校验，失败会报错。
SSH 断开会停止由该启动器创建的网关；网关退出会清理它创建的隧道。
**它不会自动启动或停止远端仿真。**

## 7. 输出、停止和重新开始

- 仿真状态写入 `configs/<robot>/outputs/teleop-<UTC时间>/status.json`；缓存位于根目录 `outputs/`。
- 网关状态输出到终端。日志可以由操作者重定向到被忽略的 `outputs/`。
- 网页重置只重置当前衣物和机器人；没有保存 episode 的功能。
- 先松开 Grip，退出 VR，再对网关和仿真分别按 Ctrl+C。远端仿真需要在远端终端停止。
- 固定运行时长按仿真主循环开始后的墙钟时间计算；GPU 初始化与自检时间不包含在内。

本入口面向可信实验室网络，没有公开互联网访问控制，不应直接作为公网遥操服务。
