# UM-O04/O23 S1 code review F9–F11 修复记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-6f4c08a6

## 预检与根因

- 工作区 `/private/tmp/dayu-upload-assets`；实施前 HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`、tracked `git diff --binary` SHA-256 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`；未跟踪 planner、planner test、usage test 分别为 `3ad3d8551a1c94eec27b6f5b6180bf9264cf3e35e9f5ea40136d1c136f6a4780`、`c151535fed72342a801c367a9099e84d8991167ec9dec9b3a39f1f6fabef5225`、`2ff264cd6c75372dfd9cef58bcef9e15549718c00ec968a3ebd1489f748d7116`，全部匹配锁定值。
- 已读根目录 `AGENTS.md`、accepted goal/plan、总控裁决末节、MiMo `code-review-20260929-133817.md`、planner/label/usage owner 和现有测试。F9–F11 动机成立：非法名在 typed 错误构造中再经严格合法 basename canonicalizer 抛裸 `ValueError`；高代理名在整批分类前的 `Path.resolve` 抛编码错误；低代理名漏过唯一标签 owner 的 Unicode `Cs` 隐藏判断。均是封闭错误及安全投影缺口；没有证据表明已发生仓储发布损坏。
- 规划原因、数量与顺序由 `dayu/fins/upload_asset_plan.py` 拥有；安全 public file label 只由 `dayu/fins/direct_events.py` 拥有；usage 文案继续由 `dayu/fins/upload_usage_contract.py` 拥有。原严格 canonicalizer 的合法 basename 合同保持；新增已拒绝文件名专用入口复用其标签规则，非法 shape 由同一 owner 投影为固定隐藏标签。CLI、tool、failure adapter 均未加兜底。

## 修改

- F9：planner typed 错误使用 label owner 的已拒绝名称投影。反斜杠名的单名、不同目录重复名、与超长名混批正逆序分别保持 `INVALID_ASSET_NAME`、`DUPLICATE_ORIGINAL_BASENAME`、`INVALID_ASSET_NAME`，标签隐藏、消息有界且无绝对路径。
- F10：material planner 对逐个路径规范化的 `UnicodeEncodeError` 记录首个非法路径，继续规划其余可判定文件；控制名仍优先于非法名，业务碰撞仍在其后。高代理名单独报 `INVALID_ASSET_NAME`，与 `META.JSON` 正逆序均报 `RESERVED_CONTROL_NAME`。未改 filing 路径 helper 的公共行为。
- F11：唯一标签 owner 将 Unicode `Cs` 纳入隐藏规则。低代理名的 typed failure、usage 和 `ensure_ascii=False` JSON 均可 UTF-8 编码。
- 增加 planner、public label、usage/public failure 和真实 CLI 回归。真实 CLI 以文件系统可创建的反斜杠 basename 执行，exit 2、封闭消息、无 traceback 且未创建目标工作区。未改既有 F8、F1–F7/R1/R2 的原因优先级或公开短名文案。
- 按更新约束核查 `dayu/fins/README.md`、`tests/README.md` 与根 `README.md`：这次是既有封闭错误和安全标签合同的纠偏，没有改变公开操作步骤、稳定架构说明或测试层级，故未改 README。

## 验证

所有测试及 pyright 均先执行 `source .venv/bin/activate`；Python 3.11.15。首轮聚焦 owner/CLI：565 passed。相邻 17 文件矩阵：1226 passed、1 skipped、3 条第三方 edgar deprecation warnings；`dayu/fins/upload_asset_plan.py` 92%、`dayu/fins/direct_events.py` 87%，均达到单文件 80%。补齐高代理名×控制名的 usage/JSON 正逆序测试后，重跑聚焦 owner/CLI：567 passed；两文件覆盖分别 92%、86%。最后一次 `python -m pyright`：0 errors、0 warnings、0 informations；`git diff --check`：exit 0。相邻矩阵覆盖本次真实 CLI 反斜杠回归和既有 F8/F1–F7/R1/R2 测试；新增两条纯函数 usage 测试在最终聚焦重跑通过。

本 macOS/APFS 工作区不能创建代理字符 basename；F10/F11 使用纯 planner、标签、usage 与 public failure JSON 边界测试，不把它们声称为真实 CLI 文件回归。本轮未重跑真实 Docling 转换或完整发布。虚拟环境 site-packages 仍复用 `/Users/leo/workspace/dayu-agent-r/.venv`，没有安装依赖。此记录只证明修复候选，未作新的双路同版 code review 或 gate pass。

