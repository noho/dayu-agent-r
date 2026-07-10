# WU-SEMANTIC-OWNERSHIP-01 P3-G Aggregate Validation

## 结论

P3-G 四个 implementation slices 已完成本地 aggregate validation，进入 aggregate deepreview gate。

Accepted commits：

- Plan: `e5e4ad97`
- S1 SEC form/shared domain typed values: `79629dfa`
- S2 CN/HK report selection ownership: `92320413`
- S3 typed SEC download rejection registry: `c0386fa2`
- S4 XBRL processor result contract: `cbbad162`

## Aggregate 验证

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_read_runtime.py tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py tests/fins/test_cn_report_selection.py tests/fins/test_fins_ingestion_runtime.py::test_start_download_persists_rejected_filing_artifact -q
```

结果：`174 passed, 3 warnings`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果：通过。

## Source Scan 分类

### S1 SEC form/shared domain

```bash
rg -n "form_type_utils|parse_sec_form_type_for_matching|normalize_sec_form_type_for_matching" dayu/fins tests/fins --glob '!tests/fins/fixtures/**'
```

分类：

- `form_type_utils`：无命中，旧 helper 已删除。
- `normalize_sec_form_type_for_matching`：只命中 `dayu.fins.domain.filing_semantics` 真源和消费者 import/call。
- `parse_sec_form_type_for_matching`：无旧路径残留。

### S2 CN/HK report selection

```bash
rg -n "CnFiscalPeriod = Literal\\[\\\"FY\\\"|CnFiscalPeriod|FiscalPeriod" dayu/fins tests/fins --glob '!tests/fins/fixtures/**'
```

分类：

- `CnFiscalPeriod = Literal["FY"...]`：无命中。
- `dayu/fins/pipelines/cn_download_models.py` 中 `CnFiscalPeriod: TypeAlias = FiscalPeriod` 是预期命中。
- 其它 `CnFiscalPeriod` 命中均消费 shared domain `FiscalPeriod` 的别名。

### S3 SEC download rejection registry

```bash
rg -n "dict\\[str, dict\\[str, str\\]\\]|DownloadRejectionEntry|DownloadRejectionRegistry|load_download_rejection_registry|save_download_rejection_registry" dayu/fins tests/fins --glob '!tests/fins/fixtures/**'
```

分类：

- `DownloadRejectionEntry` / `DownloadRejectionRegistry`：预期 typed contract 命中。
- `load_download_rejection_registry` / `save_download_rejection_registry`：预期 repository protocol/implementation/test 命中。
- `_fs_maintenance_core.py` 的 `payload: dict[str, dict[str, str]]`：仅为 JSON 落盘前局部 serialization payload，不是 public registry contract。
- `sec_downloader.py::_build_file_metadata_map(...)` 的 `dict[str, dict[str, str]]`：SEC 文件元数据 mapping，与 download rejection registry 无关。
- `tools/section_semantic.py` 的 `dict[str, dict[str, str]]`：SEC section map 常量，与 download rejection registry 无关。

### S4 XBRL processor result contract

```bash
rg -n "normalized_payload\\[\\\"total\\\"\\]|\\\"total\\\": len\\(deduped_facts\\)|deduped_fact_count|validate_xbrl_facts_result_payload" dayu/fins tests/fins --glob '!tests/fins/fixtures/**'
```

分类：

- 未发现 `"total": len(deduped_facts)`。
- `normalized_payload["total"] = validated.total`：保留 processor raw total，非重算。
- `validate_xbrl_facts_result_payload`：domain validator、read runtime consumer、fiscal inference consumer。
- `deduped_fact_count`：read runtime 派生 projection 与测试断言。

## Propagation Audit 汇总

- SEC form semantics：`dayu.fins.domain.filing_semantics` 统一产生/校验 SEC form、fiscal period、document/financial data quality；processors、download pipeline、read runtime 均消费 domain helper。
- CN/HK report selection：HTTP downloaders 只负责 provider raw payload/HTTP/PDF 边界；report filtering、language/fiscal inference、amended priority、grouping/dedupe 和 candidate construction 由 `dayu.fins.pipelines.cn_report_selection` 持有。
- SEC rejection registry：producer 写 `DownloadRejectionEntry`；repository load/save 使用 `DownloadRejectionRegistry`；SEC skip、SC13 filtering、diagnostics 和 ingestion runtime rejected artifact 路径消费同一 typed registry。
- XBRL facts result：processors 产生 raw `facts`/`total`；`dayu.fins.domain.xbrl_result_contract` 校验 raw result；read runtime 与 fiscal inference 在投影/推断前消费同一 validator；LLM-facing read result 保留 processor-owned `total`，dedupe 后数量用 `deduped_fact_count`。

## README 判定

- `dayu/fins/README.md` 已记录 P3-G 新增/迁移的稳定 Fins contract：source/rejection registry 和 XBRL processor result contract。
- `tests/README.md` 未更新：本 P3-G 没有新增测试层级、目录职责或运行方式；只是在既有 Fins 测试边界补充测试。

## Residual Risk

- S4 `xbrl_result_contract.py` 单文件覆盖率为 `80%`，刚好满足 gate；未覆盖每一个错误消息分支。
- 旧 workspace 中已有坏 `_download_rejections.json` 会 fail closed；P3-G 按新 schema/contract 起库处理，不做兼容迁移。

## Next Gate

P3-G aggregate deepreview by AgentMiMo and AgentDS.
