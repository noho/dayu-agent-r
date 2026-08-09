# Code Review — WU-CLI-CONFORMANCE-F01-F07 S2/F02 Fix Re-review（MiMo）

## Scope

- Mode: current changes（未提交 S2 fix diff 相对 HEAD `a41526ec`）
- Branch: `codex/interactive-oracle`
- Base: `a41526ec`（S1 accepted commit）
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-rereview-mimo.md`
- Included scope: `dayu/cli/composer.py`、`tests/cli/test_interactive_composer.py`、`tests/cli/test_interactive_command.py` 未提交 diff 相对 `a41526ec`
- Excluded scope: `utils/`、registry、README、design、Host、Service、Engine
- Parallel review coverage: 无

## Reference Documents

- Controller adjudication: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-controller-adjudication.md`
- 首审 MiMo: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-mimo.md`
- 首审 DS: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-codex.md`
- Implementation artifact: `docs/reviews/wu-cli-conformance-f01-f07-s2-implementation-codex.md`
- Accepted plan §4 / §6: `docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`

## Validation Summary

- **Focused pytest**: `104 passed, 3 warnings`（首审 99 passed → fix 新增 5 个 owner test）。
- **Focused pyright**: `0 errors, 0 warnings, 0 informations`。
- **Coverage**: `dayu/cli/composer.py` — `373 statements / 35 missing / 91%`（首审 356/33/91% → fix 增加 17 stmt / 2 miss）。
- **Full pyright**: 两处 `utils/` `explicit_config_dir` 残留，确认为 S1 引入的 cross-slice regression，与 S2 fix 无关。

## Accepted Findings 逐项验证

### S2-C01 — primary exception ownership（`accepted`，中）

**总控要求**: round trip body 的任何在途 `BaseException` 先标记为 primary 再原样重抛；`finally` 无论成功、失败或取消仍尝试一次 `temporary_path.unlink(missing_ok=True)`。unlink 的 `OSError` 只有在不存在 primary 时才形成 `CLEANUP_FAILED`；否则不得覆盖 typed tempfile、`SPAWN_FAILED`、`READBACK_FAILED`、`CancelledError` 或未知 primary identity。须增加组合失败 owner test。

**代码验证**:

`dayu/cli/composer.py:789-850`:

```python
primary_failure = False
try:
    try:
        # ... tempfile creation, spawn, readback ...
    except OSError:
        raise _EditorActionError(TEMPFILE_UNAVAILABLE, ...) from None
    # ... spawn OSError → SPAWN_FAILED; nonzero → return CANCELLED; readback → READBACK_FAILED ...
except BaseException:
    primary_failure = True
    raise
finally:
    if temporary_path is not None:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            if not primary_failure:
                raise _EditorActionError(CLEANUP_FAILED, ...) from None
```

控制流分析：

1. **primary + cleanup 双故障**: inner try 抛 `SPAWN_FAILED` → outer `except BaseException` 设 `primary_failure = True` 并 `raise` → `finally` 运行，`unlink` 失败 → `not primary_failure` 为 `False` → 不覆盖。`SPAWN_FAILED` 原样传播。✅
2. **CancelledError + cleanup 双故障**: task 被 cancel → `CancelledError` 进入 outer `except BaseException` → `primary_failure = True`，`raise` → `finally` `unlink` 失败 → 不覆盖。`CancelledError` 原样传播。✅
3. **success + cleanup 单故障**: inner try 全部成功 → `primary_failure` 仍为 `False` → `finally` `unlink` 失败 → `not primary_failure` 为 `True` → raise `CLEANUP_FAILED`。正确。✅
4. **success + cleanup 成功**: `unlink(missing_ok=True)` 成功 → `finally` 结束 → 到达 `buffer.document = Document(...)` 回填。✅

**测试验证**:

- `test_primary_editor_failure_survives_cleanup_failure` (line 832): 参数化 `SPAWN_ERROR` 和 `INVALID_UTF8`，monkeypatch `Path.unlink` 抛 `OSError`。断言 `cleanup_failure.calls == [(temporary_path, True)]`、diagnostic 包含 primary fragment、不包含 `"无法清理"`、document 保留。✅
- `test_editor_cancellation_survives_cleanup_failure` (line 879): `_BlockedTerminalRunner` 阻塞 spawn → task.cancel() → `CancelledError` 传播。unlink 被 monkeypatch 失败。断言 `CancelledError` 仍被抛出、cleanup 被尝试、document 保留。✅

