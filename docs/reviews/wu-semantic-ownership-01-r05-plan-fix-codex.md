# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Fix — AgentCodex

## 1. Gate 身份与范围

- work unit：`WU-SEMANTIC-OWNERSHIP-01` umbrella continuation；不是新 WU，也不重开历史 standalone WU。
- gate：`R05 remediation plan fix`。
- plan base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- authoritative adjudication：`docs/reviews/wu-semantic-ownership-01-r05-plan-review-controller-adjudication.md`。
- fixed target：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`。
- 本 artifact：`docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md`。
- current decision：`R05-PF-01` 至 `R05-PF-04` 均已在计划层关闭；下一入口是 AgentMiMo / AgentDS 对修订计划全文作双路 re-review。
- scope：本 gate 只修改上述 plan 与本 artifact；没有修改产品、测试、README、design、control 或既有 review artifact，没有进入 implementation、commit、push 或 PR。

## 2. 第一性原理与直接证据结论

修订动机成立，并且初始 plan 的严重性判断在两个位置被直接代码证据推翻：

1. `dayu/host/wait_adapter.py::poll_once(...)` 对已 claim 的 `CANCELLED` record 先调用 `_abandon_cancelled_wait(...)` 并 `continue`，`_handle_time_boundary(...)` 位于其后的非-CANCELLED poll path。因此 cancelled abandon observation 持续 timeout 时，不能声称既有 wait deadline 会经 `_handle_time_boundary(...)` 自动终止 retry。
2. `dayu/host/durable/state.py::mark_wait_record_poll_abandon_timeout(...)` 的唯一作用是把 generic observation timeout 写成 terminal `poll_abandoned_at`；当前调用图只有 `wait_adapter.py` 的 import、`_MarkWaitRecordAbandonTimeoutOperation` wrapper 与 timeout branch。该语义已被 Controller final decision 否定，移除 consumer 后没有合法 owner-level consumer，因而不能保留 dead/deprecated/compat helper。
3. `docs/host/design.md` 当前仍使用 `wait_abandon_timeout diagnostic/close marker`，会把 transient observation close 与 terminal `poll_abandoned_at` 混淆；权威裁决已经足以纠正该真源，不需要发明新 policy。
4. `WaitObservationRunner` token/generation fence、`release_wait_record_poll_claim(...)`、provider authoritative `WaitPollLost`、explicit applied/unsupported/noop lifecycle outcome 与 Engine accepted-awaiting handshake boundary 都有正确现有 owner；R05 不应在这些下游/相邻 owner 添加 fallback 或第二语义。

## 3. Finding 逐项关闭

### 3.1 R05-PF-01 — cancelled abandon timeout 长期 capped retry residual

| 维度 | Before | After |
|---|---|---|
| retry 事实 | 初始 plan 的 wait-deadline 行没有限定非-CANCELLED path，且 §15 未登记 cancelled abandon 长期 retry | §2.1、§4、§15 明确记录 `CANCELLED -> _abandon_cancelled_wait -> continue`，不进入 `_handle_time_boundary(...)`；provider 无 explicit terminal outcome 时可能长期按 capped backoff retry |
| 有限资源边界 | 只描述一般 backoff/fencing，未把资源影响作为 residual | 明确列出 claim CAS、`max_outstanding_adapter_calls` cap、finite single-call timeout、late-publication fencing、backoff cap；说明它们只限制单轮/并发资源，不是终止证据 |
| future owner | 仅有泛化的 future LOST evidence policy | 增加 future Host cancel/abandon durable evidence policy owner；Issue 175 只负责 Fins Docling 物理 containment，两者不混同 |
| 禁止扩域 | 未显式排除 max retry / abandon deadline | 明确禁止 R05 发明 max retry、abandon deadline、timeout terminal marker，也禁止把 `_handle_time_boundary(...)` 误称为现有 CANCELLED 收口路径 |

直接证据：`poll_once(...)` 的 CANCELLED 分支先于 `_handle_time_boundary(...)`；`release_wait_record_poll_claim(...)` 保持 `poll_abandoned_at` 不变且写 capped policy backoff，due/claim query 对 `CANCELLED` 只要求 `poll_abandoned_at IS NULL`。

结论：`已修复`。该 residual 已分类为 `requiring new issue or explicit user decision`，future owner 是显式 Host cancel/abandon durable evidence policy；当前 R05 不需要新产品裁决。

### 3.2 R05-PF-02 — public smoke timing 可执行性

| 维度 | Before | After |
|---|---|---|
| phase 驱动 | 只要求“给 CI 足够 margin”与“不靠偶然 sleep 顺序” | handshake accepted、operation start/finish、first observation entered、late result release、runner dropped count、second observation entered 全部分别由 event/condition/durable state polling 驱动 |
| 时间真源 | 没有统一 deadline contract | 只用 `time.monotonic()` 建立具名 overall deadline；每个 phase 从同一 deadline 计算 remaining budget |
| relative margins | 只有一个未量化严格不等式 | 具名 handshake/timeout/backoff/quantum/margin/deadline/CI-cap constants；断言三段带 margin 的严格不等式，且 `margin >= 5 * state-poll quantum` |
| 产品 policy ownership | 已要求从 packaged snapshot `dataclasses.replace`，但与 timing orchestration 混写 | 继续从 packaged 12-field snapshot 派生 test-effective policy，packaged 与 test timing 分开打印/断言，不写回 config、不建第二 backoff |
| bounded CI | 未规定统一上界 | overall deadline 必须小于等于具名 CI duration cap；所有等待在该上界内结束 |
| 失败证据 | 主要列最终 assertion，phase timeout 证据不足 | module-level phase helper 在失败时输出 phase ledger、monotonic elapsed、runner dropped count、Run/Wait claim/status/next-observe/diagnostic/`poll_abandoned_at`/terminal outbox 快照 |

直接证据：当前 smoke 已有 event 与 state-poll 基础，但计划原文只规定 timing 不等式和笼统 margin，不能约束实现者避免单次固定 sleep 推断。修订后的 §5.2 与 §11 给出完整 phase/state contract，同时不硬编码 reviewer 举例的产品数值。

结论：`已修复`。timing flake 风险归类为 `fixed in current slice`（计划要求由 R05-S2 实现并验证）。

### 3.3 R05-PF-03 — Host design `close marker` 真源纠错

| 维度 | Before | After |
|---|---|---|
| implementation docs allowlist | `docs/host/design.md` 被排除，初始 plan 只计划 README | `docs/host/design.md` 加入 R05-S1 implementation docs write allowlist |
| exact writeback | 没有计划修改 `diagnostic/close marker` | §5.1 规定精确改写为 poll-local transient `wait_abandon_timeout` diagnostic + release claim + Host policy backoff + keep `CANCELLED` + no terminal `poll_abandoned_at` |
| explicit terminal lifecycle | 容易被“删除 close marker”误伤 | 明确保留 provider explicit applied/unsupported/noop outcome 写 terminal abandon marker，且不调用 wait resolve |
| 新设计边界 | design 全文件是 stop 条件 | 只允许纠正该句；禁止新增 retry 上限、deadline、policy/schema，超出即 stop |

直接证据：`docs/host/design.md` 当前句子是 “cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker”；umbrella R05 manifest 与 Controller final decision 均要求 timeout non-terminal release/backoff，explicit lifecycle terminal outcome 保留。

结论：`已修复`。design ambiguity 归类为 `fixed in current slice`（R05-S1 owner transaction）。

### 3.4 R05-PF-04 — durable invalid timeout-only primitive 删除

| 维度 | Before | After |
|---|---|---|
| production allowlist | `dayu/host/durable/state.py` 被判为 read-only，允许 timeout primitive 成为 dead code | `dayu/host/durable/state.py` 加入 R05-S1 production allowlist，只删除 `mark_wait_record_poll_abandon_timeout(...)` 及仅服务 invalid semantic 的代码 |
| compatibility/dead surface | 初始 plan 允许 definition 保留、只要求 production zero caller | 明确要求零定义、零调用；禁止 deprecated wrapper/docstring、compat re-export 或 dead helper |
| legal terminal owner | source scan 容易把所有 abandon marker 混在一起 | 明确保留 `mark_wait_record_poll_abandoned(...)` 与 `poll_abandoned_at` schema，用于 explicit applied/unsupported/noop lifecycle terminal outcome |
| owner tests | 只有 adapter-level timeout tests | `tests/host/test_wait_record_state.py` 加入 test allowlist，新增 CANCELLED release/backoff 后同 row 到期可再次 claim 的 durable owner test，并保留 explicit terminal parameterized test |
| source/schema scan | 只要求 wrapper reachable path 为零、允许 store definition | strict guard 要求 `mark_wait_record_poll_abandon_timeout` / `_MarkWaitRecordAbandonTimeoutOperation` 在 `dayu tests` 中零匹配；schema file no-diff |
| per-file coverage | 只门禁 planned `wait_adapter.py` | actual changed production files 预期为 `durable/state.py`、`wait_adapter.py`，两者分别 `>=80%`；其它 production path 出现即 stop |

直接证据：当前全仓 symbol scan只命中 `state.py` 的一处 definition，以及 `wait_adapter.py` 的一处 import、wrapper definition、wrapper call；tests 没有该 function 的合法 caller。explicit terminal helper是独立的 `mark_wait_record_poll_abandoned(...)`，不得随 timeout-only primitive 删除。

结论：`已修复`。invalid dead semantic 归类为 `fixed in current slice`（R05-S1 storage owner boundary）。

## 4. Allowlist、tests、coverage 与 scans 变化

### 4.1 Allowlist delta

| 分类 | 新增路径 | 权限与预期 |
|---|---|---|
| R05-S1 production | `dayu/host/durable/state.py` | 只删除 invalid timeout-only primitive；预期 diff |
| R05-S1 implementation docs | `docs/host/design.md` | 只纠正 close-marker 句；预期 diff |
| R05-S1 tests | `tests/host/test_wait_record_state.py` | 新增 durable release/claimability owner test；预期 diff |

其余 allowlist 保持不变。`dayu/engine/agent.py`、`dayu/host/_wait_observation.py`、`dayu/host/waiting.py` 仍预期 no diff；两 slice 不变，R05-S1 仍是唯一 production semantic transaction，R05-S2 仍是 Engine no-diff regression + public smoke evidence。

### 4.2 Test / coverage delta

- test-first 红灯仍只属于两个 timeout behavior owner tests与一个 integration test；新增 durable owner preservation node 在 base 与 implementation 后都应为绿，不能伪造成红灯。
- Host focused/aggregate matrix加入 `tests/host/test_wait_record_state.py`。
- plan-fix probe 直接证明原四文件 coverage 集不足：`67 passed`，`durable/state.py=64%`、`wait_adapter.py=78%`。
- 扩大后的 green read-only Host coverage 命令为 `tests/host --ignore=tests/host/test_toolruntime_executor.py`，当前 probe 为 `1916 passed, 1 skipped, 5 deselected`、`durable/state.py=83%`、`wait_adapter.py=85%`；implementation 必须再次对两个 actual changed production files逐文件执行 `--fail-under=80`。
- `test_toolruntime_executor.py` 是无关 process-backed ToolRuntime 路径，不参与 R05 两个 changed owner 的 contract；排除只用于本 coverage session，不改变其它功能矩阵或 Issue 175 owner。

探索性非绿 coverage probe 单独登记，不作为 pass evidence：

```text
exact command:
  source .venv/bin/activate && python -m pytest -q tests/host
  --cov=dayu.host.durable.state --cov=dayu.host.wait_adapter --cov-branch
  --cov-report=term
  --cov-report=json:workspace/tmp/r05-plan-fix-full-host-coverage-probe.json
