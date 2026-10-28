# 模型与衣物资产

仓库只提供来源与哈希，不分发机器人模型或衣物几何。详见
[第三方说明](../THIRD_PARTY_NOTICES.md)。资产导入只从用户指定目录读取，不下载、
不修改源文件，不覆盖已有目标；导入后的文件被 Git 忽略。

## 需要的内容

| 类型 | 源内容 | 导入后位置 |
|---|---|---|
| Franka Panda | 验证时使用的 `panda.xml` 和 `meshes/` | `assets/franka/` |
| X5 | RoboDojo `Robots/x5/`，包括 `X5A.urdf`、`robot_config.yml`、`meshes/` | `assets/x5/` |
| 衣物 | 已按布局导出的 `garment.obj` | `assets/garment/garment.obj` |

Franka 使用的是 **Panda 模型**，并非经过等价验证的 FR3 型号。当前夹爪接触参数依赖
带平面指腹的那份模型，直接换用任意 Panda／FR3 描述不保证一致。

## 导入已验证资产

```bash
python3 -B scripts/import_assets.py --robot franka --source /path/to/matching-franka-assets
python3 -B scripts/import_assets.py --robot x5 --source /path/to/RoboDojo/Robots/x5
python3 -B scripts/import_assets.py --garment /path/to/exported/garment.obj
```

哈希表在 [sources.json](../assets/sources.json)。模型关键描述与网格逐文件校验，衣物则
核对 OBJ 的完整 SHA256。不匹配会在复制前报错，不会悄悄替换成其他模型。
机器人源目录整个复制，以保留描述引用的相对网格、材质及许可文件；请只提供该资产目录，
不要把包含私人文件的上层工作目录当作资产目录。

这些精确哈希也意味着：新用户仍需要取得匹配资产。本版尚未提供可自由分发的替代衣物
和标准 Panda 模型适配；这是独立机器复现的已知门槛，而非一键安装已经完成。

## 从原衣物 USDZ 重新导出

可选导出器需要 NumPy 与 `pxr`，原验证的 `usd-core` 为 `25.11`。使用明确的现有解释器：

```bash
/path/to/export-env/bin/python -m pip install -r requirements/export.txt
/path/to/export-env/bin/python -B simulation/export_garment.py \
  --source /path/to/Top_Long/00004/object.usdz \
  --layout /path/to/resolved-layout.json \
  --output /path/to/new-export-directory
```

导出器期望一个三角网格和布局中的 `Garment/Top_Long[0]`，烘焙 USD 变换、单位、
scale／orientation／position，写出 OBJ 与来源 manifest。输出目录必须是新目录。
布局必须与哈希记录匹配，才能重建当前衣物；不匹配不是可直接忽略的差异。

原衣物源顶点 9487、三角形 18626。Genesis 可以重新离散化，实际粒子数应读运行输出，
不能从 OBJ 顶点数直接推断。PhysX 材料参数只保留溯源，不代表与 Genesis compliance 等价。

## 已记录的布局

两种机器人均保留 `0.765m` 原桌面、`0.12m` 高附加平台、`0.01m` 厚台面和 `0.08×0.08m`
中央支柱。Franka 平台 `0.70×0.50m`、中心 Y=`−0.15m`；X5 为避开肩部，平台
`0.70×0.40m`、中心 Y=`−0.10m`。衣物出生位置按顶面和 clearance 平移，重置恢复出生状态。
本轮整理没有改变上述几何或材料。
