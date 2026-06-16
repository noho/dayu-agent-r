# WU-CLI-FINS-OBS-01 Slice S6 Implementation

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S6-docs-sync`
- Gate: implementation
- Agent: Codex

## Scope

只做 README 同步和本 implementation artifact。未修改生产代码、测试代码、控制文档或 GitHub 状态。

## First-principles Judgment

S6 动机成立。S1-S5 已落地 Fins job event sidecar、Service/Fins direct event consumer、CLI progress / terminal renderer、日志装配和对应测试；稳定开发手册需要把旧的 direct start / poll / cancel 描述同步为 start / event observation / poll terminal fallback / cancel。

本轮不扩大范围：README 只记录当前代码事实，不写 future plan，不写 work unit 流水账，不把 Fins job event 描述成 Host EventLog 或 Host event stream。

## README Decisions

- `dayu/README.md`: 已更新。顶层 Service/Fins direct 边界从 start / poll / cancel 改为 start / event observation / poll terminal fallback / cancel；工具与 Fins 执行路径补充 direct command 消费 Fins job event，并保留 terminal job record fallback 与 durable cancel。
- `dayu/fins/README.md`: 已更新。事件流章节补充 Fins job event sidecar 是 direct 调用方可读取的观察信号，并明确它不是 Host EventLog 或 Host durable truth。
- `dayu/service/README.md`: 未修改。现有内容已说明 `dayu.service.fins_direct` 覆盖 job start、job event observation、poll terminal fallback、durable cancel、terminal exit mapping，以及 `stream_job_events_until_terminal(...)` 的 terminal fallback 语义，职责范围已命中且与代码一致。
- `tests/README.md`: 未修改。现有 `tests/cli`、`tests/service`、`tests/fins` 章节已覆盖 Fins direct live event consumption、CLI log assembly、progress / terminal UI 投影、UI/log distinction、Fins job event sidecar、`read_job_events(...)` 游标读取和 sensitive payload 边界，职责范围已命中且与测试事实一致。

## Direct Evidence

- `dayu/service/fins_direct.py` 提供 `stream_job_events_until_terminal(...)`，通过 runtime `read_job_events(...)` 按 sequence 消费事件；terminal event sidecar 缺失时读取 terminal job record 并合成 terminal event。
- `dayu/fins/ingestion_runtime.py` 与 `dayu/fins/ingestion_events.py` 提供 Fins job event append/read、per-job sequence、event sidecar JSONL、状态观察事件和 progress / cancel observation 事件。
- `dayu/cli/commands/fins.py` 使用 Service event stream 渲染 progress / terminal output，并在用户中断后调用 `request_cancel(job_id)`。
- `dayu/cli/main.py` 调用 runtime log 装配，使 CLI 全局日志参数进入 Dayu logger。
- `tests/cli/test_fins_commands.py`、`tests/service/test_fins_direct.py`、`tests/fins/test_fins_ingestion_runtime.py` 覆盖 live events、terminal fallback、cancel、CLI log assembly 与 sidecar payload 边界。

## Validation

- 已通过: `git diff --check`
- 已通过: 文本核对四份 README 中不再保留顶层 Fins direct `start / poll / cancel` 旧边界描述；`dayu/fins/README.md` 中的“不轮询 job”仅描述 awaiting tool 不直接 resolve Host wait，不属于 direct command 旧边界。

## Residual Risks

- 未覆盖项: README-only 变更无 pytest / pyright 必要性；按 docs-only 验证处理。
- 分类: 当前 slice 已覆盖。不存在需要后续 owner 的未分类 residual risk。

## Completion Status

Implementation complete. Docs-only validation passed.

## Artifact Path

`docs/reviews/wu-cli-fins-obs-01-s6-implementation-codex.md`
