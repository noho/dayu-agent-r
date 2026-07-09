# WU-SEMANTIC-OWNERSHIP-01 P2-A Implementation Re-Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-A`
- Gate: implementation re-review（controller adjudication fix 后）
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-review-controller-adjudication.md`
- Initial DS review: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-review-ds.md`
- Initial MiMo review: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-review-mimo.md`
- Review type: adversarial re-review（不改代码，只验证 DS F1/DS F2 关闭）

## Verdict

**pass**

DS F1 和 DS F2 均已关闭。controller adjudication fix 没有引入新的 correctness、semantic ownership、testing、pyright 或 README 问题。MiMo/DS 未接受的 low/info findings 仍可安全作为 residual，不构成 P2-A blocker。

---

## Closure Check

### DS F1: `session.py` 不再捕获 prompt/interactive 专属 usage exception

**原始 finding：** `session.py` 跨模块依赖 `CliCommandUsageError` / `CliInteractiveUsageError`（定义在 prompt/interactive command module），未来各自的 usage error 类型演进时 session command 需要同步更新。

**修复：** Controller 接受 DS F1，在 CLI 公共层新增 `CliUsageError` 基类，让 prompt/interactive/session 的 usage error 继承同一公共基类，`session.py` 只捕获公共基类。

**关闭确认：**

| 检查项 | 状态 | 证据 |
|---|---|---|
| 新增 CLI 公共 `CliUsageError` 基类 | ✅ | `dayu/cli/errors.py:11` — `class CliUsageError(ValueError)` |
| `CliCommandUsageError` 继承 `CliUsageError` | ✅ | `dayu/cli/commands/prompt.py:65` — `class CliCommandUsageError(CliUsageError)` |
| `CliInteractiveUsageError` 继承 `CliUsageError` | ✅ | `dayu/cli/commands/interactive.py:57` — `class CliInteractiveUsageError(CliUsageError)` |
| `CliSessionUsageError` 继承 `CliUsageError` | ✅ | `dayu/cli/commands/session.py:107` — `class CliSessionUsageError(CliUsageError)` |
| `session.py` 不再导入 `CliCommandUsageError` / `CliInteractiveUsageError` | ✅ | `rg "CliCommandUsageError\|CliInteractiveUsageError" dayu/cli/commands/session.py` 无命中 |
| `session.py` 捕获 `CliUsageError` 公共基类 | ✅ | `session.py:152-154` — `except CliUsageError as exc:` 处理 prompt/interactive resume 兼容 usage error |
| session-local usage error 仍精确捕获 | ✅ | `session.py:149-151` — `except CliSessionUsageError as exc:` 先于 `CliUsageError`，确保 session-local 错误前缀为 `"dayu-cli session:"` |
| 无错误前缀回归 | ✅ | session-local: `"dayu-cli session: {exc}"`；resume 兼容: `"dayu-cli session resume: {exc}"` |
| 无更宽的错误吞噬 | ✅ | `CliUsageError` 是 `ValueError` 子类，不扩大 `session.py` 的异常捕获范围 |
| AST import boundary test 仍通过 | ✅ | `test_import_boundary.py` 1 passed |

**结论：DS F1 已关闭。**

---

### DS F2: CLI Fins direct 本地取消路径不再构造 `FinsResultSummary`

**原始 finding：** `_cancelled_result_summary()` 在 CLI 层构造完整 `FinsResultSummary(status=CANCELLED, ...)` 包含 `error_kind`、`error_message` 等业务字段，与 plan S2 "不在 CLI 构造 FinsEvent/FinsResultSummary fallback" 存在张力。构造完整业务 DTO 只为取 `exit_code` 字段，存在过度构造。

**修复：** Controller 接受 DS F2，将本地取消路径替换为 CLI-private `_CliDirectLocalExit`，只携带 `exit_code`。

**关闭确认：**

| 检查项 | 状态 | 证据 |
|---|---|---|
| `_cancelled_result_summary()` 已删除 | ✅ | `rg "_cancelled_result_summary" dayu/` 无命中 |
| 新增 CLI-private `_CliDirectLocalExit` | ✅ | `dayu/cli/commands/fins.py:100-107` — frozen dataclass，仅含 `exit_code: int` |
| 不再构造 Fins 业务 DTO | ✅ | `_CliDirectLocalExit` 不依赖 `FinsResultSummary`、`FinsResultStatus`、`FinsErrorKind` |
| SIGINT 取消路径返回 `_CliDirectLocalExit` | ✅ | `fins.py:704-705` — `render_fins_direct_local_exit_after_cancel()` 后 `return _CliDirectLocalExit(exit_code=EXIT_KEYBOARD_INTERRUPT)` |
| terminal result race 保留真实 `FinsResultSummary` | ✅ | `fins.py:699-703` — event task 在取消后仍完成时返回真实 terminal result |
| 类型签名正确 | ✅ | `_wait_for_terminal_handling_sigint` 返回 `FinsResultSummary \| _CliDirectLocalExit` |
| 测试覆盖取消路径 | ✅ | `test_sigint_cancels_stream_task_without_job_id:955` — `assert isinstance(result, fins_command._CliDirectLocalExit)` + `assert result.exit_code == FINS_DIRECT_EXIT_KEYBOARD_INTERRUPT` |
| 测试覆盖 terminal result race | ✅ | `test_cancel_race_does_not_override_terminal_result:1000` — `assert isinstance(result, FinsResultSummary)` + `assert result.status is FinsResultStatus.SUCCESS` |
| `FinsResultSummary` 等 import 保留的用途合法 | ✅ | 诊断日志（`_fins_event_verbose_diagnostic_parts`、`_fins_event_debug_diagnostic_parts`）与 terminal result race 路径仍需这些类型；不涉及 S2 目标场景 |

**结论：DS F2 已关闭。**

---

## MiMo/DS Unaccepted Findings Residual Assessment

| Finding | Source | Controller disposition | Residual safety |
|---|---|---|---|
| session generic `Exception` catch inline format vs helper | MiMo F-1 | Not accepted | **安全。** `session.py:169-171` 的 generic `Exception` path 处理非 `HostApiError` 异常，不重复 Host error code/message 映射；若未来 helper core format 变化，generic path 不受影响。风险仅限文本不一致，且触发概率极低。 |
| Tests call `session_execution` private state-machine helpers | MiMo F-2 / DS F3 | Not accepted | **安全。** 测试访问的是 `session_execution` 模块自身的内部符号，属于同一 owner 内的 implementation test，不构成原始 bug（`session.py` 跨模块导入 `prompt.py`/`interactive.py` 私有符号）的复现。 |
| prompt/interactive submit-stage `HostApiError` 缺少直接集成测试 | DS residual | Not accepted | **安全。** session resume TOCTOU 测试（`test_session_command.py`）间接覆盖了 submit 阶段 `HostApiError` 处理路径；prompt/interactive create 阶段测试覆盖了入口 command presentation。无已知未覆盖的 HostApiError code/mapping 分支。 |
| `_resume_host_error_message` 使用 `host_api_error_context` 而非完整 `format_host_api_error` | DS info | Not accepted | **安全。** `_resume_host_error_message` 有意添加 selector/session 上下文前缀后复用公共 `host_api_error_context` 核心格式化器；不重复 Host code/message owner。 |

**结论：四个未接受的 low/info findings 均可安全作为 residual，不构成 P2-A blocker。**

---

## `dayu/cli/errors.py` 合规检查

| 检查项 | 状态 | 证据 |
|---|---|---|
| 模块 docstring | ✅ | 中文说明 CLI adapter 层公共异常分类职责，明确不承载 Host/Service/Fins 业务事实 |
| `from __future__ import annotations` | ✅ | line 8 |
| `CliUsageError` 基类有中文 docstring | ✅ | line 12 — `"""CLI 用户用法错误基类。"""` |
| `__all__` 已定义 | ✅ | line 15 — `("CliUsageError",)` |
| 无 `object` / `Any` / `hasattr` / `getattr` | ✅ | 全文无上述符号 |
| 无 `type: ignore` 或 pyright suppression | ✅ | 全文无 |
| 分层约束 | ✅ | `dayu.cli.errors` 无 import；不依赖 Host/Service/Engine/Fins 任何层 |
| 无跨层依赖 | ✅ | 纯标准库 + `__future__` |

**结论：`dayu/cli/errors.py` 符合 AGENTS.md 类型/docstring/分层全部约束。**

---

## New Findings

**无。**

本次 re-review 在 DS F1/DS F2 fix 后的代码中未发现新的：

- Correctness 问题：所有测试通过（129 CLI + 1 import boundary + 156 扩展），逻辑无退化。
- Semantic ownership 问题：`CliUsageError` 是 CLI 公共层真源；prompt/interactive/session usage error 各自由 owner module 定义但共享公共基类；`_CliDirectLocalExit` 是 CLI-private 本地退出状态，不承载 Fins 业务语义。
- Testing 问题：controller fix 后测试从 128 → 129 passed（新增对 `_CliDirectLocalExit` 的覆盖）。
- Pyright 问题：0 errors, 0 warnings, 0 informations。
- README 问题：controller validation 已确认 `tests/README.md` 更新；其他 README 未触发。

---

## Validation Notes

本 re-review 执行的验证命令与结果：

```
source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_import_boundary.py
# → 129 passed, 3 warnings

