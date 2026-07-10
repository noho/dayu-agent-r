# WU-SEMANTIC-OWNERSHIP-01 P3-G S4 Implementation - Codex

## 动机校验

S4 动机成立。`query_xbrl_facts` 的 raw `total` 是 processor-owned 结果契约；read runtime 之前在 `_normalize_xbrl_query_payload(...)` 中把 `total` 覆盖为 dedup 后 facts 数量，会掩盖 processor 缺字段、字段类型错误或 raw total 与 raw facts 数量不一致等 contract violation。

本 slice 只处理 XBRL processor result contract 和 read runtime / fiscal inference consumption；未修改 S1 SEC form parser、S2 CN/HK report selection 或 S3 rejection registry。

## 文件变更

- `dayu/fins/domain/xbrl_result_contract.py`
  - 新增 `ValidatedXbrlFactsResult` 与 `validate_xbrl_facts_result_payload(...)`。
  - 校验 raw `query_params` 必须为 object、raw `facts` 必须为 list、raw `total` 必须为非 bool 整数，且 `total == len(raw_facts)`。
  - 可选 `data_quality` 复用 domain `normalize_financial_data_quality(...)`；可选 `reason` 必须为非空字符串。
- `dayu/fins/tools/read_runtime_helpers.py`
  - `_normalize_xbrl_query_payload(...)` 在 fact normalization / dedupe 前先调用 validator。
  - 不再重算或覆盖 processor-owned `total`；valid payload 保留 raw `total`。
  - dedupe 后数量与 raw `total` 不同时，用 `deduped_fact_count` 投影派生数量。
- `dayu/fins/tools/read_runtime.py`
  - 将 `query_xbrl_facts` raw payload cast 收窄为 JSON payload，交给 contract validator。
- `dayu/fins/pipelines/sec_fiscal_fields.py`
  - 直接消费 processor `query_xbrl_facts` 的 fiscal inference 也先调用同一 validator；坏 contract fail closed 为 `(None, None)`。
- `dayu/fins/tools/result_types.py`
  - `XbrlQueryResult` 增加可选 `deduped_fact_count`。
- `tests/fins/test_fins_read_runtime.py`
  - 覆盖 missing total、non-int total、raw total mismatch 均 fail closed。
  - 覆盖 valid raw total 在 read runtime dedupe 后被保留，并投影 `deduped_fact_count`。
  - 覆盖 SEC fiscal inference 直接消费 processor 时拒绝 invalid total。
- `tests/fins/test_fins_storage_provider.py`
  - 更新既有 XBRL cancellation 测试 processor，使其遵守 raw `total` contract。
- `dayu/fins/README.md`
  - 记录 XBRL facts processor result contract 的当前稳定 owner 和 read runtime consumption 规则。

## Owner Boundary / Propagation Audit

- 产生：`sec_processor.py` 与 `bs_report_form_common.py` 的 `query_xbrl_facts(...)` 继续产生 raw `facts` 和 `total=len(facts)`。
- 校验：`dayu.fins.domain.xbrl_result_contract.validate_xbrl_facts_result_payload(...)` 是 raw XBRL facts result contract validator。
- 持久化：本 slice 不新增 durable state；processor result 是 read path runtime value。
- 消费：
  - read runtime 在 `_normalize_xbrl_query_payload(...)` 中先校验 raw payload，再做 fact normalization / dedupe / LLM-facing projection。
  - `sec_fiscal_fields._extract_fiscal_from_xbrl_query(...)` 作为另一个 direct processor consumer，也先校验同一 raw contract。
- 投影：
  - LLM-facing `query_xbrl_facts` result 保留 processor-owned `total`。
  - post-dedup 展示数量仅用派生字段 `deduped_fact_count`，不冒充 processor raw total。

## Source Scan 分类

命令：

```bash
rg -n "normalized_payload\\[\\\"total\\\"\\]|\\\"total\\\": len\\(deduped_facts\\)|deduped_fact_count|validate_xbrl_facts_result_payload|query_xbrl_facts" dayu/fins tests/fins --glob '!tests/fins/fixtures/**'
```

分类：

- `normalized_payload["total"] = validated.total`：保留 processor raw total，非重算。
- 未发现 `"total": len(deduped_facts)`。
- `deduped_fact_count`：仅 read runtime derived projection 与测试断言。
- `validate_xbrl_facts_result_payload`：domain validator、read runtime consumer、fiscal inference consumer。
- `query_xbrl_facts`：producer、tool name、tests 和 docs 预期命中。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py -q`
  - 结果：`82 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py --cov=dayu.fins.domain.xbrl_result_contract --cov-report=term-missing --cov-fail-under=80 -q`
  - 结果：`82 passed, 3 warnings`
  - `dayu/fins/domain/xbrl_result_contract.py` coverage：`80%`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过

## README 决策

- `dayu/fins/README.md`：已更新。S4 改变了 Fins read runtime / processor result 的稳定公共契约。
- `tests/README.md`：未更新。只是在既有 Fins read/runtime 测试边界补充 contract cases，没有新增测试层级、运行方式或目录职责。

## 残余风险

- `xbrl_result_contract.py` 单文件覆盖率刚好 80%，满足当前 gate；未额外覆盖所有错误消息分支。
- 若第三方或未来 processor 返回非 JSON payload，当前 read runtime 仍按既有 cast 边界进入 validator；本 slice 只修 raw XBRL result contract，不扩展 processor invocation type system。

## Completion State

ready-for-code-review
