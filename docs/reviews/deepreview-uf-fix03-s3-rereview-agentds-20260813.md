# Deep review re-review — UF-FIX03 S3 controller review-fix（AgentDS 路）

## Scope

- Mode: current changes（定向 re-review）
- Branch: `codex/upload-filing-oracle`
- Base: `a65cec93`（`gateflow: accept UF-FIX03 typed failure S2`）
- Output file: `docs/reviews/deepreview-uf-fix03-s3-rereview-agentds-20260813.md`
- Review date: 2026-08-13
- Reviewer: AgentDS（re-review 路）
- Included scope: 当前未提交工作树相对 `a65cec93` 的全部改动（8 文件，+692/-30），对照输入：
  - `docs/reviews/deepreview-uf-fix03-s3-20260813.md`（AgentMiMo 首轮）
  - `docs/reviews/deepreview-uf-fix03-s3-agentds-20260813.md`（AgentDS 首轮，三项 NEEDS_FIX）
  - `docs/gateflow/uf-fix03-s3-review-fix-20260813.md`（controller 裁决与修复记录）
  - `docs/gateflow/uf-fix03-s3-implementation-20260813.md`（S3 implementation artifact，已复核 deferred 条目状态）
- Excluded scope: S1/S2 已提交改动；UF-PF03 未执行（按要求不执行真实 UF-PF03）
- Parallel review coverage: 无（主 reviewer 全程走读）

## 首轮 findings 逐项判定

### F1 — file label cap：已闭环

首轮 Finding 1（高）：content failure 的 canonical `file` label 位于 detail position 9，renderer `_FINS_SUMMARY_MAX_ITEMS = 8` 截断后不进入真实 CLI stderr。

修复判定（PASS）：

- `dayu/fins/ingestion_runtime.py:6372-6395` `_upload_result_details` 新顺序：`source kind`、`status`、`requested files`、`stored files`、`failure kind`、`failure code`、`file`（存在时）、`failure message`、`retry hint`（存在时）、`document`（存在时）。failure 前缀前 8 项同时包含 counts（3/4）、kind（5）、code（6）、file（7）、reason（8）；`document` 与 `retry hint` 只在无失败或前缀未满时进入 cap=8 窗口。
- 排序仍由 typed owner 机械投影：`_direct_upload_terminal_events`（`ingestion_runtime.py:6030`）与无 runner failed 路径（`ingestion_runtime.py:3967-3978`）直接消费 `_upload_result_details`，值全部来自同一个 `FinsUploadResultSummary` / `FinsUploadFailureReason`，无重算、无字符串解析。
- renderer 无特例：`dayu/cli/output.py:496-509` `_summary_parts` 仍是对任意 `FinsEventDetail` 元组的纯机械 cap=8 截断；`output.py` 相对基线零改动（no-touch 已验证）。
- owner 护栏：`tests/fins/test_fins_ingestion_runtime.py::test_upload_direct_details_consume_typed_failure_label_and_retry_hint` 在带 `document_id` + `retry_hint` 的 content failure 上断言完整 10 项顺序与 cap=8 前缀 `("source kind", "status", "requested files", "stored files", "failure kind", "failure code", "file", "failure message")`——即 document/retry hint 存在时 file 与 bounded message 也不会被截断。
- 真实 CLI 护栏：`tests/cli/test_fins_commands.py::test_real_cli_content_failure_has_bounded_stderr_and_zero_fresh_workspace_mutation` 参数化 empty.pdf/corrupt.pdf/corrupt.docx，subprocess 断言 `file="{file_name}"`、`failure_code=`、`requested_files="1"`、`stored_files="0"`、bounded reason 均在真实 stderr 且长度 ≤1024、无 Traceback、无仓库绝对路径、无输入绝对路径。
- implementation artifact 已把该条从「Assigned to later work unit」移入「Fixed in current review-fix」（`docs/gateflow/uf-fix03-s3-implementation-20260813.md:135`）。

### F2 — unknown --log-file 可行动性：已闭环

首轮 Finding 2（中）：默认匿名 `TemporaryFile` 日志进程结束即删，固定文案未提及唯一可行动出口 `--log-file`。

