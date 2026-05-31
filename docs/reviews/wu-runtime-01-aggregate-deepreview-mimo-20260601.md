# WU-RUNTIME-01 Aggregate Deep Review

## Scope

- Mode: current changes
- Branch: `refactor/wu-runtime-01-filelock-contraction`
- Base: `main`
- Output file: `docs/reviews/wu-runtime-01-aggregate-deepreview-mimo-20260601.md`
- Included scope: `git diff main...HEAD` 中的已提交变更；忽略未提交的 `AGENTS.md` / `CLAUDE.md` pre-existing user changes
- Parallel review coverage: 无

## Conclusion

**pass**

WU-RUNTIME-01 只收缩 `RuntimeFileLock`，没有过度设计。`released` / `_active_token` 移除一致、无兼容 wrapper、无 public contract 残留。`_context_token` 仅作为 context manager cleanup guard，不恢复 acquire lifecycle gate。design.md、runtime tests、Host regression tests 互相一致。validation scope 足够。control doc / artifacts 足以进入 ready-to-open-draft-PR 前状态。无 blocking finding。

## Findings

未发现实质性问题。

以下为已知、已裁决的事项复核，不构成新 finding：

### 已裁决-Slice1-同一实例嵌套 context fail-fast

- **入口/函数**: `RuntimeFileLock.__enter__()`
- **文件(行号)**: `dayu/runtime/filelock.py:189-190`
- **状态**: accepted / closed（Slice 1 controller adjudication）
- **复核结论**: `__enter__()` 检查 `_context_token is not None` 后 fail-fast，防止嵌套覆盖外层 token 导致漏 release。这不恢复旧 `_active_token` acquire gate，`acquire()` 仍不读写 `_context_token`。实现正确。

### 已裁决-Slice1-白盒测试访问 `_context_token`

- **文件(行号)**: `tests/runtime/test_filelock.py:174`
- **状态**: accepted residual（Slice 1 controller adjudication）
- **复核结论**: `test_context_manager_release_failure_clears_context_token` 直接写入 `lock._context_token` 以构造 release 失败场景。这是白盒测试，不暴露 `_context_token` 为 public API（不在 `__all__`、不在 dataclass fields、不在 public shape 断言中）。相比引入更复杂 mock seam，这是最小可维护测试。

### 已裁决-Slice1-release 失败语义变更

- **入口/函数**: `RuntimeFileLockToken.release()`
- **文件(行号)**: `dayu/runtime/filelock.py:98-104`
- **状态**: deliberate contract contraction（plan Section 4 & 5）
- **复核结论**: 旧实现在第三方 release 抛错时设置 `released = True`，阻止 retry 但掩盖失败。新实现 `_release_completed` 只在第三方 release 成功后设为 `True`，失败时允许后续 retry。这是 deliberate 设计收缩，plan 和 design.md 已同步记录。测试 `test_release_failure_does_not_complete_and_allows_retry` 验证 `release_calls == 2`。

## Overdesign Check

**无过度设计。**

- 只修改 1 个 production source 文件（`dayu/runtime/filelock.py`），46 行变更。
- Host production source（`dayu/host/audit.py`、`dayu/host/tool_trace.py`）未修改。
- 删除 `_active_token` 及其 acquire gate，不引入新抽象。
- `_context_token` 是最小 context manager cleanup 机制，不是 lifecycle truth。
- `_release_completed` 是私有幂等 guard，不暴露为 public API。
- 不引入 async wrapper、stale lock 探测、break lock、durable lease 或 Host recovery。
- 不引入兼容 property、wrapper、re-export 或 facade。
- design.md 变更只删除 `released: bool` 并补充 release 语义说明，不引入新架构决策。

## Validation 复核

| 验证项 | 结果 |
|---|---|
| `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 23 passed |
| `pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q` | 13 passed |
| `pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing` | 90% coverage（>= 80% 阈值） |
| `pyright dayu/runtime/filelock.py` | 0 errors, 0 warnings, 0 informations |
| `rg "RuntimeFileLockToken\.released\|_active_token" dayu/ tests/ docs/host/design.md` | 仅剩测试中的负向断言 |
| import boundary | `tests/runtime/test_import_boundary.py` 未修改，继续通过 |

## Design / Test / Doc 一致性复核

| 检查项 | 结论 |
|---|---|
| `docs/host/design.md` API shape 是否删除 `released: bool` | 是（diff 确认） |
| `docs/host/design.md` release 语义是否说明失败不标成功、允许 retry | 是（diff 确认） |
| `RuntimeFileLockToken` public fields 是否只剩 `lock_path` | 是（`test_public_api_shape_and_non_goals_are_explicit` 断言 `public_token_field_names == {"lock_path"}`） |
| `RuntimeFileLock.__slots__` 是否不含 `_active_token` | 是（测试断言） |
| `_context_token` 是否不在 `__all__`、dataclass fields | 是（测试断言） |
| Host tests 是否通过 public `file_lock(...)` + `lock_path` 参数验证 | 是（未导入第三方 `filelock`、未读取 token） |
| Host production source 是否未被修改 | 是（`git diff` 确认空） |

## Control Doc / Artifacts 状态

| 项目 | 状态 |
|---|---|
| Plan artifact | `docs/host/wu-runtime-01-filelock-contraction-plan.md`，已 accepted |
| Slice 1 review artifacts | 4 份 review + 1 份 adjudication，已 accepted |
| Slice 2 review artifacts | 4 份 review + 1 份 adjudication，已 accepted |
| Aggregate deepreview | 本文档 |
| Residual risks | 已分类、有 owner（见下方） |
| Blocking open questions | none |

## Residual Risk

| 风险 | 分类 | Owner |
|---|---|---|
| 同一 `RuntimeFileLock` 实例的 reentrant / nested acquire 具体行为不承诺 | accepted residual（设计真源 non-goal） | 无（第三方 `FileLock` 语义） |
| Lock marker 文件不是 Host truth；marker restore 是 best-effort debug 语义 | accepted residual（设计真源明确） | 无（已有 debug log） |
| 白盒测试直接访问 `_context_token` | accepted residual（Slice 1 adjudication） | 无（最小可维护测试） |

以上 residual risks 均已 closed 或 deferred-with-owner，无 open item。control doc `ready-to-open-draft-PR` 条件满足。
