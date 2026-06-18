# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-b-code-review-mimo-20260617.md`
- Included scope: Slice B - `prompt --detail/--no-detail`
- Excluded scope: Slice A (--log-file)、Slice C (interactive run view)、Host/Engine 变更

## Reviewed Files

- `dayu/cli/arg_parsing.py` - detail 字段与 --detail/--no-detail 参数注册
- `dayu/cli/commands/prompt.py` - activity renderer 创建与 cancel 提示逻辑
- `dayu/cli/activity.py` - CliActivityRenderer 实现（只读参考）
- `tests/cli/test_arg_parsing.py` - detail 默认值、互斥、正交性测试
- `tests/cli/test_prompt_command.py` - prompt activity 行为测试
- `tests/README.md` - 测试覆盖事实更新

## Findings

未发现实质性问题。

实现与已接受 plan (`docs/reviews/wu-cli-output-channels-plan-20260617.md`) 的 Slice B 要求一致：

1. **默认 no-detail 不注册 activity renderer**：`_execute_prompt_on_existing_session` 中 `detail=args.detail` 控制，`args.detail` 默认 `False`，传入 `activity_renderer=None`，不调用 `new_cli_activity_renderer()`。

2. **--detail 强制 enabled 且不污染 log-file**：`_new_detail_activity_renderer()` 创建 `CliActivityRendererOptions(visible=True, enabled=True)`，绕过 TTY gate；activity 写 stderr，不进入 `--log-file`（由 `test_prompt_detail_activity_does_not_enter_log_file` 覆盖）。

3. **--debug/--verbose 不打开 detail**：`arg_parsing.py:922-949` 的 `test_prompt_detail_flags_are_orthogonal_to_log_level` 覆盖 `--verbose`/`--debug` 时 `detail` 仍为 `False`。

4. **cancel activity 提示只在 renderer 存在时输出**：`prompt.py:496-497` 检查 `if activity_renderer is not None` 后才调用 `render_cancel_requested()`。

5. **测试覆盖真实路径**：
   - 默认 no-detail 即使收到 activity event 也不输出 `Activity:`（`test_prompt_default_no_detail_suppresses_activity_and_keeps_final_answer_stdout`）
   - 显式 `--detail` 在非 TTY 下输出 activity（`test_prompt_detail_outputs_activity_for_non_tty_and_keeps_final_answer_stdout`）
   - `--detail` activity 不进入 `--log-file`（`test_prompt_detail_activity_does_not_enter_log_file`）
   - `--verbose`/`--debug` 不显示 activity（`test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout`）

## Open Questions

无。

## Residual Risks

无显著残留风险。Slice C (interactive run view) 属于后续 work unit，本 slice 未实现。

## Validation

### 已运行（由 implementation artifact 确认）

```bash
source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py -q
# 81 passed, 3 warnings

source .venv/bin/activate && python -m pyright dayu/cli/arg_parsing.py dayu/cli/commands/prompt.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 0 errors, 0 warnings, 0 informations
```

### 未运行

无。本次 review 基于静态代码阅读和 implementation artifact 验证记录，未独立重新运行测试。

---

Review timestamp: 2026-06-17T22:26:11+08:00
Reviewer: AgentMiMo
