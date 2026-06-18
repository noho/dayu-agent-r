# Code Review — WU-CM-12 S4 MiMo Fix Re-Review

## Scope

- Mode: current changes (focused re-review after MiMo review fixes)
- Branch: `wu-cm-12-conversation-memory-drift`
- Base: `main`
- Output file: `docs/reviews/code-review-wu-cm-12-s4-rereview-ds-20260618.md`
- Included scope: `dayu/host/dispatch.py`、`tests/host/test_dispatch_scheduler.py` 的未提交 diff，以及 `docs/reviews/wu-cm-12-s4-implementation-codex-20260618.md` 的 MiMo fix 更新。
- Excluded scope: `dayu/host/compact_material.py`、`tests/host/test_compact_material.py`（已在 DS review 中通过，本次 MiMo fix 未修改）。
- Source artifact: `docs/reviews/code-review-wu-cm-12-s4-ds-20260618-164407.md`（DS review，PASS，2 Open Questions）
- Parallel review coverage: 无。单一 reviewer 逐项复核。

## Findings

未发现实质性问题。两个 MiMo finding 均已关闭，无新增 blocker。

### MiMo Finding 1 复核：`accepted_attempt_number` 全局 proposal 序号

**结论: CLOSED。** 修复正确。

**修复内容**：

1. **新增 `_completed_compaction_proposal_attempt_count`**（`dispatch.py:4121-4141`）：

   ```python
   def _completed_compaction_proposal_attempt_count(result):
       rejected_completed = sum(
           1 for rejected in result.rejected_attempts
           if rejected.failure_category
           is not CompactionFailureCategory.CANCELLATION_REQUESTED
       )
       if _compaction_result_accepted(result):
           return rejected_completed + 1
       return rejected_completed
   ```

   - `CANCELLATION_REQUESTED` 类型的 rejected attempt 不计入（cancellation-before-attempt 无实际 proposal call）
   - accepted result → `rejected_completed + 1`
   - non-accepted result → `rejected_completed`

2. **`accepted_attempt_number` 初始化**（`dispatch.py:1344`）：

   ```python
   accepted_attempt_number = _accepted_attempt_number(result)
   ```

   从 normal compact result 获取初始值。若 normal compact 即 accepted，值 = `len(rejected_attempts) + 1`。

3. **recovery loop 中 failed tier proposal 的计数**（`dispatch.py:1385-1387`）：

   ```python
   completed_attempt_count += (
       _completed_compaction_proposal_attempt_count(tier_result)
   )
   ```

   每个 failed recovery tier 的 completed proposal count 累加。

4. **recovery accepted 时的计算**（`dispatch.py:1365-1368`）：

   ```python
   accepted_attempt_number = (
       completed_attempt_count
       + _accepted_attempt_number(tier_result)
   )
   ```

   = 所有先前 completed proposals + 当前 tier 的 attempt number（=1，因为 recovery `max_attempts=1`）

5. **cancellation-before-attempt 不计入**（`dispatch.py:1341-1342, 1351-1352`）：

   ```python
   if cancellation_token.is_cancelled():
       break
   ```

   两个 `break` 均在 `completed_attempt_count +=` 之前，cancellation 导致的退出不会将当次 tier 计入。✓

**场景验证**：

| 场景 | normal | tier 1 | tier 2 | tier 3 | `accepted_attempt_number` |
|------|--------|--------|--------|--------|---------------------------|
| normal accepted | accepted | — | — | — | `_accepted_attempt_number(normal_result)` |
| tier 1 accepted | failed (1 completed) | accepted | — | — | `1 + 1 = 2` |
| tier 2 accepted | failed (1) | failed (1) | accepted | — | `2 + 1 = 3` |
| tier 3 accepted | failed (1) | failed (1) | failed (1) | accepted | `3 + 1 = 4` |
| cancelled before tier | failed (1) | cancelled → break | — | — | (never written, goes to fallback) |
| cancelled after tier proposal | failed (1) | executed → stale → break | — | — | (never written, goes to fallback) |

**测试断言**：

- Tier 1: `assert compacted_payload["accepted_attempt_number"] == 2`（`test_dispatch_scheduler.py:4750`）
- Tier 2: `assert compacted_payload["accepted_attempt_number"] == 3`（`test_dispatch_scheduler.py:4828`）
- Tier 3: `assert compacted_payload["accepted_attempt_number"] == 4`（`test_dispatch_scheduler.py:4906`）

**实现 artifact 更新**（line 11）：明确描述 "recovery accepted 复用同一个 operation anchor 时，`accepted_attempt_number` 改为 normal 已完成 proposal attempts + 已失败 recovery proposal attempts + 当前 accepted tier attempt 的全局序号；cancellation-before-attempt 不计入已完成 proposal call。"

### MiMo Finding 2 复核：stale 测试命名/语义一致性

**结论: CLOSED。** 修复正确。

**修复前**（DS review 时的命名）：

- `test_proactive_compaction_recovery_stale_before_tier_attempt_discards` — stale before tier
- `test_proactive_compaction_recovery_stale_after_tier_proposal_discards` — "after tier proposal" 歧义：是指 proposal 返回后还是 accepted 后？

