# WU-CM-01 Slice C Implementation Blocker

## Gate

- Work unit: WU-CM-01 Conversation Memory overall optimization.
- Gate: Slice C implementation gate.
- Design source: `docs/host/design.md`.
- Control source: `docs/host/issues-implementation-control.md`.
- Plan source: `docs/host/wu-cm-01-conversation-memory-plan.md`.
- Result: blocked before implementation.

## 动机判断

动机成立，严重性评估正确。

直接设计依据：

- `docs/host/design.md` 第 3 章已把 `memory_projection_policy` 固定为按语义分区的 deterministic floor / cap 字段集合，不再使用 `enabled`、旧 stable layer / history pool / working assumptions shape。
- `docs/host/design.md` 第 24.4 章固定 `ConversationMemorySnapshotVNext` 为 `trace_memory`、`evidence_fact_memory`、`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory`、`diagnostics`。
- `docs/host/design.md` 第 24.6 章固定 prompt assembly 顺序，并明确 fallback 只渲染 bounded recent window 和 current input，不物化高阶 memory。
- `docs/host/design.md` 第 25 章明确 Context Governance 只 append compact facts，Conversation Memory projection 才消费 accepted compact event 物化 snapshot。

直接代码证据：

- `dayu/host/memory.py` 仍定义旧 `MemoryProjectionPolicy` 字段：`max_pinned_items`、`max_evidence_backed_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、`history_pool_*`、`stable_layer_*`。
- `dayu/host/memory.py` 仍定义旧 `ConversationMemorySnapshot` 顶层字段：`pinned_state`、`evidence_backed_facts`、`working_assumptions`、`conversation_continuity`。
- `dayu/runtime/config_loader.py` 仍按旧 `memory_projection_policy` 字段集合 exact-fields validation。
- `dayu/service/host_assembly.py` 仍把 runtime config 旧字段映射到 Host `MemoryProjectionPolicy`。
- `dayu/config/execution_profiles.json` packaged profiles 仍使用旧 `max_evidence_backed_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、`history_pool_*`、`stable_layer_*` 字段。

因此 Slice C 不是命名清理，而是 public policy、durable snapshot、projection、RunInputBuilder、dispatch、Service assembly 与 Runtime config 的契约闭包；若继续保留旧字段，会直接违背设计真源和计划禁令。

## Blocker

当前 allowed files 不能形成 pyright-clean vertical closure。

Slice C 要求：

- 删除旧 `MemoryProjectionPolicy` 字段，不保留旧字段 alias。
- `CompactMaterialPack` 顶层字段从 `stable_input`、`history_input`、`evidence_input` 迁移到 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`。
- `CompactMaterialBlockKind` 删除旧 enum alias。

但当前生产代码中仍有不在用户给定 Slice C allowed files 内的直接消费者：

- `dayu/host/engine_ingest.py:1279` 读取 `self._memory_projection_policy.recent_raw_turns_floor`。删除旧 policy 字段后，`python -m pyright dayu/ tests/ utils/` 必然失败；保留该字段作为 property / alias 又违反“旧 `MemoryProjectionPolicy` 字段 alias”禁令。
- `dayu/host/context_governance.py:802` 仍引用 `CompactMaterialBlockKind.OPEN_QUESTION`、`CompactMaterialBlockKind.WORKING_ASSUMPTION`。
- `dayu/host/context_governance.py:805` 仍读取 `request.material_pack.stable_input + request.material_pack.history_input`。迁移 `CompactMaterialPack` 顶层字段后这里会断裂；保留旧字段 alias / wrapper 又违反“旧字段不得保留 alias、wrapper 或 compatibility facade”禁令。

这不是可通过 allowed files 内局部修补解决的问题。若在 `MemoryProjectionPolicy` 或 `CompactMaterialPack` 上保留旧名字来让未授权模块继续编译，会把旧 contract 伪装成 vNext contract，正好落入本 gate 的禁止项。

## 最小修复建议

二选一：

1. 修正 Slice C allowed files，把 `dayu/host/engine_ingest.py` 与 `dayu/host/context_governance.py` 明确加入 Slice C implementation scope，并限定只迁移：
   - reactive compaction pending 的 recent-window floor 字段读取，从旧 `recent_raw_turns_floor` 改为 vNext `selected_recent_window_turn_floor` 或计划指定的新字段。
   - context governance 对 `CompactMaterialPack` vNext sections 的读取和旧 `CompactMaterialBlockKind` 引用。
2. 回到 Slice B fix gate，先把 `context_governance.py` / `engine_ingest.py` 中遗留的旧 compact material / policy consumer 迁移掉，再重新进入 Slice C。

我建议选择 1，因为当前 Slice C 已被计划扩大为 policy、material、projection、assembly 的纵向闭包；把这两个仍直接消费旧 shape 的生产模块纳入同一 gate，风险小于保留跨 gate 半迁移状态。

## README 同步情况

未修改生产代码、测试或配置文件，因此未触发 README 内容同步。已检查触发规则：如果后续继续 Slice C 并修改 `dayu/host/`、`tests/`、`dayu/runtime/config_loader.py` 或 `dayu/config/execution_profiles.json`，需要分别检查 `dayu/host/README.md`、`tests/README.md` 与 `dayu/config/README.md`。

## 验证

未运行测试或 pyright。原因是 gate 在实现前因 allowed files 不闭环被阻塞；继续实现会违反用户停止条件，或者产生预期的 pyright 断裂。

已执行的证据收集命令：

- `git branch --show-current`
- `git status --short`
- `rg` / `sed` 检查 `docs/host/design.md` 第 3/24/25 章、计划文档和当前生产代码引用。

## 未覆盖风险

- 尚未实施 Slice C，因此 accepted vNext compact event 物化五类 session memory、ordinary Run input 消费 vNext snapshot、fallback/rejected/failed compact 不生成高阶 memory、Runtime config loader 与 Service assembly 迁移等目标均未验证。
- 如果 Controller 选择扩大 allowed files，后续实现仍需完整运行计划要求的 pytest 矩阵与 `python -m pyright dayu/ tests/ utils/`。
