# Conversation Memory smoke/log diagnostics plan

## Gate

- Gate: plan
- Work unit: Conversation Memory smoke/log diagnostics and smoke coverage boundary
- Baseline: 当前 clean commit；`git status --short` 为空。
- Design documents:
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/host/conversation-memory-smoke-compact-followup.md`
- Scope source: 用户确认只修 smoke/log diagnostics 和 smoke coverage boundary；第 2 个问题只实现分层边界，不实现完整 issue 80 eval，不新增 production memory 行为。

## Goal

补齐 `utils/smoke_host_public_conversation_memory_scenarios.py` 的 compact smoke 诊断输出，并在 README / tests README 中明确 daily smoke、diagnostic smoke、eval / regression suite 的边界。

完成后，`--suite memory-compact --pressure-mode auto --long-rounds 25 --log-level DEBUG` 如果再次观察到 `CONTEXT_COMPACTION_FAILED`，stdout 应能直接看到：

- 哪个 compact operation failed。
- request event sequence、operation id、trigger source、run id。
- rejected attempt count。
- 每类 rejected failure category 与 normalized diagnostic suffix 次数。
- `proposal_manifest_ref` present / missing 分类。
- failed event 的 `failure_reason`、`policy_decision`、`fallback_policy_decision`、`fallback_action`、`attempt_count`。
- 当 rejected attempt 缺失 `proposal_manifest_ref` 时输出 `failure_stage=prepare_or_material_projection` 与 `log_insufficient=offending_material_block_unavailable`。
- `SMOKE TOOL_CALLS_BY_KEY`、compact audit 和 `SMOKE FAIL` 各自独立换行。

## Motivation and First-Principles Judgment

日志不足问题成立。当前 clean baseline 中已经有 compact audit 相关数据类和 stdout 前缀常量，但 `run_smoke()` 调用的 `_compact_audit_report()` 与 `_print_compact_audit_report()` 缺失。直接证据：

- `utils/smoke_host_public_conversation_memory_scenarios.py` 已定义 `CompactRejectedAttemptAudit`、`CompactFailedOperationAudit`、`CompactOperationAudit`、`CompactAuditReport`。
- `run_smoke()` 在 `utils/smoke_host_public_conversation_memory_scenarios.py:2095` 调用 `_compact_audit_report()`，在 `:2097` 调用 `_print_compact_audit_report()`。
- `source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` 当前报告这两个函数未定义。

smoke 覆盖增强应限定在 smoke/eval 边界。`docs/host/design.md` 明确：

- tier 4/5 dispatch fallback 不提交 `CONTEXT_COMPACTED`，不 materialize memory snapshot，必须有 `CONTEXT_COMPACTION_FAILED` 或等价 diagnostic 痕迹。
- retry budget 耗尽后只能写最终 `CONTEXT_COMPACTION_FAILED`。
- `current_input_anchor` readable but not citable。

因此本轮只增强 smoke 观察与文档边界，不修改 production compact parser、prompt、accept barrier、memory projection 或 Host / Engine compact 行为。

第 2 个问题范围较大，本轮只落地分层边界：

- Daily smoke: 默认、轻量、稳定，使用 `memory-core`。
- Diagnostic smoke: `memory-compact` 作为压力 / 诊断入口，输出 operation timeline、reject histogram、fallback details。
- Eval / regression suite: issue 80 的完整 memory correctness 目标，包括 memory snapshot、prompt assembly、conflict / update、abstention / refusal、tool reuse efficiency 等，当前只规划边界，不实现。

## Non-goals

本 work unit 不做：

- 不修改 `dayu/host/compact_material.py`。
- 不修改 compactor prompt。
- 不修改 accept barrier。
- 不修改 memory projection 语义。
- 不修改 production Host / Engine compact 行为。
- 不新增 reactive compact、fallback tier 1-5 的 production 行为。
- 不读取 compact artifact 正文、memory 表或 private Host implementation 来替代 public / EventLog 诊断。
- 不因为 `fallback_action=dispatch` 放宽验收；`memory-compact` 中任何 `CONTEXT_COMPACTION_FAILED` 仍是 hard fail。
- 不实现完整 issue 80 eval / regression suite。

## Affected Files

Allowed implementation files:

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `README.md`
- `tests/README.md`
- `docs/host/conversation-memory-smoke-compact-followup.md` 仅可补充实施状态或澄清，不改设计语义。

Gateflow / review artifact files:

- `docs/reviews/wu-cm-conversation-memory-smoke-log-diagnostics-plan-20260619-115520.md`
- 后续 plan review / code review / implementation / fix / deepreview artifacts 位于 `docs/reviews/`。

Forbidden implementation files:

- `dayu/host/compact_material.py`
- `dayu/config/prompts/` 下 compactor prompt
- Host accept barrier 相关 production 文件
- memory projection 相关 production 文件
- production Host / Engine compact 行为文件

## Public Contract / Schema / State Changes

- 无 production public contract 变更。
- 无 schema 变更。
- 无 Host / Engine state-machine 变更。
- CLI 参数保持现状：`--suite memory-core` 默认轻量；`--suite memory-compact --pressure-mode auto` 作为 diagnostic / pressure entry。
- stdout 增加稳定 `SMOKE COMPACT_*` 诊断行；这是 utils smoke 的人工诊断输出，不是 Host public API。

## Implementation Decisions

1. 复用已有 dataclass，不新增抽象层。
   - `CompactRejectedAttemptAudit`
   - `CompactFailedOperationAudit`
   - `CompactOperationAudit`
   - `CompactAuditReport`

2. 新增或补齐模块级私有 helper，只处理 EventLog row payload 的结构化字段。
   - 禁止 nested function。
   - 禁止 `Any` / `object` 签名。
   - 使用 `JsonValue`、`Mapping[str, JsonValue]`、`tuple[str, ...]`。
   - payload 解析集中走一个 typed helper，避免重复 `json.loads` 与非 object 检查。
   - typed payload helper 的字段缺失和类型不匹配都返回 `None` 或空 tuple；只有 `payload_json` 不是 JSON object 时沿用现有 fail-fast 语义抛出 `ValueError`。

3. compact operation 归因规则。
   - request row 的 operation id 采用 request `event_id`。
   - accepted / rejected / failed row 优先读取 payload `operation_id`。
   - 若 operation id 缺失，使用 `_COMPACT_OPERATION_MISSING_ID`，但不把它误判为业务事实。
   - trigger source 优先读取 row payload `trigger_source`，否则通过 request operation id 回查 request row。
   - run id 使用 `EventLogRow.run_id`；缺失时打印 `<none>`。

4. rejected attempt 诊断规则。
   - `failure_category` 缺失时用 `_COMPACT_NONE_VALUE`。
   - diagnostic suffix 从 `diagnostic_refs` 提取；算法为 `diagnostic_ref.split(_DIAGNOSTIC_REF_SEPARATOR)` 后，若分段数量大于 `_DIAGNOSTIC_REF_SUFFIX_OFFSET`，取 offset 后剩余分段并用 separator 重新拼接，否则返回完整 ref。示例：`compact:operation:attempt:ValueError:previous reference continuity text is invalid` 归一为 `previous reference continuity text is invalid`；`ValueError:previous reference continuity text is invalid` 分段不足，保留完整 ref。空 diagnostic refs 不进入 histogram。
   - `proposal_manifest_ref` 是非空字符串时 classified 为 present，否则 missing。
   - `proposal_manifest_ref` missing 时：
     - `failure_stage=prepare_or_material_projection`
     - `log_insufficient=offending_material_block_unavailable`
   - present 时：
     - `failure_stage=proposal_or_quality`
     - `log_insufficient=none`
   - 该 stage 映射依赖当前 Host 记录 proposal manifest 的事实：manifest 在 proposal run input 成功准备后才可能出现。若后续 Host 改变 manifest 写入时机，diagnostic smoke 需要随生产 payload 语义重新校准。

5. failed event 诊断规则。
   - 输出 `failure_reason`、`policy_decision`、`fallback_policy_decision`、`fallback_action`、`fallback_tier`、`attempt_count`、`retry_repair_budget_exhausted`、`budget_after_attempted_compact`。
   - 不把 `fallback_action=dispatch` 当 compact accepted。
   - hard fail 仍由 `_assert_compact_acceptance()` 基于 summary 中 failed total 判断。

6. stdout 换行规则。
   - 现有 `run_smoke()` 中关键 summary 行使用 `print(..., flush=True)`：最终 `SMOKE TOOL_CALLS_BY_KEY`、compact artifact summary、compact audit summary、operation / histogram / detail 行、compact acceptance、`SMOKE PASS`、workspace kept。
   - `main()` 的 `SMOKE FAIL` 使用 `print(..., file=sys.stderr, flush=True)`，确保异常路径不会和最后一个 stdout summary 粘连。
   - `main()` 在捕获异常前后不拼接 stdout / stderr 文本。
   - 不通过 partial write 输出 `SMOKE TOOL_CALLS_BY_KEY`，避免和 `SMOKE FAIL` 粘连。

7. README 边界。
   - 根 README 的 conversation memory smoke 段补充 daily / diagnostic / eval 分层。
   - `tests/README.md` 对 assembly helper 测试增加 compact timeline / histogram / manifest missing / failure-stage 断言说明。
   - 不把 issue 80 全量目标写成已实现。

## Data Flow

`run_smoke()` 结束 Host handle 后：

1. `_print_compact_summary(assembly.options)` 打印 artifact root / file count。
2. `_compact_audit_report(assembly.options, session_id=session_id)`：
   - 通过 `_durable_options_from_open_host_options()` 打开本次 smoke durable store。
   - 通过 `_read_compact_event_rows()` 读取指定 session 的 canonical compact event rows。
   - 调用 `_compact_audit_report_from_rows(rows)` 生成完整 report；该纯函数内部复用 `_compact_audit_summary_from_rows(rows)` 和 `_compact_request_trigger_sources(rows)`。
   - 构造 request index、operation buckets、global histograms。
   - 返回 `CompactAuditReport`。
3. `_print_compact_audit_summary(compact_audit.summary)` 打印 aggregate summary。
4. `_print_compact_audit_report(compact_audit, debug_smoke_output=args.debug_smoke_output)`：
   - 始终打印 per-operation timeline 与 global histograms。
   - `debug_smoke_output=True` 时可额外打印 bounded rejected detail，避免 INFO 默认过噪。
5. `_assert_compact_acceptance()` 保持现有 hard fail 语义。

## Slices

### Slice 1: Smoke log diagnostics

Objective:

补齐 compact audit report 构造和打印，修复当前 pyright 未定义函数，并增强 long25 failure 定位信号。

Allowed files:

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `docs/reviews/` 对应 implementation / review artifacts

Exact allowed changes:

- 新增 `_compact_audit_report(options: OpenHostOptions, *, session_id: str) -> CompactAuditReport`。
- 新增 `_compact_audit_report_from_rows(rows: tuple[EventLogRow, ...]) -> CompactAuditReport`，供单元测试不打开真实 DB。
- `_compact_audit_report()` 只能负责 durable store 打开与 row 读取，必须直接返回 `_compact_audit_report_from_rows(rows)`，禁止复制 report 构造逻辑。
- 现有 `_compact_audit_summary()` 若仍保留，必须改为 `_compact_audit_report(...).summary` 的薄包装，或保持不在 smoke flow 中调用；不得新增第二套 durable read / summary 逻辑。
- 新增 `_print_compact_audit_report(report: CompactAuditReport, *, debug_smoke_output: bool) -> None`。
- 新增 typed payload helpers：
  - `_compact_row_payload(row: EventLogRow) -> Mapping[str, JsonValue]`
  - `_compact_payload_str(payload: Mapping[str, JsonValue], field_name: str) -> str | None`
  - `_compact_payload_int(payload: Mapping[str, JsonValue], field_name: str) -> int | None`
  - `_compact_payload_bool(payload: Mapping[str, JsonValue], field_name: str) -> bool | None`
  - `_compact_payload_str_tuple(payload: Mapping[str, JsonValue], field_name: str) -> tuple[str, ...]`
- 新增 formatting helpers：
  - `_compact_normalized_diagnostic_suffix(diagnostic_ref: str) -> str`
  - `_compact_manifest_presence(proposal_manifest_ref: str | None) -> str`
  - `_compact_failure_stage(proposal_manifest_ref: str | None) -> str`
  - `_compact_log_insufficient(proposal_manifest_ref: str | None) -> str`
  - `_compact_optional_text(value: str | int | bool | None) -> str`
- 修改 `_compact_row_trigger_source()` 与 `_compact_row_operation_id()` 复用 `_compact_row_payload()`。
- 将 `main()` 的 failure print 改为独立 flush 输出。

Tests:

- 新增或更新 assembly helper 测试，构造 request / rejected / failed / compacted rows。
- 断言 `_compact_audit_report_from_rows()`：
  - operation timeline 包含 request event sequence、run id、trigger source、rejected / failed / compacted count。
  - global failure histogram 正确。
  - global diagnostic suffix histogram 正确。
  - proposal manifest present / missing histogram 正确。
  - missing manifest rejected attempt 的 `failure_stage` 与 `log_insufficient` 正确。
  - failed event 保留 `fallback_action=dispatch`，但 summary failed count 仍触发 `_assert_compact_acceptance()` hard fail。
- 边界 / 错误路径测试：
  - empty rows 返回 empty operations 和 empty histograms。
  - payload JSON 非 object 仍抛出 `ValueError`，与现有 `_compact_row_trigger_source()` 行为一致。
  - `diagnostic_refs` 为空时不产生 histogram 项。
  - typed payload helper 对字段缺失或类型不匹配返回 `None` / empty tuple，不抛出。
  - operation id 缺失的 rejected / failed row 使用 `_COMPACT_OPERATION_MISSING_ID` 归组并可打印。
- 使用 `capsys` 断言 `_print_compact_audit_report()` 输出独立 `SMOKE COMPACT_OPERATION`、`SMOKE COMPACT_REJECT_HISTOGRAM`、`SMOKE COMPACT_REJECT_DETAIL` 行。
- 使用 `capsys` 或格式化 helper 断言 stdout line 均以独立 `SMOKE` 前缀开始；异常路径至少通过 `main()` 的 `SMOKE FAIL` flush 单元断言覆盖。

Stop condition:

- 如果只能通过读取 production compact artifact 正文、memory 表或修改 production compact 行为才能输出上述信息，停止并报告。
- 如果发现 EventLog payload 不包含 request seq / run id 等必要信息且无法从 `EventLogRow` 获取，停止并在 plan/fix gate 重新裁决输出降级。

Completion signal:

- 当前 pyright 的 `_compact_audit_report` / `_print_compact_audit_report` 未定义错误消失。
- 受影响 pytest 覆盖新增 report / print helper。

### Slice 2: Smoke coverage boundary docs

Objective:

明确 daily smoke / diagnostic smoke / eval / regression suite 的边界，不把 issue 80 全量目标塞进 utils smoke。

Allowed files:

- `README.md`
- `tests/README.md`
- `docs/host/conversation-memory-smoke-compact-followup.md` 仅补充实施状态或澄清，不改设计语义。
- `docs/reviews/` 对应 implementation / review artifacts

Exact allowed changes:

- 阅读目标 README 内的 `Agent更新约束【必须遵守】` 或等价章节；若不存在，按 AGENTS.md 触发规则判断是否更新。
- 根 README conversation memory smoke 段补充：
  - `memory-core` 是 daily smoke，默认轻量，不要求 compact。
  - `memory-compact --pressure-mode auto` 是 diagnostic smoke / pressure entry，输出 compact timeline / histogram / fallback details。
  - 当前 smoke 不覆盖 memory correctness 全量验证；不要在 README 提及内部 issue 编号或把未来 eval 写成已实现能力。
  - `CONTEXT_COMPACTION_FAILED` 在 diagnostic smoke 中仍为 hard fail，即使 fallback dispatch 成功。
- `tests/README.md` 补充测试边界：
  - 当前 assembly helper 测试覆盖 smoke report 构造、histogram、manifest missing stage、hard fail 语义。
  - 不覆盖真实 LLM long25，也不证明 production compact failure 已修复。
- `docs/host/conversation-memory-smoke-compact-followup.md` 可追加“本 work unit 实施状态”小节：
  - 前两个问题已被拆成 smoke/log diagnostics 与 smoke coverage boundary。
  - 第 3 个 production memory compact failure 未修复，后续单独处理。

Tests:

- 无 README 专用测试。
- 用 `rg` 检查 README 不把 issue 80 eval 写成已实现。

Stop condition:

- 如果 README 目标读者约束禁止记录这类 smoke 边界，停止并报告。
- 如果需要修改 production docs 的设计语义才能解释本轮行为，停止并报告。

Completion signal:

- README / tests README 明确分层边界。
- 文档没有声称 production memory compact failure 已修复。

### Slice 3: Validation and artifacts

Objective:

完成验证、记录 artifacts，并准备后续 review gate。

Allowed files:

- `docs/reviews/` validation / implementation artifact。
- 前两 slice 已允许文件中的必要小修。

Validation commands:

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
```

