# WU-OBS-00 Slice 1 Live Workspace Remediation

```text
status=complete
work_unit=WU-OBS-00
slice=S1
gate=implementation re-review 后 live validation remediation
branch=work/wu-obs-00
artifact path=docs/reviews/wu-obs-00-slice-1-live-workspace-remediation-codex.md
next=Controller final acceptance
```

## 目标、范围与第一性原理裁决

- 本 gate 只关闭 Slice 1 的 live validation environment blocker，不修改 Analyzer、producer、
  schema、测试、control、plan、design 或 README。
- 旧真实 workspace 的 `PRAGMA user_version=20` 与当前 fresh schema owner 要求的 `24`
  不一致，strict loader fail closed 是正确行为。根因属于过期验证环境，不是 Analyzer 应通过
  compatibility、fallback、loose parser 或 raw SQLite 修复的 production 缺陷。
- 用户明确说明目标中的 `.dayu` 全为旧测试/验证数据，授权直接删除且不备份；随后又明确裁决
  本轮不要运行 `dayu-cli init`，不要创建或修改 `workspace/config`，fresh Host workspace
  由真实 `dayu-cli prompt` 正常 bootstrap。

## 删除目标与不可恢复性

删除前再次执行只读锁定：

```text
requested=/Users/leo/workspace/dayu-agent-r/workspace/.dayu
resolved=/Users/leo/workspace/dayu-agent-r/workspace/.dayu
type=Directory
symlink=false
inode=242211740
device=16777230
mode=drwxr-xr-x
owner=leo
group=staff
```

唯一删除命令：

```bash
rm -rf -- /Users/leo/workspace/dayu-agent-r/workspace/.dayu
```

删除后：

```text
exists_after=false
backup_created=false
recoverable=false
```

没有扩大删除 target，没有删除 `workspace`、`portfolio`、`workspace/tmp` 或其它路径。旧测试数据
未备份，删除不可恢复。

## CLI 文档、历史与采用的正式 workflow

本 gate 完整阅读了 `docs/cli_ci.md`，并执行：

```bash
git log --follow -- docs/cli_ci.md
```

结果显示该文档当前可追溯引入提交为：

```text
bd1d3e94c571e0b98096e9cfa4d169cefd8003c9
2026-07-20T21:30:37+08:00
WU-SEMANTIC-OWNERSHIP-01: align implementation with design truth (#179)
```

同时完整读取并关联以下真实 CLI 历史证据；三份 artifact 的原始提交均为
`3410d7422655c56bdf13c643f77c27f40b9d4550`：

- `docs/reviews/wu-cli-smoke-01-final-closeout.md`：用户清空 `.dayu` 后运行真实
  `dayu-cli interactive`，生成 EventLog、Tool Trace hot/cold 与业务工具样本。
- `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-gap-codex.md`：记录真实 prompt 产生
  runner-call、工具 request/result、terminal payload 与 descriptor graph 的证据。
- `docs/reviews/wu-cli-smoke-01-auto-validation-codex.md`：记录当时正式 init 命令与 public Host
  smoke；本 gate 最终按用户最新明确裁决不运行 init。

只读检查确认历史 `workspace/tmp/wu-cli-smoke-01-manual/interactive.log` 仍存在；没有复制其 DB、
cold JSONL、descriptor 或任何旧 schema 数据。

当前 `dayu-cli init` 与历史版本不同：它的正式事务同时拥有 `.dayu` 与 `config` 两个 managed
roots。由于用户硬边界禁止创建/修改 `workspace/config`，本 gate 没有运行 init，也没有采取
“先写后删 config”的越界路径。两个真实 prompt 均使用当前 CLI 默认/package config 解析，
`workspace/config` 在运行前后都不存在。

## 正式 CLI / Host producer 重建

### Prompt 1：验证 scene 工具暴露并触发 fresh Host bootstrap

