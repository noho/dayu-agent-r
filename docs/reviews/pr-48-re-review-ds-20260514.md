# PR #48 Focused Re-Review (AgentDS)

## Scope

- **Mode**: focused re-review of uncommitted workspace changes fixing PR #48 controller accepted findings.
- **PR**: #48 `feat/host-phase-1` -> `main`
- **Controller adjudication**: `docs/reviews/pr-48-controller-adjudication-20260514.md`
- **Fix artifact**: `docs/reviews/pr-48-fix-20260514.md`
- **Original reviews**:
  - `docs/reviews/pr-48-review-20260514-0753.md`
  - `docs/reviews/pr-48-review-20260514-0800.md`
- **Review items**: A1/A3/A4/A5/A6 per controller accepted fixes; scope violation check.
- **Changed files** (uncommitted):
  - `dayu/runtime/filelock.py`
  - `dayu/README.md`
  - `tests/runtime/test_filelock.py`
  - `tests/runtime/test_lane.py`
  - `tests/host/test_public_contracts.py`
- **Excluded scope**: PR original diff, Engine/Fins/Service/UI layers, rejected findings A2/A7.

## Findings

未发现实质性问题。

## Item-by-Item Verification

### A1: `RuntimeFileLockToken.release()` partial failure state consistency

- **入口/函数**: `RuntimeFileLockToken.release()` at `dayu/runtime/filelock.py:89-108`
- **生产逻辑检查**:
  1. 幂等 guard `if self.released: return` 在最顶部（line 96），未变动。
  2. 第三方 `release()` 在 try/except 块中（line 99-102），失败时抛 `RuntimeFileLockError`，不推进状态。
  3. `self.released = True` 在第三方 release 成功后立即设置（line 103），先于 marker 恢复。
  4. Marker 恢复 `_ensure_lock_file_marker_exists` 在独立 try/except 中（line 105-108），失败只 `pass`，不抛异常，不修改 `released` 状态。
  5. 执行顺序正确：第三方 release → 标记 released → best-effort marker touch。
- **`__exit__` 检查**: `dayu/runtime/filelock.py:180-198` 未修改，无 exception priority change。
- **Public API 检查**: `release()` 签名、返回值、raises 文档未变。`__all__` 未变。
- **测试检查**: `test_release_marks_released_after_underlying_release_before_marker_failure`（`tests/runtime/test_filelock.py:130-154`）
  - 使用 `_CountingThirdPartyLock` 替身验证底层 release 调用次数。
  - 使用 `monkeypatch` 替换 `_ensure_lock_file_marker_exists` 为 `_raise_marker_restore_error`。
  - 断言 `token.released is True`（marker 失败不阻止 released 标记）。
  - 断言 `third_party_lock.release_calls == 1`（底层仅释放一次）。
  - 第二次 `token.release()` 后断言 `release_calls` 仍为 1（幂等）。
  - 测试未引入 logging/diagnostic policy。
- **结论**: 修复正确。

### A3: `RunSnapshot` source relation failure-path tests

- **测试**:
  - `test_run_snapshot_rejects_relation_without_source_run_id`（`tests/host/test_public_contracts.py:251-265`）：`source_run_id=None` + `source_run_relation=RETRY` → `ValueError("source_run_relation")`
  - `test_run_snapshot_rejects_source_run_id_without_relation`（`tests/host/test_public_contracts.py:268-282`）：`source_run_id="source-run-1"` + `source_run_relation=None` → `ValueError("source_run_id")`
- **生产代码检查**: `dayu/host/api.py` 零未提交修改（`git diff -- dayu/host/api.py` 无输出）。
- **结论**: 修复正确，完整覆盖 controller 要求。

### A4: `FollowupSnapshot` behavior consistency failure-path tests

- **测试**:
  - `test_followup_snapshot_steer_requires_target_run_id`（line 285-295）：steer 缺 `target_run_id` → `ValueError("target_run_id")`
  - `test_followup_snapshot_steer_rejects_queued_run_id`（line 298-308）：steer 携带 `queued_run_id` → `ValueError("queued_run_id")`
  - `test_followup_snapshot_queue_rejects_target_run_id`（line 311-321）：queue 携带 `target_run_id` → `ValueError("target_run_id")`
  - `test_followup_snapshot_queue_requires_queued_run_id`（line 324-334）：queue 缺 `queued_run_id` → `ValueError("queued_run_id")`
