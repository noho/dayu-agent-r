# WU-CM-01 Slice B Fix Gate - Codex

## 范围

本次只处理 Controller accepted findings A1/A2，未扩大到 Slice C/D，未提交、未 push。

## 修改

### A1: 清理旧 compact payload dead helper

- 在 `dayu/host/context_events.py` 删除未调用的旧 `CONTEXT_COMPACTED` payload helper：
  - `_range_list_json`
  - `_evidence_list_json`
  - `_fact_candidate_list_json`
  - `_minimum_preserve_candidate_list_json`
  - `_evidence_ids`
  - `_validate_patch_evidence`
  - `_validate_confirmed_subject_patch`
  - `_validate_replace_patch_value`
  - `_validate_confirmed_subject_item`
  - `_validate_fact_candidates`
  - `_reject_old_preserved_fact_ref_fields`
  - `_validate_minimum_preserve_items`
  - `_validate_opaque_ref_text`
  - `_validate_opaque_ref_kind`
  - `_allowed_opaque_ref_kinds`
  - `_validate_quality_check_result`
  - `_reject_old_quality_result_fields`
- 删除上述 dead helper 牵引的旧 compact 类型、旧 enum、旧最大值常量、旧 opaque-ref helper 与 `canonical_json_dumps` import。
- 保留 vNext fail-closed 逻辑：`_COMPACTED_OLD_FIELDS` 与 `_reject_old_compacted_fields()` 未删除，仍在 `validate_context_compacted_payload()` 入口拒绝旧顶层 compact 字段。

### A2: 修正 stale preserved refs 测试语义

- 将 `tests/host/test_compaction_operation.py` 中陈旧的 preserved refs merge 测试改为 `test_reactive_multi_pass_uses_last_whole_vnext_fact_tuple`。
- 将 fake compactor 改为每个 pass 返回不同 `evidence_backed_facts` tuple。
- 断言 reactive multi-pass 接受最后一次完整 vNext fact tuple：最终只有 pass 2 的 fact tuple，避免继续描述旧 preserved refs merge 语义。

## 验证

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py -q
```

结果：`270 passed in 1.82s`。

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

## README 决策

触发规则命中 `dayu/host/` 与 `tests/`。本次修改只删除已无调用路径的旧 helper，并修正测试名称与断言；不改变 Host 公共契约、执行路径、状态机、事件字段语义或测试手册中稳定说明。因此不更新 README。

## Residual Risks

- vNext `CONTEXT_COMPACTED` 后续 memory durable / projection 消费仍属于 Slice C。
- ordinary RunInputBuilder 对 vNext compacted view 的消费仍属于 Slice D。
- 本次未处理 Controller 明确标为 non-fix 的 `_NO_CONTEXT_BUDGET_POLICY_REF` 观察项。