**结论**: `S2-C01` 已正确关闭。primary exception 不被 cleanup 覆盖，cleanup-only 场景仍准确投影 `CLEANUP_FAILED`。测试覆盖了 spawn/readback primary + cleanup 双故障和 CancelledError + cleanup 双故障。

---

### S2-C02 — synchronous public Document snapshot（`accepted`，中）

**总控要求**: 同步 `_open_explicit_editor` 在 `asyncio.create_task(...)` 前冻结完整 public `buffer.document`，并把它作为必填 `original_document: Document` 参数显式传给 `_run_explicit_editor_round_trip`。async body 不再读取 original buffer state。须测试证明 task 调度前后 buffer 变化不能改变 original snapshot。

**代码验证**:

`dayu/cli/composer.py:749-768`:

```python
def _open_explicit_editor(
    buffer: Buffer,
    command: _ExplicitEditorCommand,
) -> asyncio.Task[_EditorProcessOutcome]:
    original_document = buffer.document          # 同步冻结
    return asyncio.create_task(
        _run_explicit_editor_round_trip(
            buffer=buffer,
            command=command,
            original_document=original_document,  # 显式传入
        )
    )
```

`_run_explicit_editor_round_trip` 签名 (line 771-775):

```python
async def _run_explicit_editor_round_trip(
    *,
    buffer: Buffer,
    command: _ExplicitEditorCommand,
    original_document: Document,  # 必填参数
) -> _EditorProcessOutcome:
```

async body 使用 `original_document.text` (line 800) 写入 tempfile，不再读取 `buffer.document`。✅

**测试验证**:

`test_explicit_editor_freezes_original_document_before_task_scheduling` (line 793): monkeypatch `_run_explicit_editor_round_trip` 为 recorder → 调用 `_open_explicit_editor` → 立即替换 `buffer.document` 为 `"changed before scheduling"` → await task → 断言 recorder 收到的 `original_document` 仍是原始值。✅

**结论**: `S2-C02` 已正确关闭。Document 在同步 call path 冻结，竞态窗口消除。

---

### S2-C03 — one EDITOR_PENDING per composer（`accepted`，中）

**总控要求**: 每个 composer 的集合大小保持 `0..1`。须在 owner 边界禁止 pending 时再次 launch，并以 owner test 断言只有一个 task/process、无第二次 buffer write。

**代码验证**:

`dayu/cli/composer.py:624-625`:

```python
if editor_tasks:
    return
```

handler 入口在 set 非空时直接 no-op。显式 `_EditorProcessOutcome` task (line 656-665) 和 unset `Buffer.open_in_editor(...)` task (line 639-653) 都进入同一 `_EditorTask` typed set。done callback 消费 task (line 886 `editor_tasks.discard(task)`)。teardown 清空集合 (line 952 `editor_tasks.clear()`)。✅

**测试验证**:

`test_repeated_editor_shortcut_while_pending_launches_one_task_and_write` (line 918): `_BlockedTerminalRunner` 阻塞首次 spawn → 同步调用 handler 两次 → 断言只有一个 `_run_explicit_editor_round_trip` pending task → release → 断言 `process_script.calls == 1`、`terminal_runner.calls == [(False, True)]`（一次 `run_in_terminal`）、`recorder.calls == [expected_document]`（一次 buffer write）。✅

**结论**: `S2-C03` 已正确关闭。重复快捷键无第二 task/process/write。

---

### S2-C04 — strict updated text type（`accepted as cleanup`，低）

**总控要求**: `updated_text is None` 分支由当前控制流证明不可达。随 fix 删除该 dead branch 并保持严格类型。

**代码验证**:

`dayu/cli/composer.py:788`:

```python
updated_text: str
```

类型声明为严格 `str`，不再是 `str | None`。所有成功路径（line 828 `updated_text = temporary_path.read_bytes().decode("utf-8")`）赋值 `str`。失败路径 raise `_EditorActionError` 或 `return CANCELLED`，不会到达 line 851 的 `buffer.document = Document(text=updated_text, ...)`。原 `if updated_text is None: raise RuntimeError(...)` 已删除。✅

**结论**: `S2-C04` 已正确关闭。dead None branch 消失，`updated_text` 严格 `str` 类型。

---

## 额外审查项

### TypeAlias 使用

```python
_EditorTask: TypeAlias = (
    asyncio.Task[_EditorProcessOutcome] | asyncio.Task[None]
)
```

