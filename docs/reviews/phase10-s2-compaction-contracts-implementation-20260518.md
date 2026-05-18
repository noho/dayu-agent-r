# Phase 10 Slice 2 Compaction Contracts Implementation

## 修改摘要

- 新增 `dayu/host/compaction.py`：定义 `ContextCompactor`、`CompactionRequest`、`EpisodeSummaryCandidate`、字段级三态 `PinnedStatePatchCandidate`、`PreservationEvidence`、`CompactQualityCheckResult` 与 `CompactionCandidate`，并提供 canonical JSON / digest 表达。
- 新增 `dayu/host/fake_compaction.py`：提供 deterministic `FakeContextCompactor`，模块文档明确仅供测试 / 本地开发显式注入，生产默认路径不得隐式使用。
- 新增 `dayu/host/context_governance.py`：实现 Slice 2 quality checker，拒绝丢失当前用户输入、丢失 accepted tool fact refs、summary 伪造 verified fact、缺 evidence、evidence anchor 未保留、pinned patch 三态非法或 evidence ref 不存在。
- 新增 `dayu/host/compact_artifact.py`：使用 `LocalArtifactStore` 写 canonical JSON artifact，并在调用方事务内通过 `PayloadStore.write_payload_descriptor_for_artifact` 写 descriptor；本 slice 不写 EventLog。
- 新增 `tests/host/test_compaction_contract.py` 与 `tests/host/test_compact_artifact_store.py`：覆盖 fake compactor、quality rejection matrix、deterministic compact artifact descriptor / digest 与 corrupted expected digest 拒绝。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q`
  - 结果：13 passed。
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：clean。

## README 决策

- 已更新 `dayu/host/README.md`：记录当前已实现的 Context Governance typed compactor boundary、quality checker、compact artifact store 与 fake compactor 使用边界。
- 已更新 `tests/README.md`：补充新增 Slice 2 测试命令和 Host 测试覆盖事实。
- 未更新根目录 `README.md` / `dayu/README.md`：本 slice 未改变用户工作流、CLI 入口、UI / Service / Host / Engine 分层关系或 production composition 方式。

## 风险与未覆盖项

- 本 slice 只建立 contract、quality check 与 artifact store；未实现 canonical compact events、memory projection 消费、RunInputBuilder durable compact provider、proactive / reactive orchestration。
- `FakeContextCompactor` 只用于测试 / 本地开发显式注入；真实 LLM scene adapter 与 production composition wiring 仍由后续 slice 负责。
- Quality checker 当前按 Slice 2 输入 refs 做保守校验；后续 Slice 3+ 接入 canonical events / memory projection 时，需要继续保持 summary 不升格 verified fact、pinned patch 只通过 accepted compact output 被 projection 消费。
