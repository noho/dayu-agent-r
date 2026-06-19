# Code Review

## Scope

- Mode: current changes
- Branch: wu-cm-12-conversation-memory-drift
- Base: main
- Output file: docs/reviews/code-review-wu-cm-12-s4-rereview-mimo-20260618.md
- Included scope: WU-CM-12 S4 focused re-review after MiMo finding fixes。只复核 2 个 accepted findings 是否闭环，以及是否引入新 blocker。
- Excluded scope: S4 其余行为（已在前轮 review 中通过）。
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

## Verification

### Finding 1: `accepted_attempt_number` 全局 proposal 序号计数 — PASS

**检查项**: Recovery accepted 后 `CONTEXT_COMPACTED` payload 的 `accepted_attempt_number` 是否按同一个 operation anchor 的全局 proposal 序号计数；cancellation-before-attempt 不应计入 completed proposal。

**直接证据**:

- 新增 `_completed_compaction_proposal_attempt_count`（`dispatch.py:4121-4141`）：
  ```python
  def _completed_compaction_proposal_attempt_count(
      result: CompactionOperationResult,
  ) -> int:
      rejected_completed = sum(
          1
          for rejected in result.rejected_attempts
          if rejected.failure_category
          is not CompactionFailureCategory.CANCELLATION_REQUESTED
      )
      if _compaction_result_accepted(result):
          return rejected_completed + 1
      return rejected_completed
  ```
  排除 `CANCELLATION_REQUESTED` 类型的 rejected attempt，只计已完成的真实 proposal call。

- Recovery loop 中累计 `completed_attempt_count`（`dispatch.py:1339-1374`）：
  - Normal compaction 后：`completed_attempt_count = _completed_compaction_proposal_attempt_count(result)`（行 1340）。
  - Recovery tier accepted 后：`accepted_attempt_number = completed_attempt_count + _accepted_attempt_number(tier_result)`（行 1356-1359）。
  - Recovery tier 失败后：`completed_attempt_count += _completed_compaction_proposal_attempt_count(tier_result)`（行 1372-1374）。

- `_append_compacted_event` 使用累计值（`dispatch.py:1469`）：`accepted_attempt_number=accepted_attempt_number`。

- 测试断言：
  - Tier 1 accepted（`test_proactive_compaction_recovery_tier1_uses_fallback_caps`）：`accepted_attempt_number == 2`（normal 1 completed + tier 1 accepted）。
  - Tier 2 accepted（`test_proactive_compaction_recovery_tier2_degrades_previous_view`）：`accepted_attempt_number == 3`（normal 1 + tier 1 failed + tier 2 accepted）。
  - Tier 3 accepted（`test_proactive_compaction_recovery_tier3_uses_delta_only`）：`accepted_attempt_number == 4`（normal 1 + tier 1 failed + tier 2 failed + tier 3 accepted）。

### Finding 2: stale 测试名称/覆盖语义 — PASS

**检查项**: Stale 测试名称是否与实际覆盖场景一致。

**直接证据**:

- 测试已重命名为 `test_proactive_compaction_recovery_stale_during_tier_proposal_discards`（行 4948）。
- Docstring 更新为 "tier proposal 执行期间 state stale 时不写 CONTEXT_COMPACTED"（行 4951）。
- 测试逻辑不变：`_RecoveryScenarioCompactor(accept_call=2, stale_after_call=2)` 在 recovery tier 1 执行期间触发 stale，验证 `CONTEXT_COMPACTED == 0`、`CONTEXT_COMPACTION_FAILED == 1`。

### 新 blocker 检查 — PASS

- 118 tests passed。
- pyright 0 errors, 0 warnings, 0 informations。
- git diff --check 无 whitespace 错误。
- Implementation artifact 已更新：residual risk 声明 "MiMo review fix：recovery accepted 复用同一个 operation anchor 时，`accepted_attempt_number` 改为 normal 已完成 proposal attempts + 已失败 recovery proposal attempts + 当前 accepted tier attempt 的全局序号；cancellation-before-attempt 不计入已完成 proposal call"。

## Open Questions

- 无。

## Residual Risk

- 无。2 个 accepted findings 均已闭环，无新 blocker。

## Conclusion

**PASS** — 2 个 accepted findings 全部闭环：
1. `accepted_attempt_number` 现在按全局 proposal 序号计数，cancellation-before-attempt 不计入。测试断言 tier 1=2、tier 2=3、tier 3=4。
2. Stale 测试已重命名为 `stale_during_tier_proposal_discards`，docstring 与实际场景一致。

118 tests passed / pyright 0 errors / git diff --check clean。无新 blocker。
