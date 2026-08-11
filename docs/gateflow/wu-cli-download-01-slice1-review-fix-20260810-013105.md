# wu-cli-download-01 Slice 1 code-review fix evidence

## 1. Gate metadata

- Work unit：`wu-cli-download-01`
- Gate：Slice 1 code-review fix，等待原 reviewer rereview
- 系统时间：`2026-08-10 01:31:05 CST`（`Asia/Shanghai`）
- accepted plan / amendment HEAD：`85e71774075e07d5b8f24a35930664fe80ffe322`
- 工作树 HEAD：`85e71774075e07d5b8f24a35930664fe80ffe322`
- review inputs：
  - `docs/reviews/code-review-20260810-004038.md`（MiMo）
  - `docs/reviews/code-review-20260810-004602.md`（DS）
- 本轮没有 commit、push、PR、真实 CLI、review 或 README 修改；首版 implementation artifact 与两份 review artifact 保持只读。
- amendment 恢复前保留的 Slice 1 产品/测试 diff 未被回退；本轮只追加 accepted review fix。

## 2. Review disposition

### DS DL-R01 — accepted / fixed

- `FinsDownloadDateRange.__post_init__` 成为日期组合不变量的唯一 owner：
  - `start_is_explicit=True` 要求 `start_bound` 非空；
  - `end_is_explicit=True` 要求 `end_bound` 非空；
  - 双 bound 存在时要求 `start_bound <= end_bound`；
  - 非空 bound 与 `explicit=False` 合法，供未来默认窗口使用；
  - 非法组合统一抛 `FinsDownloadUsageError`。
- builder 删除重复的倒序范围判断，倒序输入仍保留中文错误：`--start 不能晚于 --end，请检查下载日期范围`。
- `start_is_explicit` 以 required `bool` 从 SEC/CN adapter 穿透 pipeline 与 workflow；没有把上层 request 泄漏给 pipeline，也没有默认值、兼容 wrapper 或下游反推。
- SEC SC13 retry 直接消费该 boolean；CN 默认业务数量限制直接消费 `not start_is_explicit`。
- owner tests 证明：
  - SEC 的 `start_date` 非空且 `start_is_explicit=False` 时仍可按 policy 扩窗；
  - CN 的 `start_date` 非空且 `start_is_explicit=False` 时仍启用默认 FY 五年限制；
  - 三种非法 date-range 组合被 owner 拒绝，非空 bound 与 `explicit=False` 被接受。

### DS DL-R02 — accepted / fixed

- 删除没有 production owner 的私有 `_cleanup_stale_filing_dirs`。
- 删除唯一直接固化该私有 helper 的测试。
- 保留并通过 `test_sec_ordinary_download_keeps_unselected_historical_document`，继续由公开 download 行为证明普通 SEC 下载不删除非目标历史文档。

### DS DL-R03 — deferred-with-owner

- 既有 process CLI `--overwrite -> rebuild_processed` 命名不一致不属于本 WU；未改 preprocess/upload 字段或代码。
- 后续由独立 process-command 专项 WU 处理，owner 为 process command 的公开参数到 preprocess request 的映射契约。

### MiMo 001 — rejected-with-reason

- 多个非法 token 从聚合错误变为首错只影响未承诺的错误格式；新 domain owner 仍以中文 actionable 错误 fail closed。
- 未在 `cn_form_utils` 或其它下游增加 catch、错误重建或兼容语义。

### MiMo 002 — rejected

- reviewer 记录的预期与实际一致、影响为无，属于覆盖确认而非 material finding；未改代码。

## 3. Review-fix code and test delta

本轮 review fix 触及的 production files：

- `dayu/fins/download_contract.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/cn_download_workflow.py`

本轮 review fix 触及的 tests：

- `tests/service/test_fins_direct.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`

签名同步范围包括 `SecPipeline.download/download_stream/download_stream_impl`、`CnPipeline.download/download_stream`、两个 workflow implementation、adapter、`_RecordingSecPipelineForAdapter`、`_RecordingPipeline`、`_collect_events`、`_collect_events_async` 及所有真实 call sites。

`tests/fins/test_cn_pipeline.py` 的既有三个显式日期下载调用均传 `start_is_explicit=True`；新增的 pipeline-layer direct contract test 显式传 `False`。该测试绕过当前 builder，仅证明下游消费 typed fact，不是公开端到端合法输入示例。

## 4. Tests and static validation

### Focused owner tests

执行日期 contract、SEC SC13、CN 默认限制和 SEC non-deletion 的 11 个 test selectors（参数化后共 23 cases）：

```text
23 passed, 3 warnings in 1.37s
```

warnings 均来自 edgartools 已弃用模块导入。

### Full Slice 1 owner union

用同一 coverage data 执行：

```bash
coverage run -m pytest \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_direct.py \
  tests/service/test_fins_wait_adapter.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_workflow.py -q
```