修复判定（PASS）：

- `dayu/cli/commands/fins.py:99-101` 新增模块级 `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE = "命令执行失败，请使用 --log-file PATH 重试并查看日志"`。
- `dayu/cli/commands/fins.py:220-228` generic `except Exception` 不绑定 `exc`：`_LOGGER.exception("Fins direct command failed; command=%s", ...)` 完整 traceback 只进 operator log；stderr 为 `dayu-cli <command>: <固定文案>`，固定且有界。
- 文案中的 flag 名与真实参数一致：`--log-file` 定义于 `dayu/cli/arg_parsing.py:405`，`dayu/cli/main.py:99-101` 以 append 模式打开用户路径。
- 已知 typed 分支（`CliFinsUsageError`/`UploadBatchPlan*`/`FinsDownloadUsageError`/`FinsUploadUsageError`/`FinsUploadPrevalidationError`/`FinsDirectStreamProtocolError`/`KeyboardInterrupt`，`fins.py:196-219`）均保留各自 closed projection，不被 generic 吞并。
- 护栏：`test_unknown_fins_direct_failure_logs_traceback_and_hides_exception_from_stderr` 断言 stderr exact 固定文案、marker/`/absolute/path`/`Traceback`/`RuntimeError` 不在 stderr 且全在 `caplog.text`；`test_stream_failure_propagates_to_cli_error` 注入的 `RuntimeError("stream boom")` 为非 typed 异常，走 generic 分支断言 exact 固定文案，`stream boom` 与 `job_id` 均不在 stderr，同时断言 stream 已确定性关闭。
- 根 README（`README.md` 上传段落 +2 行）明确 `PATH` 应为可写文件、需重新执行命令，与 `main.py:180` 默认日志「进程结束即清理」的既有语义自洽。

### F3 — upload_filing 四状态 requested/stored CLI 护栏：已闭环

首轮 Finding 3（中）：success/delete/skip/failure 的 CLI 摘要渲染无 requested/stored 断言，`uploaded_files` 缺失无护栏。

修复判定（PASS）：

- `tests/cli/test_fins_commands.py::test_upload_terminal_summary_renderer_uses_typed_requested_and_stored_counts` 参数化 `ok/deleted/skipped/failed` 四终态：
  - 每个 fixture 先构造 production `FinsUploadResultSummary`，再经 `FinsUploadFilingRequest` + public `validate_fins_upload_filing_request`（`ingestion_runtime.py:987`）取得 typed request；
  - 调用 production 唯一 terminal owner `_direct_upload_terminal_events`（production 主路径调用点 `ingestion_runtime.py:3995`），将 summary 机械投影为真实 `FinsResultSummary.details`，再进入既有 `render_fins_direct_event`；
  - 断言 `requested_files=` / `stored_files=` 正确值、`uploaded_files` 不出现、另一 stream 为空（ok/deleted/skipped → stdout，failed → stderr，与 `output.py:236-258` 的 SUCCESS/FAILURE 分流及 `_direct_upload_result_status` COMPLETED→SUCCESS 映射一致）。
- 复用而非复制：validator 为 public API；failure fixture 用 public `fins_upload_failure_from_exception(RuntimeError(), file_label=None)`（`upload_failure.py:161-201`，映射为固定 RUNTIME/UNEXPECTED_RUNTIME 中文 message，无异常文本），与 production 无 runner failed 路径 `ingestion_runtime.py:3973-3976` 同源构造；`_NeverCancelledJobChecker` 完整实现 `FinsJobCancellationChecker`（`__call__`）+ `CancellationToken`（`is_cancelled`/`cancel_reason`/`requested_at`）协议面（`dayu/contracts/cancellation.py:21-47`），未复制取消、计数、状态或错误映射逻辑。
- 业务逻辑未复制：测试只构造最小 `_FinsIngestionExecutionContext` 与 validator 所需的安全输入文件，不产生 workspace/业务 publication。

## Controller 补充检查复核

### no-artifact jobs path 真源

