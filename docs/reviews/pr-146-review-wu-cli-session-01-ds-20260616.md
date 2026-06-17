# Code Review

## Scope

- Mode: PR review
- PR: #146 https://github.com/noho/dayu-agent-r/pull/146
- Title: WU-CLI-SESSION-01 CLI session management
- Author: noho
- Head: wu-cli-session-01
- Base: main
- Output file: docs/reviews/pr-146-review-wu-cli-session-01-ds-20260616.md
- Included scope: 59 changed files — Host formal `list_sessions` API (api.py, read_api.py, durable/state.py, open_host.py, `__init__.py`), CLI session list/resume/purge (session.py, session_identity.py, output.py, arg_parsing.py, main.py, host_context.py), removal of interactive `--new-session` (interactive.py, prompt.py), docs/tests/readme updates (design.md, issues-implementation-control.md, plan artifacts, review artifacts)
- Excluded scope: 无
- Parallel review coverage: 无；本 review 由单个 AgentDS reviewer 完成全量走读
- Design/control sources: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, `CLAUDE.md`, `dayu/README.md`

## Findings

### F-01-PASS-WITH-FINDINGS — 跨模块导入私有 `_` 前缀函数破坏模块封装

- **入口/函数**: `dayu/cli/commands/session.py:_run_session_resume()` → `_execute_prompt_on_existing_session` / `_execute_interactive_on_existing_session`
- **文件(行号)**: `dayu/cli/commands/session.py:36-44`
- **输入场景**: `dayu-cli session resume --mode prompt --label proj --kind prompt <prompt>` 触发 prompt mode 分支，或 interactive mode 分支
- **实际分支**: session.py 导入 `dayu.cli.commands.prompt` 模块的 `_prepare_prompt_existing_session_execution` 和 `_execute_prompt_on_existing_session`，以及 `dayu.cli.commands.interactive` 模块的 `_prepare_interactive_existing_session_execution` 和 `_execute_interactive_on_existing_session`
- **预期行为**: 按 Python 惯例，`_` 前缀函数是模块私有接口。跨模块导入私有函数标志这些函数应有正式的公共接口，或提取到共享模块。合理的做法是：将 `_execute_prompt_on_existing_session` / `_execute_interactive_on_existing_session` 及其 preparation dataclass 提升为非 `_` 前缀的稳定接口（加入 `__all__`），或提取到 `dayu/cli/commands/` 下的共享 narrow-entrypoint 模块
- **实际行为**: session.py 直接导入并使用四个私有函数，绕过 Python 封装约定
- **直接证据**: `dayu/cli/commands/session.py:36-44` 的 import 语句，以及 `_run_session_resume():258` 和 `_run_session_resume():279` 的调用点
- **影响**: 如果 prompt.py 或 interactive.py 修改现有 session 执行接口的签名、语义或内部状态依赖，session.py 会在编译/类型检查通过但语义层面静默断裂。该 PR 的 plan 明确指出这是刻意设计（"不复制 submit/watch/cancel 业务路径"），但未解释为什么不把这些函数提升为公共 API
- **建议改法和验证点**: 将 `_PreparedPromptExistingSessionExecution` / `_prepare_prompt_existing_session_execution` / `_execute_prompt_on_existing_session` 以及对应的 interactive 变体提升为非 `_` 前缀名称并加入各自 `__all__`；或在 `dayu/cli/commands/` 下新增 `_session_execution.py` 共享模块，同时被 prompt.py、interactive.py 和 session.py 引用。验证点：导入路径变更后 prompt/interactive/session 的 CLI 测试仍全部通过
- **修复风险（低）**: 只是重命名或重组模块，不影响执行语义
- **严重程度（低）**: 可维护性风险；当前行为正确，但违反模块封装约定，为后续重构埋隐患

### F-02-PASS-WITH-FINDINGS — `list_sessions` SQL 子查询对每个 Session 执行关联子查询，表规模增长时线性性能退化

