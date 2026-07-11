# WU-SEMANTIC-OWNERSHIP-01 P3-I Aggregate Deepreview (DS)

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `b24b0a76`
- Range: `b24b0a76..HEAD`（6 commits）
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-i-aggregate-deepreview-ds.md`
- Included commits:
  - `b46259f1` Start P3-I goal confirmation
  - `6eb0b3f5` Accept P3-I plan
  - `bef202c4` Record P3-I plan commit
  - `6c6e278b` Implement P3-I S1 public entrypoints
  - `a0e126e2` Record P3-I S1 commit
  - `8bba9a52` fix: accept P3-I S2 terminal cursor delivery
  - `ba09ac0a` docs: record P3-I S2 accepted commit
  - `ee21bb59` docs: fix P3-I S2 artifact whitespace
- Included scope:
  - `dayu/web/`、`dayu/wechat/`、`dayu/render/` 公开入口包（新建）
  - `dayu/runtime/argparse_exit.py` 层中立 argparse 退出码规范化（新建）
  - `dayu/runtime/__init__.py` docstring 更新
  - `dayu/cli/session_execution.py` cursor 推进逻辑修复
  - `README.md`、`dayu/README.md`、`tests/README.md` 文档更新
  - `docs/host/` P3-I 设计文档与 review artifacts
  - `tests/cli/test_public_package_entrypoints.py`（新建）
  - `tests/cli/test_prompt_command.py` cursor 回归测试（扩展）
  - `tests/cli/test_interactive_command.py` cursor 回归测试（扩展）
- Excluded scope:
  - `docs/cli_ci.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`（untracked，与 P3-I 无关）
  - `docs/reviews/code-review-20260710-*.md`（旧 review artifacts，与 P3-I 无关）
  - `docs/reviews/wu-semantic-ownership-01-p3-i-aggregate-deepreview-mimo.md`（上一轮 DS 中断残留）
- Parallel review coverage: 无。本次 scope 集中且已由前序 S1/S2 review/fix/rereview 分 slice 覆盖，本次 aggregate 走读全部生产变更路径一次。

## Validation Baseline

以下全部在当前 workspace 验证通过：

- CLI 全量测试：`pytest tests/cli -q` → `294 passed, 3 warnings`
- 类型检查：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`
- 模块 help smoke：
  - `python -m dayu.web --help` → 0
  - `python -m dayu.wechat.main --help` → 0
  - `python -m dayu.render.render --help` → 0
- 控制台脚本 help smoke：
  - `dayu-web --help` → 0
  - `dayu-wechat --help` → 0
  - `dayu-render --help` → 0
- 范围空白检查：`git diff --check b24b0a76..HEAD` → passed

## Source Scans（本次复核）

- Cursor 条件残留扫描：
  ```
  rg -n "if render_exit_code == EXIT_SUCCESS|advance_cli_terminal_cursor" \
    dayu/cli/session_execution.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py
  ```
  结果：生产代码中已无 `if render_exit_code == EXIT_SUCCESS` cursor gate；三处 `advance_cli_terminal_cursor` 调用（prompt L374、startup reconnect L522、interactive REPL L853）均为无条件调用，位于 render 返回之后。

- 公开命令声明一致性扫描：
  ```
  rg -n "dayu-web|dayu-wechat|dayu-render" README.md tests/README.md dayu/README.md pyproject.toml
  ```
  结果：`pyproject.toml` 脚本声明指向三个已存在的可导入模块；README 与 tests/README.md 一致反映当前 help/diagnostic-only 状态。

## Findings

### S1 — Public Package Entrypoints

沿每个入口的 import → argparse → help → 非 help 诊断路径逐一走读：

