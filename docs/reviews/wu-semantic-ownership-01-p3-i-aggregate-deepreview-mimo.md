# WU-SEMANTIC-OWNERSHIP-01 P3-I Aggregate DeepReview (AgentMiMo)

## Scope

- Mode: current changes (aggregate P3-I range)
- Branch: `phaseflow/host-issues-control`
- Base: `b24b0a76`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-i-aggregate-deepreview-mimo.md`
- Included scope:
  - `dayu/web/__init__.py`, `dayu/web/__main__.py` — S1 public entrypoint
  - `dayu/wechat/__init__.py`, `dayu/wechat/main.py` — S1 public entrypoint
  - `dayu/render/__init__.py`, `dayu/render/render.py` — S1 public entrypoint
  - `dayu/runtime/argparse_exit.py` — S1 shared runtime helper
  - `dayu/runtime/__init__.py` — S1 docstring update
  - `dayu/cli/session_execution.py` — S2 cursor advancement logic
  - `README.md`, `dayu/README.md`, `tests/README.md` — S1/S2 README truth
  - `docs/host/issues-implementation-control.md` — control doc records
  - `tests/cli/test_public_package_entrypoints.py` — S1 tests
  - `tests/cli/test_prompt_command.py` — S2 cursor tests
  - `tests/cli/test_interactive_command.py` — S2 cursor tests
- Excluded scope: `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`, Host/Engine/Service production code
- Parallel review coverage: 无

## Review Sources

- Plan: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Aggregate validation: `docs/reviews/wu-semantic-ownership-01-p3-i-aggregate-validation.md`
- S1 artifacts: implementation, code review (MiMo/DS), controller adjudication, fix, re-review (MiMo/DS), controller re-adjudication
- S2 artifacts: implementation, code review (MiMo/DS), controller adjudication, fix, re-review (MiMo/DS), controller re-adjudication

## Verification Matrix

| 验证项 | 结果 |
|--------|------|
| CLI test suite (`pytest tests/cli -q`) | ✅ 294 passed, 3 warnings |
| Type check (`pyright dayu/ tests/ utils/`) | ✅ 0 errors, 0 warnings, 0 informations |
| Range whitespace (`git diff --check b24b0a76..HEAD`) | ✅ passed |
| Module help smoke (`python -m dayu.web/wechat.main/render.render --help`) | ✅ 3/3 passed |
| README command surface audit (`rg "dayu-web\|dayu-wechat\|dayu-render" README.md`) | ✅ 全部声明与实现一致 |
| Cursor condition audit (`rg "if render_exit_code == EXIT_SUCCESS" dayu/cli/session_execution.py`) | ✅ 无残留 success-gated cursor |
| pyproject script targets vs importable modules | ✅ 3/3 匹配 |

## Aggregate Review Findings

未发现实质性问题。

### 走读详情

#### S1: Public Package Entrypoints

**入口恢复正确性**：

- `pyproject.toml` 声明 `dayu-web -> dayu.web.__main__:main`、`dayu-wechat -> dayu.wechat.main:main`、`dayu-render -> dayu.render.render:main`，三个模块均已创建且可导入。
- 每个入口模块使用 `argparse` 提供 `--help`，不 import 可选重依赖（`streamlit`、`playwright`、`pypandoc`）；测试 `test_public_entrypoint_import_does_not_load_optional_heavy_dependencies` 验证了这一点。
- 非 help 执行返回受控诊断和 `EXIT_UNAVAILABLE (1)`；`dayu-render` 接受位置参数但不声称实现转换能力。

**`dayu.runtime.argparse_exit` 层中立性**：

- 只依赖 `typing.Final`，不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `dayu/runtime/__init__.py` docstring 已登记该模块，包根不 re-export。
- 三个入口模块均使用该 helper，消除了原始 review DS-F1 指出的重复实现。

**README truth**：

- `README.md` 中所有 `dayu-web`、`dayu-wechat`、`dayu-render` 引用均已对齐为"当前只支持 --help 和当前能力诊断"。
- 已删除 `dayu/web/README.md` 的链接（文件不存在），已删除 WeChat daemon/service 详细参数表和 workflow 示例，已删除 Pandoc 安装说明和渲染格式声明。
- `dayu/README.md` 更新了 UI 稳定边界描述，将 `dayu.web` / `dayu.wechat` / `dayu.render` 定位为"只提供已声明公开命令的 import/help 与当前不可用诊断"。
- `tests/README.md` 更新了 CLI 测试覆盖描述，新增公开包入口和 cursor 测试说明。

**owner boundary 验证**：

- 包装元数据和 README 拥有公开命令声明。
- 具体模块拥有 importable `main` 函数和 help/diagnostic 行为。
- Host/Engine/Service 未被 S1 修改。

#### S2: CLI Terminal Cursor After Successful Render

**cursor 推进条件变更**：

三处 cursor 推进点已从 `if render_exit_code == EXIT_SUCCESS` 改为 render 后无条件推进：

1. `execute_prompt_on_session` (line 374): render 后直接调用 `advance_cli_terminal_cursor`。
2. `_run_existing_session_startup_reconnect` (line 522): render 后 cursor 推进，再检查 exit code。
3. `_run_interactive_repl` (line 853): render 后 cursor 推进，再检查 exit code。

**语义正确性**：

- `terminal is None`（prompt SIGINT-before-run-id、interactive 第二次 SIGINT）路径不经过 render，不推进 cursor。测试验证 cursor 停留在 `event_sequence=0`。
- cursor 推进在 render 之后、exit code 检查之前。这意味着即使 renderer 返回非零退出码，已成功展示的 terminal 仍被水位记录。
- cursor 写入失败作为 `CliTerminalCursorError` 传播，不被吞掉，不被改写为 renderer 退出码。

**测试覆盖**：

| 路径 | 非成功 cursor 推进 | cursor 写失败传播 | terminal=None 不推进 |
|------|--------------------|--------------------|----------------------|
| prompt existing-session | ✅ parametrized FAILED/CANCELLED/LOST | ✅ | ✅ SIGINT-before-run-id |
| startup reconnect | ✅ parametrized FAILED/CANCELLED/LOST | ✅ | — (startup 不返回 None) |
| interactive turn | ✅ parametrized FAILED/CANCELLED/LOST | ✅ | ✅ 第二次 SIGINT |

**owner boundary 验证**：

- Host/Service 终端状态事实未被修改。
- CLI output/renderer 策略未被修改。
- `dayu.cli.session_terminal_cursor` 持久化 schema 未被修改。
- 修复落在 `dayu.cli.session_execution`，符合 plan 规定的 owner boundary。

#### Propagation Audit

**Public package entrypoint truth**：

- `pyproject.toml` console scripts → importable modules → `main()` callable → `--help` returns 0 → README describes same surface → tests verify same surface。链路完整一致。

**Terminal cursor truth**：

- Host terminal facts (status, event_id, event_sequence) → Service projection (`EntrypointRunTerminalResult`) → CLI render (exit code) → CLI cursor persistence (watermark)。每一层只修改自己拥有的事实，不重写上游真源。
- Cursor write failure → 传播为 `CliTerminalCursorError` → 不改写 renderer exit code → 不改写 Host terminal status。失败语义正确。

## Open Questions

无。

## Residual Risk

- `dayu-web`、`dayu-wechat`、`dayu-render` 仍为诊断型入口，直到后续 UI/render 实现 WU 提供真实功能。README 已明确标注当前不可用状态。
- Cursor 写入失败后可能导致同一 terminal 在后续 reconnect 时重复展示。这是已接受的本地投递 trade-off，且已有测试覆盖。
- `dayu.render` package-data 资源文件（CSS/HTML/Lua/template）未在本 WU 创建，属于后续渲染能力的残留工作。
