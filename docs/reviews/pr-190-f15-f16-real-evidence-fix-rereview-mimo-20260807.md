# F16 Real-Evidence Publication Follow-up Re-Review

## Scope

- Mode: current changes（未提交 workspace changes）
- Branch: `codex/interactive-oracle`
- Base: `1a339fd9e046b959a96d290297930279204790f4`
- Reviewer: AgentMiMo（独立只读审查）
- Output file: `docs/reviews/pr-190-f15-f16-real-evidence-fix-rereview-mimo-20260807.md`
- Included scope:
  - `utils/cli_ci_run_observation.py` — tracked helper，新增唯一 typed raw DB path classifier
  - `tests/cli/test_cli_ci_run_observation.py` — owner 测试矩阵扩展
  - `workspace/tmp/prompt_observe_calibration.py` — ignored prompt harness snapshot producer
  - `workspace/tmp/f14_real_cli_observation.py` — ignored F14 harness cold JSONL collector
  - `docs/cli_ci.md` — contract 文档同步
  - `docs/gateflow/pr-190-f15-f16-implementation-20260807.md` — implementation artifact
  - `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md` — review-fix artifact
  - `tests/README.md` — test 覆盖说明同步
- Parallel review coverage: 无

## 审查重点

1. tracked helper 的 typed raw DB path classifier 是否为唯一 owner
2. 主库及 WAL/SHM、嵌入文本、普通路径反例、symlink target producer 处理和 final scanner fail-closed 是否同源且无放宽
3. ignored prompt harness snapshot producer 是否不再发布 raw DB path 而仍保留独立只读 SQLite 投影
4. ignored F14 harness 用 canonical cold JSONL 调用 production `dayu-cli tool_trace analyze` 是否保留本场景所需 Run/tool-call/finding/request-response/audit 真源、是否与 EventLog context compact 投影同源且没有下游字符串删除或双真源
5. tests/docs/digests、F14 Host product 与 formal Oracle 禁改面零漂移

## Findings

未发现实质性问题。

### 审查证据链

#### 1. Typed Raw DB Path Classifier 唯一所有权

`classify_public_evidence_path()`（`utils/cli_ci_run_observation.py:245-263`）是唯一的 typed 分类真源：

- `PublicEvidencePathClassification` StrEnum 定义 `PUBLISHABLE` / `RAW_DATABASE` 两个 typed 值（行 65-69）。
- `_RAW_DATABASE_PATH_PATTERN` regex（行 43-46）覆盖 `.sqlite`、`.sqlite3`、`.db` 主库及其 `-wal`、`-shm` sidecar，以 end-of-string 或 `[/\\?#\s"',;)\]]` 作为终止符。
- `scan_public_evidence_files` 在文件路径检查（行 785-792）和文件内容文本扫描（行 832-838）两处均调用该函数，不复制 suffix 集合或 regex。
- 旧的 `_RAW_DATABASE_SUFFIXES` frozenset 已被删除，无残留。
- `__all__` 已导出 `PublicEvidencePathClassification` 和 `classify_public_evidence_path`。

**Regex 正确性验证**：
- 主库 + WAL/SHM：`.sqlite`、`.sqlite-wal`、`.sqlite-shm`、`.sqlite3`、`.sqlite3-wal`、`.sqlite3-shm`、`.db`、`.db-wal`、`.db-shm` → 全部 `RAW_DATABASE` ✓
- 嵌入文本：`{"path": "/private/ci/.dayu/host/dayu_host.sqlite"}` → `RAW_DATABASE` ✓
- 普通路径反例：`reports/sqlite-summary.json`、`database/report.json`、`archives/report.db.backup`、`notes/report.sqlite3.txt`、`.dayu/artifacts/tool-trace/tool-trace-cold.jsonl` → 全部 `PUBLISHABLE` ✓
- 边界：`report.db.backup`（`.db` 后跟 `.backup` 不是终止符）→ `PUBLISHABLE` ✓

