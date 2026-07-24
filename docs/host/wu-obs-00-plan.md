# WU-OBS-00 Tool Trace Analyzer Implementation Plan

## 1. Gate / Status

- Work Unit：`WU-OBS-00` Tool Trace Analyzer。
- Issue：GitHub Issue #70；Issue #34 作为 integrity / large-payload 子项并入本 WU；
  Issue #119 的 usage observation correlation 边界在本 plan 中完成裁决。
- 当前 gate：`second plan fix complete / ready-for-second-plan-re-review`。
- 本 artifact 只定义 code-generation-ready implementation plan，不实现代码、不修改 issue、
  control doc、design doc、测试、README 或生产文件。
- Plan status：`complete / ready-for-second-plan-re-review`。
- Blocking open questions：None。
- Stop-condition decision：未触发。现有 semantic owner、输入 contract、公开入口和 schema 边界
  均可由 design、goal confirmation、当前代码与真实 trace 直接裁决，无需猜测或下游补偿。
- Plan review artifacts：
  - `docs/reviews/plan-review-20260724-110330.md`
  - `docs/reviews/plan-review-20260724-110122.md`
- 首轮 Controller disposition：
  `docs/reviews/wu-obs-00-plan-review-adjudication-controller.md`，
  decision=`plan-fix-required`。
- Plan fix artifact：`docs/reviews/wu-obs-00-plan-fix-codex.md`。
- Plan re-review artifacts：
  - `docs/reviews/plan-review-20260724-112830.md`
  - `docs/reviews/plan-review-20260724-112958.md`
- 当前唯一 disposition 真源：
  `docs/reviews/wu-obs-00-plan-rereview-adjudication-controller.md`，
  decision=`plan-fix-required`；本版已落实全部新 accepted findings，并清除被新裁决取代的
  public lock field、全文件持锁读取、SQLite timeout 自建与复数 report schema 描述，等待同一
  计划的再次双路独立 re-review。
- Second plan fix artifact：
  `docs/reviews/wu-obs-00-plan-rereview-fix-codex.md`。

## 2. Goal / Motivation / Success Signal

### 2.1 Goal

交付一个本地 operator-facing Tool Trace Analyzer：

1. 输入当前 Dayu Tool Trace cold JSONL 文件，或当前 Dayu workspace / `.dayu` /
   tool-trace 目录。
2. 对有 hot SQLite 与 artifact root 的目录输入，读取并校验 hot rows、cold lines 与
   payload descriptor graph；对 file-only 输入保持 cold-only。
3. 输出同一分析结果派生的 structured JSON report 与 Markdown report。
4. 报告按 Host / Engine / Tool 分层；每条 confirmed finding 必须引用直接 trace /
   hot row / cold line / resolved descriptor 证据。
5. 覆盖重复调用、工具失败、异常延迟、provider/protocol 异常、large payload、
   truncation / `fetch_more`、hot/cold/payload integrity、context pressure 和 vendor
   debugging block。
6. 对 file-only、hot store 缺失、payload 不可解析、timing/partial signal 缺失、
   provider identity 缺失及 Issue #64 尚未完成的 native Anthropic / Claude Code gateway
   path 显式输出 limited signal。
7. WU-OBS-01 后续直接复用本 WU 的 typed source、analyzer、rules 与 report contract，不再实现
   第二套 Host / Engine / Tool 归因逻辑。

### 2.2 Motivation / first-principles judgment

动机成立，且严重性评估正确。

生产系统已经生成可关联的 hot row、cold JSONL 和 payload descriptor，但没有 operator
入口把这些投影转换成可复核的诊断。当前人工排障必须同时理解 JSONL、SQLite、EventLog
payload、runner-call manifest 与 resolver 代码；这不是普通日志统计缺口，而是“现有诊断事实
无法稳定投影成 operator decision support”的缺口。

正确方案不是复制旧 `tool_trace_v2` analyzer，也不是在 Analyzer 中建立第二套 truth：

- EventLog / Engine / ToolRuntime producer 继续拥有 canonical facts 和 signal。
- `dayu.host.tool_trace` 继续拥有 hot/cold projection。
- `dayu.host.durable` resolver 继续拥有 descriptor ref/digest/size 与实际 bytes 的完整性。
- Analyzer 只拥有输入标准化、聚合、诊断规则、limited-signal 判定和 report contract。
- Service 只拥有用户路径发现与 report 文件发布。
- CLI 只拥有参数、退出码和 operator 文本。

### 2.3 Success signal

- `dayu-cli tool_trace analyze <INPUT> --output-dir <DIR>` 可对当前 Dayu 输入形态运行。
- 成功运行总是生成：
  - `<DIR>/tool-trace-analysis.json`
  - `<DIR>/tool-trace-analysis.md`
- 两个文件来自同一个 immutable `ToolTraceAnalysisReport`；Markdown 不重新计算规则。
- JSON report 的 `schema_version=1`，字段、枚举、null / limited-signal 含义稳定、自解释。
- 当前 workspace 目录输入能发现：
  - `workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`
  - `workspace/.dayu/host/dayu_host.sqlite3`
  - `workspace/.dayu/artifacts`
- 当前真实样本可完成 hot/cold join 和 runner-call / payload resolution；不产生虚假的
  digest mismatch。
- cold-file 输入可完成 cold parse、line digest 与可由 cold 直接证明的规则，同时明确
  `hot_store_unavailable` / `payload_resolution_unavailable`。
- corrupt line、missing cold line、source-key conflict、dangling ref、digest mismatch 都有
  owner-level analyzer tests。
- provider-native request id、client correlation id 与本地 run / attempt / execution /
  iteration / event / trace refs 同一 vendor block 呈现；缺失项进入 limitations，不被伪造。
- Issue #64 path 只能显示 limited signal，不根据 header 名、provider 名、timestamp、
  iteration 顺序或本地 id 猜 provider-native identity。
- `USAGE_REPORTED` 只产生 post-call context-pressure observation，不与 provider debugging
  block 做 request-level join。
- 新增/修改代码通过受影响测试、全量 pyright；每个新增/修改的 analyzer 源文件覆盖率
  单文件不低于 80%。

## 3. Non-goals / Scope Boundary

### 3.1 Explicit non-goals

- 不修改 Tool Trace producer 语义或输出 contract：event filter、extract/render、cold line
  schema、digest 计算、append ordering 与既有 file-lock timeout value 均保持不变。S1 允许把
  lock path 派生移动到 Tool Trace owner 的共享内部 helper，并由 projection regression tests
  证明 producer 行为等价。
- 不修改 EventLog、Run / Attempt / Host / Engine 状态机。
- 不新增 trace-completion slice。
- 不扩展 `UsageReportedData`、Host usage payload 或 usage Tool Trace schema。
- 不从 iteration、event sequence、timestamp、display text 或 client correlation id 推断
  provider request identity。
- 不复制旧仓库 `tool_trace_v2`、Engine-owned recorder、`raw_payloads` 布局或旧类型。
- 不实现 prompt / final-answer fragment 反查、bundle export 或历史 run 选择；由 WU-OBS-01
  承接。
- 不连接真实 provider、外部观测平台、远端数据库、告警系统或 ticket system。
- 不创建通用 rule engine、plugin framework、DSL、registry discovery、stream processor 或
  新存储层。
- 不实现 cold trace rotation / retention / archive discovery；由 Issue #36 承接。
- 不把 report 写回 Host SQLite、EventLog、projection checkpoint、memory、audit 或其它
  durable truth。
- 不输出财报业务判断，不把 trace signal 伪装成财务事实。
- 不把 resolved full prompt/messages、provider raw body、完整工具 payload 或 secret
  写进 JSON/Markdown report；resolver 只用于校验、计量和读取现有 typed signal。
- 不按 finding severity 改变成功退出码，不在首版加入 `--fail-on` policy。
- 不新增 CLI policy tuning flags；CLI 使用写入 report 的默认 policy，typed Host API 继续允许
  显式注入 policy。
- 不预先决定 WU-OBS-01 是否复用本 WU 的 Service path discovery；本 WU 只承诺 typed Host
  source/analyzer/report 可复用。

### 3.2 Scope boundary invariants

1. Analyzer 不 repair 输入，不重写 JSONL，不修复 descriptor，不 catch up projection。
2. confirmed finding 和 limitation 分离：
   - `findings` 只承载由直接证据成立的诊断，`evidence` 非空。
   - `limitations` 只承载无法证明的 signal coverage，不能写成已发生故障。
3. 缺失字段不使用默认业务语义；strict parser 把 malformed record 记录为 input integrity
   finding，并排除出后续业务规则。
4. hot/cold/payload mismatch 不使用 loose join；只用 `event_id`、`cold_trace_ref`、
   digest、typed ref 和现有 resolver。
5. Analyzer recommendation 只指向正确 owner，例如 producer protocol、Host governance 或
   Tool contract；不在下游报告建议通过 fallback 掩盖错误。

## 4. Alignment

### 4.1 Design document alignment

与 `docs/host/design.md` 的对齐如下：

- §14 / §14.1：Tool Trace 是 committed EventLog 的 hot/cold 派生 projection，不是 recovery、
  resume、memory 或状态迁移真源。Analyzer 只读该 projection。
- §13.1：payload descriptor resolver 是 ref/digest/size/actual bytes 完整性的唯一 owner。
  Analyzer 复用 resolver，不从 metadata 或 digest 猜 payload。
- Tool Trace runner-call reconstruction contract：Analyzer 只消费 manifest / projection /
  schema refs 和 typed diagnostic；完整 messages 不进入 report。
- `PROVIDER_DIAGNOSTIC` 与 `PROVIDER_PROTOCOL_ERROR` 保持非致命/致命语义区别，不从一个
  event kind 猜另一个。
- `USAGE_REPORTED` 是 response 后 observation，只能解释后续 context pressure，不回写既有
  dispatch decision。
- Tool Trace / audit / memory 等 projection 不能反向驱动 Host truth。

### 4.2 Control document alignment

与 `docs/host/issues-implementation-control.md` 对齐：

- WU-OBS-00 必须交付 analyzer，WU-OBS-01 复用其能力。
- WU-OBS-00A / Issue #34 合入同一 analyzer，覆盖 corrupt/missing/mismatch 和 large payload。
- WU-OBS-00B / Issue #119 在本 plan 中裁决为“不扩展 usage correlation fields”。
- Issue #64 保持 open；native Anthropic / Claude Code gateway-specific signal 缺失时只能
  limited signal。
- 不修改 control doc；gate 状态由 Controller 在本 plan 返回后更新。

### 4.3 Goal confirmation alignment

`docs/reviews/wu-obs-00-goal-confirmation-tool-trace-sufficiency-controller.md` 的
`analyzer-ready` 结论保持不变：

- 不增加 producer/schema completion。
- file-only 与不可解析 payload 明确 limited signal。
- provider debugging terminal/protocol 主链与 usage observation 分离。
- 当前 hot/cold/payload descriptor 足以支撑 analyzer。

### 4.4 Issue alignment

- Issue #70：实现分层诊断、structured/Markdown report 与 vendor block。
- Issue #34：实现当前 hot/cold/descriptor 形态的 integrity 与 large payload 规则。
- Issue #119：不扩展 usage producer；Analyzer 只消费现有 post-call pressure。
- Issue #64：保持 residual risk，不在本 WU 补 native runner/gateway signal。

## 5. Direct Code / Data Evidence

### 5.1 Production code evidence

1. `dayu/host/tool_trace.py`
   - `ToolTraceProjectionConsumer.apply_event` 只消费 committed projection input，构造 hot row
     和 cold line。
   - `_build_cold_line` 使用不含 digest/ref 三字段的 canonical object 计算 `line_digest`，
     然后写入 `line_digest`、`cold_trace_ref`、`cold_trace_digest`。
   - `_append_line` 以 `event_id` 与 `cold_trace_ref` 为 source keys，已存在同 key 不同 digest
     时 fail closed。
   - `_extract_diagnostic_trace` 明确分离 `provider_request_id` 与
     `client_correlation_id`。
   - `_extract_usage_trace` 只投影实际 usage observation，不提供 Analyzer 可合法重建的
     request-level correlation。
