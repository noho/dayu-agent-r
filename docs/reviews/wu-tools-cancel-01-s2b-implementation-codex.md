# WU-TOOLS-CANCEL-01 S2B Doc Process-Backed Implementation

## Verdict

READY_FOR_CODE_REVIEW

## Scope

本轮只实施 S2B `Doc process-backed`。未修改 Host public cancel API、Engine public contract、durable schema / migration、Fins / Web 工具迁移、`dayu.runtime.interruptible_process` 返回类型或 Host core 工具名分支。

## First-Principles Judgment

目标成立。S2A1 / S2A2 已提供 typed `ToolDefinition.execution` 与 Host declaration-backed capsule factory；Doc 生产路径仍通过 async callable 内部 `asyncio.to_thread(...)` 执行同步文档处理，父进程无法物理中止已经阻塞的同进程线程。S2B 的根因修复应把 Doc 生产 execution 声明迁移到 process-backed，让 Host capsule 在 cancel / timeout 后 terminate / kill 子进程并由 accept barrier 拒绝 late result，而不是继续强化 provider lock 或在 Host core 按 Doc 工具名分支。

旧 provider-lock 串行测试的动机已过期：它验证的是同进程 `to_thread` fallback 行为，不是生产 cancel closeout 能力。本轮已迁移为 process-backed 声明、pickle round-trip、process target 业务语义与 ToolRuntime cancel / late-result 测试。

## Changed Files

- `dayu/tools/doc_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/README.md`
- `docs/reviews/wu-tools-cancel-01-s2b-implementation-codex.md`

## Behavior Summary

- 五个 Doc tools：`list_files`、`get_file_sections`、`search_files`、`read_file`、`read_file_section` 的 `ToolDefinition.execution` 均声明为 `ProcessBackedToolExecutionCapability`。
- 新增模块级 `_DocProcessTargetFactory` / `_DocProcessTarget`，仅保存 `tool_name`、JSON arguments 副本、`allowed_root_locators`、`DocToolLimits` 与 `timeout_seconds` 标量；不捕获 provider lock、`DocumentProcessor`、repository/runtime/session、`CancellationToken` 或 Host internals。
- 子进程 target 内重新解析 `allowed_root_locators`，复用路径 containment 校验，并在业务 helper 内重新通过 `create_doc_file_processor(path)` 创建 processor。
- 抽出 `_execute_doc_business_value(...)` 作为 fallback callable 与 process target 共用的同步业务路由，保留参数校验、路径白名单、成功结果 shape、路径投影和 truncate spec。
- `_invoke_doc_business(...)` 仍保留为 direct callable fallback / 测试入口，并在 docstring 中明确不再是 production default path。
- process target 只返回 `completed` / `failed` JSON envelope；不返回 awaiting、cancelled、timeout 或 host_cancelled。
- ToolRuntime cancel 测试证明父进程返回 governed cancel，accept barrier 只收到一次 governed candidate，慢 target 的 late completed result 不进入 accept barrier。

## Tests / Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py -q`
  - `44 passed in 1.77s`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - `55 passed in 6.32s`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## README / Design Sync Decision

- `tests/README.md` 已按触发规则更新 `tests/tools/` 中 Doc provider 覆盖说明，移除过期的 provider 级串行策略表述，补充 process-backed execution、process target 可序列化、子进程路径校验与 cancel late-result 覆盖。
- `docs/host/design.md` / `docs/engine/design.md` 无需更新：本轮消费 S2A 已接受的 typed execution capability 与 Host process capsule 设计，不修改 Host / Engine 架构边界、公共契约或状态机。
- `dayu/tools/` 无 README 触发项。

## Stop Conditions Checked

- 未发现 Doc process-backed 需要父进程 provider lock 才能正确执行。
- 未传递 `DocumentProcessor`、provider lock、`CancellationToken`、repository、runtime、session 或 Host object 跨进程。
- 未修改 Engine contract。
- 未修改 `dayu.runtime.interruptible_process` 的 `JsonValue` 契约。
- 保持 path containment 语义：allowed roots 在子进程内重新解析并由同一 containment helper 校验。
- 保持成功 output shape 与现有 callable baseline 对齐；测试覆盖 read fast path 与 Docling processor path。

## Residual Risks

- process-backed failed envelope 的既有 Host 契约只有 `error_type` 和 `message`，没有独立 `hint` 字段。本轮未修改 Host / runtime 契约；为避免生产路径丢失恢复提示，Doc process target 将 hint 附加进 failed `message`。这保持 S2A envelope 约束，但不是与 fallback `ToolFailedOutcome.hint` 字段一比一的结构等价。后续如需完全结构化保留 hint，应作为独立 Host process envelope contract work unit 处理。
