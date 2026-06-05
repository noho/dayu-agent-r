# WU-CM-01 Slice D Code Review — mimo

## Gate / Scope

- Gate: Slice D code review
- Work unit: WU-CM-01 Conversation Memory overall optimization
- Reviewer: mimo
- Review source: workspace unstaged changes
- Design source: `docs/host/design.md`
- Plan source: `docs/host/wu-cm-01-conversation-memory-plan.md`
- Implementation artifact: `docs/reviews/wu-cm-01-slice-d-implementation-codex.md`

## Verdict

**PASS** — 无 blocking finding。变更范围合理、契约一致、测试正确迁移、README 同步准确。

## Findings

按 severity 排序。当前无 blocking / high / medium finding。

### F-01 [low/info] `_compact_pressure_reserve_tokens` 两个分支返回相同值

- 文件：`utils/smoke_host_public_conversation_memory_scenarios.py:2372-2382`、`smoke_host_public_conversation_memory.py:1114-1124`、`smoke_host_public_multiturn.py:919-932`
- 证据：三个 smoke 脚本的 `_compact_pressure_reserve_tokens` 函数均有 `if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS` 分支，但两个分支返回相同值。scenarios 脚本从 8192 改为 160000 后两分支均为 160000；另外两个脚本两分支均为 8192。
- 评估：这是预留的扩展点，当前行为正确。不构成 dead code 误导，因为函数签名和 docstring 明确表达"按窗口大小选择预留量"的语义。`smoke_host_public_multiturn.py` 的大窗口分支和小窗口分支本来就应该返回不同值（小窗口应额外扣减工具压力），但当前实现对 1M 模型场景是正确的。
- 建议：无需修改。若未来需要对不同窗口大小区分预留策略，直接修改对应分支即可。

### F-02 [low/info] `_resolve_workspace_root` 在三个 smoke 脚本中重复定义

- 文件：`utils/smoke_host_public_conversation_memory.py:389-406`、`utils/smoke_host_public_conversation_memory_scenarios.py:1149-1166`、`utils/smoke_host_public_multiturn.py:351-368`
- 证据：三个文件各有 `_resolve_workspace_root`，函数体完全相同，仅 prefix 常量不同。
- 评估：按编码硬约束"模块间依赖最小化"和 `utils/` 脚本默认无测试约束，各 smoke 脚本保持自包含是正确的。三个相同函数符合"三行相同代码优于过早抽象"原则。
- 建议：无需修改。

## Review Checklist

### 1. Fresh workspace 默认语义

- [x] 三个 smoke 脚本的 `_resolve_workspace_root` 在 `--workspace-root` 为 None 时生成 `workspace/tmp/<prefix>-<uuid>` fresh workspace。
- [x] 显式传 `--workspace-root` 时行为不变（`pathlib.Path(...).resolve()`）。
- [x] `--reuse-session` 语义不受 fresh workspace 影响；session slot key 逻辑独立。
- [x] fresh workspace 不影响 production `dayu-cli` 命令的默认 workspace（仍为 `./workspace`）。
- [x] 不掩盖 production old schema fail-closed 语义——显式 `--workspace-root` 指向旧库时仍会 fail closed。

### 2. Scenarios pressure reserve 8192 → 160000

- [x] 变更只影响 `smoke_host_public_conversation_memory_scenarios.py`，不影响另外两个 smoke。
- [x] 160000 reserve 使 core+long 场景套件的累积 messages / memory / framing 不会越过 hard threshold，同时仍保留 context pressure 覆盖。
- [x] `_compact_pressure_padding` 计算逻辑：`prompt_tokens = max(MIN, target - reserve - tool_pressure)`。reserve 增大使 prompt padding 减小，但 tool pressure（120K chars ≈ 30K tokens）+ 套件内多轮累积文本仍构成有效压力。
- [x] implementation artifact 正确描述为"smoke pressure 预算问题"而非生产 policy 变更。

### 3. README 与脚本行为一致性

- [x] 5.1 节（multiturn smoke）新增 fresh workspace 说明和 `--workspace-root` + `--reuse-session` 复用说明。
- [x] 5.2 节（conversation memory smoke）新增 fresh workspace 说明。
- [x] 5.3 节（conversation memory scenarios smoke）新增 fresh workspace 说明。
- [x] README 只描述已落地事实，不写未来计划。
- [x] 无越界内容（不写 eval benchmark、recall、User Profile 等 deferred 内容）。

### 4. `test_purge_session.py` item kind 迁移

- [x] `raw_user_turn` → `selected_recent_window` 是正确的 vNext durable item kind。
- [x] `dayu/host/durable/schema.py:810-818` CHECK 约束包含 `selected_recent_window`，不包含 `raw_user_turn`。
- [x] `dayu/host/memory.py:137` `MemoryIncludedReason.SELECTED_RECENT_WINDOW` 与 schema 一致。
- [x] 变更位于 `_insert_memory_rows` 测试夹具，不影响 production purge 逻辑。

### 5. Implementation artifact 可信度

- [x] 验证命令覆盖：pytest 单元测试（64 passed, 1 skipped）、三个 smoke 脚本、purge 测试（28 passed）、Host 全量回归（1100 passed, 1 skipped, 5 deselected）、pyright（0 errors）。
- [x] 中间失败及裁决逻辑清晰：旧 schema DB → fresh workspace；pressure 预算 → 调整 reserve；raw_user_turn → selected_recent_window。
- [x] Residual owners 合理：eval benchmark → WU-CM-10 / #80；User Profile → WU-CM-11 / #115；recall → #39；tokenizer adapter → 后续 Context Governance；Fins integration → Fins work unit。
- [x] Issue-80 / Design 24.7 mapping 复核与 Slice C 后状态一致。

### 6. 过度设计 / 契约违规检查

- [x] 无新增 helper 跨 smoke 脚本共享（各脚本自包含）。
- [x] 无 `Any`、`object`、无类型参数。
- [x] 无旧字段兼容读取或旧 schema bridge。
- [x] 无 recall / eval / User Profile 越界。
- [x] 无 `hasattr` / `getattr` 逃逸。
- [x] 所有新增函数有完整中文 docstring。

## Conclusions

Slice D 变更范围为 closure / smoke hardening，不涉及生产 Host / Runtime / Service 代码修改。三个 smoke 脚本的 fresh workspace 默认值、scenarios pressure reserve 调整、test fixture item kind 迁移和 README 同步均正确、一致、可验证。implementation artifact 验证结果可信，residual owners 合理。