source .venv/bin/activate && pyright
# → 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/cli/test_runtime_display.py tests/cli/test_arg_parsing.py tests/cli/test_session_terminal_cursor.py tests/cli/test_activity_renderer.py tests/service/test_fins_direct.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py
# → 156 passed, 3 warnings
```

与 controller adjudication 报告的结果一致（129 passed），pyright 干净，扩展验证全部通过。

---

## Propagation Audit（DS F1/DS F2 fix 增量）

### DS F1 fix: CliUsageError 公共基类

```
prompt.CliCommandUsageError(CliUsageError) ─┐
interactive.CliInteractiveUsageError(CliUsageError) ─┤
session.CliSessionUsageError(CliUsageError) ─────────┘
  → session.py: except CliUsageError as exc:
  → stderr + EXIT_USAGE_ERROR
```

**审计结果：** ✅ `session.py` 不再依赖 prompt/interactive 的具体异常类型名；只依赖 CLI 公共 `CliUsageError`。prompt/interactive 各自的 usage error 仍由各自 owner module 定义和抛出，未来各自演进其内部异常层次不影响 session command。

### DS F2 fix: _CliDirectLocalExit

```
SIGINT → cancellation_token.request_cancel()
  → event_task.cancel()
  → asyncio.CancelledError（stream 已在取消前清空）
    → _CliDirectLocalExit(exit_code=EXIT_KEYBOARD_INTERRUPT)
  → 或 event_task 完成（terminal result race）
    → 真实 FinsResultSummary（Service 产出）
  → _run_fins_direct_command_async: return terminal.exit_code
