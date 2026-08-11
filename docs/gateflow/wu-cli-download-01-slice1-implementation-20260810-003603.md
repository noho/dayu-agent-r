# wu-cli-download-01 Slice 1 implementation evidence

## 1. 执行身份与范围

- 生成时间：`2026-08-10T00:36:03+0800`（系统时钟）。
- accepted plan commit / base：`0e18abdcd1fb7edbc2fbd2e6a366580beccf5ee8`。
- 当前 Git HEAD：`0e18abdcd1fb7edbc2fbd2e6a366580beccf5ee8`。
- 实现状态：未提交 working-tree diff；base 与 HEAD 相同。
- 计划真源：`docs/gateflow/wu-cli-download-01-plan-20260809.md`。
- 本次仅实现 Slice 1，严格按 S1-A 后 S1-B 推进；未执行 review、commit、push、PR、真实 CLI、Oracle 或 calibration。
- 未修改 runtime helper、Host/Engine、registry/oracle、README；README 统一留待后续 closeout。

## 2. 修改文件

### Production

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/fins.py`
- `dayu/service/fins_direct.py`
- `dayu/fins/download_contract.py`（新增）
- `dayu/fins/domain/filing_semantics.py`
- `dayu/fins/ingestion/observation_handle.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_sc13_filtering.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/pipelines/cn_form_utils.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`

### Tests

- `tests/cli/test_fins_commands.py`
- `tests/service/test_fins_direct.py`
- `tests/service/test_fins_wait_adapter.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`

### Gate evidence

- `docs/gateflow/wu-cli-download-01-slice1-implementation-20260810-003603.md`

## 3. Finding 到 owner 修复映射

| Finding | Owner-level implementation | 关键证明 |
|---|---|---|
| DL-F01 | 新增 `download_contract`，唯一 owner 校验 ticker/forms/date/数量与长度边界；Service builder 和 CLI 在 workspace resolution/runtime factory 前构造 typed request。 | invalid matrix 同时断言中文 usage、exit 2、factory 0 次、workspace 无副作用。 |
| DL-F02 | download builder 拒绝中英文逗号 CSV；重复 `--ticker` 保持 argparse last-wins；download 路径不调用 `_parse_ticker_csv`。 | AST 证明 `_download_stream` 仅调用 Service download；`upload_filings_from` 仍调用 `_parse_ticker_csv`，alias 回归测试通过。 |
| DL-F03 | typed date range携带 inclusive bounds/explicitness；SEC SC13 retry 收到 `start_is_explicit`，显式 start 直接禁止扩窗；候选在 outcome 前通过统一 inclusive 终检。 | 新增显式 SC13 窗口外 filing 不 selected/downloaded/rejected、不持久化测试。 |
| DL-F04 | 普通 SEC workflow 删除 stale cleanup invocation，maintenance API 本身保留。 | 新增真实 source 历史文档在普通 download 后仍存在测试；AST 证明 workflow 不调用 cleanup。 |
| DL-F05 | download-only 字段统一为 `rebuild_local_artifacts`；adapter 将其传给现有 SEC/CN pipeline rebuild branch；runtime/adapter/rebuild workflow 删除 download-only processed 读写。 | SEC/CN adapter 与真实 rebuild tests 证明不联网、不改变 source bytes、不改变 processed；rebuild 文件静态扫描无 processed/reprocess 引用。 |
| DL-F06 | CN/HK missing period 改为独立 `missing_periods`，不再构造 synthetic filing/result/progress event。 | 零候选测试断言 total/downloaded/skipped/failed 均为 0、filings 为空、无 filing completed event。 |

CN/HK 财期 alias 的唯一真源迁移到 `dayu.fins.domain.filing_semantics.parse_fiscal_period_filter_value`；download contract 与 `cn_form_utils.resolve_target_periods` 共同复用，原 `_TOKEN_TO_PERIOD` 已删除。

## 4. S1-A checkpoint

在进入 pipeline 行为修改前完成：

- focused tests：
  - 命令：`source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_runtime.py tests/service/test_fins_wait_adapter.py -q`
  - 结果：`250 passed`，仅 3 条第三方 edgartools deprecation warning。
- 受影响路径 pyright：`0 errors, 0 warnings, 0 informations`。
- import/construct checkpoint：所有 Python import 均来自 `dayu.fins.download_contract`；旧 runtime 不定义或 re-export `FinsDownloadRequest`；production/test 中唯一直接构造点位于 owner builder。
- `git diff --check`：通过。

## 5. S1-B 与完整 Slice 1 owner union

- 最终同一 coverage run：
  - 命令：`source .venv/bin/activate && coverage run -m pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py -q`
  - 结果：`861 passed`，仅 3 条第三方 edgartools deprecation warning。
- changed-files Ruff：全部通过。
- 全量 pyright：`source .venv/bin/activate && python -m pyright dayu tests utils`，结果 `0 errors, 0 warnings, 0 informations`。
- changed-files compileall：通过。
- `git diff --check`：通过。

## 6. 单文件 coverage

以下结果全部来自第 5 节同一次 coverage data；每个文件分别执行 `coverage report --include=<file> --fail-under=80`，退出码均为 0。

| Production file | Statements | Miss | Coverage |
|---|---:|---:|---:|
| `dayu/cli/arg_parsing.py` | 342 | 2 | 99% |
| `dayu/cli/commands/fins.py` | 458 | 66 | 86% |
| `dayu/service/fins_direct.py` | 62 | 6 | 90% |
| `dayu/fins/download_contract.py` | 119 | 3 | 97% |
| `dayu/fins/domain/filing_semantics.py` | 115 | 20 | 83% |
| `dayu/fins/ingestion/observation_handle.py` | 127 | 8 | 94% |
| `dayu/fins/ingestion_runtime.py` | 1663 | 156 | 91% |
| `dayu/fins/tools/download_tools.py` | 50 | 5 | 90% |
| `dayu/fins/pipelines/sec_pipeline.py` | 374 | 48 | 87% |
| `dayu/fins/pipelines/sec_download_workflow.py` | 177 | 19 | 89% |
| `dayu/fins/pipelines/sec_sc13_filtering.py` | 216 | 38 | 82% |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 129 | 13 | 90% |
| `dayu/fins/pipelines/cn_form_utils.py` | 114 | 21 | 82% |
| `dayu/fins/pipelines/cn_pipeline.py` | 320 | 64 | 80%（精确 256/320） |
| `dayu/fins/pipelines/cn_download_workflow.py` | 236 | 38 | 84% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 157 | 30 | 81% |

## 7. Stop-condition 证明

- AST：`_download_stream` 不调用 `_parse_ticker_csv`；`_run_upload_filings_from` 仍调用它。
- AST：`FinsSourceDownloadAdapterRequest` 字段仅为 `normalized_ticker/source/form_types/date_range/overwrite_existing/rebuild_local_artifacts/cancellation_checker/progress_sink`。
- AST/import scan：runtime 不定义 `FinsDownloadRequest`；所有 Python import site 均从 `dayu.fins.download_contract` 导入。
- AST：普通 SEC `run_download_stream_impl` 不调用 `cleanup_stale_filing_dirs`。
- rg/AST：`cn_form_utils.py` 不定义 `_TOKEN_TO_PERIOD`。
- rg：`sec_rebuild_workflow.py` 与 `cn_download_rebuild.py` 均无 `processed_repository` / `reprocess_required`。
- production/test 直接 `FinsDownloadRequest(...)` 构造只存在于 owner builder；README 中旧示例按本 slice 的禁止修改要求未处理。
- worktree 检查：除本 artifact 外，仅包含第 2 节列出的 Slice 1 allowed production/test files；accepted plan/review artifacts 未改动。

## 8. 未执行项、blocking 与 residual risk

- 未运行真实 CLI；未触发 provider 网络、真实下载、Docling、Oracle 或 calibration。
- 未执行 review；未 commit、push、创建或更新 PR，未使用 PR 190。
- Blocking：无。
- Residual：Slice 2/3/4 的 provider policy、public terminal、canonical cancellation、并发与 integrity repair 仍未实施；这是计划内后续工作，不由 Slice 1 扩张处理。
- Residual：`dayu/fins/README.md` 仍含旧 download request/rebuild 描述；按用户明确要求留待实现后统一 closeout，当前 runtime contract 不依赖该文档。
- 测试 warning 仅来自 edgartools 已弃用模块导入，不影响 Slice 1 结果。
