# 下载失败诊断：S1 implementation

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6.1-sol

CANARY=gpt-6-sol-726ab7ce

- Work unit：download-failure-diagnostics-20261010；slice S1：任何合法下载终态交付同源完整失败诊断。
- 当前 gate：implementation；下一 entry point：总控 code review。本文不裁决 slice/gate/work unit pass。
- Branch：`fix/download-failure-diagnostics-20261010`。
- Accepted plan / 当前 HEAD：`a1df000835c61d1acfa383532488746e1487ed7b`；base：`c65c2aa28fae9c47ad947783d63f7559db7768c4`。
- Plan SHA256 实测：`7de77259a5ca545ef959376471f7d902c48fd31dece024b3ce04468b7e18c9f9`，冻结身份一致。
- 本轮 canary 工具读取路径：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.Ffv4UQ/canary.txt`，逐字内容如上。provider 与 configured model 分开报告，无物理型号独立证明，无 Node 探针。
- 初轮事实与失败保留在总控只读归档 `download-failure-diagnostics-implementation-initial-20261010.md`；续作记录在 `download-failure-diagnostics-implementation-continuation-20261010.md`。

## Preflight 与边界

已读仓库 AGENTS.md、gateflow implementation slice、confirmed goal、approved plan（重点 §3—§5）、initial partial、总控 test-scope-adjudication、plan re-review adjudication 和 primary artifact；四个 README 的职责已核对。动机成立：已有完整 typed rows 在公开摘要截断、CN/HK 原因投影改写处丢信息；冻结方案修直接 owner，而不是在 CLI 推测旧原因。本轮不重新 plan、不更换接口、不撤销初轮合适实现。

Preflight/status 的所有改动均属于本 unit。state/test-scope-adjudication/implementation-initial 为总控 owned，只读；review 报告归 reviewer。没有未知 dirty。初轮缺的两个 import、locator 文本断言、六命令真实 operation fixture、F5 旧总行数、trailing whitespace 已收尾；名单外 F5 测试权限由总控既有裁决明确授予，无新范围请求。

仅 exact5 生产、指定测试、三个允许 README 与本 implementation/continuation artifacts 写入。`test_cn_download_workflow.py`、`test_fins_ingestion_tools.py` 及 SEC 两个回归文件只运行、不修改。无子 Agent、staging/commit/push/PR、后续 review、调用方文件处理、生产 query、网络新来源观测、原生产 root 下载/overwrite/recovery。临时验证输出仅 `workspace/tmp/`，未新增脚本文件或常驻分析工具。

## 完整 changed files（含初轮延续的 S1 改动）

| 文件 | 最终行为 / 改动 |
| --- | --- |
| `dayu/fins/download_contract.py` | 下载 durable/public uncertain 共用 4096 JSON 预算常量；原计数与来源 schema 不变。 |
| `dayu/fins/direct_events.py` | `download_result` 单一 typed 真源、派生 `download` property、public classmethod、共享 row helper、完整 diagnostics JSON 与操作不变量。 |
| `dayu/fins/ingestion_runtime.py` | 全链传完整 typed result；request-scoped 空失败/取消、activation owner 收口、claim 取消保存前缀；删除旧 public helper。 |
| `dayu/fins/pipelines/cn_pipeline.py` | CN/HK FAILED/SKIPPED strict 保真 reason pair，无 fallback。 |
| `dayu/cli/output.py` | 默认唯一完整诊断物理行、原输出通道、human summary terminal_disposition。 |
| `tests/fins/test_download_failure_diagnostics.py`（新增） | owner、完整/bounded 同源、多来源/数量/未知/特殊身份、操作负例、CLI 通道及 OSError。 |
| `tests/fins/test_cn_download_runtime.py` | 实际 owner import、strict fixture；真实 CN/HK reason 矩阵、已知日期/不同覆盖、skip/rebuild/mismatch、typed abort 同对象前缀。 |
| `tests/fins/test_fins_ingestion_runtime.py` | 完整 constructor 迁移；activation、prepare cancel、已确认 downloaded+failed 与 claim 竞争；direct/durable 同源与 SEC 机械投影。 |
| `tests/fins/test_fins_direct_stream.py` | 合法 DOWNLOAD terminal fixture 带完整 typed 真源，原 stream 状态机回归。 |
| `tests/fins/test_f5_result_contract.py` | public projection 调用迁移到 direct owner，预算/未知合同不变。 |
| `tests/fins/test_f5_workflow_rebuild.py` | 按总控裁决仅增加唯一诊断行同源解析，旧物理行数 +1，原 counters/channel/未知语义保留。 |
| `tests/cli/test_output.py` | typed fixture 迁移、locator 公共字符串及按前缀单行解析，保留原业务计数和通道。 |
| `tests/cli/test_fins_commands.py` | 六命令真实 operation fixture、原调试 detail；主入口 default/quiet 十二失败、绝对 fixed binary fresh empty rebuild。 |
| `tests/service/test_fins_direct.py` | 合法下载/非下载 fixture 迁移；validated stream/event/terminal/full result 同对象三终态。 |
| `tests/service/test_fins_wait_adapter.py` | 完整 typed fixture、真实 observation→wait 三终态 bounded，原 scope_note 等 schema 保留。 |
| `README.md` | 用户默认诊断、两通道捕获、退出 0/partial 区别、临时日志历史限制。 |
| `dayu/fins/README.md` | 稳定 full/bounded 接口、原因 owner、取消及 observation 生命周期边界。 |
| `tests/README.md` | 新 owner/真链/CLI/Service 回归及 fixed binary smoke 的命令与证据限制。 |
| 本 primary implementation artifact | 最终实现、断言证据、验证与剩余边界。 |
| continuation artifact（新增） | 本轮身份、preflight、初轮缺口收尾与停止入口。 |

## Owner 与 dataflow

候选身份、日期、form/coverage 和安全原因由来源 workflow 产生。CN/HK adapter 在直接输入处严格读取 reason_code/reason_message，交给 typed row 的安全校验；正常、rebuild、typed integrity 三入口共享投影。缺字段/空字段/unsafe 不得用 skip_reason 或默认文案补救。来源已有报告日与覆盖在真实 workflow→typed→public/diagnostics 逐字段对齐；未知保持 null/空数组。SEC 不改既有 adapter，完整接口只机械保留其已有安全字段。

`FinsDownloadResultSummary` → runtime 请求身份/计数校验 → 原终态 claim → `FinsResultSummary.download_result`。无另一个 public constructor 输入。direct owner 的 `from_result_summary` 派生前十行、omitted 和原 uncertain 预算；完整 FAILED rows 与 bounded rows 共用 `_download_public_document` 及 public row JSON，只把相对 PurePosixPath 转字符串。

诊断字段精确为 operation/status/exit_code/summary/failed_documents/failure/scope_note；失败数组原序无截断，`len(failed_documents)=full.failed_count=summary.counts.failed`。整体 failure 与候选原因分开。DOWNLOAD RESULT 必须有 full result，其它 operation 禁止携带；非下载诊断方法拒绝。启动前及 activation 失败只由持有请求的 runtime owner 生成 typed 空 FAILED，不从消费者补默认值。activation 原异常同对象抛出，safe whole failure 不包含原异常文本。

取消用同一完整 snapshot 覆盖 terminal 为 CANCELLED，已确认下载/失败行保留、failure=null，未处理候选不造事实；claim 后已接受终态不被取消覆盖。validated stream 仍只在 clean exhaustion 后交付唯一 RESULT，协议/异常/close 原语义不变。

CLI 用 `ensure_ascii=True, sort_keys=True` 序列化 owner JSON，不走 bounded/truncation helper；特殊字符和 240 码点 ID 可逆且不增物理行。SUCCESS/partial 写 stdout，FAILURE/CANCELLED 写 stderr，进度仍 stdout，退出政策不变。default/quiet 不影响业务诊断。

Service 原样传同一验证流/终态。wait 仍只序列化 property 的 bounded JSON；失败/取消原业务 scope_note 保留，不新增完整 diagnostics wrapper。durable download 摘要 schema、真实 store validator/status 及 4096 预算不变。LLM/tool/Host/EventLog/memory/trace 没有新增完整失败数组。

## Plan §5.1 八组 success signal 断言证据

以下用例都进入最终受影响集合；命令终态见下一节，不把计划预期当验证结果。

| 组 | 具体断言与测试 owner |
| --- | --- |
| 1 owner/public | `test_failures_after_first_ten_are_complete_and_same_source`：11 skip+1 downloaded+12 FAILED，full 24、failed 12、bounded 10、omitted 14，失败逐字段/同序/full 同对象；`test_complete_diagnostics_across_sources_counts_and_unknowns`：三 source×0/1/10/11/12×null/已知，240 码点特殊 ID 可逆、全失败完整。owner 负例分别检查 DOWNLOAD 缺 full、错误 typed 值、每个非下载 operation 带 full 拒绝、合法非下载调用诊断拒绝。 |
| 2 CN/HK 真链 | `test_cn_hk_real_workflow_failure_reasons_reach_complete_diagnostics`：两 source×timeout/http/protocol/storage/execution，真实隔离 Fs、workflow 和 adapter，只替外部 discovery/PDF transport/converter；候选日期、报告日、不同 coverage、reason pair 在 workflow→typed→bounded/full 逐字段相等，敏感原异常不泄漏。`test_cn_hk_real_skip_and_hk_rebuild_keep_workflow_reason` 保 integrity_complete/period_metadata_current；`test_hk_period_metadata_mismatch_is_real_failed_diagnostic` 真正本地 FY 与新来源 FY/Q4 mismatch，workflow failed、typed FAILED、完整数组含该行且无额外 transport。strict 3 入口×2 disposition×缺/空/unsafe 30 负例拒绝。 |
| 3 runtime | `test_download_runtime_full_result_and_durable_budget_same_source` 验 empty/partial/all_failed status/exit/terminal/full 同对象与真实 job store bounded JSON。启动前 provider 用例断言 request-scoped typed 空 FAILED、0 counts/rows、真实 PROVIDER/CONNECTION whole failure，原安全值不变。CN 真实 churn typed abort 断言 `full is adapter_failure.persisted_summary`、downloaded+failed 前缀、停止尾候选及完整原因；SEC 真实 integrity direct 两场景只断言已有 typed rows 逐字段机械进入 diagnostics，不承诺 upstream 原因保真。activation submit OSError/ValueError 均原异常同对象、poll FAILED/FAILURE/1、EXECUTION safe whole failure、全部 request filters/0 rows，非下载 upload 保 None 与诊断拒绝。 |
| 4 cancellation/stream | `test_cancel_prepared_download_preserves_request_and_never_submits` 按 prepare→cancel→activate→poll，两个 snapshot CANCELLED/130、executor.operations=[]、请求过滤原样、空 typed、failure=None。`test_download_cancel_preserves_downloaded_failed_prefix_and_claim` 的 workflow_cancelled/before_claim/after_claim 三例保 1 downloaded+12 failed 及原 tuple/原因，只在取消赢时 CANCELLED/130；claim 后 SUCCESS/0 与原 full 同对象。原 very-early cancel、validated stream 唯一/缺失/重复/后续 RESULT、clean exhaustion、BaseException 身份/close 一次全部回归。 |
| 5 CLI render | owner 测试 SUCCESS/partial/FAILURE/CANCELLED 按固定前缀选恰一条物理行，json.loads 还原同一 diagnostics；另一通道无前缀、human terminal 可见。特殊引号/换行/反斜杠/U+2028/U+2029 身份可逆、原因/null 不截断；输出 OSError 原样传播。非下载六命令 fixture 真实 operation、无 diagnostics，原 counters/processed_count/log detail 断言留在适用操作。F5 新物理行按总控裁决 +1，同源唯一 JSON 和原渠道仍断言。 |
| 6 LLM/durable | `test_real_download_observation_wait_three_terminals_stay_bounded`：真实 prepare/activate/poll→wait 三终态、12 failures、前 10 skips，bounded documents=10/omitted 守恒、full tuple 原样；没有 failed_documents/download_result/完整 wrapper。现有 F5/未知报告预算回归与真实 store 验证字段/预算/原取消规则，无旧库兼容。 |
| 7 Service/主入口 | `test_service_passes_same_stream_terminal_full_result` 三终态 assert stream/event/terminal/full tuple 原对象、12 failures。`test_cli_main_default_temporary_log_delivers_twelve_failures` 三终态×default/quiet，factory 仅替外部装配，full typed 经真正 owner 算 JSON；原通道、exit、唯一行、12失败/10 bounded、stream terminal 同对象。 |
| 8 fixed executable | `test_fixed_cli_download_diagnostics_on_empty_rebuild`：fresh tmp 来源 root、另一仓库外空 cwd、绝对 `.venv/bin/dayu-cli`、timeout=60/check=False；真实 returncode=0，stdout 前缀恰一行、stderr 无前缀，parsed ticker 0700/forms FY,H1/原窗口/rebuild true/全零 counts/failed_documents=[]/terminal succeeded。只证明固定 binary 实际加载新协议与装配，不是远端失败、原生产恢复或旧原因的证据。 |

## 实际 validation

基线 pyright=0 引用总控已验证证据，不重复基线。下列命令全部先 `source .venv/bin/activate`；pytest 使用托管 session，逐次取得真实 exit，不用后台文件增长或 ps 代替终态。最终源码/测试没有 ignore、compat 或 coverage 计算修改。

最终受影响集合 A（exact plan §5.2）：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_download_failure_diagnostics.py \
  tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py \
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_direct_stream.py \
  tests/fins/test_f5_result_contract.py tests/fins/test_fins_ingestion_tools.py \
  tests/cli/test_output.py tests/cli/test_fins_commands.py \
  tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py \
  tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_f5_workflow_rebuild.py -q --tb=short \
  > workspace/tmp/dfdiag-continuation-affected-final-state.txt 2>&1
python -m pyright dayu/ tests/ utils/ \
  > workspace/tmp/dfdiag-continuation-pyright-final.txt 2>&1
```