```bash
source .venv/bin/activate
dayu-cli \
  --base /Users/leo/workspace/dayu-agent-r/workspace \
  --log-level debug \
  --log-file /Users/leo/workspace/dayu-agent-r/workspace/tmp/wu-obs-00-s1-live-remediation-prompt.log \
  prompt --no-thinking --detail \
  '请调用 get_current_time 工具获取 Asia/Shanghai 当前时间，然后只报告工具返回的时间。'
```

精确结果：

```text
exit_code=0
Activity: started 运行已接受
Activity: info 上下文预算已评估
Activity: in_progress 运行已开始
当前任务环境中没有 get_current_time 这个工具可供调用。
```

`prompt` scene 当前只暴露 `fins-read` / `web`，不暴露 `utils`；模型没有伪造工具调用。该正式
运行仍由 Host fresh bootstrap 创建 schema 24、initial runner-call 与 terminal trace。

### Prompt 2：生成真实 Tool Trace 工具链样本

```bash
source .venv/bin/activate
dayu-cli \
  --base /Users/leo/workspace/dayu-agent-r/workspace \
  --log-level debug \
  --log-file /Users/leo/workspace/dayu-agent-r/workspace/tmp/wu-obs-00-s1-live-remediation-list-documents.log \
  prompt --ticker 600519 --no-thinking --detail \
  '必须先调用 list_documents 工具，ticker 使用 600519，列出本地已有财报；然后只用一句话报告返回的文档数量。'
```

精确结果：

```text
exit_code=0
Activity: started 运行已接受
Activity: info 上下文预算已评估
Activity: in_progress 运行已开始
Activity: started 调用工具：列出文档 tool=列出文档 参数字段数：1
Activity: failed 工具返回：列出文档 tool=列出文档 结果状态：failed severity=error
Activity: failed 工具批次完成 total=1 completed=0 failed=1 cancelled=0 severity=error
Activity: info 上下文预算已评估
当前财报工具中未收录 ticker "600519"（贵州茅台）的任何文档，返回的文档数量为 0。
```

这是合法 current producer 样本：`list_documents` 被真实模型请求并由真实 Fins read tool
执行；业务结果是 source-owned `not_found`，Run 正常继续并 `RUN_SUCCEEDED`。没有 fake tool、
mock runner、raw SQLite insert、手改 DB/schema、复制旧数据或自行拼装 producer event。

## 真实样本概览

目标路径：

- cold：`workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`
- hot：`workspace/.dayu/host/dayu_host.sqlite3`
- artifact root：`workspace/.dayu/artifacts`

current-schema 结果：

```text
PRAGMA user_version=24
PRAGMA journal_mode=wal
hot_rows=14
cold_rows=14
payload_descriptors=12
```

Cold / hot event types 完全一致：

| Event type | Count |
| --- | ---: |
| `RUN_ACCEPTED` | 2 |
| `RUN_STARTED` | 2 |
| `RUNNER_CALL_INPUT_ASSEMBLED` | 3 |
| `USAGE_REPORTED` | 3 |
| `TOOL_CALL_REQUESTED` | 1 |
| `TOOL_RESULT_ACCEPTED` | 1 |
| `RUN_SUCCEEDED` | 2 |

真实工具链：

```text
tool_name=list_documents
tool_call_id=call_4d4499003b06448fa230af01
arguments={"ticker":"600519"}
arguments_summary_text=ticker=600519
result_status=failed
error_code=not_found
result_details=Financial Document Tools do not have this company: ticker='600519'.
```

Descriptor storage rows 全部是 current `sqlite_payload`，业务 descriptor kind 概览：

| Descriptor kind | Rows |
| --- | ---: |
| `runner_call_prepared_candidate` | 2 |
| `runner_call_input_manifest` | 3 |
| `runner_call_input_projection` | 3 |
| `selected_tool_schema_snapshot` | 2 |
| `engine_terminal_payload` | 2 |