`from __future__ import annotations` (line 8) 使所有 annotation 在运行时为字符串，不会触发 `|` 运算符的运行时求值。pyright 0 errors 验证类型正确。`_EditorTask` 只在 module-private 位置使用（`_build_interactive_key_bindings`、`PromptToolkitInteractiveComposer._editor_tasks`、`_consume_*`、`_cancel_editor_tasks`），不暴露到 `__all__`。✅ 最小正确。

### system editor task ownership

`_consume_system_editor_task` (line 903-927) 与 `_consume_explicit_editor_task` (line 869-900) 共享同一 `editor_tasks: set[_EditorTask]` 强引用集合。system fallback 的 `buffer.open_in_editor(validate_and_handle=False)` 返回的 task 也受 `if editor_tasks: return` 守卫保护。teardown `_cancel_editor_tasks` 统一取消两种 task。✅ 单一 owner，无第二状态机。

### BaseException re-raise

`except BaseException:` (line 836) 是正确的设计选择：

- `CancelledError` 在 Python 3.11 是 `BaseException` 的直接子类，不是 `Exception` 子类。
- 若用 `except Exception:` 会漏掉 `CancelledError`，导致 `primary_failure` 不被设置，cleanup 失败会覆盖取消身份。
- `finally` 中 `not primary_failure` 守卫正确区分了 "有 primary 在途" 和 "cleanup-only" 两种场景。
- 没有引入 fallback、diagnostic drift 或新的 teardown 逻辑。✅ 最小正确。

## S2-R01 / S2-R02 裁决复核

### S2-R01（`rejected`，低）— public `build_interactive_key_bindings` editor tasks orphaned

总控裁决 `rejected`，理由：`editor_tasks=set()` 被 returned bindings 的 handler closure 与 done callback 持有，非"无外部引用"；`S2-C03` 同时阻止该路径重复 launch。

本次复核确认裁决正确。`build_interactive_key_bindings` (line 453-473) 创建的 `set()` 由 closure 捕获并传入 `_build_interactive_key_bindings`，handler 和 done callback 都持有引用。`S2-C03` 的 `if editor_tasks: return` 守卫确保同一 set 内最多一个 task。public API 不管理 application lifecycle 是合理的分层边界。✅ 裁决维持。

### S2-R02（`not a defect`，低）— `_write_editor_diagnostic` broad `Exception`

总控裁决 `not a defect`，理由：diagnostic sink 最外层，不捕获 `BaseException`，防止 background callback 产生第二 traceback。

本次复核确认裁决正确。`_write_editor_diagnostic` (line 1011-1025) 的 `except Exception` 只覆盖 `OSError`、`ValueError` 等 `Exception` 子类；`KeyboardInterrupt`、`SystemExit`、`GeneratorExit` 不被捕获。✅ 裁决维持。

## Cross-slice pyright 分类

两处 `utils/` `explicit_config_dir` 残留确认为 S1 引入的 cross-slice regression，不是 existing debt，也不归 S8。S2 focused 三文件 pyright 零错误。按总控裁决，S2 accepted 后、S3 前须独立 S1 corrective gate 收口。本次复核不改变该分类。

## Open Questions

无

## Residual Risk

- `covered by later approved slice S8`: 真实 PTY 下不同 editor 的 terminal suspend/resume 与最终 immutable CLI evidence bundle。
- `assigned to S1 corrective gate before S3`: 两处 `utils` 旧 keyword 与 full pyright closure。
- `out of scope`: Windows text-mode newline。

当前没有未分类的 S2 residual risk。

## Verdict

总控 accepted `S2-C01`–`S2-C04` 已全部正确关闭：

| ID | 状态 | 验证方法 |
|---|---|---|
| S2-C01 | ✅ 已关闭 | `primary_failure` 控制流 + 两个组合故障 test |
| S2-C02 | ✅ 已关闭 | 同步冻结 + task 调度竞态 test |
| S2-C03 | ✅ 已关闭 | `if editor_tasks: return` 守卫 + 重复快捷键 single-process test |
| S2-C04 | ✅ 已关闭 | `updated_text: str` 严格类型 + dead branch 删除 |

新 TypeAlias、system editor task ownership、BaseException re-raise 均最小正确，未引入新的 teardown/fallback/diagnostic drift。S2-R01/S2-R02 裁决维持。Full pyright 两处 `utils/` 错误为 S1 cross-slice regression，不归 S2。

**S2 fix re-review 通过，无 blocking finding。**

---

*Review 完成。未修改实现/tests/artifact/registry，未 stage/commit/push/PR。*