| 命令 / 本轮阶段 | 真实 exit / 计数 | 证据 |
| --- | --- | --- |
| focused：CN runtime、CLI output/commands、F5 rebuild 四文件 `-q --tb=short` | 1；400 passed/1 failed/3 warnings，85.94s。默认下载 fixture 的调试 detail 被删，随后只恢复测试的合法 detail。 | `dfdiag-continuation-focus.txt`。 |
| focused：runtime 新前缀/claim、empty/partial/all_failed、activation/prepare cancel 与 HK mismatch，`-k` 对应名称 | 0；10 passed/603 deselected/3 warnings，1.51s。 | `dfdiag-continuation-runtime.txt`。 |
| focused：Service/wait 三终态、CLI 主入口/调试 detail，首次 | 1；4 passed/9 failed/283 deselected/3 warnings，2.20s。原因是测试错误 factory 符号、错误读取成功 value 与误禁既有 scope_note；均在指定测试修正。 | `dfdiag-continuation-entry.txt`。 |
| 同 focused 修正后 | 0；13 passed/283 deselected/3 warnings，1.50s。 | `dfdiag-continuation-entry-fixed.txt`。 |
| A 收尾集合（随后只补测试候选已知元数据/类型收窄） | 0；1478 passed/0 failed/0 skipped/3 warnings，101.82s。 | `dfdiag-continuation-affected-final.txt`。 |
| **A 最终文件状态完整集合** | **0；1478 passed/0 failed/0 skipped/3 warnings，106.83s。** | `dfdiag-continuation-affected-final-state.txt`。 |
| `python -m pyright dayu/ tests/ utils/` 中间轮 | 1；先 4 个新 wait 测试字段收窄错误，再 2 个 CN Optional 收窄错误，均修在指定测试；不是基线。 | 前者 `dfdiag-continuation-pyright-first.txt`，后者原工具输出；不冒充最终。 |
| **最终 `python -m pyright dayu/ tests/ utils/`** | **0；0 errors/0 warnings/0 informations。** | `dfdiag-continuation-pyright-final.txt`；仅 pyright 新版本提示。 |
| `git diff --check` | 0；无 trailing whitespace。 | 真实工具输出。 |