#### 2. Final Scanner Fail-Closed 未放宽

`scan_public_evidence_files`（行 710-846）的 path hygiene 检查：

- scope 外文件 → `outside_evidence_root` violation ✓
- symlink（含 ancestor） → `symlink_forbidden` violation，先于 raw DB 检查 ✓
- resolved path 逃逸 root → `outside_evidence_root` violation ✓
- raw DB 文件路径 → `raw_database_file_forbidden` violation，复用 `classify_public_evidence_path` ✓
- raw DB 文本内路径 → `raw_database_path_forbidden` violation，复用同一函数 ✓
- 任一命中均 `continue` 跳过后续检查 ✓

`write_final_publication_scan_report`（行 849-939）：
- report target 拒绝 `..` traversal ✓
- resolved report 必须在 root 内 ✓
- ancestor symlink 检查 ✓
- 既有/stale report → fail closed ✓
- 独占创建 `open("x")` ✓

未发现放宽 fail-closed 的修改。

#### 3. Ignored Prompt Harness Snapshot Producer

`workspace/tmp/prompt_observe_calibration.py` 的 `_filesystem_snapshot`（行 720-764）：

- 遍历 `root.rglob("*")` 时，对每个 relative path 调用 `run_observation.classify_public_evidence_path(relative)`，`RAW_DATABASE` 时 `continue` 跳过（行 737-740）。
- 对 symlink target 也调用同一函数，target 为 raw DB 时跳过（行 744-748）。
- 独立只读 SQLite 投影 `_sqlite_snapshot()` / `_runtime_lane_snapshot()` 仍保留，输出 schema/counts/selected rows，不包含 DB 文件路径。
- `_run_scenario` 写入 `sqlite-before.json` / `sqlite-after.json` / `runtime-lane-before/after.json`，这些是业务/audit 投影，不含 raw DB 路径。

**验证**：snapshot producer 不发布 raw DB path，独立 SQLite 投影保持不变，符合预期。

#### 4. Ignored F14 Harness Cold JSONL Collector

`workspace/tmp/f14_real_cli_observation.py` 的 `_collect_public_evidence`（行 808-856）：

- 输入改为 canonical `TOOL_TRACE_COLD_RELATIVE` = `.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`（行 45-47），这是已发布的 artifact 路径，不是 raw DB。
- 调用 production `dayu-cli tool_trace analyze --base <workspace> --output-dir <evidence> <cold_jsonl>`。
- 未修改产品 analyzer/schema，未删除报告字段或做字符串替换。
- `tool_trace_input_mode` 固定为 `"canonical_cold_jsonl"`（行 851）。
- output report 路径为 `evidence/public/{CHAIN_NAME}/tool-trace-analysis.json`（行 853）。

**Context compact 真源**：`_context_compaction_observation`（行 924-969）通过 `open_host_durable_read_store` + `EventLogStore` filtered reader 读取 `CONTEXT_COMPACTED` 事件，与 EventLog context compact 投影同源。`_project_context_compactions_in_transaction` 使用 `resolve_context_compacted_payload` + `parse_context_compacted_semantic_payload` production owner 解析 payload。无下游字符串删除或双真源。

**Run/tool-call/finding 真源**：cold JSONL 由 production `dayu-cli tool_trace analyze` 生成，保留 28 runs、10 findings、9 tool calls、20 payload rankings（implementation artifact 记录），`hot=false` 且无 `.db` 路径。与 EventLog hot-store 投影 (`_tool_trace_projection`) 为同一 production owner 的不同 input mode，不形成双真源。

#### 4b. Per-Scenario tool-trace.json Request/Response 事实链

Controller 要求补充审查 per-scenario `tool-trace.json` 的 request/response 事实链完整性。本场景存在两条 Tool Trace 投影路径：

**路径 A — per-scenario `tool-trace.json`（内部证据，prompt harness `_tool_trace_projection`）**：

