# WU-CLI-PROMPT-01 Final Replay Fix

## Gate

- Gate: aggregate deepreview fix / re-review
- Work unit: `WU-CLI-PROMPT-01`
- Trigger: target `9021cc43` 的 frozen exact `P46-tty-double-sigint` replay 返回 `-2`
- Completion status: fixed and re-reviewed

## Direct Evidence and Root Cause

- 第一次 final replay 中，两次 `SIGINT` 均按 frozen timeline 实际发送；屏幕已经显示 `Cancelled.`，Host SQLite 中 Run/attempt 已为 `cancelled`，EventLog 已含 `ATTEMPT_CANCELLED` 与 `RUN_CANCELLED`，但进程最终 return code 为 `-2`。
- 第二个 `SIGINT` 到达时 canonical 130 已确定，进程仍处于 Python teardown。原 console/module entry 先把整数返回给 launcher，再由 launcher 执行 `sys.exit(...)`；teardown 阶段仍可被后续原始 `SIGINT` 覆盖。
- `CliSigintMonitor.close()` 还会移除 command-local handler，却没有恢复安装前由 `asyncio.Runner` 拥有的进程 handler，扩大了 command cleanup 与 process exit 之间的 signal ownership gap。

## Semantic Owners and Changes

- `dayu/cli/agent_entrypoint.py`：command-local SIGINT handler lifecycle owner 保存并恢复安装前 handler；不改变 prompt/interactive/Fins 各自的取消状态机。
- `dayu/cli/__main__.py`：新增公共 `exit_module` 作为 canonical exit code 确定后的 process teardown owner；只在规范退出码为 130 时屏蔽后续 `SIGINT`，随后以同一 130 结束进程。正常退出不屏蔽。
- `pyproject.toml`：console script 与 `python -m dayu.cli` 都进入同一 `exit_module` owner。
- `tests/cli/test_prompt_command.py`、`tests/cli/test_public_package_entrypoints.py`：覆盖 previous-handler 恢复、130/0 teardown 分支和 wheel entrypoint。
- `tests/README.md`：按测试文档职责记录新增 owner-level coverage。

## Validation

- 独立 reviewer：pass，无 findings；确认不是 prompt-only shim，shared prompt/interactive/Fins handler lifecycle 一致。
- shared affected tests：`1229 passed, 7 skipped`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：pass。
- fresh exact P46 probe：exit 130；两次 SIGINT 均 `sent`；UI 仅含 `cancel requested` / `Cancelled.`；Run/attempt 为 `cancelled`；包含 `ATTEMPT_CANCELLED` / `RUN_CANCELLED`。
- final target `174f65cb` focused-real replay：321/321 pass；evidence binding 位于 `/Users/leo/workspace/.dayu-cli-ci/prompt-postfix-final-20260731T200500Z-174f65cb/evidence/post-fix-evidence-binding.json`。

## Residual Risks

- OS 创建进程后、任何项目 Python bytecode 执行前的极早 SIGINT 仍不由纯 Python owner 控制。frozen exact `PC-CN-01` 0.05 秒路径已通过；若产品 contract 未来扩展到 0.005 秒级 interpreter pre-bytecode 窗口，需要由 native launcher/distribution owner 建立独立 work unit，由用户另行裁决。本 work unit 不扩大到该非冻结范围。
- frozen P46/PC-BD-02 的 post-terminal teardown 窗口已在当前 fix 覆盖；final evidence 中 Host instance 均为 `stopped`，runtime lane claim 为 0，不再保留该风险。

## Artifact

- Path: `docs/reviews/wu-cli-prompt-01-final-replay-fix.md`
