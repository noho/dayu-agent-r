# Code Review — WU-CLI-CONFORMANCE-F01-F07 S2/F02 Fix Re-Review (DS)

## Scope

- Mode: current changes（未提交 S2 fix diff 相对 HEAD a41526ec）
- Branch: `codex/interactive-oracle`
- Base: `a41526ec`（S1 accepted commit）
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-rereview-ds.md`
- Included scope:
  - `dayu/cli/composer.py`（production fix）
  - `tests/cli/test_interactive_composer.py`（owner-level fix tests）
  - `tests/cli/test_interactive_command.py`（integration tests，fix 未修改）
- Reference documents:
  - Controller adjudication: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-controller-adjudication.md`
  - First-round DS review: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-ds.md`
  - First-round MiMo review: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-mimo.md`
  - Fix record: `docs/reviews/wu-cli-conformance-f01-f07-s2-fix-codex.md`
  - Implementation artifact: `docs/reviews/wu-cli-conformance-f01-f07-s2-implementation-codex.md`
  - `CLAUDE.md`
- Excluded scope: S1、S3-S8、utils/、Host/Engine 生产代码、registry、design docs
- Parallel review coverage: 无（单 reviewer 全路径走读）

## Validation Summary

- **Focused pytest**: `tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py` — 104 passed, 3 warnings（均为 edgar 依赖既有 deprecation warning）。
- **Focused pyright**: `dayu/cli/composer.py tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py` — 0 errors, 0 warnings, 0 informations。
- **Coverage**: `dayu/cli/composer.py` — 373 statements / 35 missing / 91%（精确 90.62%，>=80% 达标）。
- **全仓 pyright cross-slice regression**: 两处 `utils/...explicit_config_dir` 残留（`smoke_cli_init_provider_matrix.py:2386`、`smoke_host_public_awaiting_entrypoint.py:808`）— 确认为 S1 引入的 cross-slice regression，按总控裁决由独立 S1 corrective gate 收口。**本 reviewer 不将其误判为 S2 pass 或 S2 修复建议。**
- **`git diff --check`**：通过（验证自 fix-codex 记录）。
- **Registry JSON/hash 不变，index 为空**（验证自 fix-codex 记录）。

## Accepted Findings 逐项关闭验证

### S2-C01 — primary exception ownership（状态：已关闭 ✅）

- **入口/函数**: `_run_explicit_editor_round_trip`
- **文件(行号)**: `dayu/cli/composer.py:789, 836-840, 841-850`
- **修复机制**: 单一 `primary_failure: bool` 控制流状态（行 789 初始化为 `False`）。round trip body 的任何在途 `BaseException`（包括 `_EditorActionError`、`CancelledError`）均由行 836-840 的 `except BaseException` 捕获，设置 `primary_failure = True` 后以裸 `raise` 原样重抛。`finally` 块（行 841-850）始终尝试一次 `temporary_path.unlink(missing_ok=True)`；unlink 的 `OSError` 仅在 `not primary_failure` 时形成 `CLEANUP_FAILED`，否则静默吸收。
- **直接证据**:
  - `SPAWN_FAILED` 路径：行 818-821 raise → 行 836 `except BaseException` 设 `primary_failure = True` → 行 840 `raise` 重抛 → 行 844 `unlink` 抛 `OSError` → 行 846 `not primary_failure` 为 `False` → 不 raise，`SPAWN_FAILED` 原样传播。
  - `CancelledError` 路径：`await run_in_terminal(...)`（行 813）被取消注入 `CancelledError` → `except BaseException` 捕获 → `primary_failure = True` → re-raise → `finally` cleanup OSError 被静默吸收 → `CancelledError` 原样传播。
  - cleanup-only 路径（无 primary）：正常 success path 无异常 → `primary_failure = False` → unlink OSError → `CLEANUP_FAILED` 正确形成。
- **Owner test 覆盖**:
  - `test_primary_editor_failure_survives_cleanup_failure`（行 832-875）：参数化 `SPAWN_ERROR` + cleanup 双故障与 `INVALID_UTF8` + cleanup 双故障，断言 primary diagnostic 出现且 "无法清理" 不出现，cleanup 被尝试。
  - `test_editor_cancellation_survives_cleanup_failure`（行 878-914）：`CancelledError` + cleanup 双故障，断言 `CancelledError` 原样传播且 cleanup 被尝试。
- **修复未引入新语义**: 无 rollback、无重试、无 filesystem product contract 扩张、无 diagnostic 新增。
- **裁决**: S2-C01 已真正关闭。✅

### S2-C02 — synchronous public Document snapshot（状态：已关闭 ✅）

