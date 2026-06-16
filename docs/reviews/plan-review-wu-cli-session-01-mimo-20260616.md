# WU-CLI-SESSION-01 Plan Review

## Review Target

`docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`

## Scope

正式增加 Host public `list_sessions` API；删除 obsolete interactive `--new-session`；实现 CLI `session list` / `resume` / `purge`，CLI 必须基于 Host truth，不读取 Host durable internals。

## Design Sources

- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/host/issues-implementation-control.md`

## Code Facts Verified

- `dayu/host/api.py`：`Host` Protocol 当前无 `list_sessions`（line 3110-3355）；`SessionSnapshot` / `SessionSlotRef` / `HostStreamCursor` / `SessionStatus` 已存在。
- `dayu/host/read_api.py`：read facade 当前只有 `get_session` / `get_run` / event stream / outbox operations；`__all__ = ["get_run", "get_session"]`。
- `dayu/host/open_host.py`：`_PublicHostHandle` 使用 `_raise_if_closed()` + delegate to read_api/command pattern（line 295-500）。
- `dayu/host/__init__.py`：包根 `__all__` 导出大量 public symbols，`list_sessions` 未出现。
- `dayu/host/durable/state.py`：已有 `read_session_by_id`、`read_session_slot_by_session_id`、`session_snapshot_from_rows`；无 `read_all_sessions_with_slots`。
- `dayu/cli/arg_parsing.py`：`ParsedCliArgs.new_session: bool`（line 101）；`_register_interactive_command` 使用 `mutually_exclusive_group` 注册 `--label` 和 `--new-session`（line 408-414）。
- `dayu/cli/host_context.py`：已有 `PROMPT_SESSION_SCOPE`、`INTERACTIVE_SESSION_SCOPE`、`prompt_slot_key()`、`interactive_slot_key()`、`interactive_process_slot_key()`。
- `dayu/cli/commands/interactive.py`：`_ensure_interactive_session` 有 `args.new_session` 分支。
- `dayu/host/api.py` `SessionSlotRef`：`scope: str` + `slot_key: str`。

## Assumptions Tested

1. Host Protocol 必须更新以包含 `list_sessions`——plan 未显式提及 Protocol 变更。
2. `list_sessions` 返回全部未 purge Session——规模假设对当前个人 workspace 合理。
3. resume-by-label 使用 `list_sessions` 全量扫描后匹配 slot——故意不增加 `get_session_by_label`。
4. purge 使用现有 `purge_session` 前置条件（closed + terminal runs）——CLI 不自动 close。
5. S1-S6 切片可独立实现、独立验证。
6. `SessionListItem` 新增 `created_at` / `closed_at` datetime 字段到 public API surface。

---

## Findings

### F01-未修复-中-Host Protocol 未要求添加 `list_sessions`

- **位置**: Section 6 "Host Protocol / Opener / Read API"；Section 9 Slice S1
- **问题类型**: 契约缺失
- **当前写法**: Plan 只说"Host Protocol 增加 `async def list_sessions(self) -> ListSessionsResult`"，但未明确指出 `Host` class/Protocol 定义（`dayu/host/api.py` line 3110）和 `dayu/host/api.py` 的 `__all__`（line 3358）也必须更新。
- **反例/失败场景**: Implementation agent 只更新 `_PublicHostHandle` 和 `read_api`，不更新 `Host` Protocol 和 `api.py.__all__`。pyright 会通过（因为 `_PublicHostHandle` 不直接声明 `implements Host`），但 `test_package_exports.py` 会失败。更严重的是，如果 agent 不更新 `Host` Protocol，其它依赖 Protocol 的代码（如 test mock）不会获得 `list_sessions`。
- **为什么有问题**: `dayu/host/api.py` 的 `Host` Protocol 是 Service-facing 异步 handle 的真源定义。`dayu/host/api.py` 的 `__all__` 是 `dayu/host/__init__.py` 导出的上游。Plan 对这两个必须修改的位置缺乏显式枚举。
- **直接证据**: `dayu/host/api.py` line 3110 `class Host(Protocol)` 定义了所有 public 方法；line 3358 `__all__` 列出了所有导出 symbol。当前两者均无 `list_sessions`。
- **影响**: Implementation agent 可能遗漏 `Host` Protocol 更新，导致 Protocol 与实现不一致；`test_package_exports.py` 捕获该遗漏时需要返工。
- **建议改法和验证点**: Section 6 "Host Protocol / Opener / Read API" 应显式列出三个修改点：(1) `Host` Protocol in `dayu/host/api.py` 增加 `list_sessions`；(2) `dayu/host/api.py` 的 `__all__` 增加 `SessionListItem`、`ListSessionsResult`；(3) `dayu/host/__init__.py` 导出并纳入 `__all__`。验证：`test_package_exports.py` 同步更新。
- **修复风险**: 低
- **严重程度**: 中

### F02-未修复-低-resume-by-label 使用 list_sessions 全量扫描

- **位置**: Section 7 "`session resume`"；Section 8 "Labeled Session"；Section 12 "Resume by label uses list_sessions"
- **问题类型**: 非最优方案（已识别的有意设计权衡）
- **当前写法**: Plan 明确说明不新增 `get_session_by_label` API，resume-by-label 通过 `list_sessions()` 在 slot truth 中查找。
- **反例/失败场景**: 当用户有大量 Session 时（例如自动化场景），每次 resume-by-label 都全量扫描所有 Session。对于当前个人 workspace 场景影响极小。
- **为什么有问题**: 这是有意的最小设计权衡，避免在真实需求出现前扩大 Host surface。Plan 在 Section 12 已明确记录该决策。
- **直接证据**: Section 12 "Resume by label uses list_sessions"："本 plan 不新增 `get_session_by_label` API，以免在真实非 CLI 调用方需要前扩大 Host surface。"
- **影响**: 当前影响极小；如果未来 Session 数量增长，可另开 follow-up issue。
- **建议改法和验证点**: 无需修改 plan。Implementation agent 应确保 `list_sessions` 在 durable 层有合理查询效率（`host_sessions` 表全量扫描 + left join `host_session_slots`）。
- **修复风险**: 低
- **严重程度**: 低

### F03-未修复-低-Kind 列反解规则未指定 slot namespace 到 display kind 的映射

- **位置**: Section 7 "`session list`" 输出列
- **问题类型**: 契约缺失
- **当前写法**: Plan 指定 KIND 列值为 `prompt` / `interactive` / `anonymous` / `other`，说明"从 `cli.prompt.<label>` 或 `cli.interactive.<label>` 反解"。
- **反例/失败场景**: Implementation agent 需要自行决定：slot scope 精确匹配 `cli.prompt` 时 KIND=`prompt`，精确匹配 `cli.interactive` 时 KIND=`interactive`，slot 为 None 时 KIND=`anonymous`，其它 scope 时 KIND=`other`。若 agent 对 `other` 的判断条件不一致（例如是否检查 prefix 而非精确匹配），可能导致分类错误。
- **为什么有问题**: 这是一个小的实现细节，但 CLI 输出是用户可见的。如果实现不一致，用户可能看到错误的 KIND 标签。
- **直接证据**: Section 7 定义了 KIND 列的四种值，但没有给出从 `SessionListItem.slot` 到 KIND 的精确映射规则。
- **影响**: 轻微——implementation agent 大概率能正确推断，但显式规则更安全。
- **建议改法和验证点**: 在 Section 7 或 Section 8 中补充：`slot is None` → `anonymous`；`slot.scope == "cli.prompt"` → `prompt`；`slot.scope == "cli.interactive"` → `interactive`；其它 → `other`。S3 的 helper 测试应覆盖这四种情况。
- **修复风险**: 低
- **严重程度**: 低

### F04-未修复-低-purge 输出中 tombstone ref 展示格式未指定

- **位置**: Section 7 "`session purge`" 成功输出
- **问题类型**: 契约缺失
- **当前写法**: "成功：stdout 输出 `Purged session <session_id>` 与 tombstone ref 的短摘要；exit `0`。"
- **反例/失败场景**: Implementation agent 可能输出完整 tombstone ref（长 hex string），也可能只输出前 8 位。格式不一致影响测试断言。
- **为什么有问题**: 小问题，但 purge 输出是用户可见的 CLI 交互。S4 测试需要断言输出格式。
- **直接证据**: Section 7 成功输出描述为 "tombstone ref 的短摘要"，未定义"短摘要"的具体格式。
- **影响**: 轻微——implementation agent 可自行决定截断长度，但测试需要固定格式。
- **建议改法和验证点**: 建议 plan 指定输出格式为 `Purged session <session_id> (tombstone: <ref前8位>...)`，或明确让 implementation agent 自行决定并冻结到测试中。
- **修复风险**: 低
- **严重程度**: 低

### F05-未修复-中-S5 resume 代码复用边界未充分约束

- **位置**: Section 9 Slice S5 "CLI `session resume`"
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: "为 prompt / interactive 抽出可复用的内部执行 core，使调用方可以传入已选定 `session_id`，同时复用 scene/runtime assembly、submit、watcher、outbox fallback、SIGINT cancel 逻辑。" 后面有停止条件："如果复用 prompt/interactive core 需要跨模块导入大量私有状态，先重构出小的 CLI-internal helper；不要复制业务执行路径。"
- **反例/失败场景**: `prompt` 和 `interactive` 命令当前的执行路径（`_ensure_prompt_session` → `prepare_entrypoint_runtime` → `open_host` → submit → watch → outbox read → SIGINT cancel）深度耦合 session 创建逻辑。Resume 需要跳过 session 创建、直接使用已有 session_id，但复用其余路径。Implementation agent 可能遇到两种困难：(1) 当前 prompt/interactive 执行函数的 session 创建和 submit 是紧耦合的，拆分需要重构多个函数签名；(2) 如果不拆分而直接复制，会违反 plan 的"不要复制业务执行路径"约束。
- **为什么有问题**: S5 是本 work unit 中最复杂的 slice。Plan 的目标描述和停止条件之间存在张力：目标要求"复用"，停止条件允许"重构出小的 CLI-internal helper"。Implementation agent 需要在不复制业务逻辑的前提下拆分 session 创建和执行路径，这可能需要重构 `prompt.py` 和 `interactive.py` 的核心函数。
- **直接证据**: `dayu/cli/commands/prompt.py` 的 `_ensure_prompt_session` 和后续执行逻辑当前是同一个函数内的顺序执行；`dayu/cli/commands/interactive.py` 类似。S5 要求从外部注入 `session_id` 跳过 session 创建。
- **影响**: S5 实现复杂度高于其它 slices。Implementation agent 可能需要先做小重构再实现 resume，或在实现过程中发现需要修改 prompt/interactive 核心路径。
- **建议改法和验证点**: Plan 应补充 S5 的前置重构提示：(1) prompt/interactive 的执行路径应先拆分为 `resolve_session` + `execute_on_session` 两阶段；(2) `execute_on_session` 接受已选定的 `session_id`，不关心 session 来源；(3) resume 复用 `execute_on_session`。这样 S5 的代码变更更明确，implementation agent 不需要在实现时自行决定重构策略。
- **修复风险**: 中
- **严重程度**: 中

---

## Open Questions

无阻塞性 open questions。Plan 在 Section 12 已识别并记录了所有关键设计权衡。

## Residual Risks

| ID | 风险 | Owner / Destination |
|---|---|---|
| RR-1 | `list_sessions` 无 pagination——当前个人 workspace 可接受，若未来 Session 数量增长需另开 issue | Follow-up issue |
| RR-2 | resume-by-label 全量扫描——同上 | Follow-up issue |
| RR-3 | S5 prompt/interactive 代码拆分复杂度——plan 已有停止条件，但实际重构可能比预期更大 | Implementation agent |

## Plan Review Conclusion

**pass-with-risks**

Plan 整体设计合理：

1. **Host public API 契约**：`list_sessions` 定位为 `get_session` 的集合读取 sibling，只读 durable truth，不写 EventLog，不触发 dispatch。`SessionListItem` 字段选择合理，`created_at` / `closed_at` 是首次在 public API surface 引入 datetime 字段但符合 list UX 需求。不过度设计——无 pagination、filter DSL 或 query callback。

2. **分层合规**：CLI 只通过 Host public API 操作，不读取 durable internals。Purge 复用现有 `purge_session` 前置条件。Resume 使用 `submit_followup(QUEUE)` 而非新 Host lifecycle transition。

3. **Slice 质量**：S1-S6 沿 Host/CLI/文档边界切分，每个 slice 有明确的 allowed files、non-goals、测试要求和停止条件。S1→S2→S3→S4→S5 依赖链合理。

4. **风险控制**：Purge 使用显式 `--yes`；Closed session resume 有明确 exit code；`--new-session` 删除有 parser negative test。

主要风险在 F01（Host Protocol 更新遗漏）和 F5（S5 代码复用复杂度），均为可修复的 implementation 细节问题，不构成结构性 blocker。