结果：`874 passed, 3 warnings in 12.95s`。warnings 同样仅为 edgartools deprecation warnings。

### Type, lint, bytecode and diff checks

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- `python -m ruff check <26 个 changed Python files>`：`All checks passed!`。
- `python -m compileall dayu tests`：exit 0。
- `git diff --check`：exit 0，无输出。
- 对未跟踪的 `dayu/fins/download_contract.py` 与本 artifact 分别执行
  `git diff --no-index --check /dev/null <file>`：无 whitespace error 输出（仅以 no-index
  差异状态结束）。

## 5. Per-production-file coverage

以下结果全部来自第 4 节同一次最终 `coverage run` 生成的 data；每个文件分别以 `coverage report --include=<file> --fail-under=80` 检查，均 exit 0。

| Production file | Statements | Miss | Coverage |
| --- | ---: | ---: | ---: |
| `dayu/cli/arg_parsing.py` | 342 | 2 | 99% |
| `dayu/cli/commands/fins.py` | 458 | 66 | 86% |
| `dayu/fins/download_contract.py` | 124 | 3 | 98% |
| `dayu/fins/domain/filing_semantics.py` | 115 | 20 | 83% |
| `dayu/fins/ingestion/observation_handle.py` | 127 | 8 | 94% |
| `dayu/fins/ingestion_runtime.py` | 1663 | 156 | 91% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 157 | 30 | 81% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 236 | 23 | 90% |
| `dayu/fins/pipelines/cn_form_utils.py` | 114 | 21 | 82% |
| `dayu/fins/pipelines/cn_pipeline.py` | 320 | 38 | 88% |
| `dayu/fins/pipelines/sec_download_workflow.py` | 176 | 19 | 89% |
| `dayu/fins/pipelines/sec_pipeline.py` | 369 | 47 | 87% |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 129 | 13 | 90% |
| `dayu/fins/pipelines/sec_sc13_filtering.py` | 216 | 38 | 82% |
| `dayu/fins/tools/download_tools.py` | 50 | 5 | 90% |
| `dayu/service/fins_direct.py` | 62 | 6 | 90% |

## 6. AST / rg stop-condition evidence

- AST 证明 `start_is_explicit` 在 SEC 三个 public pipeline 方法、CN 两个 public pipeline 方法及两个 workflow implementation 中均为无默认值的 required keyword-only `bool`。
- AST 证明两个 workflow implementation 内不存在以 `start_date is/is not None` 反推显式性的比较；SEC 向 `_retry_sc13_if_empty` 传 typed boolean，CN 以 `not start_is_explicit` 控制默认业务限制。
- `rg -n "_cleanup_stale_filing_dirs" dayu tests`：无结果；普通 download non-deletion owner test 保留。
- AST 证明 `FinsDownloadRequest` 字段仅为 `normalized_ticker/source/form_types/date_range/overwrite_existing/rebuild_local_artifacts`，download request 不含 `rebuild_processed`。
- `rg -n "FinsDownloadRequest" dayu tests` 与 import 检查确认 production/test import 均指向 `dayu.fins.download_contract`；`ingestion_runtime.py` 只消费 owner 类型，无 re-export。
- `rg -n "_TOKEN_TO_PERIOD" dayu/fins/pipelines/cn_form_utils.py`：无结果。
- AST 对比 HEAD 证明 `dayu/cli/commands/fins.py:_parse_ticker_csv` 与 `_run_upload_filings_from` 均未变化，upload/preprocess alias 行为未被 download builder 改写。
- local-only rebuild workflow 的 `processed`/`processed_repository` 搜索无结果；未恢复 download-only `rebuild_processed`。
- download production 路径未新增 `getattr`/`hasattr` fallback，未新增 compatibility shim 或 re-export。
- `tests/fins/test_cn_pipeline.py` 相对 HEAD 的全部 diff hunks止于新 direct download test；首个 upload test 从当前第 546 行开始，upload tests、fixtures、helpers 零 diff。
- worktree 检查未发现 Slice 1 allowlist 之外的产品/测试修改；额外未跟踪文件仅为既有 implementation/review evidence 与本 fix evidence。

## 7. Residual risks and next gate

- Blocker：无。
- DS DL-R03 仍为明确 deferred item，由后续 process-command 专项 WU 接管。
- Slice 2/3/4 的 provider policy、public terminal、canonical cancellation、并发与 integrity repair 仍未实施，属于 accepted plan 的后续范围。
- README 按 accepted plan 留到实现完成后的 closeout 统一更新；本轮未触碰现有 README 文本。
- 未运行真实 CLI；网络 provider 行为不在本 review fix 验证范围。
- 下一 gate：把本 artifact 交还原 MiMo/DS reviewers rereview；AgentCodex 不自行 review、commit、push 或建 PR。
