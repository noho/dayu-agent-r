# WU-SEMANTIC-OWNERSHIP-01 P3-G S4 Controller Validation

## 结论

P3-G S4 当前实现进入 code review gate。

Controller 复核确认：read runtime 不再用 dedup 后数量覆盖 processor-owned `total`；raw XBRL facts result contract 由轻量 domain validator 统一校验，read runtime 与 fiscal inference 两个 direct consumers 均消费同一 validator。

## Controller 审阅范围

- `dayu/fins/domain/xbrl_result_contract.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/pipelines/sec_fiscal_fields.py`
- `dayu/fins/tools/result_types.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_fins_storage_provider.py`
- `dayu/fins/README.md`

## Owner Boundary 判定

- First producer：`sec_processor.py` 与 `bs_report_form_common.py` 的 `query_xbrl_facts(...)`，当前均返回 raw `facts` 与 `total=len(facts)`。
- Validator：`dayu.fins.domain.xbrl_result_contract.validate_xbrl_facts_result_payload(...)`。
- Consumer/projection：
  - read runtime normalization 在 raw payload validation 后才清洗、dedupe facts。
  - fiscal inference direct consumer 在读取 facts 前校验 raw payload。
  - LLM-facing result 保留 processor-owned `total`；dedupe 后数量使用派生字段 `deduped_fact_count`。

## 验证

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py -q
```

结果：`82 passed, 3 warnings`

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py --cov=dayu.fins.domain.xbrl_result_contract --cov-report=term-missing --cov-fail-under=80 -q
```

结果：`82 passed, 3 warnings`；`dayu/fins/domain/xbrl_result_contract.py` coverage `80%`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果：通过。

## Source Scan

```bash
rg -n "normalized_payload\\[\\\"total\\\"\\]|\\\"total\\\": len\\(deduped_facts\\)|deduped_fact_count|validate_xbrl_facts_result_payload|query_xbrl_facts" dayu/fins tests/fins --glob '!tests/fins/fixtures/**'
```

结论：

- 没有 `"total": len(deduped_facts)`。
- `normalized_payload["total"] = validated.total` 是保留 processor raw total，不是重算。
- `validate_xbrl_facts_result_payload` 命中 validator、read runtime consumer 与 fiscal inference consumer。
- `deduped_fact_count` 仅作为 read runtime 派生投影字段存在。

## 待 Code Review 挑战点

- validator 是否位于正确 owner boundary；`dayu.fins.domain` 是否比 `dayu.fins.processors` 更适合作为轻量 contract owner。
- read runtime 是否仍可能在 validation 前过滤、dedupe 或覆盖 raw facts / total。
- fiscal inference 是否应 fail closed 还是继续旧的 best-effort 读取坏 payload。
- `deduped_fact_count` 是否为必要且命名清晰的派生字段，是否会造成 LLM-facing 误解。
- 测试是否覆盖 S4 要求的 missing total、non-int total、raw mismatch、valid raw total preserved、dedupe shrink、direct consumer fail closed。