```

**审计结果：** ✅ CLI 本地取消路径不再构造 `FinsResultSummary`、`FinsResultStatus`、`FinsErrorKind` 等 Fins 业务 DTO。`_CliDirectLocalExit` 仅携带 `exit_code: int`，不投影任何业务 failure fact。terminal result race 路径保留真实 `FinsResultSummary` 传递。

---

## Residual Risks（re-review 后更新）

| Risk | Severity | Owner | 说明 |
|---|---|---|---|
| session generic `Exception` catch inline format 与 helper 格式潜在不一致 | Low | 后续 WU | MiMo F-1，controller 未接受，residual |
| prompt/interactive submit-stage `HostApiError` 缺少直接集成测试 | Low | 后续 WU | DS 原 residual，controller 未接受，residual |
| `_resume_host_error_message` 与 `format_host_api_error` 存在轻微重复 | Info | 后续 cleanup | DS 原 info，controller 未接受，residual |
| P2-B memory/test hardening 未触碰 | — | P2-B owner | 后续 sub WU |
| P2-C fallback prompt source-of-truth 未触碰 | — | P2-C owner | 后续 sub WU |
| `CliFinsUsageError` 继承 `ValueError` 而非 `CliUsageError` | Info | 后续 cleanup | Fins direct 无跨模块 usage error 消费场景（与 DS F1 场景不同），当前设计合理；若未来统一 CLI usage error 层次可考虑迁移 |
