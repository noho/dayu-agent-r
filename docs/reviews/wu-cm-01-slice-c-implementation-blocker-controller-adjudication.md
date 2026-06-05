# WU-CM-01 Slice C Implementation Blocker Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C implementation blocker adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| implementation artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted-blocker`。

动机成立，严重性没有被高估。Slice C 要删除旧 `MemoryProjectionPolicy.recent_raw_turns_floor`、旧 `CompactMaterialPack.stable_input` / `history_input` 和旧 `CompactMaterialBlockKind`，但仍有两个生产 direct consumers 不在 Slice C 专属 allowed files 内。

## Direct Evidence

- `dayu/host/engine_ingest.py` 的 reactive compaction pending request 仍读取 `self._memory_projection_policy.recent_raw_turns_floor`。
- `dayu/host/context_governance.py` 的 `_original_open_questions_present` 仍引用 `CompactMaterialBlockKind.OPEN_QUESTION`、`CompactMaterialBlockKind.WORKING_ASSUMPTION`，并读取 `request.material_pack.stable_input + request.material_pack.history_input`。

若在 Slice C 内删除旧字段而不迁移这两个消费者，全量 pyright 会失败；若保留旧字段 alias / wrapper 来让它们继续编译，则违反 accepted plan 中禁止旧 field alias、compat wrapper、旧 material field wrapper 的硬约束。

## Decision

接受 AgentCodex 建议的方案 1：继续修正 Slice C allowed files，把以下文件纳入同一 pyright-clean vertical closure：

- `dayu/host/engine_ingest.py`，仅限 reactive compaction pending request 的 recent-window floor 字段迁移。
- `dayu/host/context_governance.py`，仅限 compact quality checker 对 vNext `CompactMaterialPack` sections 与旧 `CompactMaterialBlockKind` 删除后的读取迁移。

同时需要把直接相关测试 owner 纳入 Slice C 测试边界：

- `tests/host/test_engine_ingest_mapping.py`，仅限 reactive compaction pending policy field 迁移。
- `tests/host/test_compaction_contract.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_llm_compaction.py` 中与 context governance / compact material contract 直接相关的断言。

## Rejected Alternative

不接受回到 Slice B fix gate。当前 Slice C 已被接受为 policy、material、projection、assembly 的纵向闭包；`engine_ingest.py` 与 `context_governance.py` 是同一旧 policy/material shape 的直接消费者，把它们拆回 Slice B 会制造跨 gate 半迁移状态。

## Next Gate

进入 `WU-CM-01 Slice C plan boundary follow-up gate`，只补 allowed files/tests 与测试命令，不做 production implementation。