focused 具体命令（runtime 和入口的筛选两文件/三文件使用相同 -k）：

```bash
python -m pytest tests/fins/test_cn_download_runtime.py tests/cli/test_output.py \
  tests/cli/test_fins_commands.py tests/fins/test_f5_workflow_rebuild.py -q --tb=short
python -m pytest tests/fins/test_fins_ingestion_runtime.py \
  -k 'download_cancel_preserves_downloaded or download_runtime_full_result or activation_submit_failure_terminalizes or cancel_prepared_download' \
  tests/fins/test_cn_download_runtime.py \
  -k 'download_cancel_preserves_downloaded or download_runtime_full_result or activation_submit_failure_terminalizes or cancel_prepared_download or period_metadata_mismatch' -q --tb=short
python -m pytest tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py \
  tests/cli/test_fins_commands.py \
  -k 'three_terminals_stay_bounded or same_stream_terminal_full_result or default_temporary_log_delivers or debug_log_outputs_event_details' -q --tb=short
```

### Coverage 与资源型验证

```bash
source .venv/bin/activate
python -m pytest tests/fins tests/cli tests/service -q -rs --tb=short \
  --cov=dayu.fins.download_contract --cov=dayu.fins.direct_events \
  --cov=dayu.fins.ingestion_runtime --cov=dayu.fins.pipelines.cn_pipeline \
  --cov=dayu.cli.output --cov-report=term-missing \
  > workspace/tmp/dfdiag-continuation-coverage.txt 2>&1
python -m coverage report \
  --include='dayu/fins/download_contract.py,dayu/fins/direct_events.py,dayu/fins/ingestion_runtime.py,dayu/fins/pipelines/cn_pipeline.py,dayu/cli/output.py' \
  --fail-under=80
```