- `dayu/web/__init__.py` + `dayu/web/__main__.py`：入口 `main(argv) -> int`，仅 import `argparse`、`sys`、`Sequence`、`Final` 与 `dayu.runtime.argparse_exit`。`--help` 返回 0；非 help 执行输出 `WEB_UNAVAILABLE_DIAGNOSTIC` 到 stderr 并返回 `EXIT_UNAVAILABLE=1`。无 import-time 重依赖。
- `dayu/wechat/__init__.py` + `dayu/wechat/main.py`：同上模式，额外暴露 `login`、`run`、`service` 子命令及 `service install/start/restart/stop/status/list/uninstall` 子子命令，全部只提供 help 与诊断，不执行真实微信操作。
- `dayu/render/__init__.py` + `dayu/render/render.py`：同上基础模式，额外接受 `input_path` 与 `output_path` optional positional 参数，非 help 执行输出 `RENDER_UNAVAILABLE_DIAGNOSTIC` 到 stderr。
- `dayu/runtime/argparse_exit.py`：`normalize_argparse_system_exit_code(exc)` 把 argparse 的 `SystemExit` 规范化为整数退出码；非整数 code 统一映射为 argparse usage error code `2`。模块正确放置于 `dayu.runtime`（层中立），未引入任何上层依赖。
- 测试 `tests/cli/test_public_package_entrypoints.py`：覆盖 pyproject target import、`--help` 退出码、模块执行 help、可选重依赖 import 边界、非 help 受控诊断与 WeChat 子命令 help。所有 9 个 test case 通过。
- README 更新：根 `README.md` 将 Web/WeChat/render 从"已实现/早期阶段"改为"已保留入口/当前仅 help 和诊断"，删除了 pandoc 安装指引、Web UI 本地工作流描述、WeChat daemon/service 管理命令文档等与实际实现不符的内容。`dayu/README.md` 稳定边界描述同步更新。`tests/README.md` 补充公开包入口测试覆盖描述。

**S1 结论：未发现实质性问题。**

### S2 — CLI Terminal Cursor After Successful Render

沿三个 cursor 推进站点逐一走读调用链：

#### 站点 1：`execute_prompt_on_session` (L371–380)

```python
if terminal is None:
    return EXIT_KEYBOARD_INTERRUPT          # 无 terminal → 不推进 cursor
render_exit_code = render_prompt_terminal_result(terminal)
await advance_cli_terminal_cursor(...)      # render 成功后无条件推进
return render_exit_code                      # 返回 renderer 退出码
```

- `terminal is None` 路径（Run accepted 前 SIGINT）正确跳过 cursor 推进。
- `advance_cli_terminal_cursor` 在 `render_prompt_terminal_result` 返回后无条件调用，覆盖 SUCCEEDED / FAILED / CANCELLED / LOST。
- 若 cursor 写入失败，`CliTerminalCursorError` 向上传播；`render_exit_code` 不会被返回。
- 测试覆盖：`test_prompt_existing_session_advances_terminal_cursor_after_rendering_non_success_terminal`（参数化 FAILED/CANCELLED/LOST）、`test_prompt_cursor_write_failure_propagates_after_terminal_render`、`test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor`。

#### 站点 2：`_run_existing_session_startup_reconnect` (L520–529)

```python
for terminal in startup.terminal_results:
    render_exit_code = render_interactive_terminal_result(terminal)
    await advance_cli_terminal_cursor(...)   # render 成功后无条件推进
    if render_exit_code != EXIT_SUCCESS:
        return render_exit_code              # 推进后再返回非零
```

- 每个 startup terminal 渲染后无条件推进 cursor，再判断是否继续。
- 若第一个 terminal 为非成功，cursor 已推进，函数返回非零；后续 terminal 不会被处理。下一次 reconnect 时 cursor 已记录该 terminal，不会重复展示。
- 测试覆盖：`test_interactive_startup_reconnect_advances_terminal_cursor_after_rendering_non_success_terminal`（参数化 FAILED/CANCELLED/LOST）、`test_interactive_startup_cursor_write_failure_propagates_after_terminal_render`。

