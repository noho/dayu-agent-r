# WU-CM-01 Aggregate DeepReview Re-Review - MiMo

## 裁决

- Gate: WU-CM-01 aggregate deepreview re-review
- Agent: AgentMiMo
- Verdict: **PASS**
- 设计真源：docs/host/design.md
- 总控文档：docs/host/issues-implementation-control.md
- 复核范围：controller adjudication accepted findings (F-1, F-2, F-3)

## 复核摘要

Controller adjudication 中 3 个 accepted findings 的修复已完成，且未引入违反 design source / AGENTS.md / vNext contract 的问题。所有验证命令通过。

## Accepted Findings 复核结果

### F-1 根 README 残留旧术语 ✅ PASS

- **文件**：`README.md`
- **检查项**：移除 `working memory` / `episode summary` 旧术语，改为 vNext 五类 session memory 表述
- **验证结果**：
  - `grep -E "working memory|episode summary" README.md` 无匹配
  - 第 35 行已更新为：`Durable memory / Retrieval layer（Memory 已落地五类 session memory：Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent）。`
- **结论**：旧术语已清除，vNext 五类 session memory 表述正确落地。

### F-2 `run_input.py` compact artifact message path 旧 payload reader ✅ PASS

- **文件**：`dayu/host/run_input.py`
- **检查项**：删除旧 compact artifact reader 与旧 field constants，改为只读 vNext accepted_candidate / accepted_evidence_mapping_refs
- **验证结果**：
  - 旧函数 `_optional_summary_text_from_compacted_payload`、`_preserved_fact_refs_summary`、`_preserved_canonical_evidence_refs` 均不存在（grep 无匹配）
  - vNext field constants 已正确落地（第 128-129 行）：
    - `_PAYLOAD_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"`
    - `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"`
  - `_compact_artifact_message_content` 函数（第 2606-2640 行）只读取 vNext payload，无兼容读取旧 payload 逻辑
  - `_accepted_evidence_mapping_refs` 函数（第 2643-2655 行）只读取 vNext `accepted_evidence_mapping_refs`
  - `_vnext_compact_candidate_summary` 函数（第 2658-2694 行）只读取 vNext `accepted_candidate`
  - 无旧 field alias、无 extra payload
- **结论**：旧 compact artifact reader 已完全删除，vNext reader 正确实现，无兼容逻辑残留。

### F-3 `test_public_compact_smoke.py` `evidence_input` 命名残留 ✅ PASS

- **文件**：`tests/host/test_public_compact_smoke.py`
- **检查项**：将 `evidence_input` 命名残留改为 `evidence_material`
- **验证结果**：
  - `grep "evidence_input" tests/host/test_public_compact_smoke.py` 无匹配
  - `evidence_material` 已正确使用（多处）：
    - 第 208-210 行：`evidence_material = material_json["evidence_material"]`
    - 第 686-690 行：`_first_material_json_with_evidence` 函数读取 `evidence_material`
    - 第 717 行：`_llm_material_with_long_tool_evidence` 构造 `evidence_material` 字段
- **结论**：`evidence_input` 命名残留已全部替换为 `evidence_material`，测试逻辑正确读取 vNext evidence_material。

## Rejected Findings 确认

### F-4 `context_events.py` 旧字段常量 (rejected-with-reason)

- **状态**：未处理（按裁决保留）
- **确认**：这些私有常量只用于 fail-closed 拒绝旧 payload 字段，且由测试覆盖；不是兼容读取或 re-export。保留作为 schema 防守层符合设计意图。

### F-5 `ForwardIntentTypeVNext.OPEN_QUESTION` (rejected-with-reason)

- **状态**：未处理（按裁决保留）
- **确认**：`open_question` 是 vNext Forward Intent 的合法枚举值，不是旧 block kind 兼容残留。

## `test_run_input_builder.py` vNext reader 覆盖确认

- **文件**：`tests/host/test_run_input_builder.py`
- **检查项**：覆盖 vNext reader 行为，且没有为了保旧测试引入兼容逻辑
- **验证结果**：
  - 第 1398-1427 行：`test_compact_artifact_reader_uses_vnext_evidence_mapping_refs` 明确验证 compact artifact reader 只读取 vNext accepted evidence mapping refs
  - 第 3570-3611 行：测试构造 vNext `accepted_candidate` 和 `accepted_evidence_mapping_refs` payload
  - 测试导入 `_accepted_evidence_mapping_refs` 和 `_vnext_compact_candidate_summary`（第 116-117 行）
  - 无兼容读取旧 payload 的测试逻辑
- **结论**：测试正确覆盖 vNext reader 行为，无兼容逻辑。

## 验证命令与结果

```bash
# 1. 运行受影响测试
source .venv/bin/activate
pytest tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py -q
# 结果：47 passed, 1 skipped in 1.03s

# 2. pyright 类型检查
python -m pyright dayu/ tests/ utils/
# 结果：0 errors, 0 warnings, 0 informations

# 3. whitespace 检查
git diff --check
# 结果：无输出（无 whitespace 错误）
```

## Residual Risks

1. **无 residual risk**：所有 accepted findings 已修复，验证通过，未引入新问题。

2. **scope 确认**：本次复核严格按 controller adjudication 范围执行，未处理 rejected findings (F-4, F-5)，未扩大 scope。

## 结论

Controller adjudication 中 3 个 accepted findings 的修复已完成并通过验证：
- F-1: README.md 旧术语已清除
- F-2: run_input.py 旧 compact artifact reader 已删除，vNext reader 正确实现
- F-3: test_public_compact_smoke.py 命名残留已修正

所有验证命令通过，未引入违反 design source / AGENTS.md / vNext contract 的问题。