Coverage 托管命令实际 exit **1**：**5059 passed、67 failed、14 skipped、3 warnings，634.37s**。这次 broad 集合不是通过；没有把其余通过项或 coverage 当成失败免责。覆盖数据来自该完整执行，未排除失败测试或生产行、未改配置/计算。

标准 `coverage report --include=... --fail-under=80 --precision=2` 实际 exit **0**。该命令只验证覆盖数据阈值，不能改写 pytest exit 1；precision 仅显示小数，不改变计算。逐文件全部 >=80：

| 文件 | Stmts | Miss | 实际逐文件覆盖率 |
| --- | ---: | ---: | ---: |
| `dayu/fins/download_contract.py` | 475 | 55 | 88.42% |
| `dayu/fins/direct_events.py` | 477 | 47 | 90.15% |
| `dayu/fins/ingestion_runtime.py` | 2500 | 198 | 92.08% |
| `dayu/fins/pipelines/cn_pipeline.py` | 458 | 27 | 94.10% |
| `dayu/cli/output.py` | 208 | 7 | 96.63% |
| 总计（不替代逐文件门槛） | 4118 | 334 | 91.89% |

原始 missing line 列表保留在 coverage 日志；未达到 100%，没有声称未覆盖分支已验证。

### Broad 范围外失败与直接证据

