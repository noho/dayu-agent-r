# upload_material 第一轮校准：UM-O28 用户裁决

登记日期：2026-09-28。状态：**用户已接受，正式 oracle/scenario 尚未更新**。用户确认 direct CLI 不产生 Fins 的 Agent/Host 运行产物是正确边界；这不否定已发布的 Fins source 与单独运行 process 后生成的 processed 业务文件。本项裁决冻结 CLI 运行的 SQLite 与 Host/EventLog/Tool Trace/Memory/runtime/旧 job 查询范围；未发现独立修复项。

## 冻结运行与覆盖核对

冻结 evidence root：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`；validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。本次核对 SHA-256：observed-behavior.md `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`、observed-behavior.json `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`、evidence-manifest.json `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd`。observed JSON 登记 160 个场景（原冻结 135、补充 25）；本次逐一读取 evidence 下 160 个 `result.json` 的 `sqlite_before/after` 与 `durable_before/after`，没有缺项或与下述模式不符的记录。

每个 `sqlite_before/after` 的 owner_scope 均为 `CI-owned workspace only`，查询候选包括 `*.sqlite`、`*.sqlite3`、`*.db` 与 WAL/SHM sidecar，`database_count=0`、`databases=[]`、`not_applicable=true`。每个 `durable_before/after` 的六个定位对象 `host_root`、`eventlog_root`、`tool_trace_root`、`memory_root`、`runtime_root`、`legacy_fins_ingestion_jobs` 均为 `queried=true`、`exists=false`、`file_count=0`。这是**已查询且在限定工作区范围内不存在**，不是未检查或仅凭未出现在 screen 中推断；也不是对机器其它目录、其它入口或未来部署的一般性否定。

交叉验证：UM-R01 的真实单文件 `upload_material` exit 0 并发布 source 后，其 `sqlite-after.json` 仍为 0 个 workspace DB；UM-X01 在同一 workspace 另行运行 `process_material` exit 0 并发布 processed 后，`durable-after.json` 六个 locator 仍 queried-but-absent。UM-X04 在这个已上传且已处理的 US workspace 运行真实 `.venv/bin/dayu-cli tool_trace analyze --base <us-msft workspace> --output-dir <run-owned path> <us-msft workspace>`；cwd 为冻结 `repo`、stdin=`DEVNULL`，退出码 2，stderr 明确为“目录不包含受支持的 Tool Trace 布局”。X04 的 `filesystem-diff.json` 无新建、修改或删除，未产生分析产物；未超时、无残留进程。X04 是对同一目录的额外 public analyzer 检查，不单凭 analyzer 退出码证明全局不存在 Tool Trace。

直接证据：

- `observed-behavior.json` 的 `scenario_count=160`、`original_frozen_scenario_count=135`、`supplemental_scenario_count=25`
- `evidence/real/UM-R01-us-msft-real/result.json`、`sqlite-after.json`
- `evidence/cross/UM-X01-process-us-material/result.json`、`durable-after.json`、`filesystem-diff.json`
- `evidence/cross/UM-X04-tool-trace-absence/command.json`、`screen.txt`、`result.json`、`filesystem-diff.json`
- 全部 160 个场景各自的 `result.json`、`sqlite-before.json`、`sqlite-after.json`、`durable-before.json`、`durable-after.json`

## 语义 owner 与 Accepted 行为

`upload_material` 与 `process_material` 的直接 CLI 命令走 Fins direct Service/stream；source 与 processed 产物分别由 Fins storage owner 持久化。Host Run、EventLog、Trace、Memory 属于 Host/ToolRuntime 治理，legacy ingestion job 属于另一运行路径；不能从 Fins 业务文件存在反推这些层的记录，也不能要求 direct CLI 为本场景凭空生成 Agent Run。当前 Fins 文档亦将 direct stream 描述为用户可见进度边界而非 Host durable truth。实测的六类定位缺席与这条边界一致，不构成产品缺陷或补建 Host 状态的动机。

接受**冻结 160 个场景在其 CI-owned workspace 中的查询事实**，并针对本任务的真实 `upload_material`/`process_material` direct CLI 路径接受“分别发布 Fins source/processed 业务文件，但不创建已查询的 workspace SQLite、Host Run/EventLog/Tool Trace/Memory/runtime/legacy job 布局”。UM-X04 的 unsupported-layout exit 2 是该目录缺少可分析 Trace 布局的对照，不登记为 upload/process 错误；此裁决不扩大到所有 Host/Agent 或 LLM 工具入口、工作区外存储、未查询的日志位置或非冻结版本。此处没有 owner 级修复项。

当前不新增正式 oracle/scenario，不改写冻结 evidence、registry/readiness 或产品代码。正式断言必须保留 `queried=true`、`exists=false`、`owner_scope` 和候选模式，不把 “0 个数据库” 简化为无任何持久化。
