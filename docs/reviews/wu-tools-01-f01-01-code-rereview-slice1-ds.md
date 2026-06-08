# WU-TOOLS-01-F01-01 Slice 1 Code Re-Review — AgentDS

## Scope

- Work unit: `WU-TOOLS-01-F01-01 Fins filelock convergence to dayu.runtime.filelock`
- Gate: `code re-review`
- Slice: `Slice 1 — ingestion job store convergence`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-01-code-review-slice1-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-01-fix-slice1-codex.md`
  - `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md`
- Source file: `dayu/fins/ingestion_runtime.py`

## Verdict

**pass** — A1 和 A2 均已修复，证据可验证。

## A1 Re-review: `RuntimeFileLockError` docstring 补充

**Status: 已修复**

### Evidence

`RuntimeFileLockError` 定义于 `dayu/runtime/filelock.py:22`，是 `file_lock()` context manager 在获取锁失败时抛出的异常类型。

`FsFinsIngestionJobStore` 的 6 个公共方法 docstring Raises 均已补充：

| 方法 | 行号 | Raises 条目 |
|---|---|---|
| `create_job` | 698 | `RuntimeFileLockError: 文件锁获取失败时抛出。` |
| `save_job` | 721 | `RuntimeFileLockError: 文件锁获取失败时抛出。` |
| `save_succeeded_or_cancelled` | 752 | `RuntimeFileLockError: 文件锁获取失败时抛出。` |
| `claim_running_or_cancelled` | 802 | `RuntimeFileLockError: 文件锁获取失败时抛出。` |
| `read_job` | 841 | `RuntimeFileLockError: 文件锁获取失败时抛出。` |
| `request_cancel` | 861 | `RuntimeFileLockError: 文件锁获取失败时抛出。` |

### 边界确认

- Protocol `FinsIngestionJobStore`（lines 485-599）的 Raises 未包含 `RuntimeFileLockError` — 这是正确的。Protocol 定义的是存储协议的抽象契约，不应泄漏具体实现的异常类型。Controller adjudication 明确要求 "不要只落在 Protocol 方法上"，fix 正确地将 docstring 补充到了具体实现类 `FsFinsIngestionJobStore` 的 6 个方法上。
- `RuntimeFileLockError` 仅在 docstring 文本中引用，无需 import 语句。Python docstring 中的类型引用是文档性文字，不要求运行时可解析。

## A2 Re-review: Coverage 验证记录

**Status: 已修复**

### Evidence

`docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md` 第 40-43 行已包含完整的 coverage 记录：

```
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py --cov=dayu.fins.ingestion_runtime --cov-report=term-missing -q`
  - Result: passed, `26 passed, 3 warnings`
  - Coverage: `dayu/fins/ingestion_runtime.py` reached `92%`, above the required `80%` per-file target.
```

92% > 80%，满足项目覆盖率要求。

## Validation Performed

1. 读取 controller adjudication artifact，确认 A1/A2 的 accepted fix 范围。
2. 读取 fix artifact，确认声称的修复内容。
3. 逐行检查 `dayu/fins/ingestion_runtime.py` 中 `FsFinsIngestionJobStore` 的 6 个公共方法 docstring，逐一核对 `RuntimeFileLockError` 是否存在。
4. 交叉验证 `dayu/runtime/filelock.py` 中 `RuntimeFileLockError` 的定义与 docstring 中引用的异常名称一致。
5. 确认 Protocol `FinsIngestionJobStore` 的 Raises 未误加 `RuntimeFileLockError`。
6. 读取 implementation artifact，确认 coverage 命令与结果已记录。

## Residual Risks / Uncovered Areas

- **Low**: 本次 fix 仅涉及 docstring 文本和 review artifact 补充，未改变运行时行为。`RuntimeFileLockError` 未在 Fins 层 import——仅以文本形式出现在 docstring 中，不影响类型检查或运行时。
- **Deferred**: Storage batch convergence 仍为 Slice 2 工作。
- **Deferred**: `dayu/fins/_file_lock.py` 删除仍为 Slice 3 工作。
- **Not a gap**: DS 在原始 review 中提出的 "dedicated lock-acquisition-failure test" 已被 controller 明确拒绝纳入当前 fix。runtime filelock 的 acquire/release 失败行为已在 `tests/runtime/test_filelock.py` 覆盖，当前 Slice 1 无需额外 Fins 层测试。

## Blocking Open Questions

None.
