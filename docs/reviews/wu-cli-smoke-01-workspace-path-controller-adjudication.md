# WU-CLI-SMOKE-01 Workspace Path Controller Adjudication

## Review Inputs

- AgentMiMo initial plan review: `docs/reviews/plan-review-20260708-134525.md`
- AgentDS initial implementation-risk review: `docs/reviews/code-review-20260708-134703.md`
- AgentCodex implementation: workspace path public contract fix
- AgentMiMo final re-review: pass, all original findings closed
- AgentDS final re-review: pass, no blocker

## Findings Adjudication

| Finding | 裁决 |
|---|---|
| `workspace_root` / `project_root` 语义混淆 | accepted-fixed |
| `init` 与 runtime location overlay 路径不一致 | accepted-fixed |
| CLI terminal cursor 创建 nested `workspace` | accepted-fixed |
| Web tools storage state 未按 workspace root 解析 | accepted-fixed |
| workspace path public contract 分散 | accepted-fixed |
| `DEFAULT_WORKSPACE = "./workspace"` 是否改为 `"."` | rejected-with-reason；用户明确允许 `workspace` 作为 `--base` 默认值保留，本次只禁止在 workspace root 下二次拼接 `workspace` |

## Controller Validation

- 代码搜索确认生产代码中 `workspace` 字符串只剩 CLI 默认值 / help 与 Host session scope 文档；未发现 workspace path 二次拼接。
- 关键 pytest 复核通过：`125 passed`。
- `pyright` 通过：`0 errors`。
- `git diff --check` 通过。
- 真实 CLI fresh-base prompt smoke 通过：`workspace/tmp/wu-workspace-path-real-20260708/workspace` 不存在，状态文件位于 `.dayu/host`、`.dayu/runtime`、`.dayu/cli`、`.dayu/artifacts`。

## Final Decision

本 follow-up 进入 accepted-fix。无 required current fix remaining。