Optional long smoke:

```bash
source .venv/bin/activate && python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact --pressure-mode auto --long-rounds 25 --log-level DEBUG
```

Long smoke may call a real LLM and be costly / flaky. If not run, closeout must state that unit / assembly tests covered the no-real-LLM diagnostics path, while production long25 remains unverified in this work unit.

Stop condition:

- pytest or pyright failure that cannot be fixed within allowed files.
- Any evidence that production memory must change to satisfy this work unit.

## Review Routing

Plan review:

- AgentMiMo: read-only `/planreview` review of this artifact.
- AgentDS: read-only `/planreview` review of this artifact.
- Both reviewers must not modify files.
- Controller adjudicates findings into accepted / rejected-with-reason / deferred-with-owner / needs-more-evidence.

Code review:

- After implementation, AgentMiMo and AgentDS may perform read-only `/deepreview` or code review gate per gateflow instruction.
- Reviewers must not modify files.

## Docs Decision

README update is required because the user-visible smoke command behavior and diagnostic boundary are documented in root README.

`tests/README.md` update is required because tests under `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` will be updated.

`docs/host/conversation-memory-smoke-compact-followup.md` update is optional and limited to implementation status / clarification. It must not alter design truth or production memory diagnosis semantics.

## Why This Is Not Over-designed