- producer：`workspace/tmp/prompt_observe_calibration.py:1868-1901`
- owner：production `dayu.host.durable.tool_trace`，通过 `open_host_durable_read_store` 打开 hot store
- 调用链：`read_tool_trace_page` → `read_runner_call_reconstruction_signals_by_run` → `resolve_runner_call_projection_from_signal`
- 保留的事实：
  - **Run facts**：`event_sequence`, `event_type`, `event_class`, `session_id`, `run_id`, `attempt_id`, `execution_id`（行 1801-1813）
  - **tool-call facts**：`tool_call_id`, `tool_name`, `provider_request_id_present`, `trace_summary`（行 1809-1812）
  - **request-response facts**：`runner_input_projection`（runner 实际发送的 input payload）、`selected_tool_schema_snapshot`（tool schema 快照）、`manifest`（runner-call manifest）（行 1843-1858），均由 hot store 的 `resolve_runner_call_projection_from_signal` 解析，具备完整 payload resolution
  - **audit facts**：`event_id`, `diagnostic.status`（signal 完整性诊断）（行 1841-1842）
- 脱敏：通过 `_redact_json(result, pairs)` 精确值替换，不删除字段（行 1894）
- 写入路径：`evidence/{scenario_id}/tool-trace.json`（行 2880）

**路径 B — public `tool-trace-analysis.json`（公开证据，F14 harness `_collect_public_evidence`）**：

- producer：`workspace/tmp/f14_real_cli_observation.py:808-856`
- owner：production `dayu-cli tool_trace analyze`，输入为 canonical cold JSONL
- capabilities：`cold=true`, `hot=false`, `payload_resolution=false`
- 保留的事实（production analyzer schema v2）：
  - **Run facts**：`runs[]` 每项包含 `run_id`, `session_ids`, `attempt_ids`, `execution_ids`, `tool_call_ids`, `tool_names`, `provider_request_ids`, `event_count`, `tool_request_count`, `tool_result_count` 等聚合
  - **tool-call facts**：cold JSONL 每行的 `tool_call_id`, `tool_name`, `normalized_arguments_digest`, `trace_summary.tool_request/tool_result`
  - **finding facts**：`findings[]` 每项含 `finding_id`, `rule_id`, `layer`, `severity`, `priority`, `evidence[]`（每条 evidence 携带 `source_path`, `line_number`, `event_id`, `event_sequence`, `event_type`, `observed`）
  - **request-response facts**：cold mode 保留 `trace_summary` 中的 bounded summary objects 和 cryptographic payload binding（`source_payload_ref/digest`, `payload_ref/digest`），不携带 raw payload body；这符合公开证据的脱敏要求
  - **audit facts**：`signal_coverage[]`（integrity/tool_timing/context_pressure/payload_measurement/vendor_debugging），`limitations[]`（每个 limitation 含 `reason_code`, `evidence[]`）
  - **compactor responses**：cold-only mode 为空（需要 hot store runner-call reconstruction signals）；此事实由独立 EventLog projection `_context_compaction_observation` 补充（见下方）
- `input` section 安全性：`hot_db_path=null`, `requested_path` 指向 cold JSONL，`capabilities.hot=false`；report 中无 raw DB 路径
- Evidence `source_path` 只引用 cold JSONL 文件路径，不引用 DB

**两条路径的关系与双真源审查**：

| 事实维度 | 路径 A（hot per-scenario） | 路径 B（cold public） | 是否双真源 |
|---|---|---|---|
| Run identity | hot store projection | cold JSONL aggregation | 否：同一 production owner 不同 input mode |
| tool-call | hot rows + runner-call resolver | cold records + deterministic rules | 否：cold 是 hot 的 projection sink |
| request-response | full payload resolution | bounded summary + crypto binding | 否：cold 是 hot 的脱敏投影 |
| findings | hot-only diagnostics | cold+rule diagnostics | 否：cold rules 是 hot diagnostics 的子集投影 |
| compactor responses | hot store resolver | 空（cold mode） | 否：由独立 EventLog projection 补充 |