2. `dayu/host/durable/tool_trace.py`
   - `ToolTraceHotRow` 是 hot row 的 strict typed owner。
   - `resolve_tool_trace_hot_row_payloads` 读取 source EventLog payload 并复用 descriptor
     resolver。
   - `resolve_runner_call_projection_from_signal` 校验 manifest、runner input projection 与
     selected tool schema snapshot。
   - 现有 query 只能按 run/tool-call/provider-request/diagnostic ref 查询；目录 analyzer
     需要新增无过滤、按 `event_sequence` 分页的 read-only scan helper。
3. `dayu/host/durable/connection.py`
   - 现有 `open_host_durable_store` 会 bootstrap schema，并暴露 write transaction runner；
     operator analyzer 不能用该 opener 读取任意输入，否则可能创建/修改 DB。
   - 因此需要 durable foundation 拥有一个 SQLite `mode=ro`、`query_only=ON` 的 read-only
     store，且只暴露 `run_read`。
   - `dayu/host/durable/options.py` 的 `HostSQLiteStoragePolicy()` 已拥有 durable SQLite
     `busy_timeout_seconds` 默认及显式 override contract；read-only opener 必须复用这个 owner，
     不在 Analyzer policy 或 CLI 另建 timeout 真源。
4. `dayu/cli/arg_parsing.py` / `dayu/cli/main.py`
   - 当前没有 tool trace analyzer command。
   - CLI 已有 `session <action>` 二级 parser 与 command runner 分发模式，可作为当前 CLI
     形状参考。
5. `dayu/service`
   - 当前 Service 只通过 Host public contract 装配与调用，不应让 CLI 直接 import
     `dayu.host.durable`；Analyzer 的用户路径发现/文件发布必须经 Service。
6. `dayu/host/open_host.py` / `dayu/host/tool_trace.py` / `dayu.runtime.filelock`
   - 默认 producer 从 cold JSONL path 派生相邻 `<cold-file-name>.lock`，并以
     `RuntimeFileLock` 在 5 秒 timeout 内保护整次幂等 append。
   - 当前 lock path 派生与 timeout 是 producer 私有实现；Analyzer 不能在 Service/CLI 复制
     相邻 path 规则，也不能绕开 runtime wrapper 直接依赖第三方 file lock。
   - S1 将 lock path 派生收敛为 Host Tool Trace projection owner 的共享内部 helper；
     producer 与 Analyzer input loader 在 Host 内部复用它。helper 不从 `dayu.host` package root
     导出，不新增 public builder/factory/classmethod/wrapper；既有 producer timeout 继续由
     producer owner 常量控制。
   - 该重构不改变 cold line、event filter、digest、append ordering 或 timeout value，并由
     projection regression tests 保护。

### 5.2 Current real workspace evidence

计划阶段直接检查：

- cold JSONL：
  `workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`
- hot store：
  `workspace/.dayu/host/dayu_host.sqlite3`
- 当前 cold file：9 行，约 25 KiB。
- 当前 hot rows：9 行。
- event types：
  - `RUNNER_CALL_INPUT_ASSEMBLED` × 2
  - `USAGE_REPORTED` × 2
  - `TOOL_CALL_REQUESTED` × 1
  - `TOOL_AWAITING` × 1
  - `RUN_WAITING` × 1
  - `TOOL_RESULT_ACCEPTED` × 1
  - `RUN_SUCCEEDED` × 1
- 当前 descriptor graph 包含：
  - runner-call input manifest × 2
  - runner-call input projection × 2（约 12–15 KiB）
  - selected tool schema snapshot × 2（约 11 KiB）
  - terminal payload × 1
- 真实 cold `TOOL_CALL_REQUESTED` 已包含 bounded business-readable request；
  `TOOL_RESULT_ACCEPTED` 已包含 bounded result；`USAGE_REPORTED` 已包含 context pressure；
  runner-call row 已包含 manifest/projection refs 与 size。

这证明当前 operator analyzer 可以只消费现有输入完成主要目标，不需要修改 producer。

### 5.3 Old analyzer evidence boundary

旧仓库 `/Users/leo/workspace/dayu-agent/utils/analyze_tool_trace.py` 只作为问题集参考：

- 可保留的问题：重复调用、失败、延迟、large payload、truncation/fetch_more、protocol、
  context pressure、integrity、Markdown summary。
- 明确丢弃：`tool_trace_v2` record types、`RawRef.storage_uri`、Engine-owned iteration recorder、
  raw payload layout、loose `Any` parser、按 iteration/timestamp 归因、领域工具专项评分。

## 6. Semantic Owners / Layer Attribution

| 语义 | 唯一 owner | Analyzer 行为 |
|---|---|---|
| canonical lifecycle / request / result fact | 现有 EventLog producer / Host typed contract | 只读，不重新推导 |
| hot/cold projection 字段 | `dayu.host.tool_trace` | strict parse / join，不修复 |
| descriptor ref/digest/size/bytes | `dayu.host.durable.payload_resolution` 及 Tool Trace resolver | 复用 resolver，失败转 integrity / limitation |
| provider request identity | Engine provider correlation contract | 只展示现有 id，不猜测 |
| usage observation | Engine usage producer + Host usage projection | 只作 post-call pressure |
| duplicate governance decision | Host duplicate governance | 解释已有 `duplicate_*`，不重做 policy |
| truncation fact / cursor | Host ToolRuntime truncation owner | 读取已有 fact；按直接后续 call 检查 fetch_more |
| tool result status/failure/timing | ToolRuntime accepted-result / signal producer | 使用 typed signal，不从 timestamp 算 duration |
| analyzer finding / priority / recommendation / limitation | WU-OBS-00 Analyzer | 新增唯一 owner |
| cold JSONL lock path 派生 / producer timeout | `dayu.host.tool_trace` projection owner + `dayu.runtime.filelock` primitive | Host 内部 producer/reader 复用同一内部 helper；Service/CLI 不接收、不派生，helper 不从 Host root 导出 |
| path discovery / output publication | Service | 不解释 trace 语义 |
| CLI args / exit code / stdout-stderr | CLI | 不直接访问 durable internals |

### 6.1 Attribution rule table

归因不是按文件名机械分组，而是按“哪个 owner 能纠正该直接证据”：

| Layer | Direct signals / rules |
|---|---|
| Host | hot/cold/payload integrity；runner-call manifest/projection missing or mismatch；duplicate governance decision；policy block；wait/replay/governance chain；context pressure / compaction failure；truncation fact 本身 |
| Engine | `PROVIDER_DIAGNOSTIC`；`PROVIDER_PROTOCOL_ERROR`；partial tool-call signal；provider/model terminal diagnostic；runner observed count/digest mismatch；vendor correlation completeness |
| Tool | tool failure/cancel/result status；同 tool + normalized arguments 的 repeated-request observation（不是 Host duplicate fact）；tool timing outlier；large args/result/schema；truncation 后没有匹配 `fetch_more` 或 cursor 使用错误 |

特殊规则：

- 同 tool/name + normalized digest 的重复只命名为 `repeated_identical_request`；只有
  `duplicate_key` / `duplicate_decision` 存在时才命名为 Host duplicate governance。
- `policy_blocked` 归 Host；`tool_failed` / `tool_cancelled` 归 Tool；
  `provider_protocol_error` 归 Engine。
- runner diagnostic 中 missing manifest/ref/digest 归 Host integrity；
  observed/expected message count 或 role digest mismatch 归 Engine observation boundary。
- unknown event 保留在 run aggregation，不产生猜测性 finding。

## 7. Input Discovery and File/Directory Contract

### 7.1 CLI contract

```text
dayu-cli tool_trace analyze INPUT --output-dir OUTPUT_DIR
```

- `INPUT` 必填，必须是现存 regular JSONL file 或受支持目录。
- `--output-dir` 必填；目录可不存在，Service 创建它；若路径已存在但不是目录则失败。
- 首版不提供递归 wildcard、glob、archive、stdin、URL、provider 或 DB connection string。
- 全局 `--base/--config` 对此命令不参与输入发现；Analyzer 的输入只由显式 `INPUT` 决定，
  避免 workspace 与 file 参数出现两个真源。

### 7.2 Supported input modes

1. `cold_file`
   - `INPUT` 是单个 regular JSONL file。
   - 只读取该文件；不向父目录猜 hot DB 或 artifact root。
2. `workspace_directory`
   - `<INPUT>/.dayu/host/dayu_host.sqlite3`
   - `<INPUT>/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`
   - artifact root=`<INPUT>/.dayu/artifacts`
3. `dayu_directory`
   - `<INPUT>/host/dayu_host.sqlite3`
   - `<INPUT>/artifacts/tool-trace/tool-trace-cold.jsonl`
   - artifact root=`<INPUT>/artifacts`
4. `trace_directory`
   - `<INPUT>/tool-trace-cold.jsonl`
   - cold-only，不向 sibling/parent 猜 DB。

目录模式中 hot/cold 任一存在即可建立 input：

- hot 存在、cold 缺失：允许运行并产生 confirmed `missing_cold_trace` findings。
- cold 存在、hot 缺失：允许运行并产生 `hot_store_unavailable` limitation。
- artifact root 缺失：hot/cold 仍可运行，payload resolution 标记 limited。
- 同一 `INPUT` 同时匹配多个布局：fail closed，列出冲突路径，要求 operator 传更具体的
  file 或 `.dayu` directory；不采用优先级猜测。
- 无任何受支持路径：usage error。
- Service 只负责把上述布局解析为完整 `ToolTraceAnalysisSource`；Source 自身在 Host public
  boundary 再次校验 mode/path/invariant。不得用 capability bool、路径存在性默认值或 CLI
  分支代替 Source contract。

### 7.3 `ToolTraceAnalysisSource` complete contract

S1 冻结以下 public dataclass；字段不得放入 extra payload，也不得用 nullable path 表达
“尚未决定”：

```text
@dataclass(frozen=True, slots=True)
ToolTraceAnalysisSource
  requested_path: Path
  mode: ToolTraceInputMode
  cold_jsonl_path: Path
  hot_db_path: Path | None
  artifact_root: Path | None
```

字段 contract：

| field | type | required | owner / meaning |
|---|---|---:|---|
| `requested_path` | `Path` | yes | Service path discovery 归一化后的绝对输入路径；只记录 operator 请求目标，不从它二次猜布局 |
| `mode` | `ToolTraceInputMode` | yes | Service 发现并由 Source boundary 复核的四值枚举 |
| `cold_jsonl_path` | `Path` | yes | 本 mode 唯一 expected cold JSONL path；目录模式允许该 expected path 当前缺失 |
| `hot_db_path` | `Path | None` | yes | workspace/dayu mode 的唯一 expected Host DB path；cold-file/trace mode 必须为 `None` |
| `artifact_root` | `Path | None` | yes | workspace/dayu mode 的唯一 expected artifact root；cold-file/trace mode 必须为 `None` |

所有非空 path 必须是 absolute normalized path；不得在 Analyzer 中再次相对 cwd 解释，也不得
通过 `resolve()` 把不存在的 expected child 当作存在。mode-specific invariants 与 discovery
验证矩阵固定为：

| mode | `requested_path` | `cold_jsonl_path` | `hot_db_path` | `artifact_root` | existence/type rules |
|---|---|---|---|---|---|
| `cold_file` | existing regular file | 与 requested path 相同 | `None` | `None` | cold 必须存在且为 regular file |
| `workspace_directory` | existing directory | `<requested>/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl` | `<requested>/.dayu/host/dayu_host.sqlite3` | `<requested>/.dayu/artifacts` | hot/cold 至少一个存在；存在者必须为 regular file；artifact 存在时必须为 directory |
| `dayu_directory` | existing directory | `<requested>/artifacts/tool-trace/tool-trace-cold.jsonl` | `<requested>/host/dayu_host.sqlite3` | `<requested>/artifacts` | hot/cold 至少一个存在；存在者必须为 regular file；artifact 存在时必须为 directory |
| `trace_directory` | existing directory | `<requested>/tool-trace-cold.jsonl` | `None` | `None` | cold 必须存在且为 regular file |

Source boundary 还必须拒绝：

- mode 与 path layout 不一致；
- cold/hot/artifact path alias 到彼此、越出该 mode 的 expected layout，或已存在但类型错误；
- cold-only mode 携带 hot/artifact path；
- directory mode 的 hot/cold 都缺失。

`cold_lock_path` 不是 public Source field，也不是 Service 输入事实。Service 只发现并传上述显式
路径；Host Analyzer input loader 收到并复核 Source 后，内部调用
`dayu.host.tool_trace` owner helper 从 `cold_jsonl_path` 唯一派生 lock path。该派生值可作为
本次实际读取信息，以单数 `cold_lock_path` 投影到 report，但不得回填 Source、要求 Service
传入，或通过 Host root public helper 暴露。