- **入口/函数**: `_open_explicit_editor`
- **文件(行号)**: `dayu/cli/composer.py:761`
- **修复机制**: 同步 `_open_explicit_editor`（行 749-768）在 `asyncio.create_task(...)`（行 762）之前于行 761 读取一次完整 public `buffer.document`，并作为必填 `original_document: Document` 参数显式传入 `_run_explicit_editor_round_trip`（行 775）。async body（`_run_explicit_editor_round_trip` 行 800）使用 `original_document.text`，不再读取 buffer 当前状态。
- **直接证据**:
  - 行 761 `original_document = buffer.document` — 同步 call path 单次读取。
  - 行 762-768 `asyncio.create_task(_run_explicit_editor_round_trip(buffer=..., command=..., original_document=original_document))` — 冻结 snapshot 以显式参数传入。
  - 行 800 `temporary_file.write(original_document.text)` — async body 只消费传入参数。
- **Owner test 覆盖**:
  - `test_explicit_editor_freezes_original_document_before_task_scheduling`（行 792-821）：创建 task 后立即替换 `buffer.document`，断言 round trip 收到的是原始 snapshot，不是修改后的 buffer 内容。
- **裁决**: S2-C02 已真正关闭。✅

### S2-C03 — one EDITOR_PENDING per composer（状态：已关闭 ✅）

- **入口/函数**: `_open_external_editor` handler
- **文件(行号)**: `dayu/cli/composer.py:624-625`
- **修复机制**: handler 入口处行 624 `if editor_tasks:` 检查 set 非空时直接 `return`（no-op）。显式 editor task（行 656-665）与 unset public system editor task（行 638-653）均进入同一个 `editor_tasks: set[_EditorTask]`，done callback 或 composer teardown（`_cancel_editor_tasks` 行 930-952）负责消费并释放 slot。集合大小保持 `0..1`。
- **直接证据**:
  - 行 624 `if editor_tasks: return` — 同步 handler 在 set 非空时直接 no-op，不存在 event loop 调度窗口。
  - 行 646/657 `editor_tasks.add(task)` — 显式与系统 task 进入同一 set。
  - 行 886/918 `editor_tasks.discard(task)` — done callback 消费后释放。
  - 行 930-952 `_cancel_editor_tasks` — teardown 先 cancel 再逐 task await，最后 `editor_tasks.clear()` 清空。
- **Owner test 覆盖**:
  - `test_repeated_editor_shortcut_while_pending_launches_one_task_and_write`（行 917-967）：第一个 handler 触发后 round trip 被 barrier 阻塞，同步重复触发 handler，断言只有一个 round trip task（行 956）、一次 `run_in_terminal` 调用（行 959）、一个 process call（行 964）、一次 public `buffer.document` write（行 966-967）。
- **未新增第二状态机**: 复用既有 editor task set 为唯一 pending 真源，无新增枚举、flag 或状态变量。
- **裁决**: S2-C03 已真正关闭。✅

### S2-C04 — strict updated text type（状态：已关闭 ✅）

- **入口/函数**: `_run_explicit_editor_round_trip`
- **文件(行号)**: `dayu/cli/composer.py:788`
- **修复机制**: `updated_text: str` 严格类型声明（行 788），不再为 `str | None`。所有可达行 851 的路径均已完成 UTF-8 readback 赋值（行 828）；nonzero 路径提前 `return CANCELLED`（行 823）；异常路径提前 raise。删除不可达 `updated_text is None` 检查与对应 `RuntimeError`。
- **直接证据**:
  - 行 788 `updated_text: str` — 不再包含 `None`。
  - 无 `if updated_text is None:` 分支 — previous line 821-822 的 dead branch 已删除。
  - 行 828 `updated_text = temporary_path.read_bytes().decode("utf-8")` — 唯一赋值点，收窄为 `str`。
- **裁决**: S2-C04 已真正关闭。✅

## 额外审查项

### 新 TypeAlias `_EditorTask`

- **文件(行号)**: `dayu/cli/composer.py:79-82`
- **审查结论**: 无问题。`_EditorTask` 是 `asyncio.Task[_EditorProcessOutcome] | asyncio.Task[None]` 的 TypeAlias，正确描述两种 editor task 的并集类型。使用位置一致（`PromptToolkitInteractiveComposer._editor_tasks`、`_build_interactive_key_bindings`、`_cancel_editor_tasks`、两个 done callback）。`from typing import TypeAlias` 导入（行 22）符合 Python 3.11 目标环境。任务类型区分依赖 handler 中的路径分离（显式 vs 系统），两个 done callback 各自接收正确的 task 子类型，`add_done_callback` + `partial` 在运行时保证类型安全。无类型收窄缺口。

### System editor task ownership

- **审查范围**: `buffer.open_in_editor(validate_and_handle=False)` 路径（行 638-654）、`_consume_system_editor_task`（行 903-927）、teardown `_cancel_editor_tasks`（行 930-952）。
- **审查结论**: ownership 边界清晰正确。Composer 拥有 task 生命周期：创建（行 639）、强引用追踪（`editor_tasks.add` 行 646）、done callback 消费（行 647-653）、teardown 取消+等待（行 394 via `_cancel_editor_tasks`）。System editor 的内部行为（tempfile、subprocess、buffer update）由 prompt_toolkit 拥有，composer 只拥有 task reference 与 diagnostic projection。不存在 composer 越权管理 prompt_toolkit 内部状态或 prompt_toolkit 泄漏状态到 composer 的问题。Sync exception（`except Exception` 行 640）与 async exception（done callback 行 923 `except Exception`）分别正确捕获。

