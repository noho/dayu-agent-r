# WU-CM-01 Implementation Blocker Report - AgentCodex

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | implementation |
| agent | AgentCodex |
| branch | `phaseflow/wu-cm-01` |
| design source | `docs/host/design.md` 第 24 章 / 第 25 章 |
| control source | `docs/host/issues-implementation-control.md` |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| accepted plan commit | `14d28009` |
| artifact | `docs/reviews/wu-cm-01-implementation-codex.md` |

## Decision

本 implementation gate 停止，不修改生产代码。

动机成立：当前代码仍以 `pinned_state`、`working_assumptions`、`ConversationContinuityKind`、旧 compact material section、旧 compaction candidate 与旧 prompt section 组织 Conversation Memory；这与设计真源第 24 章固定的五类 session semantic memory、vNext compact I/O、current input anchor 不可引用、whole-candidate repair 和固定 prompt assembly 不一致。

但当前 accepted plan 的实施路径不能在本 implementation unit 内形成可验证的 pyright-clean 最小闭环。阻塞点不是单纯工作量，而是计划把必须同源切换的契约、持久化、projection、parser、accept barrier、operation state 与 RunInputBuilder 拆成概念域 Slice 1-5，并且 plan 自身承认 Slice 1-4 结束后不承诺全量 pyright。用户本轮要求最终必须 pyright-clean，且不能留下旧兼容 wrapper、旧字段 re-export、旧库兼容读取或 lazy import seam；在当前 plan 粒度下，任何局部删除旧 contract 都会立即让后续未迁移模块产生类型错误，任何为了保持可编译而新增兼容层又违反约束。

因此按用户 stop condition：不改生产代码，只记录 blocker，并建议把 accepted plan 重写为可编译闭环 slices 后再进入 implementation。

## Direct Evidence

只读核对结果：

- 当前分支为 `phaseflow/wu-cm-01`，工作区初始 clean。
- `python -m pyright dayu/ tests/ utils/` 当前基线为 `0 errors, 0 warnings, 0 informations`。
- 旧 contract 贯穿生产路径：`rg` 命中显示 `dayu/host/memory.py`、`dayu/host/durable/memory.py`、`dayu/host/compaction.py`、`dayu/host/compact_material.py`、`dayu/host/llm_compaction.py`、`dayu/host/context_governance.py`、`dayu/host/compaction_operation.py`、`dayu/host/run_input.py` 都直接引用旧 `working_assumptions`、`pinned_state`、`ConversationContinuityKind`、`MinimumPreserve*`、`stable_input` / `history_input` / `evidence_input` 或旧 candidate 字段。
- 相关生产文件与核心测试合计约 27,011 行：`memory.py` 4,054 行、`compaction.py` 2,183 行、`run_input.py` 3,245 行、`durable/memory.py` 1,087 行，相关核心测试中 `test_memory_projection.py` 3,313 行、`test_run_input_builder.py` 3,761 行、`test_compaction_operation.py` 1,958 行。
- `dayu/host/compaction_operation.py` 当前把多 pass candidate 合并为旧 `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preserved_*`；这不是简单 parser 替换，必须同步重写 operation-level accepted candidate digest、reject reason、payload builder 与 projection consumer。
- `dayu/host/context_governance.py` 当前质量检查围绕 pinned patch、minimum preserve、preservation evidence、open questions；vNext source label allowlist、cross-section label、current input anchor not citable、answer anchor、forward intent、reference continuity 必须同一 accept barrier 切换。
- `dayu/host/durable/memory.py` 当前 durable item kind 与 snapshot codec 消费旧 `ConversationContinuityKind` 和旧 snapshot fields；按仓库 schema 约束又禁止旧库兼容读取，因此 schema / codec / projection / tests 必须同一闭环迁移。
- `dayu/host/run_input.py` 当前普通 prompt section 仍渲染旧 stable block headers；若先迁移 snapshot shape 而不迁移 RunInputBuilder，pyright 与行为测试都会同时失效。

这些证据说明 root cause 是 accepted plan 的切片边界不是可编译边界，而不是某个单文件实现缺口。

## Why I Did Not Implement A Partial Fix

可选的局部策略均不满足本仓库约束：