67 个 failure entry 都在未修改的其它 CLI/Service 测试，精确分布如下，不把它们当通过：

| 未修改测试 | 数量 | 实际失败事实 / 最小后续 owner 路径 |
| --- | ---: | --- |
| `tests/cli/test_interactive_command.py` | 36 | 多个原 call chain 明确在 `host_assembly._render_headers` 抛 `missing env MIMO_PLAN_API_KEY`，在 Host open/请求/业务输出之前失败；当前 fixture 样本只配置 DEEPSEEK_API_KEY。后续 owner 是 Service model/env 装配与对应 CLI fixture，先裁决现有配置选择/测试输入，不在 Fins 输出层补原因或注入凭据。 |
| `tests/cli/test_prompt_command.py` | 23 | 同类环境/模型装配失败与未达到预期请求/退出/输出。直接 traceback 指向上述 unchanged owner；不承诺每个只有 exit 断言的实例都已单独证明相同根因，完整列表留 raw log 给总控。 |
| `tests/cli/test_init_workspace.py` | 4 | 真实 discovery observer 得到 `(False,False)`，旧断言要求 `(True,True)`；单例独立重现。最小后续路径是 init transaction/discovery 配置 owner 与这些 fixture，不改变本 S1 下载职责。 |
| `tests/cli/test_arg_parsing.py` | 2 | upload_material help 缺旧预期 `--internal-document-id`；上传非 filing 的 `--primary` 没有按旧断言 SystemExit。最小后续路径是上传 CLI grammar 与该测试期待的既有不一致，未修改。 |
| `tests/cli/test_workspace_root.py` | 1 | 纯 AST 对 unchanged `commands/fins.py` 数到 3 次 `resolve_workspace_root`，旧断言固定 2 次。 |
| `tests/service/test_import_boundary.py` | 1 | 纯 AST 命中 unchanged Service 的 `dayu.fins.download_contract` / `dayu.fins.company_metadata_warning`，旧 allowlist 未包含两条现存 import。 |

