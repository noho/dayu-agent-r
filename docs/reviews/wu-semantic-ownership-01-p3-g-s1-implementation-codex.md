# WU-SEMANTIC-OWNERSHIP-01 P3-G S1 Implementation - AgentCodex

## 状态

- Completion state: `ready-for-code-review`
- Slice: S1 - SEC Form and Shared Domain Typed Values
- 本轮只实现 S1；未移动 CN/HK downloader filtering，未修改 rejection registry contract，未修改 XBRL total contract，未 commit。

## 动机校验

动机成立。S1 前 SEC form 归一化至少分散在 processor helper、SEC pipeline helper、SEC fiscal helper 与 SC13 browse-edgar 辅助路径中；`fiscal_period`、processed `quality`、financial data quality 也缺少共享封闭值 parser。多个入口分别解释同一业务事实，会让 storage/read/processor 表面可用但持久化语义漂移。S1 应把 parser 真源收束到 `dayu.fins.domain`，下游只消费 domain 投影。

## 文件变更

- 新增：`dayu/fins/domain/filing_semantics.py`
- 删除：`dayu/fins/processors/form_type_utils.py`
- 修改：
  - `dayu/fins/domain/document_models.py`
  - `dayu/fins/pipelines/sec_form_utils.py`
  - `dayu/fins/pipelines/sec_filing_collection.py`
  - `dayu/fins/pipelines/sec_fiscal_fields.py`
  - `dayu/fins/pipelines/sec_pipeline.py`
  - `dayu/fins/pipelines/sec_rebuild_workflow.py`
  - `dayu/fins/pipelines/sec_sc13_filtering.py`
  - `dayu/fins/processors/sec_processor.py`
  - `dayu/fins/processors/bs_report_form_common.py`
  - `dayu/fins/processors/sec_report_form_common.py`
  - `dayu/fins/processors/sec_form_section_common.py`
  - `dayu/fins/tools/read_runtime_helpers.py`
  - `tests/fins/test_sec_pipeline_download.py`
  - `tests/fins/test_fins_storage_provider.py`
  - `tests/fins/test_fins_read_runtime.py`
  - `dayu/fins/README.md`

未触碰 handoff 列出的无关 untracked 文件。

## Source Finding Coverage

- AgentDS 7 / SEC form normalization drift：已收束到 `dayu.fins.domain.filing_semantics`。旧 `processors/form_type_utils.py` 已删除；processor、pipeline、read runtime、SC13 browse-edgar 均改为消费 domain helper。
- AgentDS 8 / naked strings current-partial：S1 覆盖共享 parser surface：`SecFormType`、`FiscalPeriod`、`DocumentQuality`、`FinancialDataQuality`，并在 `RejectedFilingArtifact.from_meta_dict(...)` 与 `DocumentSummary.from_dict(...)` decode 边界校验 form/fiscal/quality。
- S1 非目标：CN/HK report selection、typed rejection registry、XBRL total contract 均未实现或迁移。

## Owner Boundary 与传播审计

- SEC form 产生：用户/CLI SEC form filter、SEC provider submissions/browse-edgar raw rows、source/rejected/processed meta restore。
- SEC form 校验真源：`dayu.fins.domain.filing_semantics`。
  - 用户输入使用 `parse_sec_form_filter_value(...)` / `expand_sec_form_aliases(...)` fail closed。
  - provider raw rows 使用 `normalize_sec_form_type_for_matching(...)` 后由现有窗口/支持集合过滤，避免把未知 SEC row 误判为用户输入错误。
  - 持久化单一 rejected filing form 使用 `parse_sec_form_type(...)`，禁止 `SC 13D/G` 组合别名进入单一 filing meta。
- Fiscal period 真源：`normalize_fiscal_period(...)` 与 `sanitize_fiscal_period_by_sec_form(...)`。download/processed fiscal helper 消费该 parser；domain summary decode 对非法财期 fail closed。
- Document quality 真源：`normalize_document_quality(...)`。`DocumentSummary.from_dict(...)` 不再接受任意 `quality` 字符串。
- Financial data quality 真源：`normalize_financial_data_quality(...)` 已提供给后续 processor contract slice 消费；S1 添加 parser 与测试，不改 XBRL total/result contract。
- 投影路径：domain parser -> SEC pipeline form expansion / SEC collection filtering / fiscal helper -> processor selection -> source/processed summary decode -> read runtime matching。read runtime 只消费 canonical form matching helper，不维护自己的 SEC form 映射。

## 行为变化

- `SC13D/G`、`SCHEDULE 13D/G` 等 SEC filter alias 由 domain helper 展开为 `SC 13D`、`SC 13D/A`、`SC 13G`、`SC 13G/A`。
- `10K`、`10-K/A`、`def 14a`、`SCHEDULE 13D` 等 SEC form alias 由 domain parser canonicalize。
- SEC user filter 不支持的 form 继续 fail closed；SEC provider submissions 中不在目标窗口的未知 form 只被跳过。
- `DocumentSummary.from_dict(...)` 对非法 `fiscal_period` / `quality` 抛 `ValueError`。
- storage JSON 字段名未变。

## 测试与验证

- `source .venv/bin/activate && pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_read_runtime.py -q`
  - 结果：`84 passed, 3 warnings`
  - warnings：edgartools deprecation warnings，非本轮变更引入。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && rg -n "form_type_utils|from dayu\\.fins\\.processors\\.form_type_utils|from \\.form_type_utils|normalize_form\\(|normalize_form_type\\(|_normalize_form\\(|_normalize_form_type\\(|_normalize_report_form_type\\(|_normalize_form_for_fiscal\\(" dayu/fins tests/fins`
  - 结果：无输出，exit code 1，表示没有命中。
- `git diff --check`
  - 结果：通过，无输出。

## Source Scan Classification

handoff 指定旧 helper / 旧 normalize pattern scan 无命中，因此没有需要分类的残留 citation 或非 citation match。

## README 决策

- 已阅读 `dayu/fins/README.md` Agent 更新约束。S1 新增稳定 domain parser/封闭值公共契约，属于 `dayu.fins` 当前已实现公共契约边界，因此更新 `dayu/fins/README.md`。
- 已阅读 `tests/README.md`。本轮只在现有 `tests/fins` 层内新增 focused tests，没有新增测试层级或改变 tests 职责，因此不更新 `tests/README.md`。

## 残余风险 / Deferred

- `DocumentSummary.form_type` 仍保留通用字符串形态，因为 Fins summary 同时承载 SEC form、CN/HK 财报形态和 material form；S1 只把 SEC 单一 form parser 与 rejected SEC artifact decode 收口，避免误把 material/CN 值按 SEC form fail closed。
- `FinancialDataQuality` parser 已建立，但 XBRL result payload 的强制 contract 校验属于 P3-G S4，未在 S1 消费。
- `Any` 类型别名与既有 `DocumentMeta = dict[str, Any]` 是既有 broad domain/storage contract，本轮未扩大；后续若要消除需单独切片。
