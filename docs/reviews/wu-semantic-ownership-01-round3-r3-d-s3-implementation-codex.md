# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S3 Implementation

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S3 — Fiscal And Normalization Owners, SEC Version Alignment, Docs And Aggregate Closure`
- Gate: `implementation`
- Agent: `AgentCodex`
- Status: `implementation-complete`
- Prerequisites: accepted S1 commit `cae77ab3`; accepted S2 commit `03fe9548`
- Artifact path: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-implementation-codex.md`
- Next allowed action: controller validation / S3 code review；本次未进入 code review、commit、S4、R3-E 或 push。

## Scope And First-Principles Judgment

S3 动机成立，属于生产语义 owner 收敛，不是 style cleanup。实施前直接代码证据显示：read runtime 与 helper 各持有一份不同 fiscal rank，read helper 仍会从 annual form 补 `FY`；三个 SEC processor 各自包装 pandas 空值；all-files-not-modified 分支没有下载版本条件；upload alias 只执行 `strip().upper()`。这些路径会让同一业务事实由多个 consumer 解释，或让 legacy SEC meta 被错误视为 current。

正确 owner 已明确：fiscal 值与 rank 属于 domain，dataframe 可选字符串属于 processor scalar adapter，SEC 下载版本相等性属于 download state，upload alias canonicalization 属于 ticker normalization。实现仅修改 accepted S3 白名单和本 artifact，没有进入 Host/Engine、R3-E 或工具安全策略。

## Changed Files

### Production

- `dayu/fins/domain/filing_semantics.py`
- `dayu/fins/processors/value_normalization.py`（新增）
- `dayu/fins/processors/sec_section_build.py`
- `dayu/fins/processors/sec_table_extraction.py`
- `dayu/fins/processors/sec_xbrl_query.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/README.md`

### Tests