基线归属证据：对上述六个测试，以及 `dayu/cli/commands/fins.py`、arg_parsing/init_workspace/session_execution、Service entrypoint_runtime/host_assembly/fins_direct/fins_wait_adapter，分别用 `git diff --exit-code` 对 accepted HEAD 和原 base `c65c2aa28fae9c47ad947783d63f7559db7768c4` 比较，两个命令均 exit 0、无差异；Config 与 base 对比也 exit 0。静态失败完全由这些相同文本产生；环境失败的真实 owner 条件是 env 中 required key 缺失，调用链不经过新增 Fins 诊断渲染。此处不把“其它文件未改”单独当根因，而以实际 traceback、纯 AST/解析结果及独立用例复现为依据。

独立最小复现命令（先激活 venv，不带 coverage，不修改配置/环境或源码）：

```bash
python -m pytest tests/cli/test_arg_parsing.py tests/cli/test_init_workspace.py \
  tests/cli/test_interactive_command.py tests/cli/test_prompt_command.py \
  tests/cli/test_workspace_root.py tests/service/test_import_boundary.py \
  -k 'test_command_help_contains_core_arguments or test_upload_filing_primary_is_append_only_on_filing_command or test_first_real_discovery_is_private_and_publishes_only_config or test_interactive_label_targets_shared_agent_slot_and_default_context or test_prompt_command_outputs_fast_live_terminal_and_converts_requests or test_workspace_root_is_the_only_ordinary_cli_resolver or test_service_does_not_import_forbidden_layers' \
  -q --tb=short > workspace/tmp/dfdiag-continuation-broad-baseline-check.txt 2>&1
```

实际 exit **1**：**7 failed、11 passed、701 deselected、3 warnings，1.72s**，同样七个代表失败重现。不是完整独立 base checkout 的全套重跑，也不冒充 67 项逐个根因裁决；范围外最小路径交总控维护侧，不顺手修。S1 exact 受影响集合的 1478 passed 和五文件覆盖数据独立报告；broad 的失败仍保持 failure。

### 资源型 skip（14，不计通过）

- 真实 Docling upload 集成：1（缺 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`）。
- 真实混合许可 XBRL/受控运行/内核：6（缺外部管理员资源），没有真实内核或来源验证声明。
- Windows 四态/junction/symlink/identity/setx：5（当前 macOS）。
- 真实 cmd.exe 上传命令：2（当前 macOS）。

三个 warnings 均为 edgar deprecation，不隐藏为 skip。没有真实财报来源下载/恢复或业务覆盖结论。

### 证据 digest

| 本轮最终证据 | SHA256 |
| --- | --- |
| exact A 最终日志 | 6970c4874a9087e35c120e910c3d7fa19240048bd14cdd5bb444913f81d41fa9 |
| 最终 pyright 日志 | 46a6c7834c9080ada23a415afd925abecc37d531f5c6e3d14ad0a7ff579096cb |
| broad coverage 日志 | edf0490ab7defa9ec90f658abbb68f7189fff6a3209cb2f0be0c4e7ccff310b3 |
| coverage report 日志 | e9d2b51b7d722cd6057a2ff857ac863288c532fb526487e75899044546047dd0 |
| broad 代表失败独立复现 | 825df6ced90b9611a2b078daeea8419007277eed11f6a3f438e77ff94a72eea8 |
| 只读 initial 归档 | 4a5e4be11bf4dddb2e32225348236e3f1223275e8e766e5a8799e770d708c506 |

## README decision

根 README 已读其最终用户职责，更新默认完整诊断、两通道全新文件捕获、退出 0 与 partial、quiet/default log 和历史限制，不写开发 gate。

Fins README 已读其稳定架构/契约职责，更新 full/property/public owner、strict 原因及取消快照/生命周期，不写用户命令或测试流水账。tests README 无额外 Agent 约束，按现有测试分层/运行/维护职责更新 owner 回归和离线 binary smoke 证据限制。

`dayu/README.md` 已读总览职责：本次没有跨层、装配根或 Host/Engine/runtime 治理边界变化，仅 Fins 内具体结果投影，因此不触发更新。其它 README 不机械同步。

## Fixed binary 的实际加载身份

从 `/private/tmp` 使用固定 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python -B -c`，不设置 PYTHONPATH。实际 import `dayu.cli.main`、`dayu.cli.output`、`dayu.fins.direct_events`、`dayu.fins.download_contract`、`dayu.fins.ingestion_runtime`、`dayu.fins.pipelines.cn_pipeline` 并读取 __file__/SHA256、sys.executable/version；工具真实 exit 0。

