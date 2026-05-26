# PR 68 post-draft reactive compaction budget hardening re-review (DS)

**Date**: 2026-05-23
**Reviewer**: AgentDS
**Scope**: 当前未提交 diff，聚焦 P12.5 reactive compaction budget hardening fix
**Gate**: P12.5 reactive compaction budget hardening fix
**Controller validation**: `pytest tests/host/test_compaction_operation.py tests/host/test_context_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_public_compact_smoke.py -q` => 177 passed; `pyright dayu tests` => 0 errors; `git diff --check` clean.

## Verdict: PASS

No blocking findings.

---

## Review items

### 1. `run_compaction_operation` 只在 proactive path 使用 compact 后 budget hard threshold reject

**Verdict**: PASS

**Evidence**:

- `dayu/host/compaction_operation.py:164` — hard threshold gate 现在由 `_requires_budget_acceptance(request)` 守卫：
  ```python
  if _requires_budget_acceptance(request) and (
      candidate.budget_after_compact
      >= request.budget_before_compact.hard_threshold_tokens
  ):
  ```
- `dayu/host/compaction_operation.py:208-219` — `_requires_budget_acceptance()` 仅在 `trigger_source is PROACTIVE` 时返回 `True`：
  ```python
  return request.trigger_source is ContextCompactionTriggerSource.PROACTIVE
  ```
- `dayu/host/compaction_operation.py:1-6` — 模块 docstring 明确声明："reactive path 不把估算值当作是否可重新 dispatch 的真源"。

**分析**: reactive path 的 `_HardThresholdOnceCompactor` 第一次 proposal 估算就会超过 hard threshold，但 budget gate 完全跳过，candidate 被接受。proactive path 的 hard threshold reject + retry 逻辑不受影响。

---

### 2. 默认 reactive compaction 上限改为 2，per-policy override 仍可设为 1

**Verdict**: PASS

**Evidence**:

- `dayu/host/context_policy.py:21` — `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN = 2`
- `dayu/host/context_policy.py:168` — `default_context_budget_policy()` 默认参数 `max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`
- `dayu/host/context_policy.py:210` — `static_context_budget_policy()` 同样默认 2
- `dayu/config/execution_profiles.json:22,90,158,226` — 所有 execution profile 的 `context_budget_policy.max_reactive_compactions_per_run` 均为 2
- `tests/host/test_engine_ingest_mapping.py:668-669` — `test_reactive_compact_count_limit_fails_closed_without_second_attempt` 传入 `max_reactive_compactions_per_run=1`，断言 fail closed

**分析**: 默认值 2 已写入模块级常量、两个 provider 默认参数、所有 execution profile JSON。per-policy override 通过 `ContextBudgetPolicy` 构造参数传入，由 `__post_init__` 校验为正整数（`_require_positive_int`, context_policy.py:103-106），可合法设为 1。

---

### 3. EngineEventIngestor reactive count gate：允许第二次 reactive request，上限耗尽后 fail closed

**Verdict**: PASS

**Evidence**:

- `dayu/host/engine_ingest.py:1129-1149` — count gate 逻辑：
  ```python
  compact_count = self._committed_reactive_compact_count(transaction, context.run)
  ...
  if compact_count >= policy.max_reactive_compactions_per_run:
      return self._fail_reactive_recovery_without_request(
          ...
          failure_reason="reactive_compact_limit_reached",
          message="Run already used its reactive compaction budget",
      )
  ```
- `dayu/host/engine_ingest.py:1322-1344` — `_committed_reactive_compact_count` 统计已提交 `CONTEXT_COMPACTION_REQUESTED` 事件中 `trigger_source=REACTIVE` 的数量，使用 `EventPayloadTextEqualsFilter` 精确过滤
- `tests/host/test_engine_ingest_mapping.py:687-722` — `test_reactive_compact_count_allows_second_operation`：已有 1 次 reactive request 时（count=1 < max=2），第二次 ingest 返回 ACCEPTED，创建第二个 Attempt，写入第二条 `CONTEXT_COMPACTION_REQUESTED`
- `tests/host/test_engine_ingest_mapping.py:652-683` — `test_reactive_compact_count_limit_fails_closed_without_second_attempt`：override=1 时，已有 1 次 request（count=1 >= max=1），断言 `RunStatus.FAILED`、`CONTEXT_COMPACTION_FAILED`、`failure_reason="reactive_compact_limit_reached"`，Attempt 数保持 1

