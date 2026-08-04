# Code Review — Interactive Memory Closure F09

## Scope

- Mode: current changes（uncommitted）
- Branch: `codex/interactive-oracle`
- Base: `47b6a2af`（F08 accepted checkpoint，与 implementation artifact 一致）
- Output file: `docs/reviews/wu-interactive-memory-closure-f09-code-review-mimo.md`
- Included scope:
  - `dayu/host/compaction_operation.py`（staged）
  - `tests/host/test_dispatch_scheduler.py`（unstaged）
  - `tests/host/test_tool_trace_queries.py`（unstaged）
  - `docs/reviews/wu-interactive-memory-closure-f09-implementation-codex.md`（untracked implementation artifact）
- Excluded scope: frozen CLI material、resolver/projector/private SQLite、其它未修改文件
- Parallel review coverage: 无（scope 较小，单 reviewer 足够）
- Review date: 2026-08-04

## Findings

未发现实质性问题。

以下逐项说明各检查维度的直接证据。

### 1. Canonical EventLog row ref/digest 同源

**根因修复正确。** 修复前 `EventLogAppendRequest.payload_ref=None`、`payload_digest=None`（旧代码 line 328-329），hot payload 携带正确 `manifest_payload_ref`/`manifest_digest`，导致 Tool Trace projector 投影 null row descriptor、formal resolver 的 row/hot equality check fail closed。

修复后（`compaction_operation.py:330-331`）：
```python
payload_ref=manifest_descriptor.payload_ref,
payload_digest=manifest_digest,
```

- `manifest_descriptor` 由同 transaction 内 `write_bounded_json_payload` 写入（line 288-306）
- `manifest_digest` 由 `sha256_digest_json(manifest)` 在 line 286 计算，与 hot payload 携带的 `manifest_digest` 同源
- hot payload 的 `manifest_payload_ref` 参数传入 `manifest_descriptor.payload_ref`（line 327）
- formal resolver 的 `row.payload_ref == hot_payload.manifest_payload_ref` 和 `row.payload_digest == hot_payload.manifest_digest` 两项 identity check 现在均由同一 transaction 已写出的 descriptor 派生

**判定：根因在 owner boundary（recorder 的 canonical manifest/EventLog producer boundary）修复，未修改 resolver、projector 或 private SQLite。**

### 2. Manifest-level projection descriptor 必要性与同源

**必要且同源。** formal resolver `resolve_runner_call_projection_from_signal` 要求 manifest body 包含 `runner_call_projection_artifact_ref` 和 `runner_call_projection_artifact_digest`（从 manifest JSON 读取后 resolve projection payload）。修复前 manifest body 不含这些字段，resolver 报 `runner-call manifest has no projection artifact ref`。

修复后 manifest body（`compaction_operation.py:1801-1803`）包含：
```python
"runner_call_projection_artifact_ref": compactor_input_projection_ref,
"runner_call_projection_artifact_digest": compactor_input_projection_digest,
"runner_call_projection_artifact_size_bytes": compactor_input_projection_size_bytes,
```

值来自 `projection_descriptor`（line 256-274 同 transaction 写入），不二次计算。`projection_descriptor` 与 `manifest_descriptor` 是两个独立 descriptor，未混用。hot payload 现在从 manifest body 读取同一 projection triple（line 1870-1881），而非 `None`。

**未扩大 schema/public surface：** `RunnerCallHotAtoms` 已有这三个字段（frozen field set `_RUNNER_CALL_HOT_FIELDS`），formal resolver 已期望 manifest 包含这些字段。F09 只是将 `None` 值替换为实际值。

### 3. Hot body/row/projector/resolver identity

identity chain 完整且同源：

1. `projection_descriptor`（同 transaction write）→ manifest body 的 `runner_call_projection_artifact_ref/digest/size_bytes`
2. `manifest_digest = sha256_digest_json(manifest)`（line 286，一次计算）→ EventLog row `payload_digest`（line 331）+ hot payload `manifest_digest`（line 328）
3. `manifest_descriptor.payload_ref`（同 transaction write）→ EventLog row `payload_ref`（line 330）+ hot payload `manifest_payload_ref`（line 327）
4. Tool Trace projector 机械投影 row 的 `payload_ref`/`payload_digest`
5. `_validated_runner_call_contract` 检查 `row.payload_ref == hot_payload.manifest_payload_ref` && `row.payload_digest == hot_payload.manifest_digest`
6. `_validate_manifest_hot_identity` 检查 projection triple（ref/digest/size_bytes）+ manifest_digest 16-tuple equality

manifest body 只计算一次（line 286），manifest digest 只从该 body 计算一次。无重复计算或分裂来源。

### 4. Success / repair-success / exhaust-fallback 重构严谨性

三个场景均由 `_resolve_and_assert_compactor_calls` 通过 public formal resolver 链路覆盖：