**修复后**：

- `test_proactive_compaction_recovery_stale_before_tier_attempt_discards`（不变）
  - docstring: `"normal 失败后 state 已 stale 时不进入 recovery compact commit"`
  - `stale_after_call=1`：call 1（normal compact）返回前将 Run 置为 FAILED
  - stale 发生在 recovery tier loop 进入之前，`is_cancelled()` → True → loop 未进入

- `test_proactive_compaction_recovery_stale_during_tier_proposal_discards`（**重命名**，原 `stale_after_tier_proposal`）
  - docstring: `"tier proposal 执行期间 state stale 时不写 CONTEXT_COMPACTED"`
  - `stale_after_call=2`：call 2（tier 1 proposal）执行期间将 Run 置为 FAILED
  - stale 发生在 proposal 执行期间（compactor 内部），`run_compaction_operation` 返回后 `is_cancelled()` 检测到 stale

**语义分析**：

- "during" 比 "after" 更精确——stale 的触发点是在 proposal 执行期间（`run_prepared_compactor_proposal` 中 `_fail_unstarted_for_stale_test`），而非 proposal 返回后由外部触发
- docstring 准确描述 "tier proposal 执行期间 state stale"，与实现行为一致
- 两个测试的命名形成清晰对比：before（循环前）vs during（执行期间）

### 无新增 correctness / stability / maintainability blocker

- **`CompactionFailureCategory` import 已添加**（`dispatch.py:147`）：`_completed_compaction_proposal_attempt_count` 依赖的 `CANCELLATION_REQUESTED` 枚举可用。✓
- **`_completed_compaction_proposal_attempt_count` 签名正确**：接收 `CompactionOperationResult`，返回 `int`。类型安全，无 `Any` 或隐式转换。✓
- **edge case 处理**：
  - `result.rejected_attempts` 为空 → `rejected_completed = 0` ✓
  - `rejected_attempts` 混合 `CANCELLATION_REQUESTED` 和非取消 rejection → 只计数非取消 ✓
  - `_compaction_result_accepted(result)` 为 True 且无 rejection → returns 1 ✓
- **`accepted_attempt_number` 变量在 commit transaction 闭包中使用**（`dispatch.py:1462`）：变量在 async 代码中赋值，在同步 `_operation` 闭包中消费——Python 闭包捕获变量引用，不捕获值。但由于 `_operation` 在 recovery loop 之后定义且 `accepted_attempt_number` 在 loop 之后不再修改，捕获的值是最终值。✓
- **无 `accepted_request`/`accepted_result`/`accepted_attempt_number` 未初始化路径**：三个变量均在正常路径初始化（line 1342-1345），recovery accepted 时覆盖（lines 1365-1371），全部 fail 时保持初始值。三个路径均可达 `_operation` 闭包，变量始终已定义。✓
- **无 regression**：`_MinimalSummaryCompactor` 改用 `_first_citable_compact_input_label`（更健壮的 source label 查找），不影响既有测试的 expected behavior。✓
- **recovery tier 计数一致性**：`_RecoveryScenarioCompactor.accept_call=2` → tier 1 accepted, `accept_call=3` → tier 2 accepted, `accept_call=4` → tier 3 accepted。序号 1=normal compact, 2=tier 1, 3=tier 2, 4=tier 3。与 `accepted_attempt_number` 值一一对应。✓

## 验证结果

| 验证项 | 命令 | 结果 |
|--------|------|------|
| S4 affected tests | `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_material.py -q` | **118 passed in 1.56s** |
| Pyright | `pyright dayu/host/dispatch.py tests/host/test_dispatch_scheduler.py` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | | **无 whitespace 错误** |
| `_completed_compaction_proposal_attempt_count` import | `grep "CompactionFailureCategory" dayu/host/dispatch.py` | **line 147，已 import** |
| `accepted_attempt_number` 测试断言 | `grep "accepted_attempt_number" tests/host/test_dispatch_scheduler.py` | **3 处显式断言：==2 / ==3 / ==4** |

## Open Questions

无。

## Residual Risk

- 与 DS review 的 residual risk 一致：reactive recovery 未扩展、无 tier 专属 durable metadata。
- `completed_attempt_count` 的累加依赖 recovery loop 中的顺序执行——如果未来 recovery loop 改为并行执行，计数逻辑需要重新设计。当前无此计划。

## Conclusion

**PASS** — 两个 MiMo finding 均已正确关闭，无新增 blocker。

- **MiMo F1**：`accepted_attempt_number` 按全局 proposal 序号计数（normal completed + failed recovery completed + current accepted），`CANCELLATION_REQUESTED` 不计入，cancellation-before-attempt 不计入。测试断言 `==2`/`==3`/`==4`。
- **MiMo F2**：stale 测试重命名为 `stale_before_tier_attempt` / `stale_during_tier_proposal`，docstring 与实现语义一致。
- **无新增 blocker**：`_completed_compaction_proposal_attempt_count` 类型安全、edge case 完整、import 到位、变量初始化路径全覆盖。