- **生产代码检查**: `dayu/host/api.py` 零未提交修改。
- **与已有测试的关系**: 行 337 的 `test_steer_requires_target_run_id` 测试的是 `SubmitFollowupRequest` 而非 `FollowupSnapshot`，不重复。
- **结论**: 修复正确，完整覆盖 controller 要求。

### A5: `dayu/README.md` filelock 位置

- **变更**: `filelock` 从 "Host 设计要求以下层中立能力沉淀到 `dayu.runtime` 或保持为 runtime 边界约束"（deferred 段）移动到 "`dayu.runtime` 当前已有以下层中立能力"（当前能力段），与 `lane` 并列（`dayu/README.md:148-151`）。
- **内容更新**: 描述增加了 "release 失败" 语义（之前仅提 "acquire 失败"），反映已实现的 release 能力。
- **Deferred 段保留**: `ToolsDiscovery` 与 `ScenePrepare` 仍留在 deferred/design-boundary 段（line 155-156），未变动。
- **结论**: 修复正确。

### A6: Lane validation / close idempotency tests

- **测试**:
  - `test_lane_owner_rejects_empty_owner_id_and_invalid_pid`（`tests/runtime/test_lane.py:210-216`）：
    - `LaneOwner(owner_id=" ", pid=1)` → `RuntimeLaneConfigError("owner_id")`，覆盖 `_require_non_blank` 校验（`dayu/runtime/lane.py:908` 使用 `value.strip() == ""`）。
    - `LaneOwner(owner_id="owner-1", pid=0)` → `RuntimeLaneConfigError("pid")`，覆盖 `self.pid <= 0` 校验（`dayu/runtime/lane.py:133`）。
  - `test_acquire_rejects_negative_timeout`（line 219-231）：`controller.acquire(..., timeout_seconds=-1)` → `RuntimeLaneConfigError("timeout")`，覆盖 `_resolve_timeout` 中 `timeout < 0` 校验（`dayu/runtime/lane.py:930`）。
  - `test_close_is_idempotent_when_called_twice`（line 234-245）：连续两次 `close()` 不抛错，覆盖 `self._close_completed` 幂等 guard（`dayu/runtime/lane.py:514-515`）。
- **生产代码检查**: `dayu/runtime/lane.py` 零未提交修改（`git diff -- dayu/runtime/lane.py` 无输出）。
- **结论**: 修复正确，完整覆盖 controller 要求。

### Scope Violation Check

- **已修改文件**（`git status --short`）:
  - `M dayu/README.md` — allowed
  - `M dayu/runtime/filelock.py` — allowed
  - `M tests/host/test_public_contracts.py` — allowed
  - `M tests/runtime/test_filelock.py` — allowed
  - `M tests/runtime/test_lane.py` — allowed
  - `?? docs/reviews/pr-48-fix-20260514.md` — review artifact, allowed
- **未修改文件验证**:
  - `dayu/host/api.py` — zero uncommitted changes ✓
  - `dayu/runtime/lane.py` — zero uncommitted changes ✓
- **结论**: 无越权文件修改。

## Validation Results（独立复验）

- `pytest tests/runtime/test_filelock.py tests/runtime/test_lane.py tests/host/test_public_contracts.py -q`: **41 passed**
- `pytest tests/host tests/runtime -q`: **112 passed**
- `pyright dayu/ tests/ utils/`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: passed（未重新运行，fix artifact 已报告通过）

## Open Questions

无。

## Residual Risk

- A1 marker restore 失败现被静默吞掉，无 diagnostic 信号。在当前 best-effort 语义下这是正确的——lock file marker 不是 Host 治理真源——但若未来 marker 恢复失败需要告警，需另行设计 diagnostic policy（controller 已将 A2 的 logging/diagnostic policy 延迟到后续阶段）。
- A6 `LaneOwner` 测试只覆盖了 `owner_id=" "`（纯空白），未覆盖 `owner_id=""`（空字符串）。但 `_require_non_blank` 使用 `value.strip() == ""`，两种输入走同一代码路径，覆盖已充分。
- 未覆盖的测试面：A3/A4 的 happy-path snapshot 构造测试依旧无 assertion 验证 source relation / followup behavior 一致性在合法输入下的正向行为。Controller 未将此项纳入 required fix，非本次 re-review scope。

## Re-Review Conclusion

- **Remaining findings**: 0 blocker, 0 major, 0 medium, 0 low.
- **通过 re-review**: 是。
