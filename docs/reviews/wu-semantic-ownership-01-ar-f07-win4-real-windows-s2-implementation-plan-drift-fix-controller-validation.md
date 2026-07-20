# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S2 Plan-Drift Fix Controller Validation

## Result

`PASS / WIN4-RW-S2-PD-F01_FIXED_IN_PLAN / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW / IMPLEMENTATION_PAUSED`

## Validated artifacts

- Final plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，1084 lines / 75,492 bytes /
  SHA-256 `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279`。
- AgentCodex fix：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-fix-codex.md`，
  SHA-256 `226e6d5d3faa27f2d55415b16e84d00197f098aa42e85926fe07f7c671197900`。
- Controller finding source：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-controller-adjudication.md`，
  SHA-256 `bf858217eafea85f4e57ef488f1ab4afbc957f3bf9f56d242c0861ed084297f7`。

## Finding closure validation

1. §13.3只把`tests/cli/test_prompt_command.py`加入S2，并把ownership限定为
   `test_prompt_command_uses_init_generated_workspace_config`的strict typed TTY stdin fixture；同文件其它nodes零diff。
2. §13.4禁止production/test compatibility seam、mock `_read_secret_input`、ambient TTY与`sys.__stdin__`；exact node只补
   `sys.stdin` TTY capability，保留getpass sequence、prompt/runtime assembly业务断言和顺序。
3. §13.5把direct integration consumer纳入TTY owner matrix，并要求误入`readline()`立即失败。
4. §13.6加入exact focused node、scoped Ruff、node-level diff review与forbidden-source scans；full CLI regression仍mandatory。
5. Product owner、README、安全/deferred、remote same-run closure、S1→S2顺序和其它slice边界零漂移。

`WIN4-RW-S2-PD-F01`状态为`FIXED_IN_PLAN / PENDING_DUAL_COMPLETE_PLAN_REVIEW`。

## Protected state

- Entry HEAD：`e3e138fedd43c8edcf0a7113ff3c0335c22c9485`。
- Four stopped payload SHA-256分别保持：`7cf41485...4cce`、`b0601a96...e4c4`、`c5de0131...25fe`、
  `1541fb84...e5f8`。
- Four-path binary diff SHA-256保持
  `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669`。
- `tests/cli/test_prompt_command.py`相对entry零diff；staged tree empty；`git diff --check` PASS。

## Next gate

AgentMiMo与AgentDS并发完整review final 1084-line plan、finding根因、exact-node scope、protected stopped tree、验证矩阵、
security/deferred/remote边界。不得只审34/10行增量。任何accepted finding必须由AgentCodex修复后完整re-review；双路closure和
docs-only accepted plan commit前，不得恢复implementation或修改`test_prompt_command.py`。