存在性变化以 load 时的第二次校验为准：discovery 后 cold/hot 消失属于读取失败，不转换为另一
mode。`ToolTraceAnalysisSource` 不保存 `cold_available`、`hot_available` 或
`payload_resolution_available`；这些 capability 由 Analyzer 对已验证 path 的本次实际读取结果
派生并写入 report，避免 bool/path 双真源。

### 7.4 File consistency and concurrent writers

- Host Tool Trace projection owner 新增模块内部
  `_tool_trace_cold_lock_path(cold_jsonl_path: Path) -> Path`，返回相邻
  `<cold-file-name>.lock`。默认 producer 与 Analyzer input loader 必须在 Host 内部复用该
  派生 helper；删除 `open_host` 中重复的私有 suffix/path 派生。helper 不从 `dayu.host`
  package root 导出，Service/CLI 不调用、不复制，也不新增 public builder/factory/classmethod/
  wrapper。
- producer 继续使用其既有命名 lock-timeout owner和值；Analyzer reader 调用同一 Host Tool
  Trace owner 的读取路径取得对应 timeout，不把 timeout 放入
  `ToolTraceAnalysisSource`、`ToolTraceAnalysisPolicy` 或 CLI flag，也不在 Service/Analyzer
  复制 `5.0` 字面量。
- hot store 先在单个 SQLite read-only transaction 中读取全部 hot pages并记录本次
  `hot_event_sequence_watermark=max(event_sequence)`；hot store 可用但无 rows 时 watermark
  固定为 `0`，只有 hot store 不可用时才为 `null`。read transaction 必须在获取 cold lock 前
  关闭，避免同时持有 SQLite snapshot 与 file lock。
- workspace/dayu mode 若 cold expected path 在 discovery/load 两次都不存在且 hot 可用，保持
  hot-only：不创建 lock marker、不尝试 cold open，并对 hot rows 产生
  `integrity.missing_cold_trace`。cold path 曾存在但 load 时消失是 fatal
  `cold_snapshot_read_failed`；cold-file/trace mode 的 cold 缺失始终失败。
- 随后 Host Analyzer input loader 内部派生 lock path，并调用
  `dayu.runtime.filelock.file_lock(..., create_parent_dirs=False)` 获取与 producer 同源的独占
  lock；无论 lock marker 当前是否存在都必须 acquire，marker 存在性不代表锁已持有或文件可信。
- 独占锁临界区必须为 O(1)：获取锁后只执行一次 binary open，立即对同一 handle `fstat`，
  记录 `prefix_byte_length=st_size` 与用于解释本次 snapshot 的必要 file identity
  （至少保留平台可用的 device/inode identity），随后释放 lock。不得在锁内做任何
  O(file-size) read、解析、SQLite、resolver 或 report 工作。
- 释放 lock 后只从上述同一 binary handle 循环读取精确 `prefix_byte_length` bytes，然后关闭
  handle；不得重新打开 path，不得读取动态 EOF，也不得包含 prefix capture 后追加的 bytes。
  追加到 prefix 之后的数据留待下一次分析。若在读满 prefix 前返回 EOF/short read、同一 handle
  的 file identity 变化、`fstat` 显示文件被截断到 prefix 以下，或任一 open/fstat/read/close
  条件不能证明精确 prefix 已取得，则 fatal `cold_snapshot_read_failed`，不得用已读短前缀
  继续分析。
- path 在释放 lock 后被替换时仍只读取已打开 handle 所引用、已记录 identity 的精确 prefix，
  不切换到新 path；同 inode truncate 导致 prefix 不满足时 fatal。该边界确保 reader 不以
  全文件持锁反向消耗 producer 的 5 秒 lock timeout，同时让并发 append 具有确定的下一次可见
  语义。
- cold bytes 按 strict UTF-8、JSONL record boundary 解析，记录 file path、1-based line number
  与 record bytes；record bytes 不包含 `\n` 或 `\r\n` 行终止符。
- `RuntimeFileLockTimeoutError` 映射为 fatal read reason
  `cold_snapshot_lock_timeout`；其它 acquire/release `RuntimeFileLockError` 映射为
  `cold_snapshot_lock_failed`；binary open/fstat、释放锁后的 exact-prefix read/close、short
  read、truncate 或 identity invariant 失败映射为 `cold_snapshot_read_failed`。三者都 fail
  analysis，Service 不发布 report，CLI exit code=`1`，不得转成 malformed-line finding 或
  limitation。
- Analyzer 不依赖 POSIX/Windows append atomicity，不把 partial last line 当作并发正常态，也
  不在 lock failure 时无锁重试。只有与默认 producer 共享同一 lock contract 得到的 snapshot
  才进入 parser。
- hot row 已提交而 cold 缺失可判 confirmed mismatch，因为当前 producer 在提交 hot transaction
  前已 append cold line。
- cold-only row 的 `event_sequence` 高于本次 hot snapshot watermark 时，不直接报 mismatch，
  产生 reason code=`input_changed_during_analysis` 的 limitation，避免把在 hot snapshot 后、
  cold snapshot 前提交的 producer 写入误判为损坏；它不是 integrity finding，不进入 finding
  count。
- hot store 可用且 snapshot 为空时 watermark=`0`：若 cold snapshot 也为空，正常返回无
  finding/limitation 的空报告；若 cold snapshot 随后出现任一正 `event_sequence` row，则这些
  rows 全部按 `input_changed_during_analysis` limitation 处理，绝不产生
  `integrity.missing_hot_trace`。不得用 row count、mtime 或时间戳猜 hot DB stale。
- 首版不为跨 JSONL/SQLite 建分布式快照或复制数据库；报告记录 input mode 与 hot watermark，
  供 operator 判断快照范围。

## 8. Typed Parser / Model / Resolver Boundary

### 8.1 Public contracts

新增 public analyzer contracts，禁止 `Any`、`object`、untyped dict：

- `ToolTraceInputMode`
- `ToolTraceAnalysisLayer`：`host | engine | tool`
- `ToolTraceFindingSeverity`：`error | warning | info`
- `ToolTraceFindingPriority`：`high | medium | low`
- `ToolTraceSignalStatus`：`available | limited_signal | not_applicable`
- `ToolTraceEvidenceKind`：
  `cold_line | hot_row | resolved_payload | input_path`
- `ToolTraceAnalysisSource`
- `ToolTraceAnalysisPolicy`
- `ToolTraceEvidence`
- `ToolTraceFinding`
- `ToolTraceLimitation`
- `ToolTracePayloadMeasure`
- `ToolTraceRunSummary`
- `ToolTraceVendorDebuggingBlock`
- `ToolTraceAnalysisSummary`
- `ToolTraceAnalysisReport`

所有 report 文本为 operator-readable 中文；id/ref/digest 明确标为定位标签，不作为业务事实。

跨 slice contract freeze：

- S1 只实现并稳定 input/read-only 路径实际消费的 contract：
  `ToolTraceInputMode`、`ToolTraceAnalysisSource`、`ToolTraceAnalysisPolicy`、input diagnostic /
  normalized dataset 所需 internal types；不得预定义未被 S1 path 消费的 report/finding/vendor
  public skeleton。
- S2 一次性定义并冻结其余最终 public report contract，包括
  `ToolTraceAnalysisReport` 顶层 schema、`ToolTraceFinding`、`ToolTraceLimitation`、
  `ToolTracePayloadMeasure`、`ToolTraceRunSummary`、finding ordering/id assignment 与完整
  `ToolTraceVendorDebuggingBlock`。S2 的 `vendor_debugging` 可以为空，但字段和 block shape 已是
  最终 schema。
- S3 不修改 `tool_trace_analysis_contracts.py`，不改变 S2 顶层字段、枚举、nullable 语义、
  finding ordering/id assignment、Host/Tool rule 语义或 vendor block shape；只在
  `tool_trace_analysis_rules.py`/orchestration 中追加 Engine/provider findings、vendor block
  instances 和对应 limitations。

public functions 固定为：

```text
analyze_tool_trace(
    source: ToolTraceAnalysisSource,
    policy: ToolTraceAnalysisPolicy,
) -> ToolTraceAnalysisReport

tool_trace_analysis_report_to_json(
    report: ToolTraceAnalysisReport,
) -> str

render_tool_trace_analysis_markdown(
    report: ToolTraceAnalysisReport,
) -> str
```

- `analyze_tool_trace` 是规则与 report 的唯一 public orchestration owner。
- 两个 renderer 只消费 report，不读取 source、不再次执行规则。
- `dayu.host.__init__` 只把上述 function 与 public contracts 纳入新的 package public surface；
  不暴露 normalized dataset、durable store 或 internal rule function。

### 8.2 Cold parser

strict parser 必须：

1. JSON parse 成 object；空行、非法 JSON、array/scalar 各自记录明确 input diagnostic。
2. `schema_version` 必须等于当前整数 `1`；未知版本不做 compatibility parsing。
3. 校验 required identity 字段的类型：
   `event_id`、`event_sequence`、`event_type`、`event_class`、`session_id`、
   `occurred_at`、`trace_summary`、`line_digest`、`cold_trace_ref`、
   `cold_trace_digest`。
4. 校验 optional id/ref/digest 的 null/text 类型与 SHA-256 形状。
5. 从 object 删除 `line_digest`、`cold_trace_ref`、`cold_trace_digest` 后，使用现有
   `sha256_digest_json` 重算 producer preimage。
6. 校验：
   - recomputed digest == `line_digest`
   - `line_digest` == `cold_trace_digest`
   - `cold_trace_ref` == `tool-trace-cold:<event_id>`
7. 保留 normalized typed record；malformed record 不进入后续 run/tool/provider rules。

internal input/rule boundary 固定为：

```text
load_tool_trace_analysis_input(
    source: ToolTraceAnalysisSource,
    policy: ToolTraceAnalysisPolicy,
    sqlite_policy: HostSQLiteStoragePolicy,
) -> ToolTraceAnalysisDataset

build_tool_trace_analysis_report(
    dataset: ToolTraceAnalysisDataset,
    source: ToolTraceAnalysisSource,
    policy: ToolTraceAnalysisPolicy,
) -> ToolTraceAnalysisReport
```

`ToolTraceAnalysisDataset`、strict cold record、joined record、input diagnostic 与 resolved payload
measure 均为 analyzer-internal frozen dataclass，不从 Host package root 导出。

public `analyze_tool_trace` 在 standalone 路径构造 `HostSQLiteStoragePolicy()` 并传给 internal
loader；SQLite policy 不进入 report 的 analyzer threshold policy，也不扩展 public CLI。S1
owner-level tests可直接向 internal loader/opener传入自定义 `HostSQLiteStoragePolicy`，验证
read-only busy timeout override与默认同源。

### 8.3 Hot scan and join

在 `dayu.host.durable.tool_trace` 新增：

```text
read_tool_trace_page(
    transaction,
    after_event_sequence,
    limit,
) -> ToolTraceQueryPage
```

- 复用现有 `TOOL_TRACE_QUERY_MAX_LIMIT`、`_query_page`、`ToolTraceHotRow` decoder。
- 只做无过滤的 `event_sequence ASC` 分页读取，不新增写入或 projection 行为。
- Analyzer 循环读取到 `has_more=False`，不使用 offset。

join key 与不变量：

- primary：`event_id`
- secondary validation：`cold_trace_ref`、`cold_trace_digest`、`event_sequence`
- 同 `event_id` / `cold_trace_ref` 多个 cold lines：
  - digest 相同：duplicate-line warning
  - digest 冲突：integrity error
- hot-only：`missing_cold_trace`
- cold-only 且不高于 hot watermark：`missing_hot_trace`
- 任一 identity/digest 不同：`hot_cold_source_mismatch`

hot store 可用但 snapshot 为空时的 join 是显式边界：

- cold snapshot 也为空：返回正常空 dataset/report，不产生 finding 或 limitation。
- cold snapshot 有正 `event_sequence` rows：所有 rows 都严格高于 watermark `0`，因此全部产生
  `input_changed_during_analysis` limitation，并保留 cold evidence/watermark；不得产生
  `missing_hot_trace`。

### 8.4 Read-only durable opener

新增内部 `HostDurableReadStore` / `open_host_durable_read_store`：

