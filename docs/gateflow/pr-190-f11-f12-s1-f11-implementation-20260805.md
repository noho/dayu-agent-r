# PR 190 F11/F12 S1 F11 implementation

## Gate metadata

- Gate：`code review -> fix`
- Work unit：PR 190 F11 public Host Tool Trace compactor response identity
- Approved slice：`S1 — F11 Host Tool Trace typed resolver 与 analysis projection`
- Accepted plan：`docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`
- Accepted S0 checkpoint：`docs/gateflow/pr-190-f11-f12-s0-accepted-checkpoint-20260805.md`
- Implementation base：`19a6d6257504876e01da3067bbc4cf33ae99525d`
- Branch：`codex/interactive-oracle`
- Completion status：`fix-complete`
- Commit status：未 stage、未 commit、未 push
- Review status：两路 code review 与 controller adjudication 已完成；唯一 accepted
  finding DS-03 已修复，re-review pending
- Review adjudication：
  `docs/gateflow/pr-190-f11-f12-s1-f11-code-review-adjudication-20260805.md`
- Artifact path：`docs/gateflow/pr-190-f11-f12-s1-f11-implementation-20260805.md`
- Next Gateflow entry point：`re-review`

## Preflight and first-principles judgment

- 实现前已核对 branch、clean worktree 与 full SHA；HEAD 和 S0 accepted base 均为
  `19a6d6257504876e01da3067bbc4cf33ae99525d`。
- 动机成立。canonical compact terminal 已持久化 actual
  `SuccessfulRunnerResponseIdentity`，runner-call manifest 也已拥有 parent Host Run、
  operation、attempt 与 compactor Engine run identity；缺口只在 Tool Trace resolver
  没有把两者严格关联为 public typed projection。
- 语义 owner 固定为：`context_events.py` 拥有 canonical terminal 与 successful
  response strict parsing；`durable/tool_trace.py` 拥有跨 manifest/terminal 的只读解析与
  exact binding；analysis input/rules/contracts/renderers 只消费 typed projection。
- 未在 Service、CLI、renderer、test fixture 或 provider adapter 中增加 fallback、loose
  parsing、provider/model 推断、默认 identity 或兼容分支。

## Implemented call and data flow

```text
RUNNER_CALL_INPUT_ASSEMBLED hot signal
-> descriptor ref/digest resolution
-> shared RunnerCallInputManifest strict parser
-> typed compactor manifest identity
-> parent Host Run canonical terminal keyset exhaustion
-> exact manifest/operation/attempt/Engine-run binding
-> ResolvedCompactorResponseIdentity | None
-> ToolTraceJoinedRecord
-> ToolTraceAnalysisReport schema v2
-> JSON / Markdown safe projection
```

### Canonical event owner

- 将 private successful-response parser 收口为公开
  `parse_successful_runner_response_identity(...)`；builder validator、terminal parser 与
  Tool Trace 共用相同 exact-key typed parser。
- 增加 compacted 与 attempt-rejected canonical terminal typed binding parser。accepted
  terminal 必须有 successful identity；post-success rejection 保留 actual identity；
  no-success rejection 保留显式 `None`。
- secret-like extra field 由 canonical exact-field owner 直接拒绝，不把 header、
  credential、authorization 或 raw payload 带入 read model。

### Durable Tool Trace resolver

- `RunnerCallResolvedProjection` 增加 nullable `compactor_response_identity`；ordinary
  runner call 固定为 `None`。
- 增加公开封闭 enum `CompactorResponseDisposition` 与公开 typed
  `ResolvedCompactorResponseIdentity`；accepted disposition 在 contract 层要求 actual
  successful identity。
- resolver 在调用方持有的同一 read transaction 中重新校验 canonical hot event、
  signal、manifest descriptor 与 typed manifest graph，避免只信派生 hot row。