三个 runner call 均为 `diagnostic.status=complete`：两次 initial dispatch 的
`message_count=2`，工具结果 continuation 的 `message_count=4`；每次都有
`runner_call_projection_artifact_ref/digest/size`。工具结果 continuation 复用已验证的 selected
tool schema snapshot ref，这解释了 descriptor 表只有 2 个 snapshot rows，而 normalized
dataset 中有 3 个 verified snapshot measures。

## Slice 1 strict loader live WAL success smoke

正式 strict call path：

```text
ToolTraceAnalysisSource(mode=WORKSPACE_DIRECTORY)
-> load_tool_trace_analysis_input(
     source,
     ToolTraceAnalysisPolicy(),
     HostSQLiteStoragePolicy(),
   )
```

未调用 writer opener、bootstrap、DDL、migration 或 transaction write。SQLite
`PRAGMA journal_mode=wal`，strict loader 在真实 WAL workspace 上成功。

精确 dataset 输出：

```text
status=success
source_mode=workspace_directory
hot_store_available=true
hot_event_sequence_watermark=41
hot_rows=14
cold_records=14
joined_records=14
input_diagnostics=[]
limitations=[]
cold_schema_versions=[1]
```

`ToolTraceAnalysisDataset` schema fields：

```text
source
cold_snapshot
hot_store_available
hot_event_sequence_watermark
hot_rows
cold_records
joined_records
input_diagnostics
limitations
payload_measures
```

Verified resolved measures 共 25 项：

| Category | Count | Exact sizes (bytes) |
| --- | ---: | --- |
| `cold_line` | 14 | 1431, 3236, 1453, 2492, 2152, 1432, 3237, 1454, 2491, 2426, 4173, 3143, 2276, 2152 |
| `runner_call_manifest` | 3 | 5775, 5781, 6229 |
| `runner_input_projection` | 3 | 10983, 11106, 12347 |
| `selected_tool_schema_snapshot` | 3 | 14656, 14656, 14656 |
| `source_event_payload` | 2 | 445, 328 |

每项均携带 owner 校验后的 `payload_ref`、`payload_digest`、实际 byte size、`event_id` 与
`event_sequence`；dataset 不暴露 payload body。没有 resolver mismatch、missing descriptor、
digest mismatch 或 capability limitation。

第一次临时取证输出脚本在 strict loader 已成功返回后，因错误从
`ToolTraceColdRecord.schema_version` 读取不存在的 convenience attribute 而退出 1；这不是
Analyzer/producer failure。临时脚本改为从 strict record 的 typed `fields["schema_version"]`
读取后重跑成功。两次均使用同一个正式 strict loader，没有替代数据路径。

## Analyzer 前后输入不变证据

成功 smoke 在同一 Python 进程内严格按
`before snapshot -> strict loader -> after snapshot` 执行。DB 统计只通过
`mode=ro&immutable=1` 读取；没有 insert/update/DDL。

| Metric | Before | After | Equal |
| --- | --- | --- | --- |
| cold SHA-256 | `404db1ec19ebcf504e4d57339ede41cd43d58b96809eef22cb294a9f760c0bed` | same | yes |
| cold `mtime_ns` | `1784870481283371756` | `1784870481283371756` | yes |
| cold size | `33562` | `33562` | yes |
| cold rows | `14` | `14` | yes |
| DB SHA-256 | `3a028b632879b093a8b43f25ae59dc55672239c85d35217fdd419a51adfa8ab1` | same | yes |
| DB `mtime_ns` | `1784870481284647460` | `1784870481284647460` | yes |
| DB size | `688128` | `688128` | yes |
| hot rows | `14` | `14` | yes |
| descriptor rows | `12` | `12` | yes |
| `user_version` | `24` | `24` | yes |

```text
inputs_unchanged=true
```

成功 smoke 的 before/after 都观察到 SQLite WAL read sidecars：
`dayu_host.sqlite3-wal` 存在且 size 0，`dayu_host.sqlite3-shm` 存在且 size 32768。它们不承载新增
业务 row；cold 与 durable DB 的 hash、mtime、size、row count 和 schema 全部不变。read-only
SQLite 在其它 OS 上的 sidecar 生命周期仍属于既有跨平台 residual。