- SQLite URI `mode=ro`、`uri=True`。
- read-only opener 显式接收并持有 `HostSQLiteStoragePolicy`。standalone
  `analyze_tool_trace` 入口使用既有 `HostSQLiteStoragePolicy()` durable 默认；内部测试/调用方
  可显式注入完整 policy 以验证 override。不得从 `ToolTraceAnalysisPolicy`、CLI flag、环境变量
  或 file-lock timeout 派生 SQLite busy timeout。
- 在 `dayu.host.durable.transaction` 新增独立
  `configure_read_only_connection_pragmas(connection: sqlite3.Connection, sqlite_policy: HostSQLiteStoragePolicy) -> None`
  helper。helper 只读取 `sqlite_policy.busy_timeout_seconds`，按以下顺序设置并校验：
  - `PRAGMA busy_timeout=<HostSQLiteStoragePolicy.busy_timeout_seconds 转换的非负整数毫秒>`
  - `PRAGMA foreign_keys=ON`
  - `PRAGMA query_only=ON`
- read-only helper 不读取或应用 `HostSQLiteStoragePolicy` 的 write retry/backoff 字段；这些字段
  仍只属于 write transaction。
- read-only opener 禁止调用现有写侧 `configure_connection_pragmas`，因为后者拥有 WAL 写连接
  初始化语义；禁止设置或读取后再改写 `journal_mode`、`wal_autocheckpoint`，禁止 bootstrap、
  DDL、`PRAGMA user_version=` 赋值或任何 repair/catch-up。
- 打开前要求 DB regular file 已存在。
- 打开后调用现有 `validate_host_durable_schema`。
- 只公开 `run_read(...)`、`close()` 与 context manager；不公开
  `transaction_runner` / `run_write`。
- `HostTransaction` 的 artifact root 使用显式 source artifact root，
  `create_artifact_root=False`。

这不是新的 storage layer，只是现有 durable foundation 的只读 capability boundary。

hot DB error contract：

- `cold_file` / `trace_directory` 的 `hot_db_path=None` 是显式 cold-only，产生
  `hot_store_unavailable` limitation。
- `workspace_directory` / `dayu_directory` 的 expected hot path 在 load 时确实不存在，且 cold
  可读，才允许产生 `hot_store_unavailable` limitation 并继续 cold-only。
- directory discovery 后 expected hot path 已存在，但不再是 regular file、URI open 失败、
  busy/permission 失败、`validate_host_durable_schema` 失败、required schema 缺失或 SQLite
  corruption，均 fail analysis；分别保留 typed cause，Service 不发布 report，CLI exit
  code=`1`。
- 不区分“auto-discovered”与“显式”DB 来降级：目录 contract 发现的 DB 就是本次显式 INPUT 的
  一部分。operator 若只需绕开损坏 DB 做 cold 分析，必须把 cold JSONL file 本身作为 INPUT。
- 禁止把已存在但不可打开/不可校验的 DB 重写为 `None`、`hot_store_unavailable` 或另一种 mode。

### 8.5 Payload resolver

目录输入对每个 hot row：

- 调用 `resolve_tool_trace_hot_row_payloads` 校验 source EventLog payload 与 row/embedded
  descriptor。
- runner-call row 先读取 typed reconstruction signal，再调用
  `resolve_runner_call_projection_from_signal`。
- payload ref/digest 单边缺失、descriptor missing、artifact escape、actual bytes
  digest/size mismatch、non-object JSON 均保留原 resolver error category，不做 fallback。
- 成功 resolution 只生成：
  - payload kind/category
  - ref/digest
  - verified byte size
  - owner event/local refs
- report 不复制 resolved payload body。

file-only：

- 不尝试直接打开 ref string。
- 对需要 hot/resolver 才能证明的 signal 产生 limitation，不把 ref existence 当作已验证。

## 9. Integrity / Large Payload / Diagnostic Decisions

### 9.1 Integrity rules

稳定 rule ids：

- `input.invalid_json_line`
- `input.non_object_json_line`
- `input.unsupported_schema_version`
- `input.invalid_record_field`
- `integrity.line_digest_mismatch`
- `integrity.cold_digest_mismatch`
- `integrity.cold_ref_mismatch`
- `integrity.duplicate_cold_line`
- `integrity.cold_source_conflict`
- `integrity.missing_cold_trace`
- `integrity.missing_hot_trace`
- `integrity.hot_cold_source_mismatch`
- `integrity.payload_ref_pair_invalid`
- `integrity.payload_unresolvable`
- `integrity.payload_digest_mismatch`
- `integrity.runner_call_reconstruction_limited`
- `integrity.runner_call_reconstruction_mismatch`

不把 resolver 失败降级成普通 unavailable；digest mismatch 是 confirmed error，同时会使依赖该
payload 的更深规则进入 limited signal。

limitation 使用 `reason_code` 而不是 finding `rule_id`。并发 watermark 场景的稳定 reason code
固定为：

- `input_changed_during_analysis`

触发条件只能是：存在 hot snapshot watermark，cold valid row 的 `event_sequence` 严格大于该
watermark，且该 row 在 hot snapshot 中不存在。该 limitation 必须携带 cold line evidence 与
hot watermark；不得产生 `integrity.missing_hot_trace`，不得增加 finding count。schema、
JSON/Markdown renderer、rule table、S1/S2 tests 和最终 validation matrix 必须逐字使用同一
reason code，不提供别名。

### 9.2 Large payload policy

`ToolTraceAnalysisPolicy` 使用显式、可注入、会写入 report 的参数：

- `large_payload_threshold_bytes`
- `payload_ranking_limit`
- `latency_minimum_sample_count`
- `latency_outlier_multiplier`
- `latency_minimum_delta_ms`

该 policy 只拥有诊断阈值，不包含 SQLite busy timeout、file-lock timeout 或其它 I/O policy；
read-only SQLite 复用 `HostSQLiteStoragePolicy`，CLI 不增加对应 flag。

默认值由 Analyzer contract 模块的命名常量产生，不从 module hidden env、当前数据 percentile 或
Host payload inline threshold 推断。理由：

- storage inline threshold 决定存储位置，不等于 operator “large” 风险阈值。
- 只取当前样本 p90 会在所有 payload 都很小时仍制造告警。
- policy 可由 WU-OBS-01 直接传入，无需 plugin/profile/DSL。

首版默认值与校验固定为：

```text
DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES = 131_072
DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT = 20
DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT = 5
DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER = 3.0
DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS = 1_000
```

- bytes/ranking/sample/delta 必须为正整数。
- multiplier 必须为 finite float 且 `>1.0`。
- `payload_size_bytes >= large_payload_threshold_bytes` 才产生 large finding。
- ranking 对全部 verified measures 按
  `(payload_size_bytes DESC, category ASC, payload_ref ASC, event_sequence ASC)` 稳定排序，只截
  top N；低于 threshold 的 measure 仍可出现在 ranking，但不产生 finding。
- latency candidate 必须同时满足：
  - 同 tool available samples `>= latency_minimum_sample_count`
  - `duration_ms >= median_duration_ms * latency_outlier_multiplier`
  - `duration_ms - median_duration_ms >= latency_minimum_delta_ms`
- median 使用同 tool 全部 `status=available` 且 source 合法的 duration；missing/invalid timing
  不进入样本。

payload categories：

- `cold_line`
- `source_event_payload`
- `tool_arguments`
- `tool_result`
- `provider_diagnostic`
- `runner_call_manifest`
- `runner_input_projection`
- `selected_tool_schema_snapshot`

每个 verified measure 都进入按 bytes 降序的 top ranking；只有超过 threshold 才产生
`payload.large_payload` finding。无法得到 exact bytes 时不按 bounded summary 长度猜原始大小，
进入 limitation。

`ToolTracePayloadMeasure` 在 S2 冻结以下 size 语义：

- `category=cold_line` 时，`measurement_source=cold_jsonl_record_bytes`，size 是 cold snapshot
  中该 JSON object UTF-8 record bytes，不含行终止符；它是 projection record 大小，不是 source
  EventLog payload、tool arguments/result、provider raw body 或其它 resolved raw payload 大小。
- 其它 descriptor/resolver category 使用
  `measurement_source=resolved_payload_bytes`，size 必须来自 resolver 校验通过的
  `payload_size_bytes` / actual bytes。
- 两类 measure 都可参与统一 byte ranking，但 JSON/Markdown 必须显示 `category`、
  `measurement_source` 和 `size_bytes`；标题使用“byte measures / JSONL record bytes”，不得把
  `cold_line` 行称为“原始 payload”。
- 同一 cold record 与其 resolved payload 是两个独立 measure，不能互相覆盖或用一个大小推断
  另一个；file-only 无 resolved payload 时只保留 cold record measure 与相应 limitation。

### 9.3 Duplicate / failure / latency rules

- Host duplicate：
  - 只消费 `duplicate_key` / `duplicate_decision` / `duplicate_scope` /
    `reuse_prior_event_refs`。
  - finding 说明已有 allow/reuse/guidance/block 事实，不重新执行 duplicate policy。
- repeated request：
  - 同一 run 内 `tool_name + normalized_arguments_digest` 出现多次时产生 Tool
    `tool.repeated_identical_request` observation。
  - 若缺 normalized digest，不以 arguments text 或时间顺序猜相同语义。
- tool failure：
  - `failure_metadata.failure_kind=tool_failed|tool_cancelled` 或 typed tool result status。
  - error code / cancel reason / repair hint 只复制已有 bounded fields。
- policy block：
  - `failure_kind=policy_blocked` 归 Host。
- latency：
  - 只使用 `tool_timing.status=available` 且
    `duration_source=tool_result_meta` 的 `duration_ms`。
  - 不从 `occurred_at` 相减。
  - 每个 tool 至少达到 `latency_minimum_sample_count` 后，才以 median +
    multiplier/minimum-delta 的上述双阈值规则产生 `tool.latency_outlier`。
  - timing missing 进入 signal coverage limitation；小样本只呈现 summary，不宣称异常。
- waiting timeline：
  - `TOOL_AWAITING` 与 `RUN_WAITING` 是 known timeline facts，按 typed run/attempt/execution/
    tool-call refs 进入 run chain，并分别累计 `tool_awaiting_count` /
    `run_waiting_count`。
  - 首版不因这两个 event 存在、缺失、相邻或没有观察到后续 accepted result 而产生 finding，
    也不从它们推断等待失败、超时、恢复失败或 tool result 语义。
  - 只有 source owner 已提供的 typed failure/rejection fact（例如明确的 late-result rejection、
    tool failure/cancel 或 Run terminal failure）才可由其已有 rule 产生 finding；不得以 timeline
    gap 代替 typed evidence。

### 9.4 Truncation / fetch_more rules

- 只消费 typed `truncation.applied/strategy/original_digest/truncated_digest/cursor_hint`。
- 找后续 `TOOL_CALL_REQUESTED(tool_name=fetch_more)`，并要求其 direct
  `tool_request.arguments.cursor` 等于原 `cursor_hint`。
- 仅同一 run、严格更大 `event_sequence` 可构成 direct continuation。
- 匹配时记录 `tool.fetch_more_followed` summary，不产生问题 finding。
- run 后续结束或调用其它 tool、且没有匹配 cursor 时，产生低/中优先级
  `tool.truncation_not_followed`；描述为“未观察到续读”，不写成 Engine 故障。
- 出现 `fetch_more` 但 cursor 不匹配时产生 `tool.fetch_more_cursor_mismatch`。
- file-only 中 tool arguments 不完整时标记 limited，不从 summary text regex 取 cursor。

### 9.5 Context pressure rules

- `USAGE_REPORTED.context_pressure` 只写入 run 的 post-call observation：
  prompt/completion/total tokens、soft/hard exceeded、budget decision、policy ref、
  estimator digest。