#### 站点 3：`_run_interactive_repl` (L847–861)

```python
if terminal is None:
    return EXIT_KEYBOARD_INTERRUPT          # 无 terminal → 不推进 cursor
if effective_run_view is None:
    render_exit_code = render_interactive_terminal_result(terminal)
else:
    render_exit_code = effective_run_view.render_terminal_result(terminal)
await advance_cli_terminal_cursor(...)       # render 成功后无条件推进
if render_exit_code != EXIT_SUCCESS:
    return render_exit_code                  # 推进后再判断是否继续 REPL
turn_index += 1                              # 仅在继续时递增
```

- 两条 render 路径（有/无 run view）之后都无条件推进 cursor。
- `turn_index` 仅在 `render_exit_code == EXIT_SUCCESS`（即 REPL 继续）时递增。这是正确语义：非成功 turn 终止 REPL，不递增轮次。
- 测试覆盖：`test_interactive_existing_session_advances_terminal_cursor_after_rendering_non_success_turn`（参数化 FAILED/CANCELLED/LOST）、`test_interactive_turn_cursor_write_failure_propagates_after_terminal_render`、`test_interactive_repl_returns_130_on_second_sigint`（无 terminal 时不推进 cursor）。

#### Owner Boundary 验证

- Host/Service：terminal status、terminal event id、event sequence、final answer、error、cancel reason 等事实未变。cursor 推进不参与 Host 状态分类。
- CLI renderer：`render_prompt_terminal_result` / `render_interactive_terminal_result` / `InteractiveRunView.render_terminal_result` 的退出码映射未变。
- CLI cursor store：`dayu.cli.session_terminal_cursor` 的 store schema 未变；docstring 已准确表达"已成功展示过的 terminal 水位"语义。
- 无 Host/Service/Engine 代码因 cursor 逻辑改动。

**S2 结论：未发现实质性问题。**

### 整体架构一致性

- 新建的 `dayu.web`、`dayu.wechat`、`dayu.render` 包均未反向依赖 Host/Engine/Service/Fins。`dayu/README.md` 稳定边界描述已同步。
- `dayu.runtime.argparse_exit` 正确置于层中立 runtime 包，仅依赖 stdlib。
- 三个公开入口的 `main(argv) -> int` 签名统一，均使用 `argparse` + `normalize_argparse_system_exit_code` 模式。
- 无兼容性 re-export、wrapper、facade 或 shim。
- 无 `hasattr`/`getattr` 规避类型设计。
- 无魔法数字/字符串逃逸到业务逻辑外。

### 测试面完整性

- S1 测试：pyproject target import、help smoke（直接调用 + 子进程 `-m`）、可选重依赖 import 边界、非 help 受控诊断（三个入口各自验证）、WeChat 子命令 help（参数化 4 组 argv）。
- S2 测试：三个 cursor 推进站点各参数化 FAILED/CANCELLED/LOST；cursor 写失败传播（prompt + startup + interactive turn 各一）；`terminal is None` 不推进 cursor（prompt SIGINT before run id + interactive second SIGINT）；已有成功路径测试保持通过。
- pyright 零错误零警告零信息。
- CLI 全量 294 测试通过。

## Open Questions

无。

## Residual Risk

1. **cursor 写入失败导致 terminal 重复展示**：plan 已明确将 cursor 写入失败后的 terminal 重复展示作为可接受的 local-delivery trade-off。当前实现中 cursor 写入失败直接传播异常（不吞、不伪装成 renderer 退出码、不改写 Host terminal status），该行为已被测试锁定。风险在于用户可能看到同一 terminal 在两次 CLI 会话中重复出现，但不会导致数据丢失或状态腐坏。

