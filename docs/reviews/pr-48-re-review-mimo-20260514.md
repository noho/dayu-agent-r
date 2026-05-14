# PR #48 Focused Re-Review (AgentMiMo)

## Scope

- Mode: current changes (focused re-review)
- Branch: `feat/host-phase-1`
- Base: `main`
- Output file: `docs/reviews/pr-48-re-review-mimo-20260514.md`
- Review date: 2026-05-14 08:25
- Re-review target: AgentCodex fix of controller accepted findings A1 / A3 / A4 / A5 / A6
- Controller adjudication: `docs/reviews/pr-48-controller-adjudication-20260514.md`
- Fix artifact: `docs/reviews/pr-48-fix-20260514.md`
- Included scope: 5 modified files — `dayu/runtime/filelock.py`, `dayu/README.md`, `tests/runtime/test_filelock.py`, `tests/runtime/test_lane.py`, `tests/host/test_public_contracts.py`
- Excluded scope: `dayu/host/api.py`, `dayu/runtime/lane.py` production logic (controller prohibited modification)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### Re-review 逐项裁决

#### A1. `RuntimeFileLockToken.release()` 部分失败状态一致性 — PASS

**文件**: `dayu/runtime/filelock.py:99-108`

修复正确。执行顺序：

1. `self._third_party_lock.release()` 失败 → 抛 `RuntimeFileLockError`，`released` 保持 `False`（正确：底层未释放）。
2. 底层 release 成功 → 立即 `self.released = True`（line 103）。
3. `_ensure_lock_file_marker_exists()` 失败 → `except Exception: pass` 压制（lines 105-108），不向调用方抛出，不回滚 `released`。

满足 controller 要求：
- "Mark the token released immediately after successful third-party release" — line 103。
- "Keep marker restoration best-effort and do not let marker failure turn a successfully released token back into a release failure" — lines 105-108。
- 未引入 public API change、logging/diagnostic policy 或 `__exit__` exception priority change。

**测试**: `test_release_marks_released_after_underlying_release_before_marker_failure`（`test_filelock.py:130-154`）。使用 `_CountingThirdPartyLock` 替身 + monkeypatch `_ensure_lock_file_marker_exists` 抛 `OSError`。断言 `token.released is True`、`release_calls == 1`、重复 `release()` 不再调用底层。覆盖完整。

#### A3. `RunSnapshot` source relation failure-path tests — PASS

**文件**: `tests/host/test_public_contracts.py:251-282`

两个测试完整覆盖 controller 要求：

| 测试 | 输入 | 预期 |
| --- | --- | --- |
| `test_run_snapshot_rejects_relation_without_source_run_id` | `source_run_id=None`, `source_run_relation=RETRY` | `ValueError` containing `"source_run_relation"` |
| `test_run_snapshot_rejects_source_run_id_without_relation` | `source_run_id="source-run-1"`, `source_run_relation=None` | `ValueError` containing `"source_run_id"` |

未修改 `dayu/host/api.py`（git diff 确认无此文件变更）。

#### A4. `FollowupSnapshot` behavior failure-path tests — PASS

**文件**: `tests/host/test_public_contracts.py:285-334`

四个测试完整覆盖 controller 要求：

| 测试 | behavior | target_run_id | queued_run_id | 预期 |
| --- | --- | --- | --- | --- |
| `test_followup_snapshot_steer_requires_target_run_id` | STEER | None | None | `ValueError("target_run_id")` |
| `test_followup_snapshot_steer_rejects_queued_run_id` | STEER | present | present | `ValueError("queued_run_id")` |
| `test_followup_snapshot_queue_rejects_target_run_id` | QUEUE | present | present | `ValueError("target_run_id")` |
| `test_followup_snapshot_queue_requires_queued_run_id` | QUEUE | None | None | `ValueError("queued_run_id")` |

未修改 `dayu/host/api.py`。

#### A5. `dayu/README.md` filelock 位置调整 — PASS

**文件**: `dayu/README.md:148-151`

`filelock` 描述已从 "Host 设计要求以下层中立能力沉淀到 `dayu.runtime` 或保持为 runtime 边界约束" 段移入 "`dayu.runtime` 当前已有以下层中立能力" 段，位于 `lane` 之后。`ToolsDiscovery` 和 `ScenePrepare` 仍保留在 deferred / design-boundary 段（lines 153-156）。语义准确，描述与当前实现一致。

#### A6. Lane failure-path / idempotency tests — PASS

**文件**: `tests/runtime/test_lane.py:210-245`

三个测试完整覆盖 controller 要求：

| 测试 | 覆盖点 |
| --- | --- |
| `test_lane_owner_rejects_empty_owner_id_and_invalid_pid` | `owner_id=" "` → `RuntimeLaneConfigError("owner_id")`；`pid=0` → `RuntimeLaneConfigError("pid")` |
| `test_acquire_rejects_negative_timeout` | `timeout_seconds=-1` → `RuntimeLaneConfigError("timeout")` |
| `test_close_is_idempotent_when_called_twice` | 连续 `close()` 不抛错 |

未修改 `dayu/runtime/lane.py`（git diff 确认无此文件变更）。

#### 越权文件修改检查 — PASS

controller 允许的文件清单：
- 生产文件：`dayu/runtime/filelock.py` ✓、`dayu/README.md` ✓
- 测试文件：`tests/runtime/test_filelock.py` ✓、`tests/runtime/test_lane.py` ✓、`tests/host/test_public_contracts.py` ✓
- review artifact：`docs/reviews/pr-48-fix-20260514.md`（untracked，非代码）

实际变更文件完全在允许范围内。`dayu/host/api.py` 和 `dayu/runtime/lane.py` 未被修改。

#### 新问题检查 — 未发现

fix 只涉及：
- `filelock.py` 中将 `released=True` 提前到 marker restore 之前，并将 marker restore 改为 best-effort。逻辑清晰，无副作用泄漏。
- 三个测试文件新增纯测试代码，不影响生产路径。
- `README.md` 仅移动已有描述位置，无新增内容。

## Open Questions

无。

## Residual Risk

- 无。所有 controller accepted findings 已被正确修复，测试通过（41 passed），pyright 通过（0 errors），无越权修改，无新问题。