- 不与 terminal/provider event 做 request-level correlation。
- `CONTEXT_COMPACTION_FAILED` /
  `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 使用现有 context/failure signal 归 Host。
- 缺 context pressure 不解释为零压力；写 signal coverage limitation。

### 9.6 Provider / protocol / vendor debugging

Engine findings：

- `engine.provider_diagnostic`
- `engine.provider_protocol_error`
- `engine.partial_tool_call_present`
- `engine.partial_tool_call_signal_missing`
- `engine.runner_observation_mismatch`
- `engine.vendor_correlation_conflict`

Vendor block 生成条件：

- `PROVIDER_DIAGNOSTIC`
- `PROVIDER_PROTOCOL_ERROR`
- provider/model-related terminal diagnostic（直接具有 provider request/client correlation/
  engine/provider refs）

分组规则：

1. 有 `provider_request_id`：只按该 id 分组。
2. 无 provider id 但有 `client_correlation_id`：可按 client id 形成 local-correlation block，
   但 `provider_request_id=null` 且 status=`limited_signal`。
3. 两者都无：每个 direct diagnostic event 独立 limited block。
4. 禁止按 run/attempt/iteration/timestamp 把多个缺 id 的 provider calls 合并。

每个 block：

- `status`
- `provider_request_id`
- `client_correlation_id`
- `session_id`
- `run_id`
- `attempt_ids`
- `execution_ids`
- `iteration_ids`
- `tool_trace_refs`（event id/sequence/cold ref）
- `diagnostic_refs`
- `partial_tool_call_signal`
- `limitations`

S2 冻结的完整 vendor block 字段 contract：

| field | type | required | invariant |
|---|---|---:|---|
| `status` | `ToolTraceSignalStatus` | yes | `available | limited_signal`；vendor trigger 已存在时不得为 `not_applicable` |
| `provider_request_id` | `str | None` | yes | 只来自 typed provider signal；不得用 client/local id 填充 |
| `client_correlation_id` | `str | None` | yes | 只来自 typed client correlation signal |
| `session_id` | `str` | yes | direct diagnostic source identity |
| `run_id` | `str` | yes | direct diagnostic source identity |
| `attempt_ids` | `tuple[str, ...]` | yes | 去重后按 lexical order |
| `execution_ids` | `tuple[str, ...]` | yes | 去重后按 lexical order |
| `iteration_ids` | `tuple[str, ...]` | yes | 只来自 resolved typed source；缺失为空并附 limitation |
| `tool_trace_refs` | `tuple[ToolTraceEvidence, ...]` | yes | 至少一项 direct event/cold/hot evidence |
| `diagnostic_refs` | `tuple[str, ...]` | yes | 只保留已有 refs；去重稳定排序 |
| `partial_tool_call_signal` | `ToolTraceSignalStatus` | yes | `available | limited_signal | not_applicable`，不得把 absent 写成 explicit none |
| `limitations` | `tuple[ToolTraceLimitation, ...]` | yes | block-local limited reasons；available 时可为空 |

该 shape、字段顺序、nullable/empty-tuple 语义在 S2 后不可变；S3 只构造实例。

iteration id 只从 resolved source event typed payload或已有 trace summary读取；file-only 不存在时为
null 并 limited。

complete/limited：

- provider request id 与 client correlation id 均存在且无冲突：`available`。
- 任一 id 缺失、source payload 不可解析、file-only 无 iteration：`limited_signal`，列出精确
  原因。
- 当前 trace 不提供 provider family/adapter 名称时，不从 endpoint/header/ref 猜名称；generic
  vendor block 在 provider/client/local refs 完整时仍可为 `available`。
- Issue #64 仍 open。报告不得声称当前 path 是/不是 native Anthropic 或 Claude Code gateway；
  provider-native id 缺失时明确写“native Anthropic / Claude Code gateway-specific signal
  无法由当前 trace 验证（Issue #64）”。

## 10. Structured / Markdown Output Contract

### 10.1 Structured JSON

顶层固定字段：

| field | type | required | meaning |
|---|---|---:|---|
| `schema_version` | integer (`1`) | yes | Analyzer report schema；不是 Tool Trace schema |
| `input` | object | yes | requested path、mode、单数 `cold_jsonl_path`、Host 内部派生的单数 `cold_lock_path`、hot/artifact paths、capabilities、hot watermark |
| `policy` | object | yes | 本次实际阈值；所有数值显式 |
| `summary` | object | yes | valid/invalid records、runs、tool calls、finding/limitation counts |
| `signal_coverage` | array | yes | 每类 signal 的 available/limited 状态与原因 |
| `runs` | array | yes | run/attempt/execution/tool/provider 聚合摘要 |
| `payload_rankings` | array | yes | verified size top offenders |
| `vendor_debugging` | array | yes | vendor request/local backlink blocks |
| `findings` | array | yes | confirmed diagnostics；每项 evidence 非空 |
| `limitations` | array | yes | 未能证明的 signal；不得混入 confirmed diagnosis |

S2 必须一次冻结的嵌套 contract 至少包含：

- `ToolTraceLimitation`：
  `reason_code: str`、`signal_status: limited_signal`、`summary: str`、
  `evidence: tuple[ToolTraceEvidence, ...]`；`input_changed_during_analysis` 的 evidence 必须
  包含 cold path/line/event sequence 与 hot watermark。
- `ToolTracePayloadMeasure`：
  `category`、`measurement_source`、`size_bytes`、`event_sequence`、`payload_ref`、
  `evidence`；`measurement_source` 只允许 `cold_jsonl_record_bytes` 或
  `resolved_payload_bytes`。
- `ToolTraceRunSummary`：除 run/attempt/execution/tool-call 聚合外，固定包含
  `tool_awaiting_count: int` 与 `run_waiting_count: int`；两者只是 timeline summary，不是
  failure count。
- `ToolTraceVendorDebuggingBlock`：字段与 §9.6 完全一致；S2 即使尚未产生 block，也必须序列化
  `vendor_debugging=[]`，S3 不得再改 shape。

signal coverage status：

- `available`：输入中存在对应 typed signal，且所需 ref/digest 校验通过。
- `limited_signal`：存在触发该 signal 的 trace fact，但必要字段/ref/payload 不足或损坏。
- `not_applicable`：输入中没有触发该类诊断的 trace fact，例如完全没有 provider/protocol
  diagnostic；不得把这种情况写成“provider signal 缺失”。

最小顶层示例：

```json
{
  "schema_version": 1,
  "input": {
    "requested_path": "workspace",
    "mode": "workspace_directory",
    "cold_jsonl_path": "workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl",
    "cold_lock_path": "workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl.lock",
    "hot_db_path": "workspace/.dayu/host/dayu_host.sqlite3",
    "artifact_root": "workspace/.dayu/artifacts",
    "capabilities": {
      "cold": true,
      "hot": true,
      "payload_resolution": true
    },
    "hot_event_sequence_watermark": 44
  },
  "policy": {
    "large_payload_threshold_bytes": 131072,
    "payload_ranking_limit": 20,
    "latency_minimum_sample_count": 5,
    "latency_outlier_multiplier": 3.0,
    "latency_minimum_delta_ms": 1000
  },
  "summary": {
    "valid_record_count": 9,
    "invalid_record_count": 0,
    "run_count": 1,
    "tool_call_count": 1,
    "finding_count": 0,
    "limitation_count": 0
  },
  "signal_coverage": [],
  "runs": [],
  "payload_rankings": [],
  "vendor_debugging": [],
  "findings": [],
  "limitations": []
}
```

示例数值只说明类型与最小 shape；实现默认值由命名常量唯一产生，测试不把当前 workspace
record count 当作长期 schema contract。

finding 固定字段：

```json
{
  "finding_id": "TT-ENGINE-0001",
  "rule_id": "engine.provider_protocol_error",
  "layer": "engine",
  "severity": "error",
  "priority": "high",
  "title": "Provider protocol error",
  "summary": "当前 trace 明确记录 provider protocol error。",
  "recommendation": "使用 vendor debugging block 中的 request/local refs 报障。",
  "evidence": [
    {
      "kind": "cold_line",
      "source_path": ".../tool-trace-cold.jsonl",
      "line_number": 3,
      "event_id": "event-...",
      "event_sequence": 17,
      "event_type": "PROVIDER_PROTOCOL_ERROR",
      "trace_ref": "tool-trace-cold:event-...",
      "payload_ref": null,
      "observed": {
        "provider_request_id": "req-...",
        "failure_kind": "provider_protocol_error"
      }
    }
  ]
}
```

`observed` 只能是 `Mapping[str, JsonValue]` 且由 rule 白名单构造；不透传 raw source payload。
finding 排序固定为：

```text
layer(host, engine, tool)
-> severity(error, warning, info)
-> priority(high, medium, low)
-> rule_id
-> minimum evidence event_sequence
-> source_path
-> line_number
```

每层排序后从 1 递增生成 `TT-HOST-0001` / `TT-ENGINE-0001` / `TT-TOOL-0001`。
给定相同 input/policy 结果稳定，不使用 timestamp/uuid。

默认 severity/priority mapping：

- error/high：digest/source identity conflict、provider protocol error、hard context pressure /
  compaction failure。
- error/medium：payload unresolvable/digest mismatch、runner reconstruction mismatch、
  vendor correlation conflict。
- warning/medium：missing hot/cold、tool failed/cancelled、policy blocked、large payload、
  truncation未续读、fetch_more cursor mismatch、latency outlier。
- info/low：exact duplicate line、repeated-identical observation、明确 `partial=none`、正常
  governance/continuation summary。
- limitation 不使用 finding severity/priority；只使用 `limited_signal` 与原因码。

S2 tests 必须按目标 `rule_id` / `reason_code` 过滤后断言 evidence、layer、severity/priority 与
ordering key，不断言整个 report 的全局 finding 数量等于固定 N。S3 追加 Engine/provider
结果后，同一 S2 Host/Tool fixture 的目标 rule/evidence 与相对 ordering 必须不变。

### 10.2 Markdown

固定章节：

1. 输入与 signal coverage
2. Executive summary
3. Host findings
4. Engine findings
5. Tool findings
6. Vendor debugging
7. Large payload ranking
8. Run / attempt / tool-call chain
9. Limitations
10. Recommended next actions

Markdown：

- 只从 `ToolTraceAnalysisReport` render。
- 每个 finding 显示 finding id、priority、summary、recommendation 与 evidence refs。
- 所有用户/工具可读文本做 Markdown escaping；多行文本使用 bounded fenced block。
- 不展开 full payload、prompt/messages、provider raw body。
- `limited_signal` 明确显示“无法证明”，不显示成绿色 pass 或“未发生”。

### 10.3 Output publication and exit codes

- Service 先在 output dir 创建同目录临时文件，UTF-8 strict 写入并 flush，随后
  `os.replace` 发布 JSON 与 Markdown。
- 任一发布失败时 best-effort 清理本次临时文件；不删除调用方既有 report。
- 首版允许两个最终文件在第二次 replace 失败时出现旧/新组合；发布顺序固定为 JSON 后
  Markdown，不为两个普通 report 文件创建 transaction/journal。
- Service 定义 typed `ServiceToolTraceAnalysisPublishError`，至少携带
  `published_paths: tuple[Path, ...]`、`failed_path: Path`、
  `primary_publish_error: ServiceToolTracePublishFailure`、
  `cleanup_error: ServiceToolTraceCleanupFailure | None` 与
  `temporary_paths_cleaned: bool`。primary detail 必须携带原 replace target 和 bounded error
  summary；optional cleanup detail 必须独立携带 cleanup target paths 和 bounded secondary
  error summary。`failed_path` 永远等于 primary replace target，不得因 cleanup 失败漂移到
  temp path。不得用一个 summary 拼接/覆盖 primary 与 secondary error。
- 第二次 replace 失败时必须明确
  `published_paths=(json_path,)`、`failed_path=markdown_path`；不得删除/回滚已经成功发布的新
  JSON，也不得把旧 Markdown 误报为本次成功发布。
- CLI exit code=`1`，stderr 同时打印“已发布路径”和“发布失败路径”。best-effort cleanup 必须
  清理仍存在的本次临时文件；cleanup 自身失败进入独立 optional secondary detail，不覆盖
  primary publish error、`published_paths` 或原 `failed_path`。
- exit code：
  - `0`：两个 report 均成功发布；findings/limitations 不改变退出码。
  - `2`：输入 path/layout/参数错误。
  - `1`：读取、SQLite schema、resolver orchestration 或 output publish 导致无法完成 report。

## 11. Public / Schema / State-machine Changes

### 11.1 Necessary changes

- 新增 Host public read-only analyzer function/types，供 Service 和 WU-OBS-01 复用。
- 新增 Analyzer report schema version 1。
- 新增 CLI public command `tool_trace analyze`。
- 新增 durable internal read-only opener 和 unfiltered hot scan query。

### 11.2 Explicitly unchanged

- Tool Trace cold line `schema_version`：不变。
- `host_tool_trace_hot` SQLite schema/index：不变。
- payload descriptor schema：不变。
- EventLog event/schema：不变。
- `UsageReportedData` / Host usage projection：不变。
- `OpenHostOptions` / `OpenHostAdminOptions`：不变。
- Host / Engine / ToolRuntime state machine：不变。
- projection catch-up、producer event filter、cold writer：不变。
- Config schema/profile：不变。
- report 不注册为 Host durable public read model。

## 12. Planned Files / Modules

### 12.1 Production

- `dayu/host/tool_trace_analysis_contracts.py`（new）
  - public enums/dataclasses/policy/source/report contract。
- `dayu/host/tool_trace_analysis_input.py`（new）
  - strict cold parser、hot scan/join、resolver orchestration、normalized dataset。
- `dayu/host/tool_trace_analysis_rules.py`（new）
  - aggregation、Host/Engine/Tool rules、vendor block、payload ranking。
- `dayu/host/tool_trace_analysis.py`（new）
  - public analyzer orchestration、deterministic JSON serialization、Markdown renderer。
- `dayu/host/tool_trace.py`
  - 唯一 cold lock path 内部派生 helper，供既有 producer 与 Analyzer reader 在 Host 内共同
    复用；不从 Host root 导出；不改 event filter、cold schema、digest、append ordering 或
    timeout value。
- `dayu/host/open_host.py`
  - 删除本地重复的 lock suffix/path 派生，改用 Tool Trace owner internal helper；不新增
    public option。
- `dayu/host/durable/connection.py`
  - read-only store/opener。
- `dayu/host/durable/transaction.py`
  - 独立 read-only connection PRAGMA helper；只读取
    `HostSQLiteStoragePolicy.busy_timeout_seconds`，不复用写侧 WAL helper。
- `dayu/host/durable/tool_trace.py`
  - unfiltered hot scan page。
- `dayu/host/__init__.py`
  - intentional new public analyzer surface；不是兼容 re-export；不导出 cold lock helper、
    builder、factory、classmethod 或 wrapper。
- `dayu/service/tool_trace_analysis.py`（new）
  - supported path discovery、Host public analyzer call、atomic report publication。
- `dayu/cli/commands/tool_trace.py`（new）
  - command validation、Service call、operator output/error mapping。
- `dayu/cli/arg_parsing.py`
  - `tool_trace analyze` parser 与 typed args。
- `dayu/cli/main.py`
  - command runner registration。

### 12.2 Tests

- `tests/host/test_tool_trace_analysis_input.py`（new）
- `tests/host/test_tool_trace_analysis_rules.py`（new）
- `tests/host/test_tool_trace_analysis.py`（new）
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_durable_connection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/service/test_tool_trace_analysis.py`（new）
- `tests/cli/test_tool_trace_command.py`（new）
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_import_boundary.py`

fixture policy 分层：

- parser syntax/type unit tests 可直接构造当前 schema 的最小合法/非法 JSONL object/text，只用于
  JSON decode、object shape、`schema_version` 与字段 type/requiredness；不得构造旧 schema、
  compatibility alias 或用 mock 定义业务语义。
- line/cold digest/ref integrity、duplicate/conflicting source key、hot/cold join、watermark、
  descriptor/resolver 与 runner reconstruction integration 必须先通过当前 production Tool Trace
  projection 生成 valid hot/cold/descriptor baseline，再只对 Analyzer 输入副本做一个目标破坏。
- projection baseline tests 必须先断言未破坏 baseline 可被当前 owner 读取，避免 fixture 自身
  先天非法造成 false positive；不得修改 producer 来让 Analyzer test 通过。

Service / CLI exact entrypoints：

```text
discover_tool_trace_analysis_source(
    input_path: Path,
) -> ToolTraceAnalysisSource