## 失败命令披露

1. 首个预检 shell 命令将三份未跟踪文件误写成不存在的 `dayu/fins/upload_material/planner.py`、`tests/fins/test_upload_material_planner.py`、`tests/fins/test_upload_material_usage.py`，`shasum` exit 1；同一命令先输出的 HEAD/tracked diff 值有效。定位实际文件后重算三份 SHA，均与锁定值匹配。
2. 第一次列出全部未跟踪文件哈希的 Python 单行命令因 f-string 引号冲突抛 `SyntaxError: f-string: unmatched '('`，exit 1；随后以 here-doc Python 命令重新计算成功。

其它本轮工具/命令均成功；不能以最终绿测抵消上述两次命令失败。

## 最终候选指纹

- HEAD：`1453a659a79d4c9a93838412dfdecfa7feeddf98`。
- tracked `git diff --binary` SHA-256：`d5fc19d7248dfc31d4865c03d12b585593107060f1ee9c07ccf22e90ebeba8ca`。
- 下表是本记录写入前所有既有未跟踪文件的内容 SHA-256；本记录自身的最终内容 SHA 需写入后从工作区计算并随交付报告给出，避免在自身内容中嵌入自身哈希。

| SHA-256 | 未跟踪文件 |
| --- | --- |
| `c2c91eeebb8cc5f16a6aea3f72db916102addf1228282c35ecd7994655eb706f` | `dayu/fins/storage/asset_filename_contract.py` |
| `5fd4d7133ce4c908981adce9164bbd515818952fe200b8ad6e82ad67b5d252c3` | `dayu/fins/upload_asset_plan.py` |
| `64e5b33a7f907d3b604f3a9efd341b1849b5f9ac8615da1feab13c7e29ae8659` | `dayu/fins/upload_usage_contract.py` |
| `32bd5870fb67d453466729eb670f2ad1d8d2eed34ce6c36c04030f83e54e837f` | `docs/gateflow/upload-material-assets-s1-code-rereview-r1r2-fix-20260929.md` |
| `36600ec7dfab99e23431af6f7140be05442752502edb2444d29905bf35265a0d` | `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` |
| `6771d1767cb7d841e8284cdae1f39c454f714690a29238f338bce6f1852bab06` | `docs/gateflow/upload-material-assets-s1-code-review-f8-fix-20260929.md` |
| `1db5c6ceb204d1ef4d4762373b9ca52a5b88b1c8579a2e429931be5a3670df8f` | `docs/gateflow/upload-material-assets-s1-code-review-fix-20260929.md` |
| `82dc79d8666d61f33f62224e833eef744ae493251b5c167fe1259f743c5908d0` | `docs/gateflow/upload-material-assets-s1-code-review-fix2-20260929.md` |
| `010a845f070756cf9d8f60ebbcb4c0c4800611761fe9e5e5c1cfeb1b1ef1040a` | `docs/gateflow/upload-material-assets-s1-implementation-20260929.md` |
| `936af67004090e0f3aae6a9ff67d3bc85519808a9c5c9d38d2b2ec7cc7b9afdc` | `docs/reviews/code-rereview-assets-s1-mimo-20260929.md` |
| `3c5609bdb875e566365f9e25aaf2ef955804a964d7804c6f6577317f1c33eb46` | `docs/reviews/code-review-20260929-114318.md` |
| `64de4b21db317a9b7312b62c4716cc9863b52977c58b7d7ee84f698c76469866` | `docs/reviews/code-review-20260929-130410.md` |
| `d7585ffa3f0783e30e4076ee51d03e7383e46bf22f6df2ec66dc2d208578fa2e` | `docs/reviews/code-review-20260929-133817.md` |
| `c5723c7016199b0dd132b77f42d5eb01980b158da1f38ca3242ef85ca5a5d534` | `tests/fins/test_storage_asset_filename_contract.py` |
| `53a5b05d23962060b993b8f5cf76b67f9652824bbb9f4a3c891bd658d0cdd804` | `tests/fins/test_upload_asset_plan.py` |
| `1ce0bd923022196ea1842de91182852aab3088c010359ff38f71638f21950c4a` | `tests/fins/test_upload_usage_contract.py` |
