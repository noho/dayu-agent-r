# WU-CLI-CONFORMANCE-F01-F07 — PR 190 Review Fix

## Gate status

- Gate: accepted-findings fix
- PR: 190
- Branch: `codex/interactive-oracle`
- Fix base HEAD: `c69445c2d22febf056bf54e331912f62b3d5ddcb`
- Scope: 仅修复 Controller 接受的 PR-M01、PR-M02、PR-D01
- Result: `READY-FOR-DUAL-PR-REREVIEW`

本轮没有重新解释 frozen oracle、design 或产品语义，也没有处理 Controller 已拒绝、通过或 deferred-with-owner 的其它 findings。

## Accepted findings closure

### PR-M01 / F07 canonical drop order

`dayu.host.context_governance` 的 accept owner 在候选通过 label、coverage、重复/矛盾、信息量和 Memory policy 校验后，使用 immutable root `source_boundary` 的 `boundary_order` 对 `explicitly_dropped_sources` 排序。`CompactAcceptedTruthV2.candidate` 与 `explicitly_dropped_coverage` 因而使用同一 root-order truth。

新增 owner-level 回归把 LLM candidate 的两个 drops 按 `T1, E1` 逆序输入，直接验证：

- accepted candidate drops 为 root order `E1, T1`；
- accepted explicitly-dropped coverage 同为 `E1, T1`；
- `build_context_compacted_payload(...)` 可通过 strict payload validation；
- `parse_context_compacted_semantic_payload(...)` round-trip 后 candidate 与 coverage 仍精确同源且保持 root order。

没有修改 frozen candidate schema、drop reason、coverage 定义或 persisted parser 规则。

### PR-M02 / attachment cleanup

`dayu.host.open_host._PublicHostHandle._close_managed_attachment` 现在在 delayed recovery cancel/join 外使用 `finally` 调用底层 `attachment.aclose()`。因此 join 的非 cancellation 异常不再跳过 native attachment 释放；底层 close 成功时，原 join 异常仍原样传播。

新增 owner-level async 回归注入固定 join `RuntimeError`，断言底层 close 恰好调用一次，并断言同一个 join failure 继续向 caller 传播。没有修改 delayed fatal reporting、health transition 或 recovery policy。

### PR-D01 / F07 compact input single owner

`CompactionRequest.compact_input` 保持 strict v2 input 唯一生产 owner。所有 production、test support 和 smoke consumer 均改为读取 request property；`dayu.host.compact_material` 中重复的 `conversation_compact_input_vnext_from_material_pack`、`_source_boundary_v2`、`_previous_source_kind_v2` 及其 export 已删除，未保留 wrapper、facade 或 re-export。

production diagnostic 的 projector identity 同步指向真实 owner `CompactionRequest.compact_input`；stage 与异常 taxonomy 均未改变。Python active source inventory 对三个旧符号扫描为零命中。

## Exact changed files

### Production

- `dayu/host/context_governance.py`
- `dayu/host/open_host.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/llm_compaction.py`
- `utils/smoke_host_public_r03_semantic_ownership.py`

### Tests and test support

- `tests/host/test_compaction_contract.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compaction_cancellation_scope.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/fake_compaction.py`

### Documentation

- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-cli-conformance-f01-f07-pr-review-fix-codex.md`

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### Focused owner regression

```text
pytest -q \
  tests/host/test_compaction_contract.py::test_accept_owner_canonicalizes_reverse_drops_for_committed_round_trip \
  tests/host/test_open_host_runtime.py::test_managed_attachment_close_releases_resource_when_recovery_join_fails

2 passed in 0.40s
```

### Affected suite

覆盖所有被迁移 consumer 及两个实质 owner：

```text
pytest -q \
  tests/host/test_compaction_contract.py \
  tests/host/test_open_host_runtime.py \
  tests/host/test_compact_material.py \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_compact_pipeline.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_compaction_cancellation_scope.py \
  tests/host/test_proactive_compaction_operation.py \
  tests/host/test_compact_artifact_store.py \
  tests/host/test_dispatch_scheduler.py

453 passed in 5.11s
```

首轮同一 suite 为 452 passed、1 failed；失败是既有 `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` 的并发计数时序。该节点与新 attachment cleanup 节点隔离复跑为 2 passed，完整 affected suite 随后复跑为 453 passed；没有为此修改 cancel/watchdog 产品或测试语义。

### Affected coverage

同一 453-test suite 经 coverage 重跑为 453 passed；实质 owner 文件结果：

```text
dayu/host/compact_material.py       85%
dayu/host/compaction.py            84%
dayu/host/context_governance.py     89%
dayu/host/open_host.py              81%
TOTAL                               83%
```

### Static and repository checks

- full `pyright`: `0 errors, 0 warnings, 0 informations`
- changed Python `ruff check`: `All checks passed!`
- `python -m compileall -q dayu/host tests/host utils/smoke_host_public_r03_semantic_ownership.py`: pass
- `git diff --check`: pass
- active Python old-projector inventory: zero matches for `conversation_compact_input_vnext_from_material_pack`、`_source_boundary_v2`、`_previous_source_kind_v2`

## README decision

- 更新 `dayu/host/README.md`：记录 strict v2 input 唯一 owner、accepted drops 的 root-order canonicalization，以及 delayed join 异常下的 attachment finally cleanup。
- 更新 `tests/README.md`：记录 reverse multi-drop committed round-trip 与 join-failure cleanup owner regression。
- 不更新根 `README.md`：没有用户可见 CLI、安装、输出、工作区或排障行为变化。
- 不更新 `dayu/README.md`：没有 `UI -> Service -> Host -> Engine` 跨层关系或装配边界变化。
- 不更新 `dayu/engine/README.md`：没有 Engine 文件、Engine contract 或 provider 语义变化。
- 不更新 `dayu/config/README.md`：没有配置、prompt asset 或 schema 配置变化。

## Scope integrity and preserved artifacts

- 未修改 frozen docs、oracle registry 或 scenario registry。
- 未修改 Controller adjudication 或两份 excluded self-review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-controller-adjudication.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-ds.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-pr-review-mimo.md`
- 未处理 parser exception taxonomy、God-function refactor、provider/model、Session resume、recovery test expansion、`cached_property` 或 defensive permit findings。
- 未 stage、commit、push，也未执行 PR mutation。

## Residual risks

- 本 fix gate 执行了覆盖所有 changed consumer 的 453-test affected suite和 full pyright，没有重新运行 PR 190 已在前序 gate 留存证据的 full-real provider matrix；本轮三项均为 deterministic Host owner 修复，不改变 provider/tool/frozen scenario 行为。
- 首轮观察到一次既有 cancel-watchdog test-order timing flake；隔离与完整 affected suite 复跑均通过。本轮禁止扩张该非 accepted finding，归属既有 Host test-runtime owner。
- 最终 PR review 结论仍需 MiMo 与 DeepSeek 双路 re-review；本 artifact 只声明 accepted findings fix 已具备复审条件。

## Final marker

`READY-FOR-DUAL-PR-REREVIEW`