**Context compact 事实补充**：compactor responses 在 cold-only mode 为空，但 context compaction 事实由 `_context_compaction_observation`（行 924-969）通过 `open_host_durable_read_store` + `EventLogStore` filtered reader 独立提供，写入 `evidence/public/context-compaction-observation.json`。该 projection 使用 `resolve_context_compacted_payload` + `parse_context_compacted_semantic_payload` production owner，与 EventLog context compact 投影同源。public bundle 的 `execution-index-f15-f16.json` 中 `context_compaction_observation` 字段引用此文件。

**结论**：两条路径为同一 production owner 的 hot/cold 双模投影，不形成双真源。per-scenario 内部证据保留完整 request/response payload；public 证据通过 cold JSONL + bounded summary + cryptographic binding 实现脱敏，compactor responses 缺口由独立 EventLog projection 补充。无下游字符串删除或 loose deletion。

#### 5. Tests/Docs/Digests/Oracle 零漂移

**Tests**：
- 新增 `test_public_evidence_path_classifier_rejects_sqlite_main_and_sidecars`：9 个 parametrize case 覆盖三类主库 + WAL/SHM + 嵌入文本 ✓
- 新增 `test_public_evidence_path_classifier_keeps_ordinary_paths`：5 个 parametrize case 覆盖普通路径反例 ✓
- 新增 `test_public_path_hygiene_detects_raw_database_sidecar_files`：6 个 parametrize case 覆盖 final scanner 对 WAL/SHM sidecar 文件的拒绝 ✓
- 新增 `test_final_publication_scan_completes_for_owner_sanitized_bundle`：完整 owner 产出 bundle 的 final scan 得到 `status=complete` ✓
- 52 passed，tracked helper 单文件 coverage 82% ✓

**Docs**：
- `docs/cli_ci.md` 同步 snapshot/cold Tool Trace owner、WAL/SHM sidecar、formal `unadjudicated` ✓
- `tests/README.md` 同步 focused owner 测试说明 ✓
- implementation/review-fix artifact 同步 SHA-256 和 fresh evidence 闭环记录 ✓

**Oracle 禁改面**：
- `oracle_status` 固定为 `"unadjudicated"`（F14 harness 行 1368）✓
- `scenario_status` 固定为 `"unadjudicated"`（prompt harness run-manifest）✓
- 未引入 `scenario_success`、综合 `success/passed` 或由 exit 0 推导的 scenario verdict ✓

## Open Questions

无。

## Residual Risk

- `assigned to subsequent accepted clean-target validation gate / Controller`：本 review 基于未提交 workspace changes 的 deterministic 代码审查；尚未对 post-fix 修复执行新的 provider/AAPL real rerun。accepted plan 要求 real rerun 只针对 clean committed target。
- `assigned to independent final re-review gate / Controller`：本轮 re-review 未发现实质性问题，但仍需 Controller 最终裁决后方可进入 commit 或 real rerun。
- regex 终止符覆盖：当前 regex 以 `[/\\?#\s"',;)\]]` 作为终止符，覆盖了常见路径分隔符和 JSON/命令行边界字符。对于非常规嵌入格式（如无分隔符直接拼接），regex 可能无法匹配，但这属于"不降低已有检测"而非"必须覆盖所有理论边界"的范畴，风险可控。

## 结论

**PASS**。F16 real-evidence publication follow-up 的代码修改在 correctness、semantic owner drift、false negative/positive 和 public bundle audit gaps 方面均未发现实质性问题。typed raw DB path classifier 为唯一 owner，final scanner fail-closed 未放宽，snapshot producer 正确过滤 raw DB path，cold JSONL collector 保留 production analyzer 真源，tests/docs/oracle 禁改面零漂移。
