# WU-CM-01 Slice B Implementation - Codex

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B implementation |
| design source | `docs/host/design.md` |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| implementation agent | Codex |
| date | 2026-06-04 |

## First-principles Judgment

动机成立，严重性没有被高估。Slice A / Slice B partial edits 已把 compaction operation 输出切到 `ConversationCompactOutputVNext`，但 reactive accepted closeout 仍通过旧 `CompactArtifactWriteRequest` 写 artifact。该旧 writer 明确要求旧 `CompactionCandidate`，因此 reactive accepted path 会在 production closeout 处类型和运行时语义同时失配。这不是测试夹具问题，而是 Context Governance accepted event / artifact closeout 未闭合。

本轮没有重做已通过的 partial edits；保留了已完成的 vNext operation、event payload、proactive dispatch 和 fake compactor 迁移，只修正 plan follow-up 明确指出的边界缺口。

## Changed Files

- `dayu/host/compact_payload.py`
  - 新增 vNext compact artifact JSON、payload ref、descriptor metadata、prompt-local label mapping refs、source boundary refs、accepted evidence mapping refs 和 projection signal helper。
  - 保留旧 preserved refs helper 只供未迁移的后续 slice consumer 避免导入断裂；operation / dispatch 不再调用旧 helper。
- `dayu/host/dispatch.py`
  - 删除本文件私有 vNext artifact helper 副本，改为复用 `compact_payload.py` 的共享 helper。
  - proactive accepted closeout 继续写 vNext compact artifact descriptor 和 vNext `CONTEXT_COMPACTED` payload。
- `dayu/host/engine_ingest.py`
  - reactive accepted closeout 不再使用旧 `CompactArtifactWriteRequest`。
  - reactive accepted closeout 写 vNext compact artifact bytes、payload descriptor 和 vNext `CONTEXT_COMPACTED` payload，包含 operation id、accepted attempt number、candidate digest、artifact ref / digest、label mapping refs、source boundary refs、accepted evidence mapping refs、quality result、budget after compact 和 projection signal。
  - 未改动非 reactive closeout 状态机、RunInputBuilder 调用、projection catch-up 或 memory durable 路径。
- `tests/host/test_engine_ingest_mapping.py`
  - reactive fake compactor 改为覆盖 `compact_request_vnext`。
  - 增加 reactive accepted closeout 断言：vNext payload schema、无旧 preserved payload 字段、payload descriptor、artifact media type、artifact JSON schema 和 candidate digest。
- `tests/host/test_dispatch_scheduler.py`
  - 将 proactive / reactive compact 后续 Engine request / RunInputBuilder consumption 断言收窄为 operation / event closeout 断言。
  - 测试 fake compactor 继承 `FakeContextCompactor`，避免显式继承旧 `ContextCompactor` 后缺少旧 `compact` 方法造成 pyright 抽象类错误。
- `tests/host/test_compaction_operation.py`
  - 测试 fake compactor 继承 `FakeContextCompactor`，保持 vNext request-level fake 行为并修复 pyright 抽象类错误。
- `dayu/host/README.md`
  - 更新 Host Context Compaction 开发说明为当前 vNext candidate、vNext artifact 和 vNext `CONTEXT_COMPACTED` closeout 事实。
- `tests/README.md`
  - 更新测试覆盖说明，移除 Slice D 才负责的 compact 后 memory / RunInputBuilder consumption 表述，改为当前 Slice B closeout 覆盖。

## Validation

已运行并通过：

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py -q
```

结果：`270 passed in 1.89s`。

已运行并通过：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

## README Decision

- `dayu/host/README.md` 触发更新：本轮修改 `dayu/host/`，且 Context Compaction 段落仍描述旧 pinned / minimum preserve closeout；已同步为 vNext artifact / event closeout。
- `tests/README.md` 触发更新：本轮修改 `tests/host/`，且测试说明仍把后续 RunInputBuilder consumption 写成当前 dispatch scheduler 覆盖；已同步为 Slice B closeout 覆盖。
- 根目录 `README.md`、`dayu/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`、`dayu/config/README.md` 未命中职责内变更。

## Residual Risks

- vNext `CONTEXT_COMPACTED` 已提交后，memory durable / projection 对 vNext payload 的完整消费尚未迁移。分类：covered by later approved slice；owner：WU-CM-01 Slice C。
- ordinary RunInputBuilder 对 vNext compacted view 的后续消费、memory section 渲染和 public smoke 尚未迁移。分类：covered by later approved slice；owner：WU-CM-01 Slice D / E。
- `compact_payload.py` 中旧 preserved refs helper 仍因未迁移 Slice D consumer 保留，operation / dispatch 已不依赖。分类：covered by later approved slice；owner：WU-CM-01 Slice D cleanup。

## Completion Status

Slice B implementation gate 本地完成：reactive accepted closeout 已闭合到 vNext artifact / event；指定 pytest 矩阵和 pyright 全量通过；README 职责内同步完成。未 commit，未 push。