2. **`dayu.runtime.argparse_exit` 缺少独立单元测试**：该模块（20 行，一个公开函数）当前通过 `test_public_package_entrypoints.py` 间接覆盖。模块极其简单且类型安全，但严格按项目"单文件 >= 80% 覆盖率"目标，缺少直接测试文件（如 `tests/runtime/test_argparse_exit.py`）。实际风险极低——该函数的两个分支（int code / non-int code）都已通过三个入口的非 help 执行路径间接验证。

3. **`dayu.render` package-data 资源文件延迟**：`pyproject.toml` 中 `[tool.setuptools.package-data]` 声明的 `dayu.render` 资源 glob 尚未被实际 CSS/HTML/Lua/template 文件满足。这是 plan 明确延迟的 render-capability 工作，不影响当前 import/help 契约。若用户通过某种方式触发 setuptools 的 package-data 收集，可能得到空资源目录——这不影响公开入口的 import/help 行为，但属于 plan 已识别且明确延迟的风险。

4. **三个公开入口仅提供诊断，无真实功能**：`dayu-web`、`dayu-wechat`、`dayu-render` 的非 help 执行全部返回"尚未提供对应实现"诊断和非零退出码。README 已明确标注这一限制。用户若未读 README 而直接尝试使用可能困惑，但这是 plan 预期的当前状态，不属于实现缺陷。

## Propagation Audit（本次复核）

以下是 P3-I 涉及的语义从产生到用户/LLM 可见输出的传播路径：

| 语义事实 | 产生者 | 校验者 | 持久化者 | 投影者 | 一致性 |
|---|---|---|---|---|---|
| 公开命令名与 script target | `pyproject.toml` | `test_public_package_entrypoints.py`（解析 toml + import 验证） | setuptools 打包 | `README.md` §1.2、§2.2、§2.3、§6 | ✓ 三端一致 |
| 入口模块 help 面 | `dayu/web/__main__.py`、`dayu/wechat/main.py`、`dayu/render/render.py` | import/help smoke 测试 | Python 模块文件 | 终端 stdout（`--help` 输出） | ✓ help 输出与 README 描述一致 |
| 当前不可用诊断 | 同上三个入口模块 | `test_non_help_execution_returns_controlled_diagnostics` | stderr 输出（一次性） | 终端 stderr + 退出码 1 | ✓ 诊断文本与 README "尚未实现" 表述对齐 |
| Host terminal status | Host durable EventLog | Host public API typed view | EventLog + state index | Service `EntrypointRunTerminalResult` | ✓ S2 未修改 Host/Service |
| CLI renderer exit code | `dayu/cli/output.py` render 函数 | 现有 exit code 测试 | 无持久化（进程内返回值） | CLI 进程退出码 + stdout/stderr | ✓ S2 未修改 renderer policy |
| CLI terminal cursor | `dayu/cli/session_terminal_cursor.py` | cursor store 测试 | `terminal_cursors.json`（workspace-local） | startup reconnect 读取去重 | ✓ cursor 在 render 后无条件推进，覆盖全部 terminal status |
| cursor write failure | `advance_cli_terminal_cursor` 内部 | `test_*_cursor_write_failure_propagates_*` 测试 | 无（异常传播前未写入） | 调用方收到 `CliTerminalCursorError` | ✓ 不吞异常、不改写 Host 状态 |

所有路径语义一致，无"显示正确但持久化错误"或"trace 正确但 memory 错误"的漂移。

## Verdict

**PASS** — 无 material findings。

P3-I 的两个 slice 均按 plan 正确实现：

- S1：恢复了三个公开入口的可导入模块与 help 面，README 已收窄至实际实现行为，测试覆盖 import/help/诊断/重依赖边界。
- S2：移除了 cursor 推进对 `render_exit_code == EXIT_SUCCESS` 的条件依赖，在三个调用站点统一改为 render 后无条件推进；`terminal is None` 路径正确跳过；cursor 写入失败传播异常而非吞没；Host/Service 语义未变。

测试（294 passed）、类型检查（0 error）、help smoke（6/6 通过）与 propagation audit 全部通过。