nodes:
  tests/host/test_toolruntime_executor.py::test_tool_runtime_process_backed_cancel_does_not_wait_for_natural_completion
  tests/host/test_toolruntime_executor.py::test_tool_runtime_default_factory_uses_declared_process_backed_execution
  tests/host/test_toolruntime_executor.py::test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy
  tests/host/test_toolruntime_executor.py::test_tool_runtime_process_backed_failed_envelope_returns_tool_failure
  tests/host/test_toolruntime_executor.py::test_tool_runtime_process_backed_failed_envelope_maps_hint
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope0-process_backed_tool_malformed_envelope]
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope1-process_backed_tool_unsupported_envelope]
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope2-process_backed_tool_unsupported_envelope]
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope3-process_backed_tool_unsupported_envelope]
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope4-process_backed_tool_unsupported_envelope]
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope5-process_backed_tool_unsupported_envelope]
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope6-process_backed_tool_malformed_envelope]
  tests/host/test_toolruntime_executor.py::test_process_backed_capsule_fail_closes_unsupported_envelopes[envelope7-process_backed_tool_malformed_envelope]
  tests/host/test_toolruntime_executor.py::test_tool_runtime_outer_task_cancel_closes_process_capsule
  tests/host/test_toolruntime_executor.py::test_tool_runtime_process_backed_cancel_kills_when_terminate_is_ignored
