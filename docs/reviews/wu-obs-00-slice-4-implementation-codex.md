# WU-OBS-00 Slice 4 Implementation Artifact

- status: `complete`
- work unit: `WU-OBS-00`
- slice: `Slice 4 — Service/CLI publication`
- implementation base: `179520e08e8c6b59cdf49aefc59bc4463c9698c2`
- implementation agent: `codex`
- next entry point: `code review`
- self-advance: `never`

## 1. 范围与停止条件

本次只执行 Slice 4 implementation，没有进入 code review、commit、push、PR 或 Issue 操作。
Controller 预先修改的 `docs/host/issues-implementation-control.md` 始终只读，不计入本次实现文件。
冻结的 contracts、rules、input、producer 与 schema 均未修改。

硬停止条件没有触发。真实 `dayu-cli prompt` 成功经 Host 生成 fresh
current-schema Tool Trace 数据，并且同时存在 hot、cold 与 payload descriptor；
随后才执行 directory mode 与 cold-file mode 的真实 analyzer smoke。

## 2. Changed files

生产代码：

- `dayu/service/tool_trace_analysis.py`
- `dayu/cli/commands/tool_trace.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`

测试：

- `tests/service/test_tool_trace_analysis.py`
- `tests/cli/test_tool_trace_command.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_import_boundary.py`

文档：

- `README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/service/README.md`
- `tests/README.md`
- `docs/reviews/wu-obs-00-slice-4-implementation-codex.md`

`dayu/host/tool_trace_analysis.py` 没有改动：Slice 3 已提供所需 Host public
analyze API 与同一 structured report 的 JSON/Markdown renderer，Slice 4 直接复用
该 public contract，避免在 Service 或 CLI 重建分析语义。

## 3. Owner decisions

### 3.1 Host

Host 是分析语义及 structured report 的唯一 owner。Service 只通过
`dayu.host` public API 获取 `ToolTraceAnalysisReport`，JSON 与 Markdown 都由
Host public renderer 从同一个 report 渲染。CLI 不导入 Host 内部模块。

### 3.2 Service

Service 是输入发现和文件发布语义的 owner：

- 支持四种显式 input mode：workspace、artifacts 目录、`.dayu` 目录、cold
  `.jsonl` 文件。
- 目录发现要求唯一 canonical source；缺失、歧义、非法文件后缀与 source
  构造失败均投影为 typed usage failure。
- 固定发布 `tool-trace-analysis.json` 与 `tool-trace-analysis.md`。
- 两份内容先在各自目标目录创建 same-directory temporary file，以严格
  UTF-8 写入并 `flush`，再按 JSON、Markdown 顺序执行 `os.replace`。
- publication failure 的 `published_paths`、`failed_path`、primary failure、
  cleanup secondary failures 与 `temporary_paths_cleaned` 由 Service failure
  contract 一次性产生；CLI 只展示，不反推。

原子发布故障矩阵覆盖：

- 第一次 replace 失败：没有已发布路径，JSON 为 `failed_path`，两份临时文件
  都进入 cleanup。
- 第二次 replace 失败且没有旧 Markdown：JSON 是唯一已发布路径，Markdown
  为 `failed_path`，只清理仍未 replace 的 Markdown 临时文件。
- 第二次 replace 失败且已有旧 Markdown：旧 Markdown 保持不变，JSON 是唯一
  已发布路径，Markdown 仍是稳定的 `failed_path`。
- cleanup 自身失败：不覆盖 primary replace failure；作为独立 typed secondary
  failure 报告，并据实际结果计算 `temporary_paths_cleaned`。

### 3.3 CLI

CLI 只依赖 Service/public contracts：

- 注册 `dayu-cli tool_trace analyze INPUT --output-dir OUTPUT_DIR`。
- 成功返回 `0`；usage failure 返回 `2`；analysis/publication failure 返回 `1`。
- partial publication 明确输出已经发布的路径与失败目标；cleanup failure 单独
  输出，不伪装成分析错误。

## 4. 真实 producer 与 analyzer smoke

### 4.1 前置清理

先精确检查目标：

- 删除目标：`/Users/leo/workspace/dayu-agent-r/workspace/.dayu`
- 目标是非符号链接目录。
- 未发现正在运行的 Dayu CLI producer。
- `workspace/config` 原本不存在，删除前后都不存在；没有运行 `init`。

按用户明确授权，仅删除上述 `.dayu` 旧测试数据。删除是不可恢复的，未创建
备份；没有删除 `workspace/config` 或扩大删除范围。

### 4.2 真实生产命令

```bash
source .venv/bin/activate
dayu-cli \
  --base /Users/leo/workspace/dayu-agent-r/workspace \
  --log-level debug \
  --log-file /Users/leo/workspace/dayu-agent-r/workspace/tmp/wu-obs-00-s4-real-producer.log \
  prompt --ticker 600519 --no-thinking --detail \
  '必须先调用 list_documents 工具，ticker 使用 600519，列出本地已有财报；然后只用一句话报告返回的文档数量。'
```

脱敏结果：

- CLI run 被接受并完成。
- Host 实际执行了 `list_documents` 工具。
- 工具返回 source-owned `not_found` 结果，最终模型报告文档数为 `0`。
- 本次 smoke 的目的在于验证真实 producer/Host/Tool Trace 链路；财报查询没有
  本地文档并不影响 Tool Trace schema 与存储验证。

producer 后的只读证据：

- SQLite schema object count：`24`
- hot row count：`9`
- cold row count：`9`
- payload descriptor count：`7`
- cold schema versions：`[1]`
- artifact regular-file count：`4`
- artifact tree digest：`589b1cc...`（脱敏缩写）

