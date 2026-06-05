# WU-CM-01 Slice C Engine Ingest / Context Governance Boundary Follow-up

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan boundary follow-up |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| latest blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-c-implementation-blocker-controller-adjudication.md` |
| current status commit | `81bf9bfd` |
| author | AgentCodex |
| date | 2026-06-04 |

## Motivation

动机成立，严重性没有被高估。

Slice C 要删除旧 `MemoryProjectionPolicy.recent_raw_turns_floor`、旧 `CompactMaterialPack.stable_input` / `history_input` 与旧 `CompactMaterialBlockKind`。如果 `engine_ingest.py` 和 `context_governance.py` 仍被排除在 Slice C 专属 allowed boundary 外，implementation 只能在删除旧字段后触发 pyright 断裂，或者通过旧字段 alias、旧 block kind alias、material wrapper 维持编译。后者会直接违反已接受 plan 对“不得保留旧字段 alias、wrapper、compatibility facade”的硬约束。

Controller 已裁决接受该 blocker，并明确选择把两个直接 consumer 纳入 Slice C pyright-clean vertical closure，而不是回到 Slice B fix gate。本 follow-up 只落实该裁决到 plan allowed files/tests、测试命令和 control doc，不进入 implementation。

## Direct Evidence

直接证据来自当前代码、计划文档和 Controller 裁决：

- `dayu/host/engine_ingest.py:1279` / `dayu/host/engine_ingest.py:1280` 仍读取 `self._memory_projection_policy.recent_raw_turns_floor` 构造 reactive compaction pending request。
- `dayu/host/context_governance.py:802` / `dayu/host/context_governance.py:803` 仍引用 `CompactMaterialBlockKind.OPEN_QUESTION` 与 `CompactMaterialBlockKind.WORKING_ASSUMPTION`。
- `dayu/host/context_governance.py:805` 仍读取 `request.material_pack.stable_input + request.material_pack.history_input`。
- `docs/reviews/wu-cm-01-slice-c-implementation-blocker-controller-adjudication.md` 的 verdict 为 `accepted-blocker`，并明确要求把 `dayu/host/engine_ingest.py`、`dayu/host/context_governance.py` 和 `tests/host/test_engine_ingest_mapping.py` 纳入 Slice C 边界。

## Plan Updates

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 在 Slice C allowed files/modules 中加入 `dayu/host/engine_ingest.py`，范围限定为 reactive compaction pending request 的 recent-window floor 字段迁移：旧 `recent_raw_turns_floor` 必须迁移到 vNext `selected_recent_window_turn_floor` 或本 slice 明确的新字段；不得恢复旧字段 alias。
- 在 Slice C allowed files/modules 中加入 `dayu/host/context_governance.py`，范围限定为 compact quality checker 对 vNext `CompactMaterialPack` sections 与删除旧 `CompactMaterialBlockKind` 后的读取迁移；不得保留旧 block kind alias 或 material field wrapper。
- 在 Slice C allowed tests 中加入 `tests/host/test_engine_ingest_mapping.py`，仅限 reactive compaction pending policy field 迁移。
- 补充说明 `tests/host/test_compaction_contract.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_llm_compaction.py` 覆盖 context governance / compact material contract 的直接断言。
- Slice C 测试命令加入 `tests/host/test_engine_ingest_mapping.py`。
- Test Matrix 删除不存在的独立 `tests/host/test_context_governance.py` 必跑表述，改为用 `test_compaction_contract.py`、`test_compaction_operation.py`、`test_llm_compaction.py` 覆盖 quality checker 与 vNext material section contract。

## Control Doc Updates

已更新 `docs/host/issues-implementation-control.md`：

- `implementation status` 改为 `slice-c-engine-ingest-context-governance-boundary-followup-complete`。
- 记录本 follow-up artifact：`docs/reviews/wu-cm-01-slice-c-engine-ingest-context-governance-boundary-followup-codex.md`。
- `next entry point` 改为 `WU-CM-01 Slice C implementation gate`。
- 保持 implementation commits 记录不变，未声称已有 Slice C implementation commit。

## Untouched Scope

本 gate 未修改 production code、tests、schema、config JSON、README。

本 gate 未进入 Slice C implementation，未运行实现测试或 pyright，未 commit、push 或创建 PR。

## Re-review Need

需要 Controller 复核本 follow-up 是否准确落实 accepted blocker。

不需要重新进入完整 plan re-review：本次没有改变 vNext memory / compact contract、schema 取舍、分层边界或 Slice C 目标，只把 Controller 已接受的两个 direct consumer 与测试 owner 明确写入 Slice C implementation boundary。