error type:
  _pickle.PicklingError
first stable frame:
  multiprocessing/reduction.py:60
normalized fingerprint:
  ForkingPickler cannot pickle multiprocessing.connection.rebuild_connection
  because it is not the same imported object
baseline SHA:
  5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
result:
  15 failed, 1962 passed, 2 skipped, 5 deselected；
  durable/state.py=83%，wait_adapter.py=87%
classification:
  exploratory diagnostic only；不是 R05 pass，也不作为 inherited exemption。
  §8 的 green owner coverage set 已替代它并达到 83% / 85%。
```

### 4.3 Scan delta

- strict zero-symbol guard：`mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation` 在 `dayu tests` 中零定义、零调用。
- schema no-diff：`dayu/host/durable/schema.py` 相对固定 base 必须无 diff。
- timeout scan继续人工区分 transient diagnostic 与 authoritative typed `ResolveWaitLostOutcome`，不能为了零命中删除正确 LOST 语义。
- backoff scan继续要求两个 timeout branches只调用既有 `_release_with_backoff(...)`；Engine source/diff scan继续证明 `agent.py` no diff。

## 5. Docs decision 与保留边界

- `docs/host/design.md`：R05-S1 必须作一处精确真源纠错，见 PF-03；本 plan-fix gate没有实际修改 design。
- `dayu/host/README.md`、`tests/README.md`：仍在 R05-S2 acceptance 按原触发规则更新。
- `dayu/engine/README.md`：当前 handshake boundary 已覆盖，`agent.py` no diff 时预期不改。
- 根 README、`dayu/README.md`：没有入口、用户工作流、分层或装配 contract 变化，不触发。
- R04 typed modes / 12-field policy、Engine `agent.py` no-diff、Issue 175、callback transport、unified authorization、R06+ scope 全部保留，不因四项 plan fix 扩域。

## 6. Residual risks 与 uncovered areas

| Residual | 分类 | Owner / destination | 当前边界 |
|---|---|---|---|
| cancelled abandon observation 可能长期 capped-backoff retry并间歇占用有限 capacity | `requiring new issue or explicit user decision` | future Host cancel/abandon durable evidence policy | R05 只保留 CAS/cap/finite timeout/fence/capped backoff，不发明终止证据 |
| Fins Docling 物理终止/containment | `tracked by existing issue` | Issue 175 | 不与 Host durable stop evidence 混同 |
| public smoke timing / CI flake | `fixed in current slice` | R05-S2 | event/condition/state-poll + monotonic deadline + relative margin + CI cap + phase evidence |
| design `close marker` ambiguity | `fixed in current slice` | R05-S1 | 精确 design writeback |
| timeout-only durable invalid primitive | `fixed in current slice` | R05-S1 | owner-boundary deletion + zero-symbol scan + coverage |
| callback / unified authorization / R06+ | `assigned to later work unit` | 既有 umbrella later WU / issue owner | 本 plan无变更 |

blocking open question：**无**。没有 unclassified residual risk。

## 7. Validation 与完成状态

已完成的只读 evidence / plan validation：

- 完整读取 AGENTS、control 当前 R05 状态、原 plan、MiMo/DS 两路初审、Controller adjudication、umbrella R05 manifest、Controller discussion Topic 5、Host/Engine design相关段落及当前 code/tests/smoke。
- 当前调用图 scan确认 timeout-only durable symbol只有一处 definition 与 wait-adapter 单一 import/wrapper/call；`CANCELLED` call order明确绕过 `_handle_time_boundary(...)`。
- coverage probes确认原 owner集不足且扩大后的 green read-only Host集可对两个 planned changed production files达到逐文件 `>=80%`。
- `git diff --check`：通过，无输出。
- 两个 untracked gate artifact 分别执行 `git diff --no-index --check /dev/null <path>`：均无 whitespace diagnostic；exit code `1` 仅表示 `/dev/null` 与新文件有内容差异。
- 本 gate exact write paths：
  - `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md`
- `git status --short` 中其余 `docs/host/issues-implementation-control.md`、Controller validation/adjudication 与 MiMo/DS review artifacts 均为 preflight 已存在状态，本 gate 未修改。

completion status：`PLAN_FIX_COMPLETE / READY_FOR_COMPLETE_DUAL_PLAN_REREVIEW`。

下一 gate：完整双路 plan re-review；不得只检查四项局部 diff，不得进入 implementation。