- **入口/函数**: `dayu/host/durable/state.py:read_all_sessions_with_slots()`
- **文件(行号)**: `dayu/host/durable/state.py:1286-1346`
- **输入场景**: `host_sessions` 表有 N 行，每行触发一个 `host_session_slots` 关联子查询（`ORDER BY ... LIMIT 1`）
- **实际分支**: SQL 使用 `LEFT JOIN ... ON slot.rowid = (SELECT current_slot.rowid FROM host_session_slots AS current_slot WHERE current_slot.session_id = session.session_id ORDER BY ... LIMIT 1)`。对每个 Session 行执行一个独立子查询
- **预期行为**: 第一版 list_sessions 设计文档承认"不新增开放 filter/profile/query callback"，且当前 CLI 场景下 Session 数量预期很小。性能在当前规模下不构成实际问题
- **实际行为**: 每条 Session 触发一个独立子查询；在当前 Session 数（< 100）下无实质性能影响
- **直接证据**: `dayu/host/durable/state.py:1307-1333` 的 SQL 文本与 plan `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md` 的明确说明（"不做分页、搜索 DSL 或 operator report"）
- **影响**: 如果 Session 数量增长到数千量级，`list_sessions` 可能有可感知延迟。但在当前阶段完全不可观测
- **建议改法和验证点**: 当前不需要修改。若未来规模增长，可将子查询改为单次 `GROUP BY` / window function 或 batch IN 查询。建议在 `SessionListItem` 或对应模块加注释记录性能假设
- **修复风险（低）**: 暂无修改需求
- **严重程度（低）**: 在当前规模下无实际影响；仅作为 forward-looking observation 记录

### 未发现实质性问题（correctness / stability）

主链路逐行走读未发现 correctness、stability、state machine、concurrency 或 data consistency 层级的实质性问题：

- **Host `list_sessions` API 链路**：`Host.list_sessions()` → `_PublicHostHandle.list_sessions()` → `read_api.list_sessions()` → `HostCommandHandle._run_read(_ListSessionsOperation())` → `read_all_sessions_with_slots(transaction)` → `SessionWithSlotRows` → `_session_list_item_from_rows()` → `SessionListItem`。全部在只读事务内完成，不写 EventLog，不触发 projection catch-up，不启动执行。类型安全：`SessionListItem.__post_init__` 校验所有字段类型、非空约束和 UTC timestamps。

- **CLI `session list` 链路**：`run_session_command()` → `_run_session_command_async()` → `_prepare_session_runtime()` → `open_host()` → `_run_session_list()` → `host.list_sessions()` → `render_session_list()`。输出仅通过 Host public API，不读取 durable internals。输出字段是公开 `SessionListItem` 属性的派生，不暴露 `event_sequence`、`event_id`、`payload_digest` 等内部治理字段（`test_render_session_list_uses_public_summary_without_internal_fields` 已验证）。

- **CLI `session resume` 链路**：`_run_session_resume()` → `_prepare_prompt_existing_session_execution()` / `_prepare_interactive_existing_session_execution()` → `open_host()` → `_resolve_existing_session_target()` → `_execute_prompt_on_existing_session()` / `_execute_interactive_on_existing_session()`。resume 复用 prompt/interactive 的窄 existing-session 入口；不复制 submit/watch/cancel 逻辑，不自动 close/cancel。`--session-id` 路径通过 `host.get_session()` 校验 OPEN 状态（`dayu/cli/commands/session.py:353-361`）；`--label --kind` 路径通过 `host.list_sessions()` 遍历匹配 slot 并校验 OPEN（`dayu/cli/commands/session.py:376-387`）。

- **CLI `session purge` 链路**：`_run_session_purge()` → `_resolve_purge_target()` → `host.purge_session()`。`--yes` 强制确认（`dayu/cli/commands/session.py:309`）。用户面对的错误信息明确说明 CLI 不会自动 close/cancel（`_purge_host_error_message` 对 `INVALID_STATE` 的错误文案："purge requires a closed Session with terminal Runs; no close/cancel was attempted"）。输出 `render_session_purge_result` 只展示 tombstone 前缀和 session_id，不暴露 `deleted_counts_digest`（`test_render_session_purge_result_hides_digest` 已验证）。

- **`--new-session` 移除**：`interactive --new-session` 已从 parser surface 完全删除（`test_interactive_new_session_flag_exits_with_usage_error` 验证返回 usage error）。`interactive_process_slot_key` 已从 `host_context.py` 移除。`_ensure_interactive_session` 删除了对应的 slot 绑定分支（`dayu/cli/commands/interactive.py:349-367` 删除区域）。

- **类型安全**：新增类型（`SessionListItem`、`ListSessionsResult`、`SessionWithSlotRows`、`_PreparedPromptExistingSessionExecution`、`_PreparedInteractiveExistingSessionExecution`、`_PurgeTarget`、`_ExistingSessionTarget`、`CliSessionLabelKind`、`CliSessionDisplayKind`、`CliSessionDisplayIdentity`）均为 `frozen=True, slots=True` dataclass，带 `__post_init__` 校验。无 `Any`、`object`、无类型参数。

- **中文 docstring**：所有新增公开函数和类均提供完整中文 docstring，含参数、返回值、异常说明。