- terminal scan 只读取 parent Host Run 的 canonical `CONTEXT_COMPACTED` 与
  `CONTEXT_COMPACTION_ATTEMPT_REJECTED`，使用固定正数 page size 与严格单调
  `after_event_sequence`；每页有界、无任意总页数 cap，直到 empty/short page 才完成
  exhaustion。
- 只接受 proposal manifest ref/digest、operation、attempt 全部 exact match 的唯一
  terminal，并要求 actual Runner request `run_id` 等于 manifest 中的 compactor Engine
  run id。wrong ref/digest/operation/attempt/Engine run、duplicate、malformed payload、
  row/cursor 不推进全部抛 durable error，不能降级为 missing。
- 只有完整 exhaustion 后无 matching terminal 且未发现冲突，才返回 `None`。

### Analysis schema v2 and safe rendering

- `ToolTraceAnalysisReport` fresh schema 固定为 version 2；删除 version 1 构造/校验
  接受路径，并新增稳定排序、唯一的 `compactor_responses`。
- `ToolTraceCompactorResponseSummary` 只投影 terminal binding、actual provider/model、
  完整 Runner request identity 与 provider request id availability/value；accepted summary
  不能携带 null successful identity，no-success rejection 的全部 response identity 字段
  必须整体为 null。
- analysis input 仅在 resolver 完整 exhaustion 返回 `None` 后附加稳定 limitation
  `compactor-response-terminal-not-observed`；resolver corruption 继续 fail closed，不产生
  scan-cap limitation。
- analysis rules 只从 `ToolTraceJoinedRecord.runner_call_projection` 构造 summaries；JSON
  与 Markdown 只消费同一个 structured report，不回读 raw payload，也不重算 identity。

## Changed files

### Production

- `dayu/host/context_events.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/tool_trace_analysis_input.py`
- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`

`dayu/host/__init__.py` 未修改：新增 durable resolver 类型已由 owner 模块的显式
`__all__` 公开，包根继续保持既有 Service-facing boundary，不新增兼容 re-export 或内部
resolution error。所有 production 变更均在 S1 allowed files 内。

### Tests

- `tests/host/test_context_compact_events.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_tool_trace_analysis_input.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`

owner matrix 覆盖 accepted、post-success rejected、no-success rejected、ordinary call、
empty/short exhaustion、一个及多个 full pages、严格 cursor 推进、non-advancing reader、
wrong ref/digest/operation/attempt/Engine run、duplicate/malformed、schema v2/v1 rejection、
JSON/Markdown 同源与 secret whitelist。

### Docs

- `dayu/host/README.md`
  - 更新当前已落地的 canonical terminal resolver、无总页数 cap 的 keyset exhaustion、
    missing limitation、analysis schema v2 与安全白名单。
- `docs/gateflow/pr-190-f11-f12-s1-f11-implementation-20260805.md`
  - 记录本 slice 的 implementation evidence、validation、docs decision 与 residual risks。

## Code review fix record

- Review inputs：
  - `docs/reviews/pr-190-f11-f12-s1-f11-code-review-mimo-20260805.md`
  - `docs/reviews/pr-190-f11-f12-s1-f11-code-review-ds-20260805.md`
  - `docs/gateflow/pr-190-f11-f12-s1-f11-code-review-adjudication-20260805.md`
- `DS-03`：`accepted-low-documentation`，最终状态 `已修复`。
  - 在 `dayu/host/durable/tool_trace.py` 的
    `_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE = 128` owner 处增加简短中文说明。
  - 说明明确：128 只界定单次 SQLite keyset read I/O；correctness 由完整
    exhaustion 与 cursor invariant 拥有；该私有值不得开放为 public config。
  - 数值、接口、查询行为、exhaustion/cursor 逻辑与 public surface 均未改变。
- MiMo `M-001`、`M-002`、`M-003`，DS `DS-01`、`DS-02` 及 DS open questions
  均按 controller adjudication 保持 rejected/no-change；没有误改 validator/parser、
  cursor guard、failure taxonomy、Service/CLI 或 compatibility path。
- 本 fix 只修改上述 owner 注释与本 implementation artifact；未修改 tests/README，
  因为测试职责和运行方式没有变化。

## Validation

全部 Python 命令均在 `source .venv/bin/activate` 后运行。

### Focused tests

```text
pytest -q \
  tests/host/test_context_compact_events.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py