- binary：`/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli`。
- binary SHA256：`42b7131da40fa45cbbdd6f9be4004b6a947f34b92a13e3571c0b1aed21b88af1`。
- shebang：`#!/Users/leo/workspace/dayu-agent-r/.venv/bin/python3.11`；入口 `dayu.cli.__main__:exit_module`。
- actual sys.executable：`/Users/leo/workspace/dayu-agent-r/.venv/bin/python`；version=3.11.15。
- actual `dayu_agent-0.1.4.dist-info/direct_url.json`：editable=true，URL 指本仓库；无需新增安装/拷贝，未执行部署。
- `isinstance(FinsResultSummary.download, property)=True`，完整诊断方法 callable=True。
- 以下 actual 模块路径均为 `/Users/leo/workspace/dayu-agent-r/` 加对应文件；当前修复是未提交工作树，HEAD/0.1.4 不能单独代表修复身份。

| 实际模块 | SHA256 |
| --- | --- |
| dayu/cli/main.py（只读） | a61ccd24765e9890eff71f38dbc91176d02174c5df9bab14e66d5400613dfa08 |
| dayu/cli/output.py | 9aa54696e8e67c5daaa721d5311052e5003c2c6c14c3520f5c8ff4c2bcdc97cd |
| dayu/fins/direct_events.py | 1eeae91e2004875b70384bb15f1d8ca5f1c7e1bb25083ac2e23a59d1177742fe |
| dayu/fins/download_contract.py | 9c66c790a49095307391380c7ddd807b7655d0e3a5bf69aefd58e31185788dd3 |
| dayu/fins/ingestion_runtime.py | 9c6a776bf2d665161671bd5497bbf1fa26ea12a0640193a74f724e2e552b8b08 |
| dayu/fins/pipelines/cn_pipeline.py | 470f4fcaef4d264ae7a08f660e134dda4b9d7382810759b9cd36b91897124e2d |

固定 executable smoke 随最终 A 集合运行并通过。实际 command 为上述 binary `download --base <fresh tmp root> --ticker 0700 --start 2018-01-01 --end 2026-10-10 --rebuild`，cwd 为另一临时空目录；来源 workflow 在 discovery/resolve_company 前从 local rebuild 返回。returncode=0、唯一新诊断行、空结果 JSON 的断言成立。没有触达原生产 root，没有真实远端故障或生产恢复证明。

## 旧证据引用与不可恢复边界

只读引用总控已经通过 public storage 完成的 `download-failure-diagnostics-old-evidence-20261010.json`，本轮不再 query。

- artifact SHA256：`008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2`。
- source_count=45；canonical metadata SHA256=`d2010a1e5d30be536dd4f24b1cc53490ddeec68a875ad2e03d611e712b502b50`。
- owner-read record SHA256=`6d42a496a0fd4bbfce4a320025e77fa92758098c380ba51513a689527f15fce7`。
- 原 stdout SHA256=`a9c8a3cc2babdd8c93313345e55f1638c27fea15b6b56c5d7f8d37b1ebd07f3a`，原 stderr 0 字节。

