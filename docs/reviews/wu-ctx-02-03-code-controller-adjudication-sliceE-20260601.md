# WU-CTX-02 + WU-CTX-03 Slice E code review controller adjudication

## 裁决结论

Slice E 通过 code review gate，结论为 **Accepted**。

本 Slice 是测试补强，不改变生产行为。实现目标是验证 reactive repeated overflow dispatch loop 在达到
`max_reactive_compactions_per_run` 上限后 fail closed，并确保该路径不会进入 `RUN_LOST`。该目标直接服务于
`docs/host/design.md` 中 Host 对 Agent/Runner 生命周期、取消、治理的强约束真源定位，也满足总控文档中
WU-CTX-02 + WU-CTX-03 对 compact failure / overflow recovery 边界的验证要求。

## 输入证据

- Implementation artifact:
  `docs/reviews/wu-ctx-02-03-implementation-sliceE-codex-20260601.md`
- Initial reviews:
  - `docs/reviews/wu-ctx-02-03-code-review-sliceE-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-review-sliceE-ds-20260601.md`
- Fix artifact:
  `docs/reviews/wu-ctx-02-03-fix-sliceE-codex-20260601.md`
- Focused re-reviews:
  - `docs/reviews/wu-ctx-02-03-code-rereview-sliceE-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-rereview-sliceE-ds-20260601.md`

## Findings 裁决

### DS F-1: 测试 helper 默认值复制生产常量

- Reviewer severity: Medium
- Controller decision: **Accepted and fixed**
- 修复方式：`tests/host/test_dispatch_scheduler.py` 从 `dayu.host.context_policy`
  导入 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`，并将 `_soft_compact_policy`
  的 `max_reactive_compactions_per_run` 默认值改为该常量。
- 裁决理由：该修复消除了测试 helper 和生产 `ContextBudgetPolicy` 默认值的双重真源，保持测试 oracle 与
  Host compact policy 公共契约同源，属于当前 phase 内最小且可维护的修复。
- Re-review: MiMo 与 DS 均确认 F-1 已正确修复，无测试语义漂移，无新增 blocking finding。

### MiMo F-01: `actual_attempt_count <= expected_attempt_count` 可精简

- Reviewer severity: Informational
- Controller decision: **Deferred / accepted as info**
- 裁决理由：accepted plan 明确要求同时校验 expected attempts equality 和 upper bound。保留上界断言能让测试直接表达
  dispatch loop 不超过 budget 的设计目标，当前不属于影响正确性的冗余。
- Owner: 无需当前 Slice 修复；若未来测试结构重写，可由触及该测试的后续改动一并评估。

### DS F-2 / F-3 / F-4

- Reviewer severity: Informational
- Controller decision: **Deferred / accepted as info**
- 裁决理由：这些项分别涉及 timeout 常量归类、既有 `del snapshot` 模式和既有 `_event_types_for_run(limit=200)` 辅助函数。
  它们不影响 Slice E 的 success signal，也不是本 Slice 引入的 correctness 风险。
- Owner: aggregate review 继续观察；后续若触及相关代码区域再做局部清理，不作为当前 gate 阻塞项。

## Gate 验证要求

Controller 需要在本裁决后运行：

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`

验证通过后，Slice E 可进入 accepted local commit，并在总控文档中关闭 `RR-CTX-PLAN-03`。
