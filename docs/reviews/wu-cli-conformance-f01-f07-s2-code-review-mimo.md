# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `a41526ec`（S1 accepted commit / HEAD）
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-mimo.md`
- Included scope: `dayu/cli/composer.py`、`tests/cli/test_interactive_composer.py`、`tests/cli/test_interactive_command.py` 未提交 diff 相对 `a41526ec`
- Excluded scope: `utils/`、registry、README、design、Host、Service、Engine
- Parallel review coverage: 无

## Findings

### 001-未修复-中-`_run_explicit_editor_round_trip` finally cleanup error masks original exception

- **入口/函数**: `_run_explicit_editor_round_trip`
- **文件(行号)**: `dayu/cli/composer.py:811-819`
- **输入场景**: editor 成功修改 tempfile（return code zero），readback 成功，但 `temporary_path.unlink()` 抛出 `OSError`
- **实际分支**: finally block 中 `unlink` 抛 OSError → `_EditorActionError(CLEANUP_FAILED)` 替换 `try` body 中已排队的任意异常（包括 `READBACK_FAILED`）
- **预期行为**: cleanup 失败应作为次要错误记录或静默处理，不应掩盖 `try` body 中已存在的主要异常（readback 失败、spawn 失败等）
- **实际行为**: Python finally 语义——finally 中 raise 替换当前 pending exception。若 `try` body 已因 `READBACK_FAILED` 抛出 `_EditorActionError`，finally 中的 `CLEANUP_FAILED` 会完全替换它，用户看到的是"无法清理编辑文件"而非"无法读取编辑结果"
- **直接证据**: `dayu/cli/composer.py:811-819`——finally block 无条件 raise `_EditorActionError(CLEANUP_FAILED)`，无 `suppress` 或 exception chaining 保护
- **影响**: 错误 answer——用户收到的 diagnostic 指向 cleanup 而非实际失败原因（readback），降低可操作性
- **建议改法和验证点**: finally 中 cleanup 失败应只记录或静默，不 raise。例如用 `try: ... except OSError: pass` 包裹 `unlink`，或在 `_EditorActionFailureReason` 中增加 `CLEANUP_FAILED` 作为不掩盖主异常的附加信息。验证：构造 readback 失败 + unlink 失败的组合，断言 diagnostic 指向 readback 而非 cleanup
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-低-public `build_interactive_key_bindings` editor tasks orphaned after binding lifetime

- **入口/函数**: `build_interactive_key_bindings`
- **文件(行号)**: `dayu/cli/composer.py:462-467`
- **输入场景**: 外部调用方使用 public `build_interactive_key_bindings()`（非通过 `PromptToolkitInteractiveComposer`），用户触发 Ctrl+X Ctrl+E 且 VISUAL/EDITOR 指向有效命令
- **实际分支**: `editor_tasks=set()` 创建一次性隔离集合；task 被加入后，无外部引用持有该集合，无法在 binding 生命周期结束时 cancel/cleanup
- **预期行为**: public API 创建的 editor task 应在 binding 生命周期结束时被清理，或文档明确说明 public API 不支持显式 editor task lifecycle
- **实际行为**: task 加入一次性 `set()` 后，该 set 无外部持有者；task 完成后 done callback 调用 `editor_tasks.discard(task)` 从已丢弃的 set 中移除，但若 editor 进程挂起，task 永远 pending
- **直接证据**: `dayu/cli/composer.py:466`——`editor_tasks=set()` 创建匿名集合；`dayu/cli/composer.py:638-647`——task 加入该集合后无外部清理路径
- **影响**: 生产代码通过 `_build_interactive_key_bindings` 使用 composer 持有的共享集合，不受影响。public API 的孤立 task 仅在外部直接调用时出现，属于 API 语义不完整
- **建议改法和验证点**: 在 `build_interactive_key_bindings` docstring 中明确说明：返回的 bindings 不管理显式 editor task lifecycle，调用方应使用 `PromptToolkitInteractiveComposer` 以获得完整 teardown。或移除 public API 中的显式 editor 路径
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无

## Residual Risk

- `covered by later approved slice S8`: 真实 PTY 下不同 editor 的 terminal suspend/resume、最终真实 CLI evidence 与 full-suite/full-pyright aggregate closure
- `covered by current owner invariant`: 显式 argv 不经过 shell，配置错误、spawn、nonzero、readback 与 teardown 都只由同一 composer owner 产生/投影；screen projection 不是判断真源
- `pyright utils existing debt`: 全仓 pyright 的两处 utils 旧参数错误（`utils/smoke_cli_init_provider_matrix.py:2386`、`utils/smoke_host_public_awaiting_entrypoint.py:808`）确认为 S1 引入的已知 cross-slice 回归，不来自 S2 diff。implementation artifact 把它称 `existing debt` 并分类为 `covered by later approved slice S8` 是准确的。S2 focused 三文件 pyright 零错误
- 当前没有未分类的 S2 residual risk

## Validation

- focused pytest（99 passed）与 coverage（91%，>=80%）均通过
- focused pyright（0 errors）通过
- 全仓 pyright 两处 utils 错误为 S1 已知 debt，不影响 S2 正确性
- `_run_editor_process` 使用 `subprocess.run(argv, check=False)` 无 shell、无 private API
- `run_in_terminal` 使用 public API + `in_executor=True`
- diagnostic 消息不含命令正文、异常正文、argv、tempfile 路径或 draft 内容

## Verdict

implementation 基本正确，与 plan §4 冻结 contract 一致。两个 findings 均非阻断性：001 是 cleanup 错误掩盖主异常的边界 case，002 是 public API 文档缺口。integration tests 使用真实 `PromptToolkitInteractiveComposer → _drive_interactive_tty_repl` 链路，editor failure 矩阵（missing/nonexec/spawn/nonzero）覆盖完整，draft/cursor/history/zero-Run contract 经真实 REPL 验证。