run_tool_trace_analysis(
    request: ServiceToolTraceAnalysisRequest,
) -> ServiceToolTraceAnalysisResult

run_tool_trace_command(
    args: ParsedCliArgs,
) -> int
```

`ServiceToolTraceAnalysisRequest/Result` 为 frozen typed dataclass；result 只返回 report 与两个已发布
path。CLI 不接收 Host dataset、durable transaction 或 renderer internal。

所有新增/修改 module、class、function 必须提供完整中文概览/docstring，函数 docstring 明确参数、
返回值与异常；签名不得使用 `Any`、`object`、无类型参数/返回值、`hasattr/getattr` fallback 或
explicit args in extra payload。

### 12.3 Docs

- `README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/service/README.md`
- `tests/README.md`

本 plan 实际不修改上述 planned files；它们只在对应 implementation slice 获准后改动。

## 13. Implementation Slices

本 WU 使用 4 个 slices。切分依据是语义闭环、依赖顺序、失败/回滚风险和验证矩阵，不是按
文件/owner 机械拆分。

超过默认 3 个 slice 的原因：

1. corrupt/missing/digest mismatch 与只读 DB opener 属于“输入是否可信”的 fail-closed
   correctness boundary；不能和行为诊断混在一次 pass。
2. Host/Tool 调用链规则与 provider/vendor identity 规则虽共用 dataset，但后者涉及不得伪造
   provider id、不得错误 join 的高风险边界；合并会让 review 同时处理大量普通规则与身份安全。
3. CLI/Service/report publication 是用户可见、带 filesystem mutation 的独立闭环；在 analyzer
   规则未稳定前暴露入口会留下半成品。

双路 review 成本：

- 每 slice 预计两个独立 code review pass，共 8 个首轮 review lane。
- S1/S3 为高风险 review，S2 为中高风险，S4 为中风险。
- 若合并 S2+S3，可减少 2 个 review lane，但会显著增加 provider identity finding 被普通规则
  噪声掩盖的风险，因此不合并。
- 4 slices 已是最小风险切分；再拆 parser/model/render 文件级 slices 会增加孤立 contract 和
  review handoff，不采用。

### Slice 1 — Trusted input snapshot and integrity boundary

**Objective / outcome**

从 explicit typed source 读取 cold/hot/payload，得到 strict normalized dataset、integrity findings
和 limitations；全程只读、无 report/CLI。

**Allowed files**

- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_input.py`
- `dayu/host/tool_trace.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/transaction.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/__init__.py`
- `tests/host/test_tool_trace_analysis_input.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_durable_connection.py`
- `tests/host/test_tool_trace_queries.py`

**Prerequisites**

- Goal artifact=`analyzer-ready`。
- 不修改 producer 语义或输出 contract；只允许共享 lock-path helper 的等价重构，并由 projection
  regression tests 保护。

**Exact changes / call path**

```text
ToolTraceAnalysisSource
  -> validate complete explicit mode/path contract
  -> HostSQLiteStoragePolicy() for standalone read-only open
  -> open_host_durable_read_store(optional, sqlite_policy)
  -> read_tool_trace_page
  -> Host-internal derive shared adjacent cold lock
  -> acquire lock
  -> open one binary handle + fstat prefix length/identity
  -> release lock
  -> read exact prefix bytes from the same handle + close
  -> strict cold JSONL parser
  -> hot/cold join
  -> resolve_tool_trace_hot_row_payloads
  -> resolve_runner_call_projection_from_signal
  -> normalized dataset + input diagnostics + payload measures
```

**Error handling / invariants**

- SQLite opener physical read-only；schema validation 不执行 DDL。
- read-only PRAGMA 只由 `configure_read_only_connection_pragmas` 设置
  busy_timeout/foreign_keys/query_only；只读取传入
  `HostSQLiteStoragePolicy.busy_timeout_seconds`，不得调用写侧 WAL helper。
- malformed cold line 进入 finding，继续读取后续 line。
- hot path 只有“实际缺失”可在 cold 存在时产生 `hot_store_unavailable` limitation；已存在但
  open/schema/corruption/permission/type 校验失败一律 fail analysis，最终 CLI exit code 1。
- cold reader 必须在 Host 内部派生并获取默认 producer 的同一相邻 lock；timeout/acquire/release/
  open/fstat/read/close failure 按 §7.4 reason fatal，不得无锁 fallback 或依赖 OS append 原子性。
- lock 只保护 binary open + fstat prefix capture；精确 prefix read 在释放 lock 后从同一 handle
  完成。short read、truncate below prefix 或 identity invariant 失败 fatal；prefix 后追加不进入
  本次 snapshot。
- descriptor mismatch 保留 resolver cause。
- resolved raw payload 不进入 dataset 的 public report fields。
- all joins typed/ref-based。

**Tests**

- read-only opener 不创建 DB、不写 user_version/table、不允许 write。
- unfiltered page 按 sequence、cursor、limit/has_more 工作。
- `ToolTraceAnalysisSource` 四 mode 的完整字段、path layout、required/null 组合、type/existence
  matrix，以及 capability 双真源拒绝；明确 Source 无 `cold_lock_path`，Service 无需访问 Host
  internal helper。
- parser unit：手写最小 current-schema JSONL 覆盖 valid syntax、corrupt JSON、non-object、
  unsupported version、invalid field type。
- production projection baseline 后目标破坏：recomputed digest、cold digest/ref mismatch。
- producer/reader 在 Host 内部对同一 cold path 使用同一相邻 lock path；projection regression
  tests 证明 producer event filter/schema/digest/append ordering/timeout value 均未变化。
- prefix snapshot：lock 内只有 binary open/fstat，无 O(file-size) read；释放后从同一 handle
  精确读取 captured prefix，不读动态 EOF；prefix 后 append 留到下一次分析。
- live producer concurrency：用 barrier 将 reader 的 prefix read 阻塞在释放 lock 之后，启动真实
  producer append；断言 writer 在其既有 5 秒 timeout 前完成且无
  `RuntimeFileLockTimeoutError`，再释放 reader，并断言本次 snapshot 不含新 append、下一次包含。
- captured handle 对应 path 被替换时不重开新 path；同 inode truncate/short read/不足 prefix
  时 fatal `cold_snapshot_read_failed`，不得解析部分 bytes。
- lock timeout/acquire/release/read failure 为 fatal typed read error；没有 malformed finding、
  limitation 或无锁重试。
- duplicate exact/conflicting source keys。
- hot-only、cold-only、identity/digest mismatch。
- cold row sequence 高于 hot watermark 只产生
  `reason_code=input_changed_during_analysis` limitation，evidence 包含 watermark，不产生
  missing-hot finding。
- hot snapshot 空且 cold snapshot 空时返回正常空报告；hot snapshot 空而随后 cold 有正 sequence
  rows 时全部是 `input_changed_during_analysis` limitation，零 `missing_hot_trace`。
- expected hot path missing 可 cold-only；已存在但 non-Dayu schema/open/corrupt/permission/type
  failure fatal。
- read-only PRAGMA helper 分别验证 standalone `HostSQLiteStoragePolicy()` durable 默认与显式
  policy override 的 `busy_timeout_seconds`，并精确验证 foreign_keys=ON/query_only=ON；通过
  trace/spy 证明 helper 未读 write retry/backoff，且未执行 journal_mode、wal_autocheckpoint、
  bootstrap、DDL 或写侧 helper。测试不得复制 `5.0` 魔法数字。
- payload missing/digest mismatch/non-object/artifact containment。
- runner manifest/projection/schema complete/limited/mismatch。
- file-only 不打开 ref。

**Validation**

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_tool_trace_analysis_input.py
python -m pyright \
  dayu/host/tool_trace_analysis_contracts.py \
  dayu/host/tool_trace_analysis_input.py \
  dayu/host/tool_trace.py \
  dayu/host/open_host.py \
  dayu/host/durable/connection.py \
  dayu/host/durable/transaction.py \
  dayu/host/durable/tool_trace.py \
  tests/host/test_tool_trace_analysis_input.py
