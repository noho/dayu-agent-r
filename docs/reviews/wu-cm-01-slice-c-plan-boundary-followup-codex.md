# WU-CM-01 Slice C Plan Boundary Follow-up

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan boundary follow-up |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| accepted plan boundary commit | `968ad83f` |
| author | AgentCodex |
| date | 2026-06-04 |

## Motivation

动机成立。刚接受的 Slice C plan boundary 已要求迁移 `CompactMaterialPack` 顶层字段与 `CompactMaterialBlockKind` 全量枚举，但 Slice C 专属 allowed files/modules 没有显式列入 owner 文件 `dayu/host/compaction.py`，allowed tests 也没有显式列入仍引用旧 material contract 的 compact contract / LLM / operation 测试。若不补齐，implementation gate 会再次遇到 allowed-files blocker，或者被迫在未授权文件中修正 root cause。

严重性为中等。全局 allowed summary 虽然泛化包含 `dayu/host/compaction.py` 与 `tests/host/*`，但 Slice C implementation agent 的直接工作边界来自 Slice C 章节本身；该章节必须 code-generation-ready，不能依赖全局摘要推断专属授权范围。

## Direct Evidence

直接证据来自当前代码和测试：

- `dayu/host/compaction.py` 定义 `class CompactMaterialPack`，其字段仍为 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor`。
- `dayu/host/compaction.py` 同时定义 `CompactMaterialBlockKind`，且 material JSON / LLM JSON serialization 仍输出 `stable_input`、`history_input`、`evidence_input`。
- `tests/host/test_llm_compaction.py` 仍断言 prompt / material JSON 中的旧字段，并引用 `CompactMaterialBlockKind`。
- `tests/host/test_compaction_contract.py` 仍构造旧 `stable_input` 和旧 block kind。
- `tests/host/test_compaction_operation.py` 仍引用 `CompactMaterialBlockKind`，并围绕旧 `evidence_input` / selected evidence input helper 建断言。
- `tests/host/test_public_compact_smoke.py` 与 `tests/host/fake_compaction.py` 仍读取或构造旧 `stable_input`、`history_input`、`evidence_input` material JSON。

## Plan Updates

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 在 Slice C allowed files/modules 中显式加入 `dayu/host/compaction.py`，并限定为 `CompactMaterialPack`、`CompactMaterialBlockKind`、material JSON / LLM JSON 与 vNext material section contract 迁移。
- 在 Slice C allowed tests 中显式加入 `tests/host/test_llm_compaction.py`、`tests/host/test_compaction_contract.py`、`tests/host/test_compaction_operation.py`。
- 显式允许 `tests/host/fake_compaction.py` 随 public smoke / compaction tests 做 material JSON 字段迁移，并限定为测试 helper 迁移，不改变生产 compactor 行为。
- 在 Slice C 测试命令中加入 `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py -q`，避免只依赖泛化 `tests/host/*` 或全局最终验证命令。

## Control Doc Updates

已更新 `docs/host/issues-implementation-control.md`：

- `implementation status` 改为 `slice-c-plan-boundary-followup-complete`。
- 新增本 follow-up artifact 记录：`docs/reviews/wu-cm-01-slice-c-plan-boundary-followup-codex.md`。
- 保持 `next entry point` 为 `WU-CM-01 Slice C implementation gate`。
- 保持 implementation commits 记录不变，未声称已有 Slice C implementation commit。

## Untouched Scope

本 gate 未修改 production code、tests、schema、config JSON、README，未运行实现测试或 pyright，未 commit / push / PR，也未进入 Slice C implementation。

## Re-review Need

建议 Controller 做轻量复核，但不需要重新进入完整 plan re-review。本次没有改变 Slice C 目标、vNext contract 语义、schema 取舍或分层边界，只把已接受边界落实为 code-generation-ready allowed files/tests、测试命令与停止条件说明。通过后可继续进入 `WU-CM-01 Slice C implementation gate`。
