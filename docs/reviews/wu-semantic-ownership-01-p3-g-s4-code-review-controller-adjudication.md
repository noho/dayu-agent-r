# WU-SEMANTIC-OWNERSHIP-01 P3-G S4 Code Review Controller Adjudication

## 结论

P3-G S4 accepted，无 fix gate。

两路 code review 均返回 PASS，未发现 material finding：

- `docs/reviews/wu-semantic-ownership-01-p3-g-s4-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-p3-g-s4-code-review-ds.md`

## Controller 裁决

本轮 accepted findings：0。

原因：

- XBRL facts raw `total` 的 owner boundary 已回到 processor result contract。
- `dayu.fins.domain.xbrl_result_contract.validate_xbrl_facts_result_payload(...)` 是轻量 domain validator，不导入 `dayu.fins.processors` 重型 package。
- read runtime 在 fact normalization / dedupe 前校验 raw payload，不再用 dedup 后数量覆盖 `total`。
- fiscal inference direct consumer 也先消费同一 validator；坏 contract fail closed 为 `(None, None)`。
- LLM-facing result 保留 processor-owned `total`，dedupe 后数量仅用派生字段 `deduped_fact_count`。
- 两路 review 均确认未越界修改 S1/S2/S3、processor producer 逻辑或 tool schema。

## 已验证

Controller validation artifact：

- `docs/reviews/wu-semantic-ownership-01-p3-g-s4-controller-validation.md`

验证结果：

- `pytest tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py -q` -> `82 passed, 3 warnings`
- `pytest tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py --cov=dayu.fins.domain.xbrl_result_contract --cov-report=term-missing --cov-fail-under=80 -q` -> `82 passed, 3 warnings`; `xbrl_result_contract.py` coverage `80%`
- `python -m pyright dayu/ tests/ utils/` -> `0 errors`
- `git diff --check` -> pass

## Propagation Audit

- 产生：`sec_processor.py` 与 `bs_report_form_common.py` 的 `query_xbrl_facts(...)` 产生 raw `facts` 和 raw `total`。
- 校验：`dayu.fins.domain.xbrl_result_contract.validate_xbrl_facts_result_payload(...)` 校验 raw `query_params`、raw `facts`、raw `total`、`data_quality` 和 `reason`。
- 持久化：本 slice 不新增 durable state；XBRL facts result 是 read path runtime value。
- 消费：read runtime 与 fiscal inference 均消费同一 validator。
- 投影：read runtime 保留 processor-owned `total`，并在去重后数量变化时投影 `deduped_fact_count`。

## 下一步

提交 accepted P3-G S4。S4 是 P3-G 最后一个 implementation slice；提交后进入 P3-G aggregate validation / deepreview gate。