```

Expected assertions：所有 fixture 使用 current schema；corruption 被分类；输入未被修改；无 write
transaction；新增文件 coverage >=80%。

**Non-goals / stop condition**

- 不实现 behavior rules/renderer/CLI。
- 若 read-only opener 无法在 live WAL current workspace 上读取一致 schema，或现有 resolver
  无法接受当前真实 descriptor，停止并回 Controller；不得改用 raw SQLite/loose payload parsing。

**Completion signal**

- explicit source 可稳定得到 typed dataset、integrity diagnostics、limitations 与 verified payload
  measures。
- S1 只稳定 source/policy/input/read-only 实际消费 contract；没有 report/finding/vendor
  skeleton。
- producer 与 reader 在 Host 内部复用同一个 cold lock path owner；Source/Service 不暴露派生
  lock；prefix snapshot、live producer non-interference 与 hot DB fatal/limited matrix 通过。
- current workspace read-only smoke 能读取 live WAL/schema，且输入文件/DB hash、mtime、row count
  不被 Analyzer 改写。
- Slice 1 focused tests、targeted pyright、per-file coverage 通过；无 behavior rule/CLI 半成品被导出。

### Slice 2 — Run/tool/Host behavioral diagnostics

**Objective / outcome**

从 trusted dataset 形成 run/tool aggregation、Host/Tool findings、large payload ranking 和 typed
structured report skeleton；不暴露 operator command。

**Allowed files**

- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`
- `dayu/host/__init__.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`

**Prerequisites**

- Slice 1 accepted。

**Exact changes / data flow**

```text
normalized dataset
  -> group by direct run/attempt/execution/tool-call refs
  -> integrity projection into report
  -> Host duplicate/governance/context/truncation rules
  -> Tool repeated/failure/timing/fetch_more/large-payload rules
  -> deterministic ordering/id assignment
  -> ToolTraceAnalysisReport
```

**Error handling / invariants**

- No timestamp latency calculation。
- No arguments-text duplicate inference。
- No percentile-only large alert。
- no finding without evidence。
- limitations not counted as confirmed errors。
- exact payload body never serialized。
- S2 一次冻结最终 report 顶层 schema、finding/limitation/payload measure/run summary、
  deterministic ordering/id assignment 与 vendor block contract；S3 不得修改。
- `cold_line` measure 必须标注 `cold_jsonl_record_bytes`，不得命名为 raw payload。
- `TOOL_AWAITING` / `RUN_WAITING` 只进入 timeline 与两个 summary count；存在/缺失本身不产生
  finding。

**Tests**

- duplicate governance decisions vs repeated-identical observation。
- tool failed/cancelled vs Host policy blocked。
- timing available/missing/small-sample/outlier。
- truncation followed by matching fetch_more、no follow-up、wrong cursor。
- context pressure soft/hard/compaction failure and usage post-call-only。
- each payload category ranking、threshold boundary、unverified size limitation。
- cold record bytes 与 resolved payload bytes measurement source 分离且 report 文案不混淆。
- awaiting/waiting present/absent 均不产生猜测 finding；typed failure/rejection 才触发已有 rule。
- deterministic finding ordering/ids。
- 按目标 `rule_id`/`reason_code` 与 evidence 断言，不固定全局 finding count。
- unknown events produce no speculative finding。

**Validation**

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py
python -m pyright \
  dayu/host/tool_trace_analysis_contracts.py \
  dayu/host/tool_trace_analysis_rules.py \
  dayu/host/tool_trace_analysis.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py
```

Expected assertions：Host/Tool layer归因、priority、evidence和recommendation稳定；每个新增/修改文件
coverage >=80%。

**Non-goals / stop condition**

- 不实现 provider/vendor block 或 CLI。
- 若规则需要从当前 trace 不存在的业务字段推断 owner，停止该规则并记录 limitation；不得新增
  producer field 或 fallback。

**Completion signal**

- public `analyze_tool_trace` 对 trusted dataset 返回 deterministic structured report。
- 最终 report schema、finding ordering 与 vendor block shape 已冻结；`vendor_debugging=[]` 是
  S2 的合法最终 shape。
- Host/Tool/integrity/large-payload/context/truncation findings 全部有 direct evidence，且
  limitation 与 finding 分离。
- Slice 2 focused tests、targeted pyright、per-file coverage 通过；operator command 尚未注册。

### Slice 3 — Engine/provider correlation and vendor block

**Objective / outcome**

补齐 Engine/provider/protocol rules、partial signal 和 vendor debugging block，使 structured
report 完整满足 #70/#64 limited-signal 边界。

**Allowed files**

- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`

**Prerequisites**

- Slice 2 accepted。

**Exact changes / data flow**

```text
provider/protocol/terminal diagnostic records
  -> source payload direct iteration refs when resolvable
  -> provider-id grouping OR client-only limited grouping OR per-event limited block
  -> partial tool-call classification
  -> Engine findings + vendor blocks + limitations
  -> completed ToolTraceAnalysisReport
```

**Error handling / invariants**

- client id never copied into provider id。
- no id means no run/time-based provider-call grouping。
- usage observation never participates in vendor grouping。
- absent partial signal != explicit `summary_status=none`。
- same provider id with conflicting client/local refs produces conflict finding, not silent merge。
- Issue #64 provider/gateway path always described as unverifiable when signal absent。
- 只追加 Engine/provider rule result 与 vendor block instance；不得修改 S2 Host/Tool
  `rule_id` 语义、finding ordering/id assignment 或 report schema。

**Tests**

- provider id + client id + local refs complete block。
- provider id missing/client present limited block。
- both missing per-event limited block。
- terminal/protocol same provider id group。
- conflicting client ids。
- absent/none/present partial signal。
- file-only missing iteration/payload limitation。
- usage row with same attempt/iteration does not add provider id。
- native Anthropic/Claude Code wording remains limited and does not infer adapter。

**Validation**

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py
python -m pyright \
  dayu/host/tool_trace_analysis_contracts.py \
  dayu/host/tool_trace_analysis_input.py \
  dayu/host/tool_trace_analysis_rules.py \
  dayu/host/tool_trace_analysis.py \
  dayu/host/tool_trace.py \
  dayu/host/open_host.py \
  dayu/host/durable/connection.py \
  dayu/host/durable/transaction.py \
  dayu/host/durable/tool_trace.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py
```

Expected assertions：request id/local refs同报告；limited reasons精确；零 identity inference；
coverage >=80%。

**Non-goals / stop condition**

- 不修改 Engine/Host signal producer。
- 若 S3 发现必须修改 S2 已冻结的 report 字段、枚举、nullable 语义、finding ordering 或
  id assignment 才能完成 Engine/provider rules，立即停止并回 Controller；不得把
  `tool_trace_analysis_contracts.py` 加回 allowed files，也不得在 rules/renderer 中加兼容
  branch 绕过 contract。
- 若当前 trace 无法区分一个计划中声称 available 的 provider identity，停止并降为 limitation；
  若 success signal 必须依赖新 producer field，则回 Controller，禁止按顺序/时间补偿。

**Completion signal**

- Engine/provider/protocol findings 与 vendor blocks 完整进入同一 structured report。
- provider/client/local refs complete、missing、conflict 与 file-only cases 均按 contract 分类。
- usage observation 与 vendor grouping 零 join；Issue #64 wording 只表达 limitation。
- S1/S2 完整矩阵复跑通过；S2 目标 `rule_id`/evidence、relative ordering、frozen schema 与
  vendor block contract 无回归。
- Slice 3 focused tests、targeted pyright、per-file coverage 通过。

### Slice 4 — Service/CLI publication and docs

**Objective / outcome**

交付可运行 operator command，原子发布 JSON/Markdown，并同步用户/开发/测试文档。

**Allowed files**

- `dayu/host/tool_trace_analysis.py`
- `dayu/service/tool_trace_analysis.py`
- `dayu/cli/commands/tool_trace.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- `tests/service/test_tool_trace_analysis.py`
- `tests/cli/test_tool_trace_command.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_import_boundary.py`
- `README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/service/README.md`
- `tests/README.md`

**Prerequisites**

- Slice 3 accepted；structured report contract finalized。

**Exact changes / call path**

```text
CLI parser
  -> dayu.cli.commands.tool_trace
  -> Service path discovery
  -> Host public analyze_tool_trace
  -> Host JSON/Markdown render from same report
  -> Service temp-write/replace
  -> CLI output paths + exit code
```

**Error handling / invariants**

- CLI module只 import Service/public contracts，不 import `dayu.host.durable`。
- path/layout ambiguity usage error。
- output dir/report write failure返回 1，不删除既有 report。
- report successful regardless of diagnostic severity。
- JSON/Markdown ref/size/finding counts同源。

**Tests**

- parser help/required args/unknown action。
- all four input modes、ambiguous/unsupported path。
- hot-only/cold-only/artifact-root-missing。
- output paths and UTF-8。
- JSON schema field assertions、Markdown sections/evidence。
- Service calls Host public API; CLI import boundary。
- publication failure cleanup/exit code。
- 第一次 replace 失败：`published_paths=()`、failed JSON path 明确、旧文件均不删除。
- 第二次 replace 失败且旧 Markdown 存在：新 JSON 保留、旧 Markdown 保留，error 明确
  published JSON path / failed Markdown path，临时文件清理。
- 第二次 replace 失败且旧 Markdown 不存在：新 JSON 保留、Markdown 仍不存在，同样明确成功/
  失败路径并清理临时文件。
- 第一次与第二次 replace 各自再覆盖 cleanup failure：typed error 同时保留
  `primary_publish_error` 与 optional `cleanup_error`；`failed_path` 始终等于原 replace target，
  不漂移到 temp cleanup path，`published_paths` 不被 secondary failure 改写。
- real subprocess/module entry smoke。

**Validation**

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py
python -m pyright dayu/ tests/ utils/
```

Real current workspace smoke：

```bash
source .venv/bin/activate
report_dir="$(mktemp -d)"
python -m dayu.cli tool_trace analyze workspace --output-dir "$report_dir"
python -m json.tool "$report_dir/tool-trace-analysis.json" >/dev/null
test -s "$report_dir/tool-trace-analysis.md"

file_report_dir="$(mktemp -d)"
python -m dayu.cli tool_trace analyze \
  workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl \
  --output-dir "$file_report_dir"
python -m json.tool "$file_report_dir/tool-trace-analysis.json" >/dev/null
```

Expected assertions：

- directory mode发现当前 hot/cold/artifact；当前真实9行无虚假digest mismatch。
- file mode明确 hot/payload limited。
- 两种 mode 都生成非空 JSON/Markdown。
- project-wide pyright 无新增/扩散错误。

**Non-goals / stop condition**

- 不接 bundle search、prompt/final lookup、external provider。
- 若 CLI 必须绕过 Service 或 Service 必须 import durable internals才能工作，停止并重新裁决 public
  Host interface；不得加胶水 facade。

**Completion signal**

- `dayu-cli tool_trace analyze` 对 directory/file 两条真实路径均发布 JSON/Markdown。
- JSON 与 Markdown finding/vendor/limitation counts 同源，CLI 分层/import boundary 成立。
- 实施 README 前必须先逐个读取 `README.md`、`dayu/README.md`、`dayu/host/README.md`、
  `dayu/service/README.md`、`tests/README.md` 各自的 Agent 更新约束，只在职责命中时更新；
  S4 不拆独立 docs slice。
- focused/full affected tests、project-wide pyright、per-file coverage、README 决策与 real workspace
  smoke 全部通过。

## 14. Complete Validation Matrix

### 14.1 Focused functional matrix

| Scenario | Expected |
|---|---|
| valid cold file | parse/report成功，hot/payload limited |
| valid workspace dir | hot/cold join + payload verify |
| Source four-mode field matrix | required/null/path layout 全部由 Host boundary 拒绝非法组合；public Source 无 `cold_lock_path` |
| reader 与 default producer lock | Host 内部同一 adjacent lock path；锁内仅 binary open/fstat prefix capture，无 O(file-size) read |
| live producer during slow prefix read | reader 释放锁后被 barrier 阻塞；真实 writer 在既有 5 秒 timeout 前完成，无 timeout；新 bytes 本次不可见、下次可见 |
| prefix append/replace/truncate | append beyond prefix 留待下次；同一 handle 不切到 replaced path；short read/truncate below prefix fatal |
| cold lock timeout/acquire/release failure | fatal read error；CLI 1；无 report、无 unlocked fallback |
| hot path absent + cold present | `hot_store_unavailable` limitation；cold-only report 可完成 |
| hot path exists but open/schema/corrupt fails | fatal analysis；CLI 1；不得降为 cold-only |
| read-only PRAGMA trace | 仅 busy_timeout/foreign_keys/query_only；无 WAL/autocheckpoint/bootstrap/DDL |
| read-only SQLite policy source | standalone 使用 `HostSQLiteStoragePolicy()` durable 默认；显式 override 只影响 busy timeout；不进入 Analyzer policy/CLI |
| corrupt JSON line | input finding含path/line；后续有效行仍分析 |
| line digest mismatch | Host error finding |
| duplicate exact line | warning；不重复计入run stats |
| same source key conflicting digest | Host error finding |
| hot row missing cold | confirmed Host integrity error |
| cold row beyond hot watermark | `input_changed_during_analysis` limitation，不误判corrupt或计入finding |
| hot-empty + cold-empty | watermark=0；正常空报告，无 finding/limitation |
| hot-empty + cold-late positive rows | 全部 `input_changed_during_analysis` limitation；零 `missing_hot_trace` |
| descriptor missing | integrity finding + dependent limitation |
| descriptor digest mismatch | error；不读取/输出body |
| large runner input/tool result/provider payload/schema | ranked + threshold finding |
| cold-line byte ranking | `measurement_source=cold_jsonl_record_bytes`；不称 raw payload |
| resolved payload byte ranking | `measurement_source=resolved_payload_bytes`；与 cold record 独立 |
| tool timing missing | limited；不从timestamp计算 |
| latency outlier with enough samples | Tool warning |
| duplicate decision present | Host governance finding |
| repeated same digest no duplicate decision | Tool repeated observation |
| truncation + matching fetch_more cursor | no missing-followup finding |
| truncation without matching fetch_more | Tool finding with both chain evidence |
| provider protocol error | Engine high-priority finding |
| partial absent/none/present | limited/explicit-none/present distinct |
| provider + client ids | vendor block with local refs |
| provider id missing | limited，不以client id伪装 |
| usage same iteration as provider error | no request-level join |
| awaiting/waiting present or absent | 只影响 timeline/summary counts；无猜测 finding |
| typed wait/tool rejection or failure | 只有 source-owned typed signal 才产生对应 finding |
| Issue #64 path | limited wording only |
| S2 report handoff | 最终 schema/order/vendor block 冻结；assert target rule_id/reason/evidence，不锁全局数量 |
| S3 regression | 复跑 S1/S2；仅追加 Engine/provider result，冻结 contract/Host/Tool rules不变 |
| second replace fails with old Markdown | 新 JSON + 旧 Markdown；error 分列 published/failed paths；temp cleaned |
| second replace fails without old Markdown | 新 JSON + Markdown absent；error 分列 published/failed paths；temp cleaned |
| replace failure + cleanup failure | primary publish error与optional cleanup secondary error并存；原 `failed_path`/`published_paths`不漂移 |

### 14.2 Final test / type / coverage commands

```bash
source .venv/bin/activate
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
  --cov-report=term-missing

