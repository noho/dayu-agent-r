# WU-SEMANTIC-OWNERSHIP-01 P2-A Implementation Re-Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-A`
- Gate: implementation re-review（controller adjudication fix 后）
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-review-controller-adjudication.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-controller-validation.md`

Re-review 确认 DS F1 / DS F2 修复是否关闭，以及修复是否引入新的 blocking finding。

## Verdict

**pass** — DS F1 和 DS F2 均已关闭，修复未引入新的 correctness、semantic ownership、testing、pyright 或 README 问题。

---

## Closure Check

### DS F1：`session.py` 不再捕获 prompt/interactive 专属 usage exception ✅

**修复前状态：** `session.py` 从 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` import `CliCommandUsageError` / `CliInteractiveUsageError`，在顶层 catch 中直接捕获这两个跨模块异常类型。

**修复后状态：**

- `dayu/cli/errors.py` 新增 CLI 公共 `CliUsageError(ValueError)` 基类。
- `CliCommandUsageError(CliUsageError)`（`prompt.py:65`）、`CliInteractiveUsageError(CliUsageError)`（`interactive.py:57`）、`CliSessionUsageError(CliUsageError)`（`session.py:107`）均继承公共基类。
- `session.py:36` 只 import `CliUsageError`，不再 import `CliCommandUsageError` / `CliInteractiveUsageError`。
- `session.py:149` 捕获 `CliSessionUsageError` 处理 session-local usage errors。
- `session.py:152` 捕获 `CliUsageError` 处理 prompt/interactive resume 兼容 usage errors。
- 无更宽的错误吞噬：`CliUsageError` 只覆盖用户用法错误，`HostApiError`、`RuntimeLocationError`、`KeyboardInterrupt`、generic `Exception` 的 catch 层次未受影响。
- 无错误前缀回归：`CliSessionUsageError` 用 `"dayu-cli session: {exc}"` 前缀；`CliUsageError`（prompt/interactive resume）用 `"dayu-cli session resume: {exc}"` 前缀；两者均通过 `render_cli_error` 输出到 stderr。

**证据：** AST test `test_import_boundary.py` 自动化守卫 `session.py` 不从 prompt/interactive import 下划线符号。`grep` 确认 `session.py` 无 `CliCommandUsageError` / `CliInteractiveUsageError` import。

---

### DS F2：CLI Fins direct 本地取消路径不再构造 `FinsResultSummary` ✅

**修复前状态：** `_cancelled_result_summary()` 构造完整 `FinsResultSummary(status=CANCELLED, ...)` 携带 `FinsErrorKind`、`FinsResultStatus` 等业务 DTO 字段，仅用于提取 `exit_code`。

**修复后状态：**

- `_cancelled_result_summary()` 已删除。
- 新增 CLI-private `_CliDirectLocalExit(exit_code: int)`（`fins.py:101-107`），只携带 exit code。
- `_wait_for_terminal_handling_sigint` 返回类型改为 `FinsResultSummary | _CliDirectLocalExit`（`fins.py:663`）。
- SIGINT cancel 路径返回 `_CliDirectLocalExit(exit_code=EXIT_KEYBOARD_INTERRUPT)`（`fins.py:705`）。
- CLI 不再为本地取消构造任何 Fins business DTO。
- 终态竞态路径（`fins.py:699-703`）仍返回真实 `FinsResultSummary`，未受影响。

**证据：** `grep` 确认 `_cancelled_result_summary` 已从 `fins.py` 删除；`_CliDirectLocalExit` 只在 SIGINT 本地退出路径使用。

---

## Residual Findings（Controller 未接受，确认为安全 residual）

| Finding | Source | Controller Decision | Re-Review 确认 |
|---|---|---|---|
| session.py generic `Exception` catch 使用 inline format 而非 helper | MiMo F-1 | Not accepted | ✅ 不是 `HostApiError` 展示路径，不重复 Host error code/message mapping，不构成 P2-A owner boundary bug |
| 测试直接访问 `session_execution` 下划线 helper | MiMo F-2 / DS F3 | Not accepted | ✅ 同 owner implementation tests，不重新引入原始 cross-command private import 问题 |

以上 residual 均不构成 P2-A blocker。

---

## `dayu/cli/errors.py` 合规检查 ✅

| 约束 | 状态 | 证据 |
|---|---|---|
| AGENTS.md 类型约束 | ✅ | `CliUsageError(ValueError)` 有明确基类；无 `object`、`Any`、无类型参数 |
| AGENTS.md docstring 约束 | ✅ | 模块级中文概览 docstring；类中文 docstring |
| 分层约束 | ✅ | 只依赖标准库（`__future__.annotations`）；不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` |
| 兼容性代码 | ✅ | 无兼容性 re-export、wrapper 或 facade |
| `__all__` 导出 | ✅ | `("CliUsageError",)` |

**观察（不阻断）：** `CliFinsUsageError(ValueError)`（`fins.py:92`）和 `CliInitUsageError(ValueError)`（`init.py:52`）仍直接继承 `ValueError`，未继承新 `CliUsageError` 基类。这不影响 P2-A 语义正确性（session.py 不捕获这两个异常），但若后续要统一 CLI usage error 层次，可考虑让它们也继承 `CliUsageError`。属于后续 cleanup 范围。

---

## New Findings

无。修复范围精简，只新增 `errors.py` 公共基类和 `_CliDirectLocalExit` CLI-private 类型，未引入新的 correctness、semantic ownership 或 testing 问题。

---

## Validation Notes

Re-review 独立运行验证命令确认 controller validation 结果仍有效：

```
source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py tests/cli/test_import_boundary.py
# → 129 passed, 3 warnings

source .venv/bin/activate && pyright
# → 0 errors, 0 warnings, 0 informations

git diff --check
# → passed
```

---

## Residual Risks

| Risk | Owner | Destination |
|---|---|---|
| MiMo F-1: session.py generic catch inline format 与 helper format 潜在不一致 | session command | P2-B/C 或日常 cleanup |
| MiMo F-2 / DS F3: 测试直接访问 session_execution 下划线 helper | session_execution owner | 同 owner 内正常重构成本 |
| `CliFinsUsageError` / `CliInitUsageError` 未继承 `CliUsageError` | CLI 层 | 后续 cleanup（统一 CLI usage error 层次） |
| P2-B memory/test hardening 未触碰 | P2-B owner | 后续 sub WU |
| P2-C fallback prompt source-of-truth 未触碰 | P2-C owner | 后续 sub WU |
