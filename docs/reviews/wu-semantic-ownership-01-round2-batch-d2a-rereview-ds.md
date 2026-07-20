# Re-Review — WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2a-F1 Fix

## Scope

- 原 finding: D2a-F1 — CLI 测试 `_run_snapshot` helper 对终态 status 始终传 `terminal_result_summary=None`，违反 `RunSnapshot` 终态约束。
- 修复文件:
  - `tests/cli/test_prompt_command.py` (`_run_snapshot`, lines 2236-2262)
  - `tests/cli/test_interactive_command.py` (`_run_snapshot`, lines 2316-2342)
- 修复模式: 与 Service 测试 `tests/service/test_entrypoint_runtime.py:2032-2043` 一致。

## Review Method

逐项验证：

1. 两个 `_run_snapshot` helper 是否对终态 status 构造 `TerminalResultSummary`。
2. Import 是否通过 Host public contract (`dayu.host.api`) 获取 `is_terminal_run_status` / `TerminalResultSummary`。
3. `tests/cli/` 下是否残留相同旧模式。
4. `tests/` 全量下 `terminal_result_summary=None` 残留是否均为非终态或 intentional validation test。
5. 修复是否引入新问题（测试通过、pyright 零报错、无 import 泄漏）。

## Findings

### 修复验证

**D2a-F1 已关闭。**

两个 `_run_snapshot` helper 均按以下模式修复：

```python
terminal_summary = None
if is_terminal_run_status(status):
    terminal_summary = TerminalResultSummary(
        status=status,
        summary_ref=None,
        summary_digest=None,
    )
```

- `test_prompt_command.py:2245-2251` — 对终态 status 正确构造 `TerminalResultSummary`。
- `test_interactive_command.py:2325-2331` — 同上。
- 两个文件均从 `dayu.host.api` import `TerminalResultSummary` 和 `is_terminal_run_status`，符合 Host public contract 边界。
- `_FakeHost.cancel_run()` 传 `RunStatus.CANCELLING`（非终态），`terminal_result_summary=None` 正确。

### F02 同模式残留检查

- `tests/cli/` 下无残留 `terminal_result_summary=None` 无条件传参。
- `tests/` 全量 `terminal_result_summary=None` 共 4 处，均为合法：
  - `tests/host/test_public_contracts.py:908,925` — `RunStatus.QUEUED`（非终态）。
  - `tests/host/test_public_contracts.py:968` — intentional validation test `test_run_snapshot_requires_summary_for_terminal_status`，断言 `ValueError` 抛出。
  - `tests/service/test_wait_callback_endpoint.py:725` — `RunStatus.WAITING`（非终态）。
- 无同模式 fragility 残留。

### 新建问题检查

- 无新 semantic ownership drift。
- 修复仅改动测试固定件，不触及生产代码。
- 无 import 泄漏：两个测试文件均通过 `dayu.host.api` public contract 引入所需符号。
- 无 fake 行为退化：`TerminalResultSummary` 构造参数 (`summary_ref=None, summary_digest=None`) 与 Service 测试 fixture 一致，语义正确。

### 验证结果

- `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`: **90 passed**, 3 pre-existing edgar warnings.
- `python -m pyright tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py`: **0 errors, 0 warnings**.

## 结论

Findings: **未发现实质性问题**。D2a-F1 已关闭。