**分析**: `>=` 语义正确——已有 compact_count 等于 max 时即耗尽。count 基于已提交 EventLog facts（`_committed_reactive_compact_count` 读 committed state），不受 inflight transaction 干扰。

---

### 4. Tests 覆盖

**Verdict**: PASS

| 测试 | 文件:行号 | 覆盖场景 |
|------|----------|---------|
| `test_run_compaction_operation_accepts_reactive_budget_estimate_overflow` | `tests/host/test_compaction_operation.py:229` | reactive path 用 `_HardThresholdOnceCompactor`（第一次 proposal 估算超 hard threshold），断言 `calls==1`、`accepted_candidate is not None`、`rejected_attempts==0`、`failure_reason is None` |
| `test_reactive_compact_count_allows_second_operation` | `tests/host/test_engine_ingest_mapping.py:687` | 默认 `max_reactive_compactions_per_run=2`，已有 1 次时第二次被允许：`ACCEPTED`、`attempt_count==2`、`RunStatus.RUNNING` |
| `test_reactive_compact_count_limit_fails_closed_without_second_attempt` | `tests/host/test_engine_ingest_mapping.py:652` | override `max_reactive_compactions_per_run=1`，已有 1 次时 fail closed：`RunStatus.FAILED`、`failure_reason="reactive_compact_limit_reached"` |
| `test_default_context_budget_policy_sets_compaction_attempt_budget` | `tests/host/test_context_policy.py:18` | 断言 `default_context_budget_policy` 的 `max_reactive_compactions_per_run == DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` |

**控制器报告 177 passed**，覆盖所有受影响的测试文件。

---

### 5. Docs / README / control 与裁决一致，未将 raw evidence aggregate prompt budget guard 列为待做方案

**Verdict**: PASS

**Evidence**:

- `dayu/host/README.md:258` — "reactive path 不把 compact 后估算值当作能否重新 dispatch 的真源；若真实 recovery dispatch 再次触发 Engine overflow，可在 `max_reactive_compactions_per_run` 范围内继续下一次 reactive compact，超过上限后 fail closed"
- `docs/host/design.md:2665-2666` — "proactive path 在 dispatch 前使用估算输入决定是否禁止 dispatch" / "reactive path 不把 compact 后估算值当作能否重新 dispatch 的真源"
- `docs/host/design.md:2666` — "每个 Run 的 proactive trigger 第一版最多启动一个 compaction operation；reactive trigger 每次 Engine overflow 最多启动一个 operation，但同一 Run 可在 `max_reactive_compactions_per_run` 上限内多次 reactive compact，默认上限为 2"
- `docs/host/design.md:2771` — "reactive path 中 compact 后若真实 recovery dispatch 再次触发 Engine overflow，可在 `max_reactive_compactions_per_run` 范围内追加下一次 reactive compact；超过上限后 append `CONTEXT_COMPACTION_FAILED` 并让 Run 进入 `FAILED`"
- `docs/host/implementation-control.md:230` — 当前 gate 结论写入追加裁决："不引入 raw evidence aggregate prompt budget guard，不让不准 token 估算阻断 reactive recovery"
- `docs/host/implementation-control.md:1714` — raw evidence aggregate prompt budget "后续裁决为不引入 prompt budget guard，改由 reactive recovery dispatch / Engine overflow 闭环和 max_reactive_compactions_per_run 上限治理"
- `docs/host/implementation-control.md:2091` — Phase 15 hardening 项从 "raw evidence prompt hardening" 更名为 "reactive overflow hardening"，内容更新为 "不引入 raw evidence aggregate prompt budget guard"

**残留引用**: 以下 review artifact 中的 "raw evidence aggregate prompt budget" 均为历史裁决记录（controller adjudication、prior DS/MiMo review），属于已归档的 review trail，不是待做方案：
- `docs/reviews/pr-68-postdraft-raw-evidence-controller-adjudication-20260523.md`
- `docs/reviews/pr-68-postdraft-raw-evidence-review-ds-20260523.md`
- `docs/reviews/pr-68-postdraft-compactor-scene-prompt-rereview-mimo-20260523.md`

这些是已有的 review artifact，不需要修改。implementation-control.md（当前控制文档真源）已正确反映裁决。

---

## No blocking findings

所有 5 项 review scope 均 PASS。变更与裁决一致，测试覆盖充分，文档无残留旧方案表述。
