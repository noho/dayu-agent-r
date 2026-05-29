# Phase 13 Plan Review — Independent Reviewer Artifact

## Gate

Phase 13 plan review。Review target:
`docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Verdict

**VERDICT: CONDITIONAL PASS — 1 blocking finding requiring plan amendment before handoff.**

Below finding F1 is blocking: `read_outbox_terminal_items` 的副作用声明自相矛盾，
implementation agent 无法从 plan 中判断实现语义。其余 findings (F2-F9) 为
material 但不阻塞 code generation start；若 controller 决定在 implementation
中逐 slice 裁决，可降级为非阻塞。

---

## Evidence Base

- **Design truth**: `docs/host/design.md` §2 (Observer/Sink/Projection boundary),
  §14 (Sink semantic contract), §14.1 (Tool Trace hot/cold), §15 (Audit),
  §16 (Outbox/read-model), P10.5 constraints.
- **Control truth**: `docs/host/implementation-control.md` Phase 13 entries,
  current gate = "Phase 13 plan review".
- **Controller adjudication**: `docs/reviews/phase13-design-discussion-controller-adjudication-20260529.md`
  D1-D5 all accepted.
- **Code evidence**: `dayu/host/api.py` (Host Protocol, HostEvent, OpenHostOptions,
  HostTerminalStatus, OutboxSummary), `dayu/host/projection.py` (ProjectionRunner,
  ProjectionConsumer, ProjectionEventView, ProjectionEventFilter),
  `dayu/host/durable/schema.py` (HOST_SCHEMA_VERSION=10, existing tables),
  `dayu/host/__init__.py` (current export list).

---

## Design Goal Compliance

### Sink / Projection Boundary

Plan 明确将 Audit/Tool Trace/Outbox 全部定位为 projection/sink，只消费 committed
EventLog。检查每一项：

- **不进入 command path**: Plan 禁止修改 Engine、EventLog append 语义、
  Run/Attempt governance state、terminal transaction（Plan §Non-goals）。
- **Sink failure 不回滚 EventLog**: Plan §Error Semantics 规定 sink failure
  只产生 projection-local failure/lag，不改变 checkpoint 直到 retry 成功。
- **Outbox 不成为恢复真源**: Plan §OutboxSink 明确 "outbox 表是 projection/work
  queue，可由 EventLog 重建"。

PASS。无违反。

### watch_session_events Live-Only 语义

Plan §Non-goals 明确：
- "不把 Outbox 合并进 watch_session_events(...)"
- "不为 live watch 加 cursor / replay 参数"
- "不新增 cursor / replay 参数"

Plan §Live Watch 去重/防漏协议 定义了两种 attach 形态（live-first, drain-first）
并要求 tests 验证。两者均不改变 `watch_session_events` signature。

PASS。无违反。

### Outbox Read / Drain 是唯一 Additive Public Extension

Plan §Public Contract Changes 明确 Outbox read/drain 是唯一 additive public
extension。不新增 `OpenHostOptions` 字段。不新增 `wait_final_answer(...)`、
`get_run_result(...)` 等。

PASS。无违反。

---

## Findings

### F1-BLOCKING-read_outbox_terminal_items 副作用声明自相矛盾

**Evidence**:
- Plan 第 197 行: "`read_outbox_terminal_items` 必须无副作用，但可以在读取前
  best-effort catch up OutboxSink；catch-up 写入仍是 projection-local。"
- Plan 第 369 行: "read/drain 前可运行 OutboxSink catch-up 到当前 EventLog high
  watermark；失败只影响 `projection_status`。"

**Impact**:
"Best-effort catch up OutboxSink" 意味着在 read 调用期间运行
`OutboxTerminalProjectionConsumer`，写入 `host_outbox_terminal_items` 表和推进
`host_projection_checkpoints` — 这就是副作用（写 durable projection rows、
advance checkpoint）。同时声称 "必须无副作用" 是 self-contradictory。

Implementation agent 无法从 plan 判断 read 的行为：
- 选项 A: read 是 pure reader，caller 负责在 read 前显式 trigger catch-up。
- 选项 B: read 自动 best-effort catch-up，catch-up 写 projection 是允许的
  "projection-local" 副作用，不算违反 "无副作用" 声明。
- 选项 C: read 在最佳努力范围内触发 catch-up，但 read 返回的 items 不改变
  item_state（这一点确实无副作用）。

Plan 需要澄清 "无副作用" 的范围：是指不改变 Outbox item_state（即不 drain），
还是指完全不写任何 durable state。当前写法无法安全实现。

**Required change**:
将 "必须无副作用" 替换为精确的副作用边界声明，例如:
"`read_outbox_terminal_items` 不得改变任何 Outbox item 的 `item_state`，不得写
EventLog，不得更新 Run/Attempt。允许在返回前 best-effort catch up OutboxSink
（写 projection rows + 推进 checkpoint），catch-up 失败时必须通过
`projection_status=LAGGED` 或 `FAILED` 暴露，不得静默返回 stale 结果。"

---

### F2-MATERIAL-purge_session 与 Audit/Outbox 交互完全未覆盖

**Evidence**:
- Design.md §15 明确: "`purge_session` 不删除已经写入的 append-only audit JSONL
  记录。purge 必须产生 purge tombstone audit record；既有 audit 行可以保留对已
  purge EventLog rows 的 refs。"
- Plan 全文中 `purge` 一词仅在 §Error Semantics 作为 session gone 场景出现一次，
  没有任何 slice 定义 purge 事件对 Audit Sink、OutboxSink 或 Tool Trace
  Sink 的处理逻辑。
- Plan §Non-goals 明确不做 "purge tombstone"，但 design.md 要求 purge 必须产生
  purge tombstone audit record。

**Impact**:
Implementation agent 会在 purge 场景遇到未定义行为：Outbox 中已投递的 terminal
item 在 session purge 后读取会怎样？Audit JSONL 是否需要处理 purge 事件？
Purge 事件本身是否要进入 audit log？

**Required change**:
在 plan 中明确 Phase 13 scope 内 purge 的处理策略。两个合理路径：
1. 在 Slice 1 (Audit) 中纳入 purge tombstone audit record（如 design.md §15
   要求）；或
2. 在 Non-goals 中明确将 purge audit tombstone 延后到 Phase 15（与 retention
   一起），并解释为何当前不阻塞 Phase 13 交付。

---

### F3-MATERIAL-tool-trace-diagnostic-whitelist-未枚举

**Evidence**:
- Plan 第 322-323 行: "diagnostic events：provider / runner usage、provider
  request diagnostic、context governance / compact diagnostic 中含 provider
  refs 的事件，可按已有 EventLog event class/type 白名单纳入；不得用无结构全量
  diagnostic payload 兜底。"
- Plan 未列出具体 event_type 白名单。

**Impact**:
Implementation agent 需要自行搜索 EventLog event types 并判断哪些属于
"provider request diagnostic"、"context governance diagnostic"。若白名单过宽，
hot projection 会被 diagnostic 噪音撑大；若过窄，provider request chain 查询
会缺失关键事件。这不阻塞 start，但增加了 implementation 返工风险。

**Required change**:
Plan 应给出初版白名单，至少包含 event_class/event_type 前缀规则。例如:
- `PROVIDER_REQUEST_STARTED`、`PROVIDER_REQUEST_COMPLETED`、`PROVIDER_REQUEST_FAILED`
- `CONTEXT_COMPACT_EXECUTED`（含 provider refs 时）
- 或明确 "以 tool trace cold JSONL 的 diagnostic_refs 查询需求反向推导白名单"
  作为 Slice 2 的第一步实现动作。

---

### F4-MATERIAL-host_audit_jsonl_events 表命名与定位冲突

**Evidence**:
- Plan 第 247-249 行定义可选的 `host_audit_jsonl_events` 表，命名为
  "audit_jsonl_events" 暗示 audit events 存在于 SQLite 中。
- Plan 明确 audit artifact 是 JSONL 文件，SQLite 表仅作 idempotency marker。
- Design.md §15: "audit projection 可以为了查询重组，但不能反向成为恢复、resume
  或 memory 真源。"

**Impact**:
命名 `host_audit_jsonl_events` 会让未来读者误认为 audit events 存储在 SQLite
中，而实际上 JSONL 才是 audit artifact。若后续迭代有人在 SQLite 上做 audit
查询，会绕过 JSONL 真源。

**Required change**:
改名为 `host_audit_sink_markers` 或 `host_audit_jsonl_idempotency`，明确表达
这是 sink-local auxiliary table，不是 audit data store。同时在该表 docstring
中明确写出 "此行不是 audit event；audit artifact 是 JSONL 文件"。

---

### F5-MATERIAL-HostTerminalStatus 不含 LOST，Outbox 终端状态映射缺口

**Evidence**:
- `dayu/host/api.py:2504` 定义 `HostTerminalStatus` 仅含 `SUCCEEDED`、`FAILED`、
  `CANCELLED`，不含 `LOST`。
- Plan 第 363 行: "`RUN_LOST` 不进入 public terminal item，除非设计已有 public
  lost display 语义。第一版建议 `RUN_LOST` 仅投影 diagnostic item 或 skipped
  with detail code。"
- Plan 第 128 行 OutboxTerminalItem 定义 `terminal_status: HostTerminalStatus`
  — 如果 RUN_LOST 最终需要 outbox item，HostTerminalStatus 需要扩展。

**Impact**:
Implementation agent 在处理 RUN_LOST 事件时有两个选择：(a) 跳过不创建 outbox
item，(b) 创建 item 但需要扩展 `HostTerminalStatus`。Plan 的 "skipped with
detail code" 暗示 (a)，但未与 HostTerminalStatus 的定义做一致性校验。若后续
Phase 11 recovery 使 LOST 成为常发事件，Service 可能期望 outbox 中有 LOST 通知。

**Required change**:
在 plan 中明确：Phase 13 第一版 OutboxSink 对 RUN_LOST 的 consumer apply 返回
`SKIPPED` + detail_code，不创建 outbox item。RUN_LOST 的 outbox item 化延后到
与 Phase 11 recovery 集成时再议。

---

### F6-LOW-tool-trace-query-helper-签名不一致

**Evidence**:
- Plan 第 345-348 行:
  - `read_tool_trace_by_run(run_id, limit, after_event_sequence)` — 有分页参数
  - `find_tool_trace_by_tool_call_id(tool_call_id)` — 无分页
  - `find_tool_trace_by_provider_request_id(provider_request_id)` — 无分页
  - `find_tool_trace_by_diagnostic_ref(diagnostic_ref)` — 无分页

**Impact**:
按 tool_call_id/provider_request_id 的查询可能返回多行（同一 tool_call 可能有
多个 trace event: REQUESTED -> GOVERNED -> RESULT_ACCEPTED）。无分页意味着
implementation 需要自行决定返回多少行。

**Required change**:
明确每个 helper 的返回类型和分页语义。对于 find-by-id 查询，声明 "返回按
event_sequence 升序排列的所有匹配行" 或 "返回最新 N 行"。

---

### F7-LOW-plan-defines-dual-host_handle-closed-error-path-but-existing-code-uses-HostClosedError

**Evidence**:
- Plan 第 201 行: "Host handle closed：抛 `HostClosedError`，不写 EventLog。"
- `dayu/host/api.py` 中 `HostClosedError` 已存在（`__all__` 中有导出）。

**Impact**:
低。Plan 正确引用了已有类型，但未说明 `read_outbox_terminal_items` 和
`drain_outbox_terminal_items` 是在 `_PublicHostHandle` 方法开头检查 closed
handle。这在现有模式中已经建立，implementation agent 可以参照现有方法。

**Required change**:
No plan change required — implementation agent 参照现有 `_PublicHostHandle`
方法（如 `get_session`、`get_run`）的 closed-handle 检查模式即可。

---

### F8-LOW-防漏窗口测试未覆盖 sink-stopped-while-terminal-happens 场景

**Evidence**:
- Plan §Live Watch 去重/防漏协议 定义了两种 attach 形态：live-first 和
  drain-first + second-read。
- Plan 未定义 "OutboxSink 尚未追上但 terminal 已发生" 场景下 drain-first
  read 的行为验证——这需要 `projection_status=LAGGED` 且 second-read 能覆盖。

**Impact**:
测试覆盖可能不完整。但这已隐含在 `projection_status` 的测试要求中（Plan 第 525
行: "projection lag / failure status 返回"）。

**Required change**:
在 Slice 4 smoke tests 中显式加入: "drain-first read 在 projection_status=LAGGED
时，second read 能追上新投影的 terminal item"。

---

### F9-INFO-agents-md-合规性-检查

逐项检查 AGENTS.md（即 CLAUDE.md）约束：

| 约束 | 状态 | 说明 |
|------|------|------|
| 禁止 `object`/`Any`/无类型参数 | PASS | Plan 明确要求所有 public dataclass 严格类型化 (§Review Gates) |
| 禁止 compat wrapper/re-export | PASS | Plan §Non-goals 明确 "不做 compat re-export, compat wrapper 或 facade" |
| 禁止魔法字符串 | PASS | Plan 使用 StrEnum、模块级常量 |
| 禁止反向依赖 | PASS | Plan §Non-goals 明确禁止修改 Engine、Service、UI |
| 禁止过度设计 | PASS | Plan 明确不做 AuditPolicy 规则引擎、不做 external audit 系统、不做 channel delivery state |
| 禁止 `hasattr`/`getattr` 逃避类型 | PASS | Plan 第 433 行: "不能用 `getattr`/`hasattr` 逃避 payload schema" |
| schema change 按全新起库 | PASS | Plan 明确 fresh schema bump 到 11，不做旧库兼容 |
| 测试覆盖 >= 80% | CONDITIONAL | Plan 列出了测试文件但未给出具体覆盖率目标 |

---

## Controller Question: LogAuditSink 路径注入

Controller 提出的待审问题:

> plan 中"不新增 OpenHostOptions 字段、sink constructor typed path injection
> + artifact_root 默认派生路径"的选择是否符合 design.md 中 typed options
> 显式传入要求；如不符合，请给 blocking finding。

**Reviewer 判断: 符合，不构成 blocking finding。**

理由:

1. Design.md §15: "audit log file 路径由 Host composition root 的 typed
   options 显式传入，可有默认值。"

   这里 "typed options" 的指称对象是路径注入所用的 typed dataclass，不必然是
   `OpenHostOptions`。Plan 中 `LogAuditSinkOptions(audit_jsonl_path: Path, ...)`
   是一个 typed dataclass，满足 "typed options" 约束。

2. "Host composition root" 指 `open_host` 函数及其装配逻辑。Plan 的方式是:
   `open_host` 在装配 `LogAuditSink` 时，从 `artifact_root` 派生默认路径，
   构造 `LogAuditSinkOptions(audit_jsonl_path=...)` 并传入 sink constructor。
   路径确实在 composition root 通过 typed options 显式传入。

3. "可有默认值": `artifact_root / "audit" / "host-audit.jsonl"` 是默认派生
   路径，不要求调用方在 `OpenHostOptions` 上额外配置。

4. 不新增 `OpenHostOptions` 字段是正确选择——`OpenHostOptions` 已有 20+ 字段，
   audit/trace JSONL 路径不应进一步扩大其 surface。sink constructor 的 typed
   options 是更合适的注入点。

5. 若未来需要覆盖默认路径，可以在不改变 `OpenHostOptions` 的前提下，通过
   `open_host` 的参数扩展或 factory 注入完成。当前 plan 的路径策略为这一演进
   保留了空间。

**结论**: 此方案满足 design.md 要求，不构成 blocking finding。建议在 plan 中
显式引用 design.md §15 的原文，让 implementation agent 理解设计意图。

---

## Slice Granularity & File Ownership

4 个 slices 粒度合理:

- **Slice 1 (LogAuditSink)**: 自包含，只涉及 audit 文件 + schema + open_host
  装配。File ownership 清晰。
- **Slice 2 (Tool Trace)**: hot projection + cold JSONL + query helpers。
  独立于 Slice 1 和 Slice 3。无 future-slice leakage。
- **Slice 3 (OutboxSink Durable)**: 纯 durable projection，不接 public handle。
  正确的先后顺序——先让 projection 正确，再接 API。
- **Slice 4 (Public API + Smoke)**: 在 Slice 3 的 durable 基础上接 public
  handle。Slice 4 显式 listed outbox.py，允许 slice 间小幅修改，合理。

Stop conditions 每个 slice 都有，覆盖了需要交 controller 的场景。

**Future-slice leakage 检查**: 无。Plan 明确 "任一 slice 发现需要修改 Engine、
command path 状态机、terminal transaction 或 watch_session_events signature，
立即停止" — 这条跨所有 slices 有效。

---

## Residual Risk Classification (Reviewer Confirmation)

Plan §Residual Risks 的自我分类经审查后确认:

- **P0 blocking**: 无 — 确认。除 F1 需在 plan 层面修复外，无架构级 blocking。
- **P1 material but accepted** (JSONL crash residual exactly-once): 同意。
  Append-only JSONL + SQLite checkpoint 的跨介质非原子性是物理约束，Plan
  通过 `event_id` 去重 + `line_digest` marker 做了合理缓解。Analyze helper
  按 `event_id` 逻辑去重的要求已明确。
- **P1 material but accepted** (Outbox drain ≠ channel delivery success): 同意。
  这是正确的边界划分。
- **P2 deferred** (purge tombstone, retention, external audit): 同意归属 Phase 15。
  但 purge tombstone audit record 的缺失（F2）需要在 plan 中显式处理。

---

## Tests / Validation / README Sync

Plan §Tests / Validation Commands 列出的 aggregate 验证命令覆盖了所有新增测试
文件。Review 确认:

- 每个 slice 有对应的 test file(s)。
- 测试场景覆盖: JSONL 字段完整性、checkpoint/duplicate replay、projection
  failure 不推进 checkpoint、API validation、closed handle、session not found、
  projection lag/failure、offline terminal read、dedupe identity alignment、
  drain-first second-read anti-leak。
- README 触发规则正确：只有 `dayu/host/` 修改 + public API 新增时更新
  `dayu/host/README.md`；只有测试分层变化时更新 `tests/README.md`。

PASS。无缺失。

---

## Summary

| Category | Count |
|----------|-------|
| Blocking | 1 (F1) |
| Material | 4 (F2-F5) |
| Low | 3 (F6-F8) |
| Info | 1 (F9) |

**Handoff readiness**: After F1 resolution, plan is code-generation-ready.
Implementation agent can proceed through slices in order without redesign.
All architectural boundaries are explicit; stop conditions are testable;
public contract changes are fully specified with types, enums, validation
rules, and error semantics.

**Controller decision required on F2** (purge interaction scope for Phase 13).