- `tests/fins/test_fiscal_normalization_contracts.py`（新增）
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`

### Artifact

- `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-implementation-codex.md`（新增）

未修改其它 allowed test files，因为现有 material upload 与 read semantic guard 已由 required focused/full regression 覆盖，且不需要为通过测试改变其契约。

## Owner Decisions And Contract Changes

### Fiscal owner

- `dayu.fins.domain.filing_semantics` 新增 `normalize_fiscal_year(...)` 和 `fiscal_period_recency_rank(...)`，固定 `None/unknown=0, Q1=1, Q2=2, H1=3, Q3=4, Q4=5, FY=6`。
- fiscal year 只接受非 bool 正整数；缺失为 `None`；bool、零、负数、浮点数和数字文本全部失败关闭。
- read source meta 使用 domain fiscal year/period parser；`fiscal_period` 只接受字符串并 canonical 化，非法非空值抛 `ValueError`。
- read runtime 删除 fiscal inference/fallback、第二份 mutable rank map、dead recency/recommendation duplicate；annual form 与 report/filing date 不再产生 fiscal 事实。
- runtime recency sort 直接调用 domain rank helper；fiscal 缺失仍可按显式日期排序，但日期不再被解释为 issuer fiscal year。

### Dataframe optional string owner

- 新增 `dayu.fins.processors.value_normalization.normalize_optional_dataframe_string(...)`，使用显式 `StringConvertible` protocol，不新增 `Any/object/getattr/hasattr` 签名逃逸。
- 统一矩阵：`None`、blank、float NaN、`pd.NA`、`pd.NaT` -> `None`；`0` -> `"0"`；`False` -> `"False"`；普通文本 trim。
- section/table/XBRL 三个 consumer 删除本地 wrapper，直接调用同一 helper。

### SEC download version owner

- `dayu.fins.pipelines.sec_download_state.has_current_download_version(...)` 成为版本相等性 helper。
- fast skip、remote fingerprint/files skip、all-files-not-modified terminal skip 都调用该 helper。
- legacy/missing version 即使所有文件返回 not-modified，也继续现有 source batch/upsert/commit；成功后的 meta 写入 current `SEC_PIPELINE_DOWNLOAD_VERSION`。
- current version 的 not-modified skip 保持 rollback/no-meta-rewrite 行为。

### Upload ticker alias owner

- upload canonical ticker 与每个非空 alias 都调用 `try_normalize_ticker(...)`，只持久化 `.canonical`。
- canonical 始终首项；`700.HK -> 0700`、`BRK.B -> BRK-B`，大小写和市场后缀变体按 canonical 稳定去重。
- 无法识别的非空 alias 抛 `ValueError`；spy repository 证明错误发生时 `upsert_company_meta` 零调用。
- CN upload 旧夹具中的 company-name alias 已迁移为真实 ticker suffix alias；没有保留 raw uppercase 或 company-name fallback。

## README Decision

已按 `dayu/fins/README.md` 的 Agent 更新约束更新当前事实：

- financial statement 与 XBRL result 的 required fields、quality/reason、scale/units、valid-empty/partial/all-failed invariant；
- storage-owned source revision 与 processor/meta cache reuse/race fail-closed contract；
- source decode、search index、XBRL all-failed、source-change typed degradation；
- fiscal parser/rank 与 dataframe optional string owner；
- upload ticker alias canonical/no-write-on-invalid contract。

README 没有写测试命令、work-unit/gate 状态或未落地能力。禁止词扫描 `R3-D|plan gate|future|tool-security|SSRF|allowlist` 为零匹配。根 README、`dayu/README.md`、`tests/README.md` 不更新：没有安装/CLI/分层/测试组织变化。

## Validation Results

全部命令均在 `source .venv/bin/activate` 后执行。

### S3 required validation

- `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`：`37 passed, 3 warnings`。
- `pytest tests/fins/test_sec_pipeline_download.py -q -k 'skip or not_modified or download_version'`：`6 passed, 30 deselected, 3 warnings`。
- `pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q -k 'company_meta or ticker_alias'`：`8 passed, 12 deselected, 3 warnings`。
- `coverage run -m pytest tests/fins/test_fiscal_normalization_contracts.py -q`：`23 passed, 3 warnings`。
- `coverage report --include='dayu/fins/processors/value_normalization.py' --fail-under=80`：`100%`（13 statements，0 missed）。
- `pytest tests/fins -q`：`628 passed, 1 skipped, 3 warnings`。
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。

warnings 均为 edgartools 现有 deprecated import warning；没有新增测试失败或类型错误。

### S1-S3 aggregate validation

- financial/read/cache/fiscal aggregate matrix：`119 passed, 3 warnings`。
- storage financial/XBRL/search/cache/revision selector：`21 passed, 44 deselected, 3 warnings`。
- named 6-K invalid UTF-8 node：`1 passed, 3 warnings`。
- SEC XBRL/6-K/skip/version selector：`12 passed, 24 deselected, 3 warnings`。
- upload company-meta/alias selector与完整 `tests/fins` 结果见上；覆盖 S1-S3 producer -> domain -> read -> tool、source revision/cache、decode/search、SEC version 与 alias propagation。

## Propagation Scan Classification

### S3 required scans

1. read/tool fiscal duplicate scan：零匹配。没有 `_FISCAL_PERIOD_SORT_ORDER`、`_infer_fiscal_*`、`_resolve_fiscal_*fallback`、`build_document_recency_sort_key` 或 `_build_recommended_documents` 残留。
2. 三个 processor 私有 optional wrapper scan：零匹配。
3. `normalize_optional_dataframe_string` scan：只命中新 owner 定义、三个 consumer 的直接 import/call 和 owner contract tests，均为预期。
4. SEC version scan：fast、remote、not-modified 三个 skip condition 均可追到 `has_current_download_version(...)`；测试覆盖 current/legacy/missing version 矩阵。
5. upload alias scan：production `upload_company_meta.py` 无 `strip().upper()`；只命中 `try_normalize_ticker` 与 `_normalize_ticker_aliases` owner/call/test。全 `tests/fins` 扫描额外命中的四处 `strip().upper()` 位于既有 SEC download fake/stub，不是 upload alias producer，未修改且不表达持久化 alias 语义。
6. Fins README 禁止词 scan：零匹配。

### Aggregate source audit

- financial shadow payload、NotRequired quality/reason、duplicate decimals scale map和 read/tool fiscal fallback：零匹配。
- financial/XBRL/revision/error consumer scan：命中均为 domain owner、直接 typed consumer、public projection或 contract test；没有旧兼容 re-export。
- virtual section assignment scan：直接 index/table assignment 只位于 S2 accepted mixin owner。
- `dayu.fins` 到 `dayu.host/dayu.engine` 反向 import scan：零匹配。
- `errors="ignore"` 有 3 个匹配，均在 `dayu/fins/downloaders/sec_downloader.py` 的远端 HTML/index-header heuristic parsing；相同匹配可在 accepted S2 commit `03fe9548` 复现，不是 S3 新增或扩散，也不在 S3 allowed files。分类为 later Fins downloader decode-policy owner residual，不能在本 slice 越界修改。
- broad `except Exception: continue` 有 3 个匹配，均在 `sec_xbrl_query.py` 的 taxonomy、units 和 fiscal evidence 辅助 probe；相同匹配可在 accepted S1 commit `cae77ab3` 复现。这些 probe 失败返回缺失证据并由 financial contract 降级为 typed `partial`，不是 `_query_facts_rows` 主 concept execution 的 failure-to-empty 路径，分类为 legitimate auxiliary adapter behavior。
- changed-file audit 只包含 S3 allowed production/test files、Fins README、新增 owner/test和本 expected artifact；无 Host/Engine/config prompt/R3-E 文件。

## Residual Risks And Uncovered Areas

- **Assigned to later work unit:** SEC downloader 的 3 处 permissive UTF-8 heuristic decode 仍存在。它们不属于 S2 strict processor source decode path，也不在 S3 allowed files；后续若收敛，owner 应是独立 Fins downloader decode policy，不能由 read runtime 下游补偿。controller 需在 umbrella closeout 前确认具体 destination。
- **Assigned to later work unit:** accepted plan 已记录的 broad `DocumentMeta` type migration与 6-K BS-only routing保持不变；S3 未宣称修复。
- **Tracked dependency warning:** edgartools deprecated import warnings 仍存在，不影响当前 contract correctness；由依赖升级工作处理。
- **Current slice coverage:** 新增 normalization owner 100%；既有大文件通过 focused branch matrix与完整 `tests/fins` 回归，没有对未触及 pipeline style/`Any` 做顺手清理。

没有未分类 residual risk；没有发现需要 issuer-specific calendar、非 ticker company-name alias、remote/security policy 或 R3-E 文件才能完成 S3 的条件。

## Scope Confirmation And Completion Status

- S3 exact allowed changes：完成。
- S1-S3 aggregate validation与 propagation audit：完成。
- R3-E / tool-security expansion：无。
- Code review：未进入。
- Commit：未创建。
- S4：未进入。
- Push：未执行。
- Blocking questions：无。
- Gate decision：`implementation-complete`，交回 controller 进入其指定的 validation / code review gate。