- **层边界**：`list_sessions` 为 Host public read API，通过 read transaction 读取 durable state，不跨层依赖 Service/UI/Engine。CLI 只通过 Host public API (`Host` Protocol) 访问，不读取 `dayu/host/durable` 内部。session.py 通过 `open_host` 和 `Host` Protocol 操作，符合 `UI -> Service -> Host -> Engine` 分层。

- **Adversarial failure pass 结果**：
  - TOCTOU：label 解析 → Host command 之间存在窗口（session 可能被并发 close/purge/slot rebound）。plan 明确承认（"CLI 不做锁或 CAS"），Host admission 是最终 gate。实际风险低：同一 operator 单机使用 CLI 时不存在并发场景。
  - 空列表：`render_session_list` 正确输出 "No sessions."。
  - 匿名 Session（slot=None）：`display_identity_from_slot(None)` 返回 `ANONYMOUS` kind，label 为 "-"。SQL 通过 LEFT JOIN 正确处理无 slot 的 Session。
  - 重复 client_request_id：session purge 使用 `session_purge_client_request_id(invocation)` 构造幂等键，格式为 `dayu-cli:session:<invocation_id>:session:purge`。Host 在 purge admission 中基于 client_request_id 做幂等吸收。
  - 非预期 session_action：`_run_session_command_async` 末尾 fallback 抛出 `CliSessionUsageError`。
  - `--kind` 非 prompt/interactive：`_require_label_kind` 通过 `CliSessionLabelKind(value)` 构造，非法值抛出 `ValueError` → `CliSessionUsageError`。
  - `--mode` 非 prompt/interactive：`_require_resume_mode` 硬编码校验列表后抛出 `CliSessionUsageError`。

## Open Questions

- 无。所有 key decisions（TOCTOU accept、不自动 close/cancel、跨模块私有函数导入）在 plan 或 implementation 中已有明确说明或裁决。

## Residual Risk

### 测试与验证状态

- **本地验证通过**：`pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q` → 120 passed, 3 edgar deprecation warnings
- **Pyright 通过**：`python -m pyright dayu/ tests/ utils/` → 0 errors, 0 warnings
- **CI/checks 状态**：未检查（`gh pr checks 146` 返回 "no checks reported on the 'wu-cli-session-01' branch"）

### 风险追踪

| ID | 严重程度 | 描述 | Owner / Destination |
|---|---|---|---|
| RR-01 | 低 | 跨模块私有函数导入：`session.py` 依赖 prompt.py / interactive.py 的 `_` 前缀函数。若这些私有接口变更，session.py 可能静默断裂 | WU-CLI-SESSION-01 后续维护者；无需独立 issue |
| RR-02 | 低 | `list_sessions` SQL 子查询随 Session 数量线性增长。当前 < 100 条 Session 无实质影响，但未在代码中注释性能假设 | WU-CLI-SESSION-01；若后续 Session 量级增长可转为 issue |
| RR-03 | 低 | TOCTOU 窗口（label → session_id 解析后到 Host command 之间）已由 plan 明确接受；Host admission 是最终 gate。单操作者 CLI 使用场景下无实际并发风险 | 无需独立 issue |

### 未覆盖区域

- CLI session 命令的端到端集成测试（需要真实 Host DB + Runner + 工具执行环境的完整路径）未覆盖。当前测试使用 fake Host 和模块级单元测试覆盖 CLI 控制流和输出格式。
- 大规模 Session（千级以上）的 `list_sessions` 性能未测试。
- `--session-id` purge 路径下 CLI 不做目标存在性预校验（直接传 session_id 给 Host），Host 在 NOT_FOUND 时返回错误。CLI 错误信息对 `--session-id` 输入者不够友好（不区分"不存在"与"其他 Host 错误"），但该路径已在 `_exit_code_for_host_error` 中处理为非 label 解析路径，返回 `EXIT_FAILURE` 而非 `EXIT_USAGE_ERROR`。这是边际 UX 差异，不是正确性问题。

## Completion Report

- **Artifact path**: `docs/reviews/pr-146-review-wu-cli-session-01-ds-20260616.md`
- **Verdict**: PASS-WITH-FINDINGS
- **Findings count and severity**: 2 findings，均为低严重程度
  - F-01: 跨模块导入私有 `_` 前缀函数 (Low — maintainability)
  - F-02: SQL 子查询线性性能退化假设 (Low — forward-looking observation)
- **Residual risks / owners**: 3 条 residual risk，均已有 owner 或无需独立 issue（见 Residual Risk 表格）
- **Validation checked**: 本地 pytest 120 passed / pyright 0 errors；CI checks 不可发现（`gh pr checks 146` 返回 no checks）