## Tests / Pyright / Repository Audit

所有 Python 命令均先执行 `source .venv/bin/activate`。

### Slice 1 focused tests

```bash
pytest -q \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_tool_trace_analysis_input.py
```

```text
111 passed in 1.18s
```

### Complete Host tests

```bash
pytest -q tests/host
```

```text
2296 passed, 2 skipped, 6 deselected in 71.69s
```

### Targeted pyright

```bash
python -m pyright \
  dayu/host/tool_trace_analysis_contracts.py \
  dayu/host/tool_trace_analysis_input.py \
  dayu/host/tool_trace.py \
  dayu/host/open_host.py \
  dayu/host/durable/connection.py \
  dayu/host/durable/transaction.py \
  dayu/host/durable/tool_trace.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_package_exports.py
```

```text
0 errors, 0 warnings, 0 informations
```

### Full pyright

```bash
python -m pyright dayu/ tests/ utils/
```

```text
0 errors, 0 warnings, 0 informations
```

### Diff / scope audit

`git diff --check`：见最终 artifact 写入后的复核，预期且实际无输出。

本 remediation 的持久变更严格限于：

- 已授权目标 `workspace/.dayu`：先不可恢复删除旧数据，再由正式 CLI/Host producer 重建；
  该路径被 gitignore，不进入 source diff。
- 本 artifact。

没有修改任何 production、test、control、plan、design 或 README。当前 worktree 的其它 dirty
paths 全部属于进入本 gate 前已存在的 Slice 1 implementation、review/fix 与 Controller
artifacts。`workspace/config` 仍不存在。

两份本 gate debug log 与临时 strict-smoke 脚本均已从精确 task-owned 路径删除：

```text
workspace/tmp/wu-obs-00-s1-live-remediation-prompt.log
workspace/tmp/wu-obs-00-s1-live-remediation-list-documents.log
workspace/tmp/wu_obs_00_s1_live_smoke.py
temporary_task_files_cleaned=true
```

没有删除或改写历史 `workspace/tmp/wu-cli-smoke-01-manual/interactive.log`。

## Docs decision

`not-updated`。本 gate 不改变用户可见 workflow、production contract 或代码；用户又明确禁止
修改 README/control/plan/design。按 accepted plan，WU-OBS-00 的用户文档仍属于 Slice 4。

## Residual risks / uncovered

1. **跨平台 WAL sidecar lifecycle**：本机 macOS/Python 3.11 的 strict loader 已证明 durable
   DB/cold 完全不变；其它 OS 的 read-only SQLite sidecar 生命周期仍只有既有测试/CI owner。
2. **工具业务结果为受控失败**：真实工具调用覆盖 request/result producer 与 resolver，但本地
   Fins repository 对 `600519` 返回 source-owned `not_found`。这不影响 S1 输入完整性验收，
   也不冒充财报业务成功。
3. **未运行 interactive**：自动化 prompt 已完整产生 initial + tool-result continuation、
   hot/cold 与 descriptor graph；继续运行 interactive 不会增加 S1 必需 input capability，
   因此未增加 provider 成本和额外 workspace mutation。
4. **无 init 证据是显式裁决**：历史 artifact 记录过正式 init，但用户最终明确禁止本 gate
   运行 init 或创建 `workspace/config`；本次 fresh schema 24 由 public prompt -> Service ->
   Host bootstrap 产生。

没有 remaining acceptance blocker、未分类 finding 或 blocking open question。本 Agent 不
commit、push、创建 PR/Issue，也不进入 accepted slice commit 或 Slice 2。

## Next

`Controller final acceptance`。Controller 读取本 artifact、复核最终 diff/scope 后裁决 Slice 1
acceptance；本 Agent 到此显式停止。
