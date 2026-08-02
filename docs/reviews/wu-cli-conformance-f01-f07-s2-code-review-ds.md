# Code Review — WU-CLI-CONFORMANCE-F01-F07 S2 (F02 external editor)

## Scope

- Mode: current changes（未提交 S2 diff 相对 HEAD a41526ec）
- Branch: `codex/interactive-oracle`
- Base: `a41526ec`（S1 accepted commit）
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s2-code-review-ds.md`
- Included scope:
  - `dayu/cli/composer.py`（+525 行，生产代码）
  - `tests/cli/test_interactive_composer.py`（+519 行，owner-level tests）
  - `tests/cli/test_interactive_command.py`（+238 行，integration tests）
- Reference documents:
  - Accepted plan §4（`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`）
  - Frozen evidence: `observed-behavior-pr190-closeout.md`、`compaction-invalid-response-audit-pr190.md`（SHA-256 已核验）
  - S2 implementation artifact: `docs/reviews/wu-cli-conformance-f01-f07-s2-implementation-codex.md`
  - `AGENTS.md`
- Excluded scope: S1、S3-S8、utils/、Host/Engine 生产代码、registry、design docs
- Parallel review coverage: 无（单 reviewer 全路径走读）

## Validation Summary

- **Focused pytest**: `tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py` — 99 passed, 3 warnings（均为 edgar 依赖既有 deprecation warning）。
- **Focused pyright**: `dayu/cli/composer.py tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py` — 0 errors, 0 warnings, 0 informations。
- **Coverage**: `dayu/cli/composer.py` — 356 statements / 33 missing / 91%（>=80% 达标）。
- **全仓 pyright cross-slice regression**: 两处 utils `explicit_config_dir` 残留（`smoke_cli_init_provider_matrix.py:2386`、`smoke_host_public_awaiting_entrypoint.py:808`）— 确认为 S1 引入的已知 debt，与 S2 diff 无关。Implementation artifact 将其分类为 `covered by later approved slice S8`，评估准确。

## Findings

### 1-未修复-中-`_run_explicit_editor_round_trip` finally 块 CLEANUP_FAILED 覆盖 try 块原始异常

- **入口/函数**: `_run_explicit_editor_round_trip` 的 `finally` 块
- **文件(行号)**: `dayu/cli/composer.py:811-819`
- **输入场景**: 显式 editor 进程 spawn 失败（`OSError` → `SPAWN_FAILED`），且随后 tempfile `unlink` 也因文件系统异常失败（例如父目录权限变更、NFS stale handle）。
- **实际分支**: try 块 `raise _EditorActionError(SPAWN_FAILED)`（行 793），Python 隐式保存该异常后进入 finally 块；`temporary_path.unlink(missing_ok=True)` 抛 `OSError`（行 814），finally 块执行 `raise _EditorActionError(CLEANUP_FAILED)`（行 816-819），替换原始 `SPAWN_FAILED`。
- **预期行为**: 原始业务错误（spawn 失败）应优先于清理错误向 done callback 报告；清理失败最多作为次要 diagnostic 记录。
- **实际行为**: done callback 只收到 `_EditorActionError(CLEANUP_FAILED)`，用户看到"无法清理编辑文件，草稿已保留"而非"指定编辑器无法启动，草稿已保留"。tempfile 未清理的事实也被错误消息间接传达，但 spawn 失败的真正原因被完全掩盖。
- **直接证据**: 行 793 `raise _EditorActionError(SPAWN_FAILED)` → 行 814 `temporary_path.unlink(missing_ok=True)` 抛 `OSError` → 行 816-819 `raise _EditorActionError(CLEANUP_FAILED)` 替换。Python 语义：finally 块中的 `raise` 会丢弃 try 块中未处理的异常。
- **影响**: 用户诊断错误方向（去排查文件权限而非 editor 配置）；tempfile 泄漏（unlink 失败意味着草稿文件残留于磁盘）。
- **建议改法和验证点**: 在 finally 块中捕获 `OSError` 不重新抛出，改为通过安全通道（例如 `_write_editor_diagnostic`）记录次要 diagnostic，让原始异常正常传播。如果确实认为 cleanup 失败是更高级别安全事件，应显式使用 `__suppress_context__` 或 `ExceptionGroup`（Python 3.11+）同时保留两条信息。验证点：模拟 tempfile 目录只读后的 spawn 失败场景，断言 diagnostic 包含 spawn 失败信息且 tempfile 泄漏被记录。
- **修复风险（低）**: 变更仅涉及 finally 块的异常策略；不影响正常路径。
- **严重程度（中）**: 仅当双故障同时发生时才触发（概率低），但发生时错误信息完全误导且 tempfile 泄漏。

### 2-未修复-低-`_run_explicit_editor_round_trip` updated_text is None 检查不可达

- **入口/函数**: `_run_explicit_editor_round_trip` 末尾防御性检查
- **文件(行号)**: `dayu/cli/composer.py:821-822`
- **输入场景**: 所有成功到达行 821 的路径。
- **实际分支**: 行 821 的 `if updated_text is None:` 检查。追溯到所有可达此处的路径：return code 非零时行 798 提前 return `CANCELLED`；return code 为零时行 803 `updated_text = temporary_path.read_bytes().decode("utf-8")` 成功赋值 `str`，或行 805 raise `_EditorActionError(READBACK_FAILED)` 提前退出。行 809 `updated_text = updated_text[:-1]` 仅将 `str` 切片为 `str`。不存在任何路径使 `updated_text` 为 `None` 且能到达行 821。
- **预期行为**: 若此检查是安全性兜底，应删除并依赖 mypy/pyright 的 exhaustive type narrowing；若确实存在遗漏的 None 路径，该路径本身就是需要修复的 bug。
- **实际行为**: Dead code；`RuntimeError("editor updated text is missing after successful readback")` 永远不会被抛出。静态分析工具（mypy strict、pyright）已能证明该分支不可达。
- **直接证据**: 行 798 `return _EditorProcessOutcome.CANCELLED`（提前退出），行 803 `updated_text = ...decode(...)`（类型收窄为 `str`），行 805 `raise`（提前退出）。从初始化 `None` 到行 821 之间不存在 `None` 保持不变且不提前退出的路径。
- **影响**: 代码误导维护者以为存在 None 路径；静态分析工具可能发出 unreachable code 警告（当前 pyright 配置未开启此检查）。
- **建议改法和验证点**: 删除行 821-822 的 None 检查；或将 `updated_text` 类型声明改为 `str`（移除 `| None`），在 readback 成功处直接赋值并让 mypy 证明后续不需要 None 检查。
- **修复风险（低）**: 纯机械删除不可达代码。
- **严重程度（低）**: 不影响运行时行为；仅影响代码可维护性。

### 3-未修复-低-`_write_editor_diagnostic` 的 `except Exception` 吞掉 `KeyboardInterrupt` 和 `SystemExit` 之外的所有 sink 错误——正确但边界值得记录

- **入口/函数**: `_write_editor_diagnostic`
- **文件(行号)**: `dayu/cli/composer.py:956-970`
- **输入场景**: stderr 流已关闭、底层 fd 损坏、磁盘满。
- **实际分支**: `try: print(message, file=stderr)` → `OSError` → `except Exception: return`。
- **预期行为**: diagnostic sink 失败时吞掉异常，不触发 prompt_toolkit callback 的第二 traceback。
- **实际行为**: 符合预期。
- **直接证据**: 行 965-970，`except Exception` 覆盖 `OSError`、`ValueError` 等所有 `Exception` 子类；`BaseException` 子类（`KeyboardInterrupt`、`SystemExit`、`GeneratorExit`）不被吞掉。
- **影响**: 无。这是正确且必要的防御设计。记录为 finding 仅用于确认 review 已覆盖此边界，并对未来维护者说明：此处的 `except Exception` 是特例，不等于鼓励宽泛 catch。
- **建议改法和验证点**: 无需修改。如需增强可观测性，可在 `except` 分支中调用 `logging`（而非再次写 stderr 导致无限递归），但不属于本次 scope。
- **修复风险（无）**: 无需修复。
- **严重程度（低）**: 记录性 finding，非缺陷。

## Validation Checklist（逐项走读确认）

### env precedence / 显式空白

- **VISUAL key 存在即优先**：`_resolve_explicit_editor_command` 行 666-669 — `"VISUAL" in environ` 检查，True 时选 VISUAL 且不尝试 EDITOR。✅
- **显式空白不降级**：行 674 `raw_command.strip() == ""` 对空白 `"   "` 抛出 `EMPTY_COMMAND`，不 fallback 到 EDITOR。✅
- **两个 key 都不存在返回 None**：行 670-671 `return None`，触发 system fallback。✅
- **测试覆盖**：`test_editor_environment_selection_is_typed_and_visual_key_has_priority` 参数化 VISUAL 空白覆盖降级拒绝，`test_unset_editor_uses_only_public_system_fallback` 覆盖 unset → `open_in_editor(False)`。✅

### shlex / which / exec validation

- **shlex.split**：行 680 `argv = tuple(shlex.split(raw_command))`；ValueError → `INVALID_SYNTAX`（行 681-685）；from None 隐藏 shlex 内部细节。✅
- **shutil.which**：行 725 `shutil.which(executable)`，无路径分隔符时搜索 PATH。✅
- **Path.resolve + expanduser**：行 724 `Path(executable).expanduser().resolve()`，处理含路径分隔符的命令。✅
- **is_file + X_OK**：行 702 `resolved_executable.is_file()` 拒绝目录；`os.access(resolved_executable, os.X_OK)` 拒绝 non-executable。✅
- **测试覆盖**：`_InvalidEditorConfigurationCase` 五元矩阵（BLANK、INVALID_SYNTAX、MISSING、DIRECTORY、NON_EXECUTABLE）全覆盖。✅

### public run_in_terminal exact argv 和 no-shell / no-private / no-fallback

- **exact argv 构造**：行 782-786 — `(str(resolved_executable), *command.argv[1:], str(temporary_path))`，不含 shell。✅
- **public run_in_terminal**：行 788-791 — `run_in_terminal(partial(_run_editor_process, exact_argv), in_executor=True)`，prompt_toolkit public API。✅
- **subprocess.run 无 shell**：行 838 — `subprocess.run(argv, check=False)`，默认 `shell=False`。✅
- **无 private API**：全程无 `_open_file_in_editor`、无 monkey-patch prompt_toolkit private method。✅
- **测试覆盖**：`test_explicit_editor_zero_uses_exact_argv_and_one_public_document_update` 断言 exact argv[:-1] == 预期，in_executor=True。✅

### secure tempfile

- **NamedTemporaryFile(delete=False)**：行 767-772，prefix=`dayu-editor-`、suffix=`.txt`、encoding=utf-8。✅
- **写入原 draft**：行 775 `temporary_file.write(original_document.text)`。✅
- **finally 清理**：行 814 `temporary_path.unlink(missing_ok=True)`。✅
- **测试覆盖**：所有 editor 测试路径断言 `not Path(exact_argv[-1]).exists()`（tempfile 已被删除）。✅

### CRLF / frozen one-LF readback

- **binary read 避免 text mode CRLF 改写**：行 803 `temporary_path.read_bytes().decode("utf-8")`。✅
- **至多删除一个末尾 LF**：行 809-810 `if updated_text.endswith("\n"): updated_text = updated_text[:-1]`。CRLF 结尾的 `\r\n` 仅删 `\n` 保留 `\r`，符合 frozen rule。✅
- **测试覆盖**：`test_explicit_editor_zero_uses_exact_argv_and_one_public_document_update` 用 `updated_bytes="编辑结果\r\n\n".encode()` 验证 CR 保留且仅删除一个 LF。✅

### cursor

- **原子回填**：行 823-826 `buffer.document = Document(text=updated_text, cursor_position=len(updated_text))`，单次 public setter 同时设置文本与光标。✅
- **失败保留原 document**：spawn/nonzero/readback 失败路径均不修改 `buffer.document`。✅
- **测试覆盖**：integration test `test_editor_failure_or_cancel_preserves_repl_until_explicit_submit` 验证 cursor position 恢复（`abc` + left arrow → cursor 在 `c` 前，editor cancel 后 `X\r` → `abXc`）。✅

### OSError actionable / nonzero silent / zero-only update / readback failure

- **spawn OSError → actionable**：行 792-796 catch `OSError` → `_EditorActionError(SPAWN_FAILED)` → done callback 产出一条含"无法启动"的诊断。✅
- **nonzero → silent cancel**：行 797-798 `if return_code != 0: return _EditorProcessOutcome.CANCELLED`，无 diagnostic 输出。✅
- **zero-only → readback + update**：行 800-810 zero rc 后读取、strip LF、更新 buffer。✅
- **readback failure → actionable**：行 805-808 catch `(OSError, UnicodeError)` → `_EditorActionError(READBACK_FAILED)`。✅
- **测试覆盖**：`test_explicit_editor_failure_matrix_preserves_document_and_cleans_tempfile` 参数化 `(SPAWN_ERROR, "无法启动", False)`、`(NONZERO, "", True)`、`(INVALID_UTF8, "无法读取", False)`。✅

### draft / history / REPL / zero Run

- **editor 动作不提交**：所有 editor 路径（配置错误、spawn 失败、nonzero、readback 失败、成功回填）都不产生 composer `SUBMIT` event。✅
- **成功回填后需显式 Enter**：`buffer.document` 更新后，用户仍需显式 Enter 才产生 submit event。✅
- **history 不变**：失败/cancel 路径不调用 `accept_submit`，history 不变。✅
- **integration 测试**：`test_editor_failure_or_cancel_preserves_repl_until_explicit_submit` 验证 editor 失败后 `submit_requests == []`、`history == []`、显式 submit 后 `history == ["abXc"]`、REPL 正常 EOF 退出。✅

### task ownership / callback / teardown / temp cleanup

- **强引用集合**：`PromptToolkitInteractiveComposer._editor_tasks: set[asyncio.Task[...]]`（行 287）。✅
- **done callback 消费异常**：行 640-647 `_consume_explicit_editor_task` 作为 `partial` done callback，消费 `_EditorActionError` 和 `Exception` 并投影诊断。✅
- **teardown 取消+等待**：行 388 `await _cancel_editor_tasks(self._editor_tasks)` 在 `read_event` finally 块中执行。✅
- **tempfile 清理**：`_run_explicit_editor_round_trip` finally 块 `unlink(missing_ok=True)`。✅
- **测试覆盖**：`test_composer_teardown_cancels_editor_task_consumes_exception_and_cleans_tempfile` 验证 task 被取消、异常被消费、tempfile 被删除、task 集合清空。✅

### 错误脱敏

- **配置错误消息**：`_editor_configuration_error_message` 只包含 source 变量名（VISUAL/EDITOR）和中文原因描述；不含命令正文、路径、env 内容。✅
- **action 错误消息**：`_editor_action_error_message` 只包含 source 变量名和中文描述；不含 argv、tempfile path、异常正文。✅
- **unexpected 错误消息**：`_unexpected_editor_error_message` 只包含 source 变量名和恢复动作；底层异常完全隐藏。✅
- **测试覆盖**：矩阵测试断言 diagnostic 不含 `Traceback`、不含 `sensitive draft`、不含 `secret`、不含 `configured_value`。✅

### 过度设计 / God helper / 宽泛 catch

- **过度设计**：不成立。所有新增类型（4 个 StrEnum、2 个 dataclass、2 个异常类、8 个函数）均在 accepted plan §4.2 明确列出，且有对应语义职责。✅
- **God helper**：不成立。`_run_explicit_editor_round_trip`（~70 行）是 round trip 生命周期内聚的最小实现；子操作（resolve、open、run process、consume、cancel、message format）各自独立为模块级函数。✅
- **宽泛 catch**：`_consume_explicit_editor_task` 的 `except Exception`（行 868）是 done callback 的最后防线，必须不抛出；`_cancel_editor_tasks` 的 `except Exception`（行 893）是 teardown 路径，必须完成清理；`_write_editor_diagnostic` 的 `except Exception`（行 968）是 diagnostic sink 的最后防线。三处均是最外层兜底，有明确文档说明"不主动抛出异常"，不是宽泛 catch 反模式。✅

### owner / integration tests 真实性

- **owner tests 使用真实 composer**：`test_interactive_composer.py` 使用 `PromptToolkitInteractiveComposer` + `create_pipe_input` + `DummyOutput` 的真实 prompt_toolkit session。✅
- **integration tests 走真实 REPL 路径**：`test_editor_failure_or_cancel_preserves_repl_until_explicit_submit` 使用 `_drive_interactive_tty_repl` 真实入口 + `PromptToolkitInteractiveComposer` + pipe input。✅
- **测试不依赖 fake composer**：editor integration 测试不使用 `_ScriptedComposer`，而是真实 composer 实例。✅
- **fake 仅用于非 editor 场景**：`_ScriptedComposer` 用于 submit/cancel/phase 等独立场景，不与 editor 测试混淆。✅

## Open Questions

1. **Windows 平台 text-mode write + binary-mode read 不对称**：`NamedTemporaryFile(mode="w")` 在 Windows 上会将 `\n` 转为 `\r\n` 写入；后续 editor 进程覆盖文件，但若 editor 未启动（spawn OSError），tempfile 中残留的初始 draft 带有 Windows 换行。当前项目主要运行于 macOS/Linux，Windows 路径不在本次 S2 test matrix 内（PTY test 有 `skipif(os.name != "posix")`）。是否需要在 `mode="w"` 处显式设置 `newline=""` 以消除跨平台不确定性？建议在 S8 集成阶段评估是否需要 Windows 兼容性验证。

2. **`run_in_terminal(in_executor=True)` 的 thread-pool executor 与 subprocess 并发**：`run_in_terminal` 使用默认 executor（`concurrent.futures.ThreadPoolExecutor`），多个 editor task 可并发运行。当前设计每个 composer 同一时刻只应有一个 pending editor task（用户无法在 editor 未返回时再按 Ctrl-X Ctrl-E），但并发安全性仍值得注意——两个 editor task 同时写各自 tempfile、各自尝试修改同一个 `buffer.document`。当前由 REPL 输入模型隐式保证单实例，S3 引入 queued followup 后是否仍成立？

## Residual Risk

1. **CLEANUP_FAILED 覆盖原始异常**（见 Finding 1）：双故障场景概率低但诊断误导，建议在 merge 前修复。
2. **真实 PTY editor suspend/resume**：S2 测试使用 pipe input 模拟终端，未覆盖真实 PTY 下 editor 进程的 terminal suspend/resume（Ctrl-Z、fg）、SIGTSTP/SIGCONT 交互。Implementation artifact 将其列为 `covered by later approved slice S8`。此风险不由 S2 owner 承担，但 S8 real evidence 必须包含真实 editor 路径（至少 vim/nano 的最小矩阵）。
3. **跨平台 tempfile 换行不确定性**（见 Open Question #1）：macOS/Linux 生产环境不受影响；Windows 部署前需额外验证。
4. **全仓 pyright 两处 S1 debt**：不为 S2 实现缺陷，S8 必须收口。

## Verdict

S2/F02 实现严格遵循 accepted plan §4 的 frozen contract。环境变量优先级（VISUAL key presence > EDITOR > unset system fallback）、shlex/which/exec 校验链、public `run_in_terminal` exact argv、secure tempfile 生命周期、CRLF 保留式 readback、cursor 原子回填、OSError/nonzero/readback 分支处理、draft/history/zero Run 语义、task ownership with done callback + teardown cleanup、错误脱敏全部正确实现并有 owner-level 与 integration tests 真实覆盖。

发现 1 个中等严重度 finding（finally 块异常覆盖）和 1 个低严重度 finding（不可达代码）。无高/严重 finding。建议修复 Finding 1 后 ship。

Implementation artifact 将全仓 pyright 两处 utils `explicit_config_dir` 残留分类为 S1 引入的 existing debt（`covered by later approved slice S8`），评估准确——残留来自 S1 删除字段后的机械闭包遗漏，与 S2 diff 无关，且 artifact 明确声明 S2 不越权修改 `utils/`。

---

*Review 完成。未修改实现/tests/artifact/registry，未 stage/commit/push/PR。*