The plan reuses existing dataclasses and EventLog rows already read by the smoke. It does not introduce new production contracts, new schema, new storage, new protocol, new public Host events, or new eval framework. The only new helpers are module-private formatting / extraction functions needed to make current incomplete smoke diagnostics type-check and become testable.

The plan explicitly leaves issue 80 full eval to a later eval / regression suite because implementing memory snapshot / prompt assembly / conflict / abstention coverage inside this utils smoke would couple daily smoke, diagnostic pressure, and correctness eval into one slow and brittle script.

## Risks and Tracking

- Production memory compact failure from long25 remains assigned to later work unit. This plan only improves observability.
- Operation-level diagnostics are limited to fields present in EventLog rows and safe payload summary fields. Offending material block text remains unavailable when `proposal_manifest_ref` is missing; this is intentionally surfaced as `log_insufficient=offending_material_block_unavailable`.
- Real LLM long25 may remain costly or flaky; no-real-LLM unit / assembly tests are the primary validation for this work unit.

## Completion Report Format

Final closeout must include:

- 改了什么。
- 验证了什么。
- README / tests README 是否更新。
- review finding 状态。
- 哪些风险仍属于第 3 个 production memory compact failure，未在本 work unit 修复。
- 如果 long25 再失败，新日志应该能看到哪些定位信号。
