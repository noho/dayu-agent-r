# upload_material 第一轮校准：UM-O25 用户裁决

登记日期：2026-09-28。状态：**用户已接受多文件必选主文件、单文件自动选，修复未实施**。`UM-O25-F01` 已登记为待实施修复项。UM-O24 的冻结双文件运行与计数仍为事实；其“无主文件参数也成功”不进入未来正式 oracle。产品代码、正式 oracle/scenario 与 registry/readiness 均未更新。

## 冻结运行与观察

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对的 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。

S24/S25 均为真实 `.venv/bin/dayu-cli upload_material --ticker AAPL --forms MATERIAL_OTHER --material-name 'Distinct Order' --company-name 'Apple Inc.'`，cwd 为冻结 run 的 `repo`，stdin=`DEVNULL`，两个独立 CI-owned fresh `--base`。唯一业务输入差异是 `--files` 顺序：

| 场景 | `--files` 顺序 | document ID / source fingerprint | source meta `primary_document` |
| --- | --- | --- | --- |
| UM-S24 | `probe.txt`、`tencent-ai-panel.md` | `mat_e24264cc1db2c612a85b99baf8153dcdc663293b` / `5d48099df0d1bd5404344073117f2422ca3db375fcd1cdec09ab8ca746a8da1d` | `probe_docling.json` |
| UM-S25 | `tencent-ai-panel.md`、`probe.txt` | 同上 | `tencent-ai-panel_docling.json` |

两次均 exit 0、未超时、无残留进程，screen 为 requested=stored=2；meta 的四个文件 name/source/sha256 集合相同，但文件条目顺序随 argv 改变。manifest 的 document ID/指纹与 meta 一致；`primary_document` 仅在 source meta 中。二者分属不同 fresh workspace，**冻结 CLI 没有测“同一 workspace 已发布后逆序重传”**。SQLite count=0，Host/EventLog/Trace/Memory/job 查询为 queried-but-absent，与主文档选择无直接因果关系。

冻结 `UM-001-help` 的 `upload_material --help` 没有 `--primary`，也没有说明 `--files` 首项就是主文件。当前代码 `dayu/cli/arg_parsing.py:_register_upload_material_command` 同样没有 `--primary`；`dayu/fins/tools/upload_tools.py:_upload_primary_selectors_from_arguments` 对 `upload_kind=material` 显式拒绝 `primary`。与 filing 的公开主文件选择契约不同，material 用户没有直接声明主文件的入口。

直接证据：

- `evidence/supplement2/UM-S24-distinct-order-forward/command.json`、`screen.txt`、`result.json`、`key-json-artifacts.json`、`filesystem-diff.json`
- `evidence/supplement2/UM-S25-distinct-order-reverse/command.json`、`screen.txt`、`result.json`、`key-json-artifacts.json`、`filesystem-diff.json`
- `evidence/static/UM-001-help/command.json`、`screen.txt`

## Owner 链与实际影响

`dayu/fins/pipelines/docling_upload_service.py:_build_pending_assets` 在转换循环中遇到第一个 Docling 产物时设置 `primary_document`；`_apply_prepared_upsert` 将其写入 source meta。`dayu/fins/storage/_fs_source_snapshot.py` 的 `get_primary_source()` 只按已持久化的 primary 取源，`dayu/fins/tools/read_runtime.py:_create_processor_from_snapshot` 直接消费这条主源。因此 primary 是跨命令消费事实，不是 UI 排序字段；不同选择可能使后续分析读取不同材料。既有 `tests/fins/test_docling_upload_service.py:test_execute_upload_material_converts_every_selected_file` 断言首项为 primary，是对当前实现的固定，不能替代公开契约裁决。

另有一项**源码推导的风险，非 S24/S25 实测结果**：`_build_upload_source_fingerprint` 对 material originals 按资产名排序，故反转输入顺序仍得同一指纹；`_can_skip_upload` 对已有未删除 source 且相同指纹、未 overwrite 时可跳过整个上传。如果将“首个 `--files` 是 primary”补写为公开规则，在同一 workspace 仅逆序重传时可能因 skip 保留旧 primary，违反规则。必须把主文件角色纳入同一 owner 的选择、指纹/skip 与持久化契约；不能只改 help 文案。

## Accepted 行为与修复方向

不接受“material 第一份 `--files` 无声明地决定主文档”作为 oracle。每个 material 原件都会转成 Docling JSON，但后续读取只取已登记的一个 primary；按文件名给未声明的多文件请求自动选主，可能让系统读取非用户意图的材料。**多文件上传必须显式指定唯一主原件**，单文件自动选唯一原件；material CLI 与 upload tool 使用同一公开 selector 语义，尽量复用 filing 已有的 exact-path 主文件选择 owner。selector 必须精确命中本次原件，转换后的对应 Docling 资产成为 primary。主文件角色应进入 source fingerprint/skip 决策，避免相同字节、不同主文件的再次上传被错误跳过；document ID 仍由 material 业务身份决定。具体公开参数名称与工具字段、错误文案须在 owner contract、CLI help 和 LLM-facing schema 一致。

### UM-O25-F01：material primary 选择与上传跳过同源

状态：**用户已接受，尚未实施**。

语义 owner：Fins material 文件选择/资产身份规划产生 authoritative primary original，再使用 UM-O23-F01 的统一派生名函数得到 exact primary Docling storage name；同一选择事实进入 source fingerprint/skip、source meta 和 read snapshot。CLI/Service/tool 只传入原始 selector；单文件省略 selector 时由同一 owner 选择唯一原件，不得各自按 argv、basename、转换质量或已落盘文件重选。storage 继续验证 primary 精确命中文件，read runtime 继续消费已验证的 primary。

修复要求：多文件缺 selector、重复 selector、未精确命中原件、delete 携带 selector 均在转换前 typed 拒绝，给安全、可行动的错误；单文件可省略 selector。所有原件仍按已接受 UM-O19/O24 的范围转换，primary 仅决定后续默认读取哪个 Docling 产物。选主结果与转换/asset identity、fingerprint/skip、source meta 的 primary、manifest 中的同源摘要和跨命令 read 一致；显式改变 primary 在同一已发布 workspace 不能被“相同原件字节”错误跳过。更新 CLI help、LLM-facing tool schema、Fins README/根 README 的读者相关说明。owner 级测试覆盖单文件自动、多文件缺失/合法/重复/未命中 selector、正逆序指定同一主文件、相同 workspace 的 skip/角色变化、与 UM-O23 同 stem 命名的组合；真实 CLI 隔离补跑合法多文件、缺 selector 拒绝、同一 workspace 变更主文件与 `process_material`/read 对应主源。旧“首项 primary”测试须按新契约改写，不能倒逼兼容分支。

## 裁决边界

本裁决不把源码推导的 same-workspace skip 当作冻结运行事实。UM-O24 对 S24/S25 的成功、计数、document ID 和源指纹相同的描述保留为冻结观察；正式多文件成功 scenario 必须提供合法 selector，原 S24/S25 不再作为“缺 selector 仍成功”的 accepted oracle。两次指定**同一**主文件时仍应有相同 document ID 与指纹；指定不同主文件可保持相同 document ID，但 role-aware 指纹应不同。冻结 evidence、正式 registry/readiness 不改写。产品实现及新隔离 lineage 验证仍需另行授权。