| 场景 | 测试 | attempts | accepted_attempt_number |
|---|---|---|---|
| single success | `test_multi_turn_proactive_compact_feeds_subsequent_run_input` | 1 | 1 |
| invalid → repair → success | `test_proactive_compaction_retries_quality_rejection_before_accept` | 2 | 2 |
| invalid exhausted → fallback | `test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback` | 4 | None |

helper 断言链：
- EventLog row `payload_ref`/`payload_digest` == signal `manifest_ref`/`manifest_digest`
- hot payload `manifest_payload_ref`/`manifest_digest` == signal `manifest_ref`/`manifest_digest`
- resolved manifest `payload_ref`/`payload_digest` == signal `manifest_ref`/`manifest_digest`
- attempt payload manifest ref/digest == resolved manifest ref/digest
- hot payload projection ref/digest == resolved projection ref/digest
- resolved projection digest == prepared input projection digest
- resolved projection payload == prepared input projection body
- compactor identity fields (operation_id, attempt_number, engine_run_id)
- response identity (provider, model, run_id)

**exhaust-fallback 场景改进：** 旧测试用 `_RecoveryScenarioCompactor(accept_call=99)` 抛异常（`failure_category="proposal_failed"`），新测试用 `_AlwaysQualityRejectingCompactor()`（`failure_category="quality_check_rejected"`）。后者每次 runner call 都有成功 response identity，符合计划要求"最后一种路径每次 runner call 都有成功 response identity，避免用 provider exception 代替 invalid/repair contract"。

### 5. Test helper 耦合 / private SQLite

**未过度耦合。** `_resolve_and_assert_compactor_calls` 只使用 public contract：
- `catch_up_tool_trace_projection`（public）
- `ToolTraceSinkOptions`（public）
- `read_runner_call_reconstruction_signals_by_run`（public）
- `resolve_runner_call_projection_from_signal`（public）

旧 imports `parse_runner_call_hot_payload`、`parse_runner_call_manifest`、`sqlite_payload_object` 已移除。private SQLite 不再是通过条件。

新增 `_required_json_mapping`/`_required_json_text`/`_required_json_int` 是 test-only 的 JSON 值校验 helper，无生产代码耦合。

`_AlwaysQualityRejectingCompactor` 继承 `_PreparedManifestProactiveCompactor`，只 override `run_prepared_compactor_proposal` 返回携带 diagnostics 的 proposal，行为清晰。

### 6. Mismatch fail-closed 未放松

**未放松。** `test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch` 构造：
- EventLog row `payload_ref = "payload-row-descriptor-mismatch"`
- hot payload `manifest_payload_ref = "payload-manifest-row-hot-mismatch"`
- 两者不同 → `_validated_runner_call_contract` 抛 `HostDurableError("tool trace row and runner-call hot identity mismatch")`

formal resolver / projector / identity check 代码未修改。

### 7. Formatter unrelated diff

production diff 全部是功能性改动（新增参数、填充 projection 字段、row descriptor 修复）。test diff 全部是 F09 相关（新 helper、新 compactor、新增断言、import 更新）。无 formatting-only 变更。

implementation artifact 记录："Tool Trace 新增测试 block 经 range format 产生，随后撤回 formatter 对既有未触及 baseline 的机械重排"——与 diff 一致。

### 8. README 与 baseline

- Host README 和 tests README 的写作边界判定不更新，理由成立（不新增公共 API、状态机、分层关系或稳定职责）
- frozen baseline SHA-256 验证通过：
  - `docs/cli_ci_oracles.json`: `da049231...` ✓
  - `docs/cli_ci_scenarios.json`: `7c991d14...` ✓
  - `docs/reviews/wu-interactive-memory-closure-f08-f10.md`: `95a09543...` ✓
  - `workspace/tmp/interactive-memory-observed-behavior.md`: `ad643151...` ✓
  - `workspace/tmp/interactive-memory-report-freeze.json`: `7ba64926...` ✓
- allowed files 精确等于四个 approved paths ✓

## Open Questions

无。

## Residual Risk

- 真实 provider/model/response identity 的跨进程 CLI evidence 仍由后续 `interactive.g06.tool-trace-formal` readiness stage 覆盖，与 implementation artifact 分类一致。
- 历史已写入 null row descriptor 的 EventLog 不做兼容读取或 migration，accepted non-goal。
- 五条正式 CLI scenarios 全部未覆盖，covered by later approved evidence stage。

## Conclusion

**PASS**

F09 slice 在正确的 owner boundary（compactor proposal manifest recorder 的 canonical manifest / EventLog producer boundary）修复了 EventLog row descriptor null 导致 formal resolver fail-closed 的根因。所有 identity 链（row/hot/manifest/projection/resolver）从同一 transaction 已写出的 descriptor 派生，无重复计算、无分裂来源、无 fallback 或兼容 shim。formal resolver / projector / private SQLite 未修改，mismatch fail-closed 未放松。测试通过 public formal resolver 覆盖 success、repair-success、exhaust-fallback 三个场景。allowed files 精确、frozen baseline 未变、formatter 无 unrelated diff。