没有使用 fixture、测试 helper、直接写 SQLite/JSONL、兼容读取、替代 producer，
也没有绕过 Service/Host。

### 4.3 真实 analyzer 命令

directory mode：

```bash
python -m dayu.cli tool_trace analyze \
  /Users/leo/workspace/dayu-agent-r/workspace \
  --output-dir '<独立 mktemp 输出目录>'
```

cold-file mode：

```bash
python -m dayu.cli tool_trace analyze \
  /Users/leo/workspace/dayu-agent-r/workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl \
  --output-dir '<独立 mktemp 输出目录>'
```

两种模式都返回 `0`，并发布非空 JSON 与 Markdown。对同一 report 的双格式
结果逐项核对 counts：

- directory mode：findings `2`、limitations `5`、vendor records `1`
- cold-file mode：findings `2`、limitations `8`、vendor records `1`

directory mode：

- `hot_available=true`
- `cold_available=true`
- `payload_resolution_available=true`
- 没有产生虚假 digest mismatch finding。

cold-file mode：

- `hot_available=false`
- `cold_available=true`
- `payload_resolution_available=false`
- limitation reason codes 包含
  `hot_store_unavailable`、`payload_resolution_unavailable`、
  `client_correlation_id_unavailable`、`provider_request_id_unavailable`、
  `vendor_execution_id_unavailable`、`vendor_iteration_id_unavailable`、
  `vendor_source_payload_unavailable` 与 `tool_timing_missing`。
- Markdown 明确表达相关事实“无法证明”，没有把 source limitation 投影成
  observed provider fact。

### 4.4 输入只读性

analyzer 读取前后完全一致：

- cold SHA-256：
  `06a9d18a369ebfefa6bee815cfa8d4a7fa541c26006bee4450907a6aac2e75f9`
- SQLite SHA-256：
  `fe72fbfcdced9006738cd9985702488e8e804cecf077ca97559f83a4d19bf400`
- hot row count：`9`
- payload descriptor count：`7`
- cold schema versions：`(1,)`
- artifact tree：`4:589b1cc...`（脱敏缩写）
- smoke assertion：`inputs_unchanged=true`

## 5. Tests, pyright and coverage

Focused tests：

```bash
pytest -q \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py
```

结果：`93 passed`。

完整 affected matrix：

```bash
pytest -q \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py
```

结果：`232 passed`，另有 `3` 条第三方依赖 deprecation warning。

完整 pyright：

```bash
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

修改文件的 focused branch coverage：

```bash
pytest -q \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py \
  --cov=dayu.service.tool_trace_analysis \
  --cov=dayu.cli.commands.tool_trace \
  --cov=dayu.cli.arg_parsing \
  --cov=dayu.cli.main \
  --cov-branch --cov-report=term-missing
```

结果：`93 passed`。

Host/Service/CLI analyzer matrix 的逐文件 branch coverage：

```bash
pytest -q \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  --cov=dayu.host.tool_trace_analysis_contracts \
  --cov=dayu.host.tool_trace_analysis_input \
  --cov=dayu.host.tool_trace_analysis_rules \
  --cov=dayu.host.tool_trace_analysis \
  --cov=dayu.service.tool_trace_analysis \
  --cov=dayu.cli.commands.tool_trace \
  --cov-branch --cov-report=term-missing
```

结果：`74 passed`。逐文件 branch coverage：

| 文件 | branch coverage |
| --- | ---: |
| `dayu/cli/commands/tool_trace.py` | 100% |
| `dayu/cli/arg_parsing.py` | 99% |
| `dayu/cli/main.py` | 92% |
| `dayu/host/tool_trace_analysis.py` | 100% |
| `dayu/host/tool_trace_analysis_contracts.py` | 86% |
| `dayu/host/tool_trace_analysis_input.py` | 81% |
| `dayu/host/tool_trace_analysis_rules.py` | 92% |
| `dayu/service/tool_trace_analysis.py` | 91% |
| aggregate | 88% |

所有被新增或修改的生产文件均达到单文件覆盖率目标。

## 6. README decisions

实现前已逐个完整阅读以下五份 README 的 `Agent更新约束` 与现有职责：

- `README.md`：命中最终用户 CLI 入口、参数、输出文件与排障方式，已更新。
- `dayu/README.md`：命中 Service/Host/CLI 分层装配与依赖边界，已更新。
- `dayu/host/README.md`：命中 Host public analyzer/report owner contract，已更新。
- `dayu/service/README.md`：命中输入发现、发布与 typed failure owner，已更新。
- `tests/README.md`：命中测试入口、覆盖矩阵与验证命令，已更新。

## 7. Remaining risks

- 双文件发布无法在普通文件系统上形成跨两个目标的单事务。实现按计划提供
  单文件原子 replace、稳定顺序与 typed partial-publication truth；调用方必须
  依据 `published_paths` 和 `failed_path` 处理第二次 replace 失败。
- cold-file mode 天然不能证明 hot-only 与 payload-backed 事实；相关 limitation
  是设计内行为，不是 analyzer failure。
- 本次真实样本的工具业务结果是 `not_found`，因此证明的是生产链路与
  current-schema 数据可用性，不证明本地财报文档存在。
- 真实 smoke 生成的数据保留在忽略版本控制的 `workspace/.dayu`；没有进入 Git
  变更集。
- affected matrix 中的 3 条 deprecation warning 来自既有第三方依赖，本次未
  修改其 owner。

## 8. Gate handoff

- implementation status: `complete`
- blocker: `none`
- stop condition: `not triggered`
- next entry point: `code review`
- instruction: `never self-advance`