| 原 document_id | 可恢复 | 当前 published_meta | 原日期/form/report_date/coverage/reason/URL |
| --- | --- | --- | --- |
| fil_cn_76fad62cd9ba3141f4cab67e8e2a0c220a93a27d | 身份、PDF file_failed 阶段 | missing | 未知 |
| fil_cn_04fb4018812cf15ca633495dbd9fcac3cb033378 | 同上 | missing | 未知 |
| fil_cn_307f1a281919204de1d3c3cb5f95322463819734 | 同上 | missing | 未知 |
| fil_cn_2a0ebbf2c2935ee14a39fec8744d626853a68424 | 同上 | missing | 未知 |
| fil_cn_d56f9cdc70daa5174522111629889cc74795448b | 同上 | missing | 未知 |
| fil_cn_535e021474217e2750d6063d7046a72ead52f7b5 | 同上 | missing | 未知 |
| fil_cn_a44583fc024459f5a22ee4eed537dea35e8882ac | 同上 | missing | 未知 |
| fil_cn_4043a094cd9d2292c378e6b6c8f1856868291372 | 同上 | missing | 未知 |

当前 missing 不证明原历史 snapshot 或原失败原因；45 不是本轮下载数或业务覆盖结论。保留生产外 45 来源，无写入/overwrite/recovery。合成原因矩阵与旧证据分开，不推断旧 8 项原因。

## Residual 风险与未覆盖项

所有风险只用 gateflow 五值分类；没有 later approved slice / existing issue，不借其分类隐藏未完成义务。

| 风险 / 限制 | 规范分类 | Owner / destination |
| --- | --- | --- |
| CN/HK 原因丢失、>10/后10失败不可取得，full/bounded/取消/activation 不一致 | fixed in current slice | S1 owner 实现及最终断言；仍待总控独立 code review，不宣称 gate pass。 |
| 初轮 import、非法 fixture、locator 与总行数断言、trailing whitespace | fixed in current slice | S1 指定测试，最终受影响集合/pyright 验证。 |
| SEC 既有安全原因泛化 | assigned to later work unit | Dayu 维护侧另定 SEC 原因治理；本轮无生产修改或保真承诺。 |
| 极端结果规模内存、operator 输出/repr 日志压力 | assigned to later work unit | Dayu 维护侧真实压力出现后另定性能工作；本轮无规模压测、分页/历史仓储框架。 |
| 旧 8 项缺失原元数据/原因；未来新观测或真实下载缺陷扩范围 | requiring new issue or explicit user decision | 巡检线另定明确观测候选/窗口/网络/仓储影响；当前已授权如实未知，不重问、不自行观测。 |
| 未捕获终态、SIGKILL/崩溃/提前关闭 stream 后历史无法追回 | requiring new issue or explicit user decision | 用户/总控如需历史诊断另定 work unit；本次仅合法被消费终态。 |
| Broad 67 项范围外既有/环境失败；14 资源型 skip 无真实资源验收 | requiring new issue or explicit user decision | 总控/Dayu 维护侧按上节直接根因裁决独立范围；本轮不把 broad 当通过，不扩 S1，不自行配置资源/凭据或修名单外文件。 |
| 未来生产观测或 merge/approve/ready/外部 comment | requiring new issue or explicit user decision | 用户/巡检线按实际后续范围裁决；自动 commit/push/draft PR 已授权，不列新审批阻断，本 Agent 按明确边界不执行。 |

Completion：S1 指定实现、owner/tests/README/artifacts 收尾完成；最终 exact A=1478 passed、pyright=0 errors、逐文件 coverage>=80、固定 binary 空 rebuild/外 cwd import/hash 证据完成。Broad pytest exit 1 的 67 范围外失败、14 skip 单列，未修复也不当通过；是否要求其另开范围由总控按上述 residual 裁决。

没有待回填的命令、托管 session 或未完成的 S1 断言。未覆盖：上述资源型真实集成、真实远端失败/旧原因恢复、极端规模、覆盖日志所列其它未执行分支，以及 broad 范围外问题的完整逐例基线裁决。最终入口为**总控 code review**，本 Agent 到此停止；没有执行 code review、staging/commit/push/PR 或其它后续 gate，不声明 gate pass。