- `test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts` 中 `jobs_dir` 先 `isinstance(job_store, FsFinsIngestionJobStore)` 收窄，再用 `job_store.root_dir`；`root_dir` 由生产 `FsFinsIngestionJobStore.from_workspace_root` 从 `_JOBS_DIR_PARTS`（`ingestion_runtime.py:139`）派生，且是同一 store 实例的同一属性——即使 `_JOBS_DIR_PARTS` 迁移，测试仍与生产 job 写入路径同源，硬编码脆弱性已消除。误触的既有 download 测试已恢复（`tests/service/test_fins_direct.py` 仅新增 3 行 Service 公开 API 负断言，语义未变）。

### 其它补充项

- `_upload_result_details` 排序仍由 typed owner 机械投影：仅有的两个调用点（`ingestion_runtime.py:3967`、`6030`）都在 fins runtime 内；CLI renderer 对 details 只做等权截断，无 label 特例、无差异化 cap。
- frozen：`docs/cli_ci_scenarios.json` SHA-256 `a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`、`docs/cli_ci_oracles.json` SHA-256 `88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`，与 accepted plan 及 review-fix artifact 声明一致。
- no-touch：`dayu/host/`、`dayu/engine/`、`dayu/runtime/`、`dayu/config/`、`dayu/service/` production、`dayu/ui/`、`dayu/cli/output.py`、`dayu/cli/main.py`、`dayu/fins/storage/`、frozen JSON/evidence 相对基线零改动（`git diff a65cec93 --name-only` 与 `git status --short` 双重验证）。
- UF-PF03：未执行；workspace 无新增 evidence 文件。
- README 边界：根 README +2 行（upload_filing requested/stored 语义、整批失败 stored=0、stderr 同时显示文件名与有界原因、unknown 固定文案与 `--log-file PATH` 指引）；`dayu/fins/README.md` +4 段（requested/stored owner、typed terminal 投影排序、fail-fast 与原子 publication、第三方异常文本只进 operator log）；`tests/README.md` +12 行（focused 回归命令与四个覆盖面的描述）。三处均在各自「Agent更新约束」职责边界内且与代码一致。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- F3 CLI 护栏通过私有 seam（`_FinsIngestionExecutionContext` / `_direct_upload_terminal_events`）直连 fins runtime 内部构造，测试与该私有签名强耦合；若 runtime 重构这两个私有结构，CLI 层测试需随动。这是 controller 已裁决的「唯一测试链」取舍，以「不复制业务逻辑」换取私有签名耦合，当前可接受。
- `document` 在 failed + document_id 同时存在时会被 cap=8 挤出（位于 position 10）；这是 review-fix 的显式优先级设计（失败前缀优先可行动事实），owner 测试已固化该前缀护栏，但真实 CLI 上该场景无 subprocess 级断言。
- 未复跑 S3 artifact 声称的全量 broader 回归与 coverage 数字（用户指示收敛）；本轮验证为定向 368 passed 与 pyright 0/0/0。`cn_pipeline.py` 69% 覆盖率裁决与 upload tool fixture `company_name` 缺失仍归 controller 后续裁决，本 slice 未扩大。
- 真实 Docling 多平台差异与 UF-PF03 evidence 按 plan 排除。

## 结论

**PASS**

首轮三项 NEEDS_FIX（F1 file label cap、F2 unknown --log-file 可行动性、F3 四状态 CLI requested/stored 护栏）均已按 controller 裁决在各自 semantic owner 处闭环：detail 排序由 typed terminal owner 机械投影且前 8 项含 counts/kind/code/file/reason、renderer 无特例；unknown 固定 stderr 自足可行动且 traceback 只进 operator log；四状态测试复用 public validator 与 production terminal owner 未复制业务逻辑；no-artifact jobs path 与生产 job store 同源；frozen SHA 与 no-touch 边界一致；README 三处更新在各自职责边界内。定向验证：`tests/cli/test_fins_commands.py` + `tests/fins/test_fins_ingestion_runtime.py` + `tests/service/test_fins_direct.py` 共 368 passed（3 warnings 均为第三方 edgar DeprecationWarning），pyright 0 errors / 0 warnings / 0 informations。未执行 UF-PF03。