python -m pyright dayu/ tests/ utils/
```

Coverage output 必须逐文件检查上述新增/修改源文件均 >=80%，不能只看 aggregate。

### 14.3 Final repository checks

```bash
git diff --check
git status --short
```

Expected：

- implementation gate 仅出现 approved planned files 与 Controller 已有 control/goal artifact。
- 无 fixture、tmp report、coverage JSON、SQLite sidecar 或真实 workspace trace 被提交。

## 15. Plan Review Disposition

最新 Controller adjudication
`docs/reviews/wu-obs-00-plan-rereview-adjudication-controller.md` 是本 gate 唯一 disposition
真源；两路 reviewer 建议与首轮 adjudication 不得覆盖它。首轮 disposition 的闭合状态保留如下，
但任何被最新裁决替代的实现方向均以第二表为准：

| Finding | Disposition | Plan section / action |
|---|---|---|
| MiMo F001 | accepted；方向由最新裁决细化 | §5.1、§6、§7.3-7.4、S1：共享 lock owner、fatal failure、prefix snapshot顺序 |
| MiMo F002 | accepted with Controller direction | §8.4、S1、§14.1：只允许 path 缺失 cold-only；已存在但不可读/不可校验 fatal |
| MiMo F003 | rejected | 保持四 slices 与 S4 code/docs 单闭环；S4 completion 先读 README 约束 |
| MiMo F004 + DS F-DS-02 | accepted/merged | §8.1、§10.1、S1-S3：S1 input-only；S2 freeze；S3 append-only并复跑 |
| MiMo F005 | accepted | §8.4、S1：独立 read-only PRAGMA helper，禁止写侧 WAL helper |
| MiMo F006 | accepted | §10.3、S4、§14.1：typed partial-publish evidence 与 old/new tests |
| MiMo F007 | rejected for current WU | §3.1：不新增 CLI policy flags |
| DS F-DS-01 | accepted | §7.4、§9.1、§10.1、S1、§14.1：稳定 reason code `input_changed_during_analysis` |
| DS F-DS-03 | accepted | §9.2、§10.1、S2、§14.1：cold record bytes 与 resolved payload bytes 分离 |
| DS F-DS-04 | accepted | §9.3、§10.1、S2、§14.1：known wait facts/summary only |
| DS F-DS-05 | deferred to WU-OBS-01 | §3.1：不预判 Service discovery 复用方式 |
| DS F-DS-06 | accepted | §12.2、S1：parser unit 与 production-baseline integrity/integration fixture 分层 |
| CTRL-PF-01 | accepted；public lock field由最新裁决删除 | §7.3：Source 显式字段、类型、必填性、mode/path matrix |
| CTRL-PF-02 | accepted | S4 allowed-files 中 `dayu/cli/main.py` 只保留一个条目 |

最新 re-review adjudication：

| Finding | Disposition | Plan section / action |
|---|---|---|
| MiMo OQ-1 + DS F-R4 | accepted；拒绝 public builder/factory | §5.1、§6、§7.3-7.4、S1、§14.1：public Source 删除派生 lock；Service 只传显式路径；Host Analyzer 内部派生；helper 不从 Host root 导出 |
| DS F-R1 | accepted | §7.4、S1、§14.1、§17.1：锁内只做 binary open/fstat prefix capture；释放后同 handle 精确读 prefix；live producer、append、replace、truncate/short-read tests |
| MiMo OQ-2 + DS F-R2 | accepted | §8.2、§8.4、S1、§14.1：read-only opener 显式使用 `HostSQLiteStoragePolicy`；standalone 使用 durable 默认；Analyzer policy/CLI 无 SQLite timeout |
| MiMo OQ-3 | accepted clarification | §7.4、§8.3、S1、§14.1：hot-empty/cold-empty 正常空报告；hot-empty/cold-late 全部 input-changed limitation，零 missing-hot |
| MiMo Spot-check 4 + DS F-R3 | accepted | §7.3、§10.1：Source/report 使用单数 `cold_jsonl_path`；report 只额外投影 Host 派生单数 `cold_lock_path` |
| MiMo Spot-check 5 | accepted | §3.1、§5.1、§12.1、S1：只承诺 producer 语义/输出 contract 不变；允许共享 helper 等价重构并做 projection regression |
| DS F-R5 | accepted | S3：冻结 contract 如需变更立即回 Controller；`contracts.py` 不回 allowed files |
| DS cleanup secondary error | accepted | §10.3、S4、§14.1：typed error 分离 primary publish 与 optional cleanup secondary；cleanup failure 不改变 failed/published paths |

Rejected/deferred 项没有通过“未来增强”“兼容分支”或 residual-risk 文字变相进入当前 scope。
修后 blocking open questions=None；下一 gate 只能是 AgentMiMo/AgentDS 对同一计划的独立
second plan re-review，不得进入 implementation。

## 16. README / Docs Decision

实现将改变用户可见 CLI、输出文件位置、operator workflow、Host analyzer public surface 与测试层级，
因此命中 README 更新触发条件：

- `README.md`：新增 `tool_trace analyze` 输入模式、典型命令、JSON/Markdown 输出、limited-signal
  说明和排障边界；只写最终用户可用操作，不展开 Host内部。
- `dayu/host/README.md`：新增 Analyzer 是 read-only projection consumer、resolver/integrity owner
  边界、report不是truth、usage/provider identity限制。
- `dayu/service/README.md`：新增 path discovery + Host public analyzer + report publication stable
  entry。
- `tests/README.md`：新增 focused analyzer/CLI test和coverage命令。
- `dayu/README.md`：仅补跨层 operator path
  `CLI -> Service -> Host Analyzer -> Tool Trace projection/resolver`，因为公开装配路径发生变化。
- 不更新 `dayu/engine/README.md`、`dayu/config/README.md`、`dayu/fins/README.md`：本 WU 不改变其
  reader-facing contract。
- 不更新 design/control doc：本实现遵循现有设计，gate状态由Controller拥有。

## 17. Risks / Open Questions / Residual Ownership

### 17.1 Classified residual risks

| Risk | Classification / owner | Plan handling |
|---|---|---|
| native Anthropic request-id / Claude Code gateway signal未完成 | tracked by existing Issue #64 | limited signal；不阻塞 |
| cold rotation/archive 后路径发现 | tracked by Issue #36 retention lane | 首版只支持当前布局；不递归猜测 |
| prompt/final-answer 反查与bundle export | assigned to WU-OBS-01 / Issue #71 | 复用本Analyzer public API |
| usage request-level correlation | closed by current WU-OBS-00B decision / Issue #119 closeout owner | 不扩展usage；只作post-call pressure |
| file-only无法验证payload/iteration | accepted WU-OBS-00 limitation | structured limitation |
| live producer导致跨hot/cold观察窗口 | fixed in current WU by hot watermark + exact cold prefix rule | prefix 后 append留待下次；不做distributed snapshot |
| reader反向阻塞live producer | fixed in current WU | 独占锁内仅open/fstat；全prefix读取在释放锁后；并发test证明writer不触发既有5秒timeout |
| 极大cold文件的内存/运行时成本 | tracked by Issue #36；首版精确prefix读取但聚合仍驻内存 | O(file-size) I/O不持锁；report cold-line size；不建stream processor |
| output两个文件无法跨文件原子提交 | accepted operator-file residual | 第二个publish失败返回1并报告路径 |
| current workspace没有真实protocol-error样本 | covered by owner-level tests；真实样本缺失分类为uncovered | 不制造真实fixture结论 |

### 17.2 Open questions

None blocking。

实现阶段不得自行扩展 scope。若出现以下任一新事实，停止当前 slice 回 Controller：

- current trace 无法通过现有 typed resolver解析且原因是producer缺失必要语义；
- vendor success signal 必须依赖新 provider schema；
- public入口必须绕过 Service；
- report需要成为 durable truth或驱动state transition；
- current schema无法裁决某规则owner。

## 18. Why This Is Not Over-designed

- 只新增一个 analyzer、一个 fixed report schema 和一个 CLI action。
- 规则是普通 typed functions + stable rule ids，不引入 engine/registry/plugin/DSL。
- policy 只有实际验收需要的 size/ranking/latency参数，不引入 config profile/schema。
- 输入只支持当前明确布局与显式 file，不递归扫描、不接 archive/cloud。
- 复用现有 Tool Trace query/resolver、canonical digest、file lock、CLI/Service layering。
- 派生 lock path 留在 Host internal owner，不增加 public Source field、builder/factory/wrapper；
  SQLite read timeout 复用既有 `HostSQLiteStoragePolicy()`，不扩 Analyzer policy/CLI。
- read-only opener是防止operator工具意外bootstrap/写DB的最小correctness能力，不是新storage。
- Markdown从structured report单向派生，避免两套诊断真源。
- WU-OBS-01复用同一public analyzer，解决了明确存在的第二消费者压力；除此之外不做通用framework。

## 19. Completion Report Format

每个 slice implementation completion artifact 必须包含：

```text
status=complete|blocked
work_unit=WU-OBS-00
slice=<S1|S2|S3|S4>
artifact path=<implementation artifact path>
changed files=<actual files>
semantic owner/interface decisions=<decisions actually applied>
tests=<commands + exact pass/fail summary>
pyright=<command + result>
coverage=<per-file result>
docs decision=<updated/not-yet-due + reason>
findings/residual risks=<classified list>
stop condition=<none or direct evidence>
next entry point=<code review; never self-advance>
```

本 plan gate 完成报告必须使用用户指定格式：

```text
status=complete|blocked
artifact path=docs/host/wu-obs-00-plan.md
plan slices数量与切分依据=<count + rationale>
关键owner/interface决策=<summary>
planned files=<list>
validation结果=<artifact self-check + git diff --check + git status>
docs decision=<implementation-stage README decisions>
residual risks/uncovered areas=<classified list>
当前worktree中实际新增/修改的文件=<actual status>
```

本 Agent 不 commit、push、创建/修改 PR、merge、修改 Issue，也不进入 plan review 或 implementation。
