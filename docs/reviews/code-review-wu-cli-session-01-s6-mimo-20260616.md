# Code Review: WU-CLI-SESSION-01 S6

## Scope

- Mode: current changes
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/code-review-wu-cli-session-01-s6-mimo-20260616.md`
- Included scope:
  - `docs/host/design.md`
  - `dayu/host/README.md`
  - `dayu/README.md`
  - `tests/README.md`
  - `docs/reviews/wu-cli-session-01-s6-doc-sync-codex.md`
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Detail

### 1. 是否只写当前已实现事实，不写未来计划或用户手册

- `docs/host/design.md`：新增 `list_sessions` 到 function list 和 behavior matrix，标注"完整实现"；新增 CLI session resume 与 Host wait-resume 术语区分段落。均为已实现事实。
- `dayu/host/README.md`：新增 `list_sessions()` 到 handle 方法、包根 facade、Host 专属契约与稳定边界。均为已实现接口。
- `dayu/README.md`：新增"Session 列表读取结果"到 Host public contract 类型列表；补充读取入口只返回 durable truth 不触发执行。均为已实现契约。
- `tests/README.md`：更新 interactive 测试描述（删除 new-session、新增 existing-session 入口）；新增 session command 测试覆盖描述；新增 Host 测试段 `list_sessions` 覆盖。均为已存在测试事实。
- **结论**：只写已实现事实，未写未来计划或用户手册。

### 2. list_sessions 是否表述为 Host durable read truth

- `docs/host/design.md` behavior matrix：`"从 durable truth 读取全部未 purge Session 的列表摘要，不触发 projection worker 或执行"`。
- `docs/host/design.md` 接口分层段：`"读取 Session 列表通过 list_sessions 暴露，它直接来自 durable Session / slot / Run state truth，不是 projection，也不触发 projection catch-up 或执行"`。
- `dayu/host/README.md` 稳定边界：`"list_sessions 属于 typed read view：它从 durable Session / slot / Run state truth 生成全部未 purge Session 的列表摘要，不读取 projection truth，不触发 projection catch-up，也不启动执行"`。
- `dayu/README.md`：`"get_session、list_sessions、get_run、outbox read 和 storage usage report 等读取入口只返回 Host durable truth 或明确的派生 read view，不触发执行"`。
- **结论**：正确表述为 durable read truth / typed read view，不是 projection，不触发执行。

### 3. CLI session resume 与 Host resolve_wait / wait-resume 是否区分清楚

- `docs/host/design.md` 新增段落：`"CLI session resume 与 Host wait-resume 是两个不同术语。CLI resume 只是 UI / Service adapter 选择一个已有 OPEN Session，再提交新的 submit_followup(queue) 输入；它不恢复旧 Agent、Runner、Engine generator 或 Attempt，也不解析 Host wait record。Host wait-resume 只指 resolve_wait 接收外部等待结果后，让同一个 WAITING Run 创建新的 resume Attempt 并继续收口。"`
- **结论**：区分清楚，语义准确。

### 4. dayu/host/README 和 dayu/README 是否符合 Agent 更新约束

- `dayu/host/README.md`：只写当前 `dayu.host` 已实现接口（`list_sessions` handle 方法、包根 facade、Host 专属契约类型、稳定边界）。未写 CLI 用户手册或未来计划。
- `dayu/README.md`：只做跨包 Host public contract 总览同步（类型列表、读取入口语义）。未扩写内部机制或 CLI 使用说明。
- **结论**：符合各自 Agent 更新约束。

### 5. tests/README 是否只记录当前测试事实

- CLI 段：interactive 描述从 "label / new-session session binding" 更新为 "默认 fresh anonymous Session、label session binding、`--new-session` 用法错误"；新增 "prompt / interactive existing-session 执行入口不会 create / ensure"；新增 session command 测试覆盖（label kind 映射、slot 反解、session list/resume/purge、TOCTOU、INVALID_STATE、purge 输出不泄漏 digest）。
- Host 段：新增 `list_sessions`、空库边界、slot row 解码 fail-closed 到 command handle / public session API 覆盖列表。
- 所有描述与实际测试文件中的测试函数一一对应。
- **结论**：只记录当前测试事实。

### 6. 是否错误修改或需要修改 docs/engine/design.md

- S6 codex 已核对 `docs/engine/design.md`：当前 Engine run-scoped 边界与 S5/S6 已实现事实不冲突。
- diff 中 `docs/engine/design.md` 无变更。
- `list_sessions` 是 Host 层 API，不影响 Engine run-scoped 一次性执行模型。
- CLI session resume 是 CLI UI adapter 行为，不引入 Engine Session 概念。
- **结论**：不需要修改 `docs/engine/design.md`。

## Open Questions

无。

## Residual Risk

- 文档同步只覆盖 S6 指定范围；未进行全仓文档语义重写。S6 codex 已记录此点。