### BaseException re-raise 最小正确性

- **文件(行号)**: `dayu/cli/composer.py:836-840`
- **审查结论**: 正确且最小。`except BaseException` 在本 coroutine 上下文中等价于 `except (Exception, asyncio.CancelledError)`——`KeyboardInterrupt`、`SystemExit`、`GeneratorExit` 不会出现在 await 点。裸 `raise`（行 840）保留原始 traceback 与异常链。设计意图（标记 primary failure 并原样传播所有异常类型）与 `asyncio` 取消语义一致。`except Exception`（仅捕获非取消异常）会漏掉 `CancelledError`（Python 3.9+ `BaseException` 子类），不能替代当前写法。无需要收窄的理由。

### 未发现新的 teardown / fallback / diagnostic drift

- **teardown**: `_cancel_editor_tasks`（行 930-952）两阶段 cancel+await 正确，`CancelledError` 被吸收（行 946-947），其他 `Exception` 被静默消费（行 948-951，done callback 已是唯一 diagnostic owner），最后 `editor_tasks.clear()`（行 952）清空。无孤儿 task、无 pending-task warning。
- **fallback**: unset VISUAL/EDITOR → `command is None` → 调用 public `Buffer.open_in_editor(False)`（行 639），与 accepted plan §4 一致。同步异常与异步异常分别处理，不进入 CLI launcher。
- **diagnostic**: 配置错误（`_editor_configuration_error_message`）、action 错误（`_editor_action_error_message`）、unexpected 错误（`_unexpected_editor_error_message`）均不含命令正文、路径、异常正文或 env 内容。`_write_editor_diagnostic`（行 1011-1025）最外层 `except Exception: return` 正确防止 callback traceback。

### `updated_text: str` 裸类型标注

- **文件(行号)**: `dayu/cli/composer.py:788`
- **审查结论**: 非缺陷，属观察项。`updated_text: str` 是裸类型标注而非初始化赋值，变量仅在 `try` block 内（行 828）被首次赋值。所有可达行 851（使用 `updated_text`）的控制流路径均已确保赋值：success path（readback 成功 → 赋值 → 无 await 可被取消 → 到达行 851）；nonzero path（行 823 提前 return）；异常 path（提前 raise）。pyright 能证明该安全性（focused pyright 零错误）。未来维护者若在行 823 与行 836 之间插入可能跳过赋值的新分支，pyright 会报告 possibly-unbound 错误作为静态防护。无需修改。

## Open Questions

无。

## Residual Risk

1. **真实 PTY editor suspend/resume**：`covered by later approved slice S8`。S2 测试使用 pipe input 模拟，未覆盖真实 PTY 下 editor 进程的 terminal suspend/resume（Ctrl-Z、fg）、SIGTSTP/SIGCONT 交互。S8 real evidence 必须包含真实 editor 路径的最小矩阵。

2. **Windows text-mode newline**：`out of scope`。当前 interactive/PTY contract 与 tests 明确为 POSIX，本 work unit 不扩张平台语义。

3. **S1 corrective gate（full pyright）**：`utils/smoke_cli_init_provider_matrix.py:2386` 与 `utils/smoke_host_public_awaiting_entrypoint.py:808` 的两处 `explicit_config_dir` 残留是 S1 引入的 cross-slice regression，由独立 S1 corrective gate 在 S2 accepted 后、S3 前收口，以 full `python -m pyright` 零错误为 acceptance signal。本 reviewer 不误判为 S2 pass，也不给 S2 修复建议。

4. **`CANCELLED` 正常返回 + cleanup OSError 双故障**：当 editor 返回 nonzero（CANCELLED）且 tempfile unlink 失败时，`finally` 中 `primary_failure = False`（非异常路径），cleanup `OSError` 会覆盖 `CANCELLED` 正常返回形成 `CLEANUP_FAILED` 诊断。此行为可辩护——cleanup failure 是此路径唯一真实故障，且 tempfile 泄漏应被报告——但改变了"nonzero 静默 cancel"的用户体验。概率极低（editor nonzero + filesystem failure），不构成 closing blocker。

## Verdict

四项 accepted findings（`S2-C01`–`S2-C04`）已由 composer owner 逐项真正关闭，owner tests 与 integration tests 覆盖双故障组合、同步 Document snapshot、EDITOR_PENDING singleton 和严格类型收窄。额外审查项（TypeAlias、system editor task ownership、BaseException re-raise）均无 drift 或新的 semantic ownership 问题。未发现新的 material finding。全仓 pyright 两处 utils 残留确认为 S1 corrective gate，不误判为 S2 pass。

**S2 fix gate 通过。**

---

*Review 完成。未修改实现/tests/artifacts/registry，未 stage/commit/push/PR。*