```

implementation 最终结果：`172 passed in 0.96s`。

fix 后以相同 5 个 focused owner test files 重跑：`172 passed in 0.94s`。

### Modified-file branch coverage

coverage 在上述 5 个 S1 files 基础上加入既有
`tests/host/test_context_budget_evaluated.py`，因为 `context_events.py` 是 compact 与
budget 共享 canonical owner；未修改该额外测试文件。

结果：`185 passed in 1.32s`，各修改生产模块：

| Module | Coverage |
|---|---:|
| `dayu/host/context_events.py` | 83% |
| `dayu/host/durable/tool_trace.py` | 82% |
| `dayu/host/tool_trace_analysis.py` | 100% |
| `dayu/host/tool_trace_analysis_contracts.py` | 84% |
| `dayu/host/tool_trace_analysis_input.py` | 83% |
| `dayu/host/tool_trace_analysis_rules.py` | 92% |

总计 branch coverage：86%；所有修改生产模块均达到 `>=80%`。

### Type and repository checks

- affected production/tests pyright：`0 errors, 0 warnings, 0 informations`。
- affected production/tests Ruff：`All checks passed!`。
- fix 后 affected `dayu/host/durable/tool_trace.py` pyright：
  `0 errors, 0 warnings, 0 informations`。
- fix 后 affected Ruff：`All checks passed!`。
- `tests/host/test_package_exports.py` regression：`15 passed`；Host package root
  Service-facing whitelist 未发生漂移。
- `git diff --check`：通过，无 whitespace error。
- 最终 base recheck：HEAD 仍为
  `19a6d6257504876e01da3067bbc4cf33ae99525d`。

## Docs decision

- `dayu/host/README.md`：命中 Host stable public resolver/report contract，已按 README 的
  developer-reader 边界更新，只写已落地行为。
- `tests/README.md`：新增断言仍属于现有 Host owner tests，不改变测试分层、运行方式、
  fixture 责任或维护规则，因此 `no-change`。
- 根 `README.md` 与 `dayu/README.md`：没有用户可见命令、工作流、输出位置或分层装配
  变化，因此 `no-change`。

## Residual risks and uncovered areas

- `fixed in current slice`：F11 public typed resolver、canonical exact binding、nullable
  terminal missing、analysis schema v2、safe JSON/Markdown projection 与 owner test matrix
  已闭合。
- `covered by later approved slice`：F12 generic structured output、compact v3、真实 provider
  conformance evidence 与 registry lifecycle 分别仍由 accepted plan 的 S2-S5 拥有；S1
  没有提前实现或模拟这些语义。
- `assigned to later work unit`：schema v2 是 accepted plan 明确要求的 fresh breaking
  contract；仓外自建 Tool Trace report consumer 如存在，需要由其 owner 按 v2 显式升级，
  本 slice 不提供 v1 reader/adapter。
- `fixed in current slice`：controller 唯一 accepted finding DS-03 已在 page-size owner
  处用注释闭合；所有 rejected findings 保持 no-change。
- `uncovered by current fix gate`：两路 independent re-review 尚未执行；该风险由下一
  `re-review` gate 闭合，不能由 fix 自评替代。

没有 blocking open question，也没有 unclassified residual risk。

## Completion decision

`fix-complete`

S1 intended implementation、owner tests、coverage、affected pyright、README 与 durable
artifact 已完成；唯一 accepted finding DS-03 已修复且 rejected findings 未被误改。按用户
指令未 stage、commit 或 push，也未越过 fix gate；当前停止在两路 re-review pending，
下一入口为 `re-review`。
