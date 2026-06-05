# WU-DUR-P01 Slice 3 Fix Codex

## Status

implemented

## Changed Files

- `dayu/host/compaction_operation.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_operation.py`
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-fix-codex.md`

工作区中已有的 `dayu/host/README.md`、`tests/README.md` 以及其它 Slice 3 retry 脏改未回滚；本次检查到 README 中关于 compactor proposal manifest ref / digest 的说明已与当前实现一致，未追加机械改动。

## Fix Summary

- 将 compactor proposal durable manifest recorder 提升为 `dayu.host.compaction_operation.DurableCompactorProposalManifestRecorder`，由 proactive dispatch 与 reactive engine ingest 共享同一 manifest / projection / hot payload 记录语义。
- proactive dispatch 改为使用共享 recorder，并继续以 `host.dispatch` 作为 EventLog source。
- reactive compaction 在 prepared compactor path 中传入共享 recorder，并以 `host.engine_ingest` 作为 EventLog source；prepared proposal 被接受时，`CONTEXT_COMPACTED` payload 现在携带 `accepted_proposal_manifest_ref` 与 `accepted_proposal_manifest_digest`。
- reactive prepared proposal 被拒绝时，`CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 现在携带 `proposal_manifest_ref` 与 `proposal_manifest_digest`。
- generic non-prepared fake compactors 仍可不产生 proposal manifest；本修复未把 compactor proposal 建模为 Host admitted Run，也未把完整 provider request/messages 写入 hot EventLog payload。
- 增加 focused coverage：
  - reactive prepared accepted compact payload 带 accepted proposal manifest ref / digest。
  - reactive prepared rejected attempt payload 带 proposal manifest ref / digest。
  - accepted compaction 缺 proposal manifest ref / digest 的 fail-closed guard。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_public_compact_smoke.py`
  - 结果：94 passed, 1 skipped
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过，无 whitespace error

## Residual Risks

- 未处理 controller 明确 deferred 的 initial compactor proposal trigger reason enum precision；本 fix 未修改 `docs/host/design.md`。
- 未处理 outcome-dependent `CompactorRunnerCallIdentity` event refs。
- 未处理 artifact filesystem / SQLite transaction boundary。
- 未实现 Tool Trace analyzer consumption。