- 只替换 typed dataclass：会让 durable memory、projection、compact operation、RunInputBuilder 的 imports / field access 断裂，无法 pyright-clean。
- 新增 vNext 类型但保留旧路径作为 bridge：如果 bridge 只是旧字段 wrapper / re-export / facade，会违反 AGENTS 禁止兼容 wrapper 与旧字段 re-export 的约束。
- 只改 parser / quality checker：operation 仍期待旧 `CompactionCandidate` 合并字段，memory projection 仍消费旧 compact payload，无法形成语义闭环。
- 只改 RunInputBuilder：snapshot 与 compact artifact 仍是旧 shape，只能做表面 renderer 改名，不能解决 root cause。
- 修改 `dayu.service` / `dayu.ui` / `dayu.fins` / `dayu.engine`：本轮明确禁止，且当前阻塞也不需要跨层扩展。

## Recommended Re-slicing

建议把 WU-CM-01 从“概念域 Slice 1-5”改写为每个 slice 都能 pyright-clean 的纵向闭环。原则是：未切换的旧路径可以原样存在到其 owner slice，但不得新增用于伪兼容的 wrapper、旧字段 re-export、旧库兼容读取或 lazy import seam；一旦某个路径切换到 vNext，必须同步迁移该路径所有生产 consumer 和测试。

建议闭环切片：

1. `WU-CM-01A compact contract closure`：在 `compaction.py`、`compact_material.py`、`llm_compaction.py`、`context_governance.py`、`tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py` 内建立 vNext compact input/output、source label map、strict parser 和 accept barrier 的闭环；旧 production operation 暂不切换，不新增 wrapper。
2. `WU-CM-01B compact operation/event closure`：同步迁移 `compaction_operation.py`、`context_events.py`、`compact_payload.py`、`fake_compaction.py` 与 operation tests，使 `ContextCompactor` 返回、quality gate、attempt rejected、`CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` payload 都使用 vNext candidate；删除旧 candidate merge 逻辑。
3. `WU-CM-01C memory durable/projection closure`：同步迁移 `memory.py`、`durable/memory.py`、`memory_repair.py` 与 memory projection / durable schema tests；全新 schema 只接受 vNext snapshot fields，旧 key fail closed，不做旧库读取。
4. `WU-CM-01D prompt/fallback closure`：同步迁移 `run_input.py`、`context_fallback.py`、必要的 `dispatch.py` 接线与 RunInputBuilder / dispatch tests，固定第 24.6 章 section 顺序，compact failed fallback 只渲染 bounded recent window 与 current input。
5. `WU-CM-01E public smoke/docs closure`：迁移 public smoke、`dayu/host/README.md`、`tests/README.md`，运行 `tests/host -q`、三个 smoke 脚本和 `python -m pyright dayu/ tests/ utils/`。

每个切片的退出条件都应包含：

- `source .venv/bin/activate` 后运行该切片受影响测试。
- `python -m pyright dayu/ tests/ utils/` 通过，或在切片 plan 中明确只允许“新增独立未接线 vNext contract”且不得删除旧 consumer contract。
- `rg` 验证本切片 owner 范围内不再残留已迁移旧术语。
- README 只在触发职责范围时同步。

## Validation

已运行：

```bash
git branch --show-current
git status --short
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：

- 当前分支：`phaseflow/wu-cm-01`。
- 初始工作区：clean。
- pyright：`0 errors, 0 warnings, 0 informations`。

未运行 pytest。原因是本 gate 未修改生产代码或测试代码，当前动作是 blocker artifact；运行受影响测试没有新的实现边界可验证。

## Changed Files

- 新增 `docs/reviews/wu-cm-01-implementation-codex.md`。

未修改：

- `dayu/host/*`
- `tests/host/*`
- `utils/smoke_host_public_*`
- `dayu/host/README.md`
- `tests/README.md`

## Residual Risks

| 风险 | 分类 | Owner / Destination | 说明 |
|---|---|---|---|
| Conversation Memory vNext 尚未实现 | requiring user decision | WU-CM-01 plan rewrite / controller | 当前 implementation gate 停止，需要把 accepted plan 改写为可编译闭环 slices 后重新进入 implementation。 |
| 完整 Conversation Memory eval benchmark | assigned to later work unit | WU-CM-10 / GitHub Issue #80 | 与 accepted plan 一致，当前不实现完整 eval harness。 |
| Cross-session User Profile Memory | assigned to later work unit | WU-CM-11 / GitHub Issue #115 | 与设计真源一致，不进入 session Conversation Memory snapshot。 |
| Deep historical recall / semantic search | assigned to later work unit | GitHub Issue #39 | 当前 vNext session memory 不实现 prompt-conditioned recall。 |

## Completion Status

状态：blocked。

不能进入 code review。下一步应回到 plan/fix 或 controller adjudication，将 WU-CM-01 implementation plan 改写为可编译、可验证的闭环 slices；之后再按新的 accepted plan 进入 implementation。
