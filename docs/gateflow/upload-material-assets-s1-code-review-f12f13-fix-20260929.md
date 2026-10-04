# O04/O23 S1 F12/F13 修复记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-fe64fae9

## 锁定与边界

- 工作区：`/private/tmp/dayu-upload-assets`。预检 HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`、tracked `git diff --binary` SHA-256 `d5fc19d7248dfc31d4865c03d12b585593107060f1ee9c07ccf22e90ebeba8ca`，以及三个未跟踪文件 `dayu/fins/upload_asset_plan.py`、`tests/fins/test_upload_asset_plan.py`、`tests/fins/test_upload_usage_contract.py` 的任务锁值全部吻合。锁值在任何编辑之前复核。
- 已读 `AGENTS.md`、accepted goal/plan、裁决末节、MiMo `code-review-20260929-142240.md`、planner/admission/tool/CLI 及对应测试。F12/F13 动机成立：material tool/CLI 在 admission 前二次 `resolve` 遮蔽 planner；planner 未分类 NUL `ValueError`、未知用户 `~name` 的 `RuntimeError`。这些都是代码直接路径与回归输入可复现的缺口。
- 本轮只修 F12/F13；F1–F11/R1/R2 行为由相邻矩阵复核。未改 goal、plan、旧 review/裁决、O05/O16/O25、存在性业务规则；未安装依赖、提交、推送、开 PR 或派发子 Agent。完整最终 tracked diff 与全部未跟踪 SHA 另列于交付报告；本文件自身无法自包含其内容哈希。

## Owner 与改动

- `dayu/fins/upload_asset_plan.py` 的 material 逐路径规划循环收口 `UnicodeEncodeError`、`ValueError`、`RuntimeError` 为同一个 `INVALID_ASSET_NAME` 候选，继续扫描可判定控制名；`OSError` 保持操作性透传。控制名 > 非法名 > 业务资产碰撞的原因优先级未变。
- `dayu/fins/tools/upload_tools.py` 对 material 只构造原始 `Path`，由唯一 `admit_fins_upload_material_request` 解析和规划后，才在工具边界执行原有普通文件/非空预检；filing 保持原路径。planner 产生的 `FinsUploadUsageError` 由同一 typed failure 投影 closed error code 与安全 message；其余既有 typed usage 仍保持 `invalid_argument` transport code，不复制 code 到 message/hint 的表。action 先于 identity，identity 先于 material 文件名分类；测试固定该顺序。
- `dayu/cli/commands/fins.py` 将 material 原始 `Path` 交给同一 admission，随后以计划中的已解析路径检查存在性及普通文件，保留原有英文预检文案和 exit `2`。NUL 与未知用户目录到达 planner 安全用法失败；CLI 不再在 material 的 admission 前单独解析文件路径。
- 仅更新 planner、tool、CLI 对应测试与 `README.md`、`dayu/fins/README.md`、`tests/README.md` 的相应说明。旧 CLI 测试固定“缺失文件时 raw request 不能构造”的时序，已改为固定可观察业务合同：原文案、exit `2`、Service 零调用。文件状态预检新增 material 专项回归。

## 验证

- 纯 planner：NUL、未知用户目录单独和与 `META.JSON` 正逆序均给封闭原因；控制名优先；注入 `PermissionError` 保持原实例透传。
- 真实 tool callable：纯 JSON 高代理、NUL、未知用户目录，以及实际创建的反斜杠文件名，均返回 planner 同源 `invalid_asset_name` 和安全、有界、可 UTF-8/JSON 编码的文案，零 observation、job、executor submit、公司发布。action 与 ticker identity 的原有优先级另有多重非法输入断言。material 缺失、目录、空文件继续沿用原预检错误。
- CLI：真实 subprocess 的反斜杠文件名和未知用户目录 exit `2`，stderr 为 owner 文案且工作区未建立；NUL 无法作为真实 argv 传递，以 CLI 主入口参数级测试核对 exit `2`、安全文案、Service 零调用。高代理 argv 不作可达性承诺；它在真实 tool JSON 边界验证。
- `source .venv/bin/activate && python -m pytest` 聚焦 planner/tool/CLI：302 passed。accepted plan 的 17 文件相邻矩阵：1244 passed、1 skipped，3 条 edgar 第三方 deprecation warning。最终 `source .venv/bin/activate && python -m pyright`：0 errors、0 warnings、0 informations。
- coverage 使用同一虚拟环境，先加载 `dayu.documents.processors.registry` 中的第三方 C 扩展，再启动 `coverage.Coverage` 测量三个修改的生产文件，并运行 302 个聚焦测试：planner 92%、tool 94%、CLI 86%，单文件均达到 80%。未在本轮重跑真实 Docling 转换/完整成功发布。

## 失败命令与限制

- 首轮聚焦 pytest exit `1`：32 failed、265 passed。原因是初稿把全部 typed usage code 映射为工具 transport error，改变 filing/ticker 既有行为；两个旧 CLI 测试还固定 admission 前不构造 raw request 的时序。收窄工具映射并修正过时测试后，聚焦与相邻矩阵均通过。首轮失败不以最终绿测抹除。
- 一次 `apply_patch` 更新根 README 因目标行比片段更长，校验失败；随后以唯一子串替换并核读 diff。
- `pytest --cov` 覆盖命令两次 exit `2`：测试收集阶段共享虚拟环境的 NumPy C 扩展报 `ImportError: cannot load module more than once per process`。分文件 planner `--cov` 成功给出 92%；单测 tool 的 `--cov` 同样 exit `2`。尝试预加载 NumPy 后的 coverage 命令 exit `2`，转为 `cv2.dnn.DictValue` 属性错误。预加载包含这些依赖的 `dayu.documents.processors.registry`、再启动 coverage API 后，302 测试及三个文件的逐文件覆盖率均成功；这仅是 coverage 启动次序调整，没有改产品代码或安装依赖。
- 既有 1 skipped 和第三方 edgar warnings 随矩阵保留。候选仍需总控对本次完整内容指纹进行同版 review；本轮未进行第二路 code gate，也未提交或集成。

## 交付内容指纹

- HEAD：`1453a659a79d4c9a93838412dfdecfa7feeddf98`。
- 最终 tracked `git diff --binary` SHA-256：`07b0df8c06253c64431316ac32b11d540df8b182861e7112d9fd417c8b3a60bf`。
- 全部未跟踪文件中除本记录自身外的 SHA-256 如下。本记录自身 SHA-256 在交付报告给出，以避免自引用导致内容哈希不稳定。

| SHA-256 | 未跟踪文件 |
| --- | --- |
| `c2c91eeebb8cc5f16a6aea3f72db916102addf1228282c35ecd7994655eb706f` | `dayu/fins/storage/asset_filename_contract.py` |
| `707d12a79c5cec4c97047749bc68bd0593a6e93adb39249aeac751bd791be7fc` | `dayu/fins/upload_asset_plan.py` |
| `64e5b33a7f907d3b604f3a9efd341b1849b5f9ac8615da1feab13c7e29ae8659` | `dayu/fins/upload_usage_contract.py` |
| `32bd5870fb67d453466729eb670f2ad1d8d2eed34ce6c36c04030f83e54e837f` | `docs/gateflow/upload-material-assets-s1-code-rereview-r1r2-fix-20260929.md` |
| `596a4b34072bc9ee640f06dad8dc58f77f9690ef18e82914012f726a9d2b169a` | `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` |
| `6771d1767cb7d841e8284cdae1f39c454f714690a29238f338bce6f1852bab06` | `docs/gateflow/upload-material-assets-s1-code-review-f8-fix-20260929.md` |
| `5dbfdbc7d5a0da5a80e752412737fdf9464372249b760269adfe72cdfb5ff00a` | `docs/gateflow/upload-material-assets-s1-code-review-f9f11-fix-20260929.md` |
| `1db5c6ceb204d1ef4d4762373b9ca52a5b88b1c8579a2e429931be5a3670df8f` | `docs/gateflow/upload-material-assets-s1-code-review-fix-20260929.md` |
| `82dc79d8666d61f33f62224e833eef744ae493251b5c167fe1259f743c5908d0` | `docs/gateflow/upload-material-assets-s1-code-review-fix2-20260929.md` |
| `010a845f070756cf9d8f60ebbcb4c0c4800611761fe9e5e5c1cfeb1b1ef1040a` | `docs/gateflow/upload-material-assets-s1-implementation-20260929.md` |
| `936af67004090e0f3aae6a9ff67d3bc85519808a9c5c9d38d2b2ec7cc7b9afdc` | `docs/reviews/code-rereview-assets-s1-mimo-20260929.md` |
| `3c5609bdb875e566365f9e25aaf2ef955804a964d7804c6f6577317f1c33eb46` | `docs/reviews/code-review-20260929-114318.md` |
| `64de4b21db317a9b7312b62c4716cc9863b52977c58b7d7ee84f698c76469866` | `docs/reviews/code-review-20260929-130410.md` |
| `d7585ffa3f0783e30e4076ee51d03e7383e46bf22f6df2ec66dc2d208578fa2e` | `docs/reviews/code-review-20260929-133817.md` |
| `7632acd85e32e733d887bccf2dbe8d6d7600869dbc210c16b30da8be9d8b19d9` | `docs/reviews/code-review-20260929-142240.md` |
| `c5723c7016199b0dd132b77f42d5eb01980b158da1f38ca3242ef85ca5a5d534` | `tests/fins/test_storage_asset_filename_contract.py` |
| `2ac85fe123eef78c7226159a47a43a6b6706fc4528cc5d089e0f4fee712bafec` | `tests/fins/test_upload_asset_plan.py` |
| `1ce0bd923022196ea1842de91182852aab3088c010359ff38f71638f21950c4a` | `tests/fins/test_upload_usage_contract.py` |
