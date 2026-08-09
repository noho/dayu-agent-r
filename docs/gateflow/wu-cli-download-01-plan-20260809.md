# `wu-cli-download-01` Gateflow Plan Gate

## 1. 文档状态

- Work unit：`wu-cli-download-01`
- Gate：plan
- 日期：2026-08-09
- Goal Confirmation：用户已在 AgentController 会话明确确认；该会话中的确认与正式任务 `workspace/tmp/agentcontroller-download-fix-task.md`、handoff `docs/gateflow/wu-cli-download-01-fix-and-coverage-handoff-20260809.md` 共同构成本 WU 的 binding source。本任务没有、也不要求虚构一份独立 Goal Confirmation artifact；本计划不重新打开目标语义。
- Design inputs：`docs/host/design.md`、`docs/engine/design.md`
- 正式任务：`workspace/tmp/agentcontroller-download-fix-task.md`
- Finding / coverage 真源：`docs/gateflow/wu-cli-download-01-fix-and-coverage-handoff-20260809.md`
- 第一轮事实 / 裁决：`workspace/tmp/download-observed-behavior.md`、`workspace/tmp/download-oracle-adjudication.md`
- 当前结论：动机成立且严重性评估正确。DL-F01～DL-F11 分别涉及公开调用契约、破坏性 mutation、processed 语义污染、取消后后台执行、并发失败、完整性无法修复及不可验收终态，不能通过 CLI 文案或兼容分支止血。
- 本 artifact 只完成 plan gate；不授权产品实现、真实 CLI、commit、push、PR 或 Oracle 接受。

## 2. Preflight 结果

| 检查项 | 直接结果 | 判定 |
|---|---|---|
| branch | `codex/download-oracle` | 与任务预期一致 |
| HEAD | `fe5f4248a05318e1fbfbe5640d84d8a1992bc9aa` | 与预期一致 |
| `github/main` | `bad90963abad48d29b5571d44a1cd9a80e0e2d77` | 与预期一致 |
| merge-base | `bad90963abad48d29b5571d44a1cd9a80e0e2d77` | 当前分支从预期 main 派生 |
| ahead / behind | `0 1`（`github/main...HEAD` 左/右） | ahead 1、behind 0 |
| worktree | `git status --short` 无输出 | 干净 |
| merge / rebase | 无进行中的 merge/rebase | 可进入 plan |
| matching open PR | `[]` | 无 open PR |
| PR 190 | merged；head=`codex/interactive-oracle` | 历史任务；禁止提交或推送 |

Preflight 后未 checkout、merge、rebase、reset、提交、推送或创建 PR。

## 3. 目标、完成定义与非目标

### 3.1 目标

在 owner boundary 修复 DL-F01～DL-F11，使 `dayu-cli download` 满足用户已裁决的 accepted behavior：静态输入在任何 workspace/runtime 副作用前成为 exit 2；单 ticker、显式窗口、非删除、local-only rebuild、missing-period、provider/UA、同 ticker 并发、canonical cancellation、integrity repair 和 public terminal summary 各有唯一 typed 真源。实现与 review 通过后，严格按 DL-G01～DL-G05 补跑真实覆盖并在 Oracle gate 暂停等待用户裁决。

### 3.2 完成定义

1. DL-F01～DL-F11 的 owner tests、受影响 union、类型与静态校验全部通过，修改文件单文件覆盖率均不低于 80%。
2. 两路独立 plan review、每 slice 两路 code review、aggregate deepreview 均无未裁决 correctness/stability finding。
3. DL-G01 完整 focused-real；DL-G02 完成代表性高成本 run；DL-G03、DL-G04 获得真实 evidence 或合规 `defensive/unreachable` 证明；DL-G05 产生新 immutable calibration report。
4. 报告生成后暂停。只有用户复核接受，才可更新 download oracle/scenario/readiness；Agent 不自行接受 Oracle。

### 3.3 非目标

- 不新增 `--source`、multi-ticker、显式 prune、后台 ingestion job 或 Host Run。
- 不修改 init/prompt/interactive 已冻结 oracle/scenario，不处理 process/upload 自身 UI 或 Oracle。
- 不用 CLI 全命令锁、operation-wide mutex、production sleep、测试后门、private timing hook、旧 schema alias、wrapper、双 schema、loose parsing 或下游 fallback。
- 不把普通 download 变成 ticker 全量清理；不新增 prune 能力。
- 不改变 `dayu.runtime.interruptible_process` 的业务中立定位；Fins/Docling 语义留在 Fins。
- 不修改 Host / Engine contract、实现、README 或 design。direct download 不是 Host Run；Engine 不拥有 Fins operation lifecycle。
- 不在本 plan gate 运行真实 CLI，不写本 artifact 以外的文件。

## 4. 直接代码证据与 root cause

| Finding | 直接证据 | Root cause / owner |
|---|---|---|
| DL-F01 | `dayu/cli/commands/fins.py::_run_fins_direct_command_async` 先 resolve workspace、调用 service factory，之后 `_download_stream` 才解析 ticker/forms/date；`DefaultFinsRuntime` 构造会初始化 storage。 | CLI invocation contract；共享 typed request parser 是其直接上游输入 owner。 |
| DL-F02 | `_parse_ticker_csv` 把 CSV 第一项当 ticker、其余当 alias。 | CLI 单 ticker grammar owner 错把多个业务主体当 alias。 |
| DL-F03 | SEC SC13 retry/browse helper 只收到计算后的日期，没有“start 是否显式”事实。 | SEC collection/filter policy 丢失 typed explicit-bound fact。 |
| DL-F04 | `sec_download_workflow.py` 完成 filing 后调用 `_cleanup_stale_filing_dirs`，以本轮集合删除历史 filing。 | 普通 download target mutation policy 越权拥有 prune。 |
| DL-F05 | `FinsDownloadRequest`、adapter request、Service 使用 `rebuild_processed`；SEC/CN adapter 强制 pipeline `rebuild=False` 后标记 processed；两个 local rebuild 又直接读写 processed reprocess。 | public request schema 与 source rebuild owner 被 processed 治理语义污染。 |
| DL-F06 | `cn_download_workflow.py` 为 missing period 构造 skipped filing 并加入 `filings`。 | request placeholder 被误建模为 provider candidate outcome。 |
| DL-F07 | `SecDownloader._resolve_user_agent` 返回 `_UNCONFIGURED_USER_AGENT`；`configure` debug 原样记录 UA；runtime `_classify_direct_error` 主要按异常基类泛化。 | SEC request policy 与 Fins terminal classifier 缺少 typed 配置/transport 契约。 |
| DL-F08 | storage `_acquire_ticker_lock` 使用 `blocking=False` 并把竞争投影为“活动 batch”业务失败；SEC 已有 workspace-shared throttle state/file lock。 | storage writer coordination 错用 fail-fast；无需另造来源限流。 |
| DL-F09 | CLI `_wait_for_terminal_handling_sigint` 请求 token 后立即 `event_task.cancel()`；CN/HK Docling 用 `asyncio.to_thread`。 | CLI 抢占 Fins terminal owner；同步第三方调用没有可 terminate/join/drain 边界。 |
| DL-F10 | source snapshot/complete validator会严格校验 physical size/digest；source workflow 在 skip/refresh 决策前没有 typed classification。 | storage 缺少非破坏性 integrity query，workflow 无法在 strict read 前选择 repair。 |
| DL-F11 | `FinsDownloadResultSummary` 只有计数和 written IDs；`_download_result_details` 只生成聚合计数；CN/HK 无 `CONVERSION_COMPLETED`。 | workflow facts 没进入统一 typed public projection；CLI 不能自行扫描补算。 |

OLD `/Users/leo/workspace/dayu-agent` 对照结论：OLD 已把 SEC/CN `rebuild` 定义为 local source meta/manifest rebuild，但同样会修改 processed，不能照搬；OLD 没有当前 direct canonical terminal 与完整 process cleanup。当前仓库已有 `dayu.runtime.interruptible_process.InterruptibleProcessHandle`（公开调用为 `start()`、`wait()`、`terminate()`、`kill()`、`close()`，并含 process-group 与 bounded cleanup），应直接复用这些机械 lifecycle API；不得新增 `spawn()` wrapper，也不得复制 OLD 的线程行为。

## 5. 语义 owner、contract、schema 与 public interface 决策

### 5.1 Public invocation 与 typed request

新增 `dayu/fins/download_contract.py`，从过大的 `ingestion_runtime.py` 抽出 download-only typed contract；这不是兼容 facade。所有 production/test call site 直接导入新真源，`ingestion_runtime.py` 不保留兼容 re-export。`rg -n "FinsDownloadRequest" dayu tests` 的当前穷举结果要求同步迁移 production 的 `dayu/service/fins_direct.py`、`dayu/fins/ingestion/observation_handle.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/tools/download_tools.py`，以及 tests 的 `test_cn_download_runtime.py`、`test_fins_wait_adapter.py`、`test_fins_ingestion_tools.py`、`test_fins_ingestion_runtime.py`、`test_fins_direct.py`；README 示例在文档 closeout 更新。所有构造点改用新 contract 的 typed 字段，测试 adapter registry 可把真实 source enum 绑定到 fake adapter，不为测试保留任意字符串 source 或旧导入路径。

核心 contract：

- `FinsDownloadSource`：`SEC | CNINFO | HKEXNEWS`，由 canonical ticker market 唯一解析；公开 CLI 不接收 source。
- `FinsDownloadDateRange`：`start_bound: date | None`、`end_bound: date | None`、`start_is_explicit: bool`、`end_is_explicit: bool`。year/year-month/full-date 在此一次性展开为 inclusive bound；source workflow 不再反解析字符串或从日期值猜 explicitness。
- `FinsDownloadRequest`：`normalized_ticker`、resolved source、canonical explicit forms、date range、`overwrite_existing`、`rebuild_local_artifacts`。不含 `rebuild_processed`。
- `build_fins_download_request(...)`：download 专用、唯一 Fins request parser。先做长度/数量/空项/CSV ticker/start-after-end 校验，再调用 ticker/domain form owner；错误抛 `FinsDownloadUsageError`，携带中文 actionable message。`dayu.service.fins_direct.build_direct_download_request(...)` 是不构造 runtime 的 product boundary：它把 CLI 显式参数映射给该 parser并返回typed request，CLI只调用Service API并机械映射exit 2，保持 `UI -> Service -> Fins` 依赖方向。
- forms/date/ticker 边界使用命名常量，不使用魔法数。当前 parser 没有 public `--limit`；计划不新增该 option。DL-F01 中的 limit 落为 ticker/date 单值长度、form item 长度与 form item count（最多 100）的 invocation bounds。
- CN/HK fiscal-period alias 归一从 `cn_form_utils.py::_TOKEN_TO_PERIOD` 迁到 `dayu/fins/domain/filing_semantics.py` 的公共业务值 parser；迁移后删除该私有 mapping，`cn_form_utils.resolve_target_periods` 与 download request builder 都调用同一 domain parser。SEC 复用现有 domain SEC form parser。这样 request validation 与 workflow 不维护两套集合。

状态顺序固定为：

`RAW_ARGV -> VALIDATED_FINS_DOWNLOAD_REQUEST -> WORKSPACE_RESOLUTION -> SERVICE/RUNTIME_CONSTRUCTION -> STREAM_OPEN`。

任何 usage failure 必须停在第二步之前；测试对 factory 未调用、workspace 不存在和 exit 2 同时断言。重复 `--ticker` 继续由 argparse last-wins；builder 只看最终值并把 canonical ticker写入 terminal summary。只有 download 专用 builder 拒绝任意逗号分隔 ticker；`dayu/cli/commands/fins.py::_parse_ticker_csv` 及其 `upload_filings_from` / preprocess / upload alias 语义不改，AST 与回归测试固定这一边界。

### 5.2 Download outcome 与 LLM-facing/public terminal schema

`dayu/fins/download_contract.py` 同时拥有 source workflow 到 runtime 的 typed结果：

- `FinsDownloadDocumentDisposition`：`DOWNLOADED | SKIPPED | REJECTED | FAILED`。
- `FinsDownloadDocumentResult`：`document_id`、`form_or_period`、`filing_date`、`report_date`、disposition、`reason_category`、`reason_message`、可选 `artifact_locator`。
- `FinsDownloadEffectiveFilters`：canonical forms、effective inclusive start/end、overwrite、rebuild。
- `FinsDownloadResultSummary`：resolved source、canonical ticker、effective filters、四类互斥 counts、bounded document rows、missing periods、omitted count、terminal disposition。
- 不变量：`discovered = downloaded + skipped + rejected + failed`；missing period 不进入 discovered/skipped；document rows 的 disposition 与 counts 同源；省略发生在最终 public projection，owner 保留完整 operation-local typed rows。
- SEC/CN workflow可以保留source-private内部mapping，但它不能跨出source adapter boundary。每个adapter只有一个strict projection helper把必填字段转换为上述typed rows；缺字段/错类型直接失败，禁止 `.get()` 默认值、loose parsing或由runtime/CLI补齐语义。

`dayu/fins/direct_events.py` 增加 `FinsDownloadPublicSummary` 与 `FinsPublicFailure`：

- download RESULT 必须携带 nested `download`，字段为 source、ticker、filters、counts、rows、missing periods、omitted count；字段名、枚举和业务含义自解释。
- failure 使用 closed classification（configuration/provider transport/storage/execution），含 source、脱敏 transport category、safe message、retry hint；不含 URL、contact value、provider raw payload、绝对路径或 traceback。
- generic `details` 不再作为 download 的事实真源；CLI renderer 与 `fins_wait_adapter` 都从同一个 nested typed object投影。awaiting tool 的成功 result 同样包含业务可读 download 对象，不能只给 label/value 或 document IDs。
- public row 上限与文本上限是 contract 常量；超限只增加 omitted count，不静默丢失而无提示。

相对 artifact locator 由 storage owner 提供新的只读 typed query，精确返回 `PurePosixPath`，指向实际 source document 目录相对 workspace 的locator。它可以含storage locator component，但public row同时提供document ID，并明确locator仅用于定位、不是业务事实；adapter只在public projection时调用 `.as_posix()`，CLI不接触 `_fs_*` 路径helper。

### 5.3 Rebuild 与 source mutation

- `FinsDownloadRequest.rebuild_local_artifacts` 经 runtime 原样映射为 `FinsSourceDownloadAdapterRequest.rebuild_local_artifacts`。SEC/CN adapter 不直接构造新 host：它们已有的 `SecPipeline` / `CnPipeline` 实例就是现有 workflow host，并继续拥有 source/batching/company 等仓储依赖。
- SEC adapter 调用现有 `SecPipeline.download_stream(ticker, form_type, start_date, end_date, overwrite, rebuild, *, cancel_checker)`：`ticker=request.normalized_ticker.canonical`，`form_type=_form_type_from_adapter_request(request.form_types)`，start/end 取 typed inclusive bounds 的 ISO 字符串或 `None`，`overwrite=request.overwrite_existing`，`rebuild=request.rebuild_local_artifacts`，并透传 cancellation checker。`SecPipeline._rebuild_download_artifacts(...)` 再按当前真实签名调用 `sec_rebuild_workflow.rebuild_download_artifacts(host, *, ticker, form_type, start_date, end_date, overwrite, pipeline_download_version, expand_form_aliases, split_form_input, parse_date, parse_sec_form)`；不另造 adapter/host/wrapper。
- CN/HK adapter 以同一字段映射调用现有 `CnPipeline.download_stream(..., rebuild=request.rebuild_local_artifacts, *, cancel_checker=...)`。`run_cn_download_stream_impl` 已拥有 canonical market 与 pipeline name，并按当前真实签名调用 `cn_download_rebuild.rebuild_cn_download_artifacts(*, host, ticker, market, form_type, start_date, end_date, overwrite, pipeline_name, cancel_checker)`；不把 request 直接传给 rebuild 函数。
- 两条现有 rebuild branch 都发 `PIPELINE_STARTED(rebuild=true)`，逐 filing 发完成/失败 event，最后发唯一 `PIPELINE_COMPLETED(payload={"result": rebuild_result})`；现有 collect helper 收集该 result，SEC/CN adapter 的 strict projection helper把它投影为 typed `FinsDownloadResultSummary`。不新增旁路 RESULT/event schema，缺少必填结果字段时 fail closed。
- 从 download-only `FinsDownloadRequest`、`FinsSourceDownloadAdapterRequest`、Service builder、runtime映射和 SEC/CN adapter 删除 `rebuild_processed`；删除 adapter 完成后调用 `mark_downloaded_processed_rebuild_required` 的分支。SEC `SecRebuildWorkflowHost._processed_repository`、`rebuild_download_artifacts` 内部 processed 参数/读写，以及 CN `rebuild_cn_download_artifacts` 的 `host.processed_repository` 读写全部删除，使 local rebuild 不读写 processed。
- `CnDownloadWorkflowHost.processed_repository` 若仍被普通 download 的 source 更新流程消费则保留；preprocess/upload request 中同名 `rebuild_processed` 是各自业务字段，本 WU 不改变。禁止为 download 保留 alias、兼容字段或 re-export。
- `rebuild_local_artifacts=True` 不得配置 downloader、发 HTTP、下载/替换 source bytes或运行 Docling；只更新符合 forms/date filters 的 download-owned source meta/manifest。`overwrite` 仍是独立字段；与 rebuild 组合时不改变 local-only 路由。
- 普通 SEC workflow 删除 stale cleanup invocation。maintenance API 仅在存在其它显式 owner 时保留；本 WU 不新增或重命名 prune API。
- SEC request 的 `start_is_explicit` 一路传到 SC13 retry/browse owner；显式 start 禁止扩大 lower bound。所有 selected/downloaded/rejected target 在产生 outcome 前再经过同一 inclusive range predicate，形成最后一道 owner-level invariant。
- CN/HK missing periods 存在独立 tuple；不再构造 synthetic filing result/progress event。

### 5.4 Provider policy 与 error classification

- `SecDownloader` 只接受显式参数或 `SEC_USER_AGENT` 环境变量解析出的非空身份。未配置时保存 typed `UNCONFIGURED` state；首次 HTTP 前抛 `SecUserAgentConfigurationError`，不构造 fallback header、不发请求。
- UA resolution 在 downloader composition 中只执行一次；`configure` 不重新 warning。日志只写 `configured=true/false`，禁止 contact 原文、部分原文或 header dump；一个 command 的未配置 warning 恰好一次。
- downloader/source adapter 在异常发生处把 httpx/HTTP/provider protocol 错误映射为 `FinsDownloadProviderError(source, transport_category, retryable, safe_message)`；runtime 不再用 `RuntimeError/OSError` 猜 provider 语义。
- static usage error 永不到 direct stream；动态 UA/config/provider/network failure为 exit 1；integrity classification不是 user input。

### 5.5 Canonical cancellation 与 Docling process boundary

Direct operation 状态机：

`RUNNING -> CANCELLATION_REQUESTED? -> QUIESCING -> SUCCESS | FAILURE | CANCELLED -> CLEAN_EXHAUSTION`。

- Fins runtime producer与 `ValidatedFinsEventStream` 是唯一 terminal owner。当前 `_run_direct_stream` 已拥有 cancellation state、producer thread、queue 与 50ms bounded queue poll，但其 `finally` 只 request cancel、没有 join。实现须由 runtime 创建并保存单次私有 `operation_task`，该 task拥有 producer thread与queue pump；正常完成、取消和 consumer abort 都必须由它收口。producer thread不得是可被遗弃的 daemon background work。
- CLI SIGINT handler第一次只幂等请求 operation token、渲染“正在取消”并继续 await同一event consumer；不调用 `event_task.cancel()`、不设置CLI terminal timeout、不 terminate/kill Fins child、不本地合成130。只有Fins产生唯一cancelled RESULT且 validator 在raw source clean exhaustion后放行，CLI才机械使用其exit 130。若operation先完成为success/failure，CLI遵守已由owner提交的终态，不因晚到SIGINT改写。
- terminal gate由Fins runtime原子裁决：token在RUNNING期间先被接受则状态进入 `CANCELLATION_REQUESTED`，此后由取消触发的provider/child异常只作安全诊断，不能改写为failure；若success/failure已先完成owner决策，晚到SIGINT不得改写。取消路径中adapter/provider先退出、Docling runner完成process cleanup、任何open storage batch commit/rollback并释放锁，producer再把唯一cancelled RESULT作为最后业务event入queue并退出；operation task join producer、drain RESULT与done marker后才让raw source clean exhaustion。禁止先写terminal再cleanup、禁止terminal后late event/write、禁止后台继续。
- consumer异常关闭或runtime shutdown时，runtime先request cancellation；必要时只由Fins owner对其私有 `operation_task.cancel()`，并在task内部捕获取消、用shielded cleanup继续等待producer thread与其下游资源退出。该owner-initiated cancel用于收回执行资源，不创造业务RESULT；CLI无权调用。`ValidatedFinsEventStream.aclose()`必须等待该owner cleanup完成，不能只关闭async generator而遗留线程。
- blocking boundary与有界机制逐项固定：direct queue读取沿用50ms poll；SEC retry/throttle sleep沿用0.1s cancellation slice；SEC/CNInfo/HKEX HTTP/PDF请求沿用各downloader的30s request timeout，并在每次I/O前后增加token checkpoint；Docling使用下述terminate/kill/close有界升级；storage不承载远端I/O且batch内每个阶段前后检查token。Python线程本身不可安全强杀，因此必须用这些owner边界保证它最终返回，不能靠CLI timeout掩盖。
- 新增 `dayu/fins/pipelines/cn_docling_process.py`，只放 production `ProcessCnDoclingConversionRunner` 与可pickle target；`CnDoclingConversionRunner` Protocol放在现有 `dayu/fins/pipelines/cn_download_protocols.py`，唯一方法为 `async convert_pdf_to_docling_json(pdf_bytes: bytes, stream_name: str, *, cancellation_checker: Callable[[], bool]) -> bytes`。`CnDownloadWorkflowHost`把现有裸callable property替换为typed runner property，`CnPipeline`构造函数注入该protocol；tests注入deterministic fake runner，不把mock带入production。
- production runner在system temp下创建每run唯一目录，目录由parent独占且不在workspace staging。parent写PDF input，child调真实Docling并写output，queue只返回size/digest等小型JSON-like结果，避免大payload IPC。parent调用现有 `InterruptibleProcessHandle.start()`；不得新增 `spawn()` wrapper。
- 等待期间runner以模块常量 `_DOCLING_PROCESS_POLL_SECONDS = 0.05` 轮询Fins cancellation；命中后依次调用 `terminate(grace_seconds=_DOCLING_TERMINATE_GRACE_SECONDS)`、必要时 `kill(grace_seconds=_DOCLING_KILL_GRACE_SECONDS)`，最后无条件 `close(kill_grace_seconds=_DOCLING_KILL_GRACE_SECONDS)` 完成join/queue drain；两个grace常量分别为2.0s与1.0s。success/failure同样先close。parent只在handle close完成后，于外层 `finally` 清理唯一temp tree，因此所有可控success/failure/cancel路径都无残留；cleanup异常只记录不含绝对路径/PDF内容的bounded warning，不覆盖已确定的业务primary outcome。若close尚未证明child退出，不得发terminal；parent被SIGKILL时system-temp残留是明确residual，不在workspace增加stale scavenger。
- CN filing状态顺序：`PDF_READY -> CONVERSION_STARTED -> CONVERSION_COMPLETED -> PUBLICATION_ELIGIBLE`。只有child正常结束、output size/digest验证和取消checkpoint通过后才发 `CONVERSION_COMPLETED`；publication batch仍在conversion后开始。
- `dayu/runtime/interruptible_process.py` 允许被import/use但禁止修改；只有owner test证明通用helper defect并重新过plan/review后才允许修改，不能把Fins业务语义下沉。

### 5.6 Storage concurrency 与 typed integrity

并发状态机：

`LOCAL_TICKER_RESERVATION -> BLOCKING_WRITER_LOCK -> STAGING -> COMPLETE_VALIDATION -> SHORT_PUBLICATION_GUARD -> OLD_OR_NEW_SWAP -> RELEASE/NOTIFY`。

- `begin_batch` 对同core同ticker使用condition/reservation等待，不抛业务冲突；不同ticker不互相等待。锁顺序唯一为local reservation -> cross-process ticker writer -> staging -> publication guard；任何路径不得在持有publication guard时再获取writer。
- `_acquire_ticker_lock` 改为blocking writer coordination；recovery的 `_try_acquire_recovery_ticker_lock` 仍保持non-blocking skip，不能全局改变lock helper语义。合法同ticker第二个writer不得因任意业务timeout失败；commit、rollback、异常和取消路径都在 `finally` 关闭batch、释放writer与local reservation并 `notify_all`。
- 远端HTTP、PDF下载、Docling转换全部发生在writer/publication lock外；owner barrier test与AST/call-graph static proof共同验证 `begin_batch` 到commit/rollback之间不可达provider client、PDF downloader或Docling runner。没有“等待超时转业务失败”的fallback；底层文件系统/OS lock永久I/O卡死仍是residual，不能用破坏DL-F08的任意timeout掩盖。
- SEC workspace-shared throttle保持现有唯一 owner；CN/HK不增加来源限流。

新增 `dayu/fins/storage/source_integrity.py`：

- `SourceIntegrityStatus`：`MISSING | COMPLETE | REPAIR_REQUIRED`。
- `SourceIntegrityReason`：`PHYSICAL_FILE_MISSING | SIZE_MISMATCH | DIGEST_MISMATCH`。
- `SourceIntegrityClassification`：ticker、source kind、document ID、`SourceDocumentRevision | None`、status、closed reasons；这是可比较的publication identity。`MISSING`必须revision为None，表示source target不存在；“meta声明文件但physical缺失”是带revision的 `REPAIR_REQUIRED`。
- 直接证据支持把published与staged integrity query都加入现有 `SourceDocumentRepositoryProtocol`：identity/meta/physical bytes/publication guard本就由source repository拥有，另造小capability protocol会重复同一storage真源并扩大factory注入。production只有composition wrapper `FsSourceDocumentRepository`（委托共享 `_FsSourceDocumentCore`）实现该Protocol；`_fs_repository_factory.py`仅构造共享core，无需修改。新增 `classify_source_integrity(...)` 在短publication guard内返回published classification；新增 `classify_staged_source_integrity(..., batch=...)` 只读当前batch复制的staging tree，不获取publication guard。
- `rg` 当前穷举的测试子类/spy为 `test_read_runtime_semantic_ownership_guards.py::_CountingSourceRepository`、`test_cn_download_workflow.py::_BatchIdentityCnSourceRepository`、`test_sec_pipeline_download_stream.py::_SpySourceRepository`、`test_processor_read_consistency.py::_RevisionProbeRepository`、`test_fins_storage_provider.py::_CountingSourceRepository`、`test_docling_upload_service.py::_SpyUploadSourceRepository`及其子类；它们继承production wrapper，无独立Protocol实现。全部纳入pyright/rg影响检查；禁止 `getattr`、compat shim或默认classification。

Integrity repair采用race-safe two-phase，固定最大重取轮数为命名常量3：

1. **Phase A / short read**：provider discovery/range selection产出typed candidate后，SEC/CN filing workflow在任何strict snapshot/skip/reuse与target payload下载前调用published classification。短publication guard内只读取并返回identity/revision+integrity。若为 `COMPLETE` 且 `overwrite_existing=False`，立即按既有policy skip，不做该target的HTTP/PDF/Docling或 `begin_batch`；若为 `COMPLETE` 且overwrite为True、`REPAIR_REQUIRED`（与overwrite无关）或 `MISSING`，才在释放guard后准备该target的remote replacement。Phase B重试回到Phase A时复用已选typed candidate，不重复provider discovery；若新状态可skip，不新增任何target网络I/O。
2. **Phase B / writer revalidation**：预取完成后调用 `begin_batch`；writer lock获取后必须复制最新published tree。workflow在该batch owner内调用staged classification，先比较Phase A publication identity/revision与latest staged identity/revision，之后才允许解释latest integrity或overwrite policy；期间不做任何外部I/O。
3. **Identity-first decision**：只要latest target的presence/identity/revision相对Phase A发生变化，无论latest status是 `COMPLETE`、`REPAIR_REQUIRED` 还是 `MISSING`，都必须rollback、释放writer/reservation、丢弃陈旧预取并回到Phase A，占用一次revision-churn轮次；禁止用旧prefetch覆盖新revision。新一轮若观察到 `COMPLETE`，重新由 `overwrite_existing` 决定：False立即skip且不再联网，True重新预取并继续overwrite。只有identity/revision相同才按latest integrity+overwrite policy裁决：`REPAIR_REQUIRED`强制apply；`MISSING`按create apply；`COMPLETE + overwrite_existing=True`按显式overwrite apply；`COMPLETE + overwrite_existing=False`丢弃预取并skip。apply只reset当前target，写齐预取blob/source并由现有complete validator+atomic commit发布。
4. 最多3轮revision churn后抛typed integrity-repair conflict failure；每轮在重新联网前均释放writer，旧/latest published tree完全不变。该失败只表示连续publication identity变化，不用于普通writer等待；稳定的两个真实并发writer都必须成功，不能丢失另一方更新。
- 同target两个合法overwrite writer的语义是序列化后的last-writer：后获得writer的一方若看到前一方新revision，必须丢弃旧prefetch、基于新revision重新获取remote replacement后再发布；两方都成功，最终内容来自最后一次经revision复核的overwrite。不同target writer在latest tree副本上只改各自target，最终published集合必须保留并集。
- identity/meta结构损坏仍严格抛storage error，不增加 `UNKNOWN`，不字符串解析兜底。ordinary `get_source_meta/read_source_snapshot` strict validator、commit atomicity和path-free错误投影不放宽；CLI不删除文件重试。

## 6. Implementation slices

本 WU 使用四个 slice。超过 Gateflow 常规三个 slice 的理由：Docling process cleanup与storage concurrency/integrity分别具有独立状态机、failure precedence和原子性风险，合并会让review无法隔离取消 race与publication race。四个 slice仍各自形成可验证行为增量。

### Slice 1 — Invocation、selection 与 local rebuild（DL-F01～DL-F06）

**Allowed production files**

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/fins.py`
- `dayu/service/fins_direct.py`
- `dayu/fins/download_contract.py`（new）
- `dayu/fins/domain/filing_semantics.py`
- `dayu/fins/ingestion/observation_handle.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/pipelines/sec_form_utils.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_sc13_filtering.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/pipelines/cn_form_utils.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`

**Exact changes / data flow**

Slice 1仍是一个Gateflow slice，但实施顺序不可交换，并设置独立checkpoint：

1. **S1-A typed contract / prevalidation checkpoint（DL-F01/F02）**：建立download contract；一次性迁移上述production imports和所有test constructs，不保留re-export；Service builder与CLI先完成single ticker/limits/forms/date/range中文usage validation，再resolve workspace/构造runtime。download builder不调用或修改 `_parse_ticker_csv`。运行S1-A tests、pyright与import rg，保存独立reviewable diff checkpoint；未稳定前禁止改pipeline行为。
2. **S1-B source pipeline checkpoint（DL-F03～F06）**：仅基于S1-A稳定contract把canonical forms/date/explicitness送入adapter；SEC硬窗口、普通download删除prune invocation；CN missing periods独立；按§5.3真实调用链把 `rebuild_local_artifacts` 传给existing pipeline/rebuild branch并删除download-only processed依赖。随后运行完整Slice 1 owner union，再提交同一slice的双路review；不拆第五个slice。

**Invariants**

- usage failure：factory调用0次、workspace副作用0、exit 2。
- explicit window外 selected/downloaded/rejected 数为0。
- 普通/overwrite只改target；rebuild不联网、不改source bytes或processed。
- missing periods不参与四类document count。
- download CSV ticker拒绝不改变 `_parse_ticker_csv` 的upload/preprocess alias语义。

**Non-goals**

- 不实现terminal UI、UA、取消、并发或integrity repair。
- 不清理无关maintenance API，不保留旧字段兼容。

**Allowed test files / owner tests**

- `tests/cli/test_arg_parsing.py`、`tests/cli/test_fins_commands.py`：全部usage矩阵、last-wins、zero-side-effect；`upload_filings_from` CSV ticker+aliases回归，AST断言download path不调用 `_parse_ticker_csv` 且该函数body/调用语义未被改成single-ticker parser。
- `tests/service/test_fins_direct.py`、`tests/service/test_fins_wait_adapter.py`、`tests/fins/test_fins_ingestion_tools.py`：CLI/awaiting入口复用同一个typed builder并从新真源import。
- `tests/fins/test_fins_ingestion_runtime.py`：request/adapter schema、counts invariant、rebuild无processed mutation。
- `tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_sec_pipeline_download_stream.py`：显式SC13边界、non-deletion、SEC local rebuild。
- `tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`：CN/HK local rebuild与missing-period分类。

**Stop condition**

S1-A checkpoint先证明zero-side-effect usage、所有 `FinsDownloadRequest` import/construct site迁到新真源且旧模块无re-export；S1-B后上述owner tests及slice pyright/Ruff/coverage通过。AST/rg证明production download request/adapter/path不存在 `rebuild_processed`，但preprocess/upload同名字段仍存在；普通SEC workflow不调用stale cleanup；`cn_form_utils.py` 不再定义 `_TOKEN_TO_PERIOD`。任一遗漏call site、source二次解析raw date/form、rebuild触及processed或upload alias回归即停止修复，不进入review。

### Slice 2 — Provider policy 与统一 public terminal（DL-F07、DL-F11 summary）

**Allowed production files**

- `dayu/fins/download_contract.py`
- `dayu/fins/direct_events.py`
- `dayu/fins/direct_event_text.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/cli/output.py`
- `dayu/service/fins_wait_adapter.py`

**Exact changes / data flow**

1. SEC装配一次解析UA；首HTTP前typed fail，无fallback header，日志只投影配置状态。
2. provider/download owner把transport错误映射为closed typed error；runtime构造safe public failure。
3. source workflows/adapters产出typeddocument rows/effective filters；storage只读query产生relative artifact locator。
4. runtime生成bounded `FinsDownloadPublicSummary`；CLI和wait adapter机械投影同一对象。

**Invariants**

- 未配置UA：HTTP client调用0、warning恰好1、exit 1。
- stdout/stderr/log/public result不含contact canary、绝对路径、URL/raw payload。
- discovered等于四类互斥计数之和；row与count逐项一致；omitted count精确。
- CLI不import私有storage模块、不扫描portfolio。

**Non-goals**

- 不改变其它operation的业务summary；仅做必要的公共failure envelope机械迁移。
- 不在UI猜测reason、source或locator。

**Allowed test files / owner tests**

- `tests/fins/test_sec_downloader.py`：configured/unconfigured、首HTTP gate、warning去重、log canary。
- `tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_cn_download_runtime.py`：typed rows、rejection/missing/effective filters。
- `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_direct_stream.py`：public schema、不变量、bounded/omitted、typedfailure。
- `tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`：screen字段与脱敏。
- `tests/service/test_fins_wait_adapter.py`：LLM-facing成功/失败自足字段及无内部标识。

**Stop condition**

owner tests/coverage/static通过；contact/absolute-path scan为0；CLI与wait adapter对相同typed summary的serialized business fields一致。任一消费者从raw dict、log、文件名或私有storage反推即停止。

### Slice 3 — Canonical cancellation 与 Docling child process（DL-F09、DL-F11 conversion）

**Allowed production files**

- `dayu/cli/commands/fins.py`
- `dayu/fins/download_contract.py`
- `dayu/fins/direct_event_text.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/download_events.py`
- `dayu/fins/pipelines/cn_docling_process.py`（new）
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`

`dayu/runtime/interruptible_process.py` 可被import/use，但不在修改allowlist；只有owner test证明通用helper缺陷并重新过plan/review后才允许修改。

**Exact changes / data flow**

1. CLI SIGINT只request token并等待validated stream terminal；删除local exit/synthetic 130分支。
2. runtime创建并拥有operation task、producer thread与queue pump；正常cancel等待协作退出，consumer abort/runtime shutdown才由owner request后cancel task，并shield等待thread/provider/Docling/storage cleanup。adapter/workflow的cancelled disposition一路传给producer，clean exhaustion前只产生唯一cancelled RESULT。
3. `CnDoclingConversionRunner` Protocol加入 `cn_download_protocols.py`，production实现/target加入 `cn_docling_process.py`；parent创建system-temp唯一目录，调用handle `start()`，临时input/output与size/digest校验，全路径handle close后finally清理。
4. conversion完成checkpoint后发 `CONVERSION_COMPLETED`，再进入publication eligibility。

**Invariants**

- 一次Ctrl+C最终只有一个canonical cancelled terminal和exit 130；无local synthetic terminal。
- cancelled/failure/success均无活child、未观察queue异常或late output。
- provider、Docling、storage cleanup完成且producer thread已join之前，validator不得放行terminal；CLI不拥有超时/kill路径。
- conversion_started没有completed时不得publication；completed之后仍需cancel checkpoint。
- commit前cancel rollback；commit开始后只允许完整old/new，不二次rollback。

**Non-goals**

- 不把Fins取消建模为Host cancel/Engine event。
- 不给production增加timing hook或sleep。

**Allowed test files / owner tests**

- `tests/cli/test_fins_commands.py`：SIGINT request-and-wait、exit来自terminal。
- `tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_direct_stream.py`：very-early、producer wait/owner abort、唯一terminal、`aclose()`等待clean exhaustion且无遗留thread。
- `tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`：provider/file/conversion/publication checkpoints。
- 新增 `tests/fins/test_cn_docling_process.py`：真实调用 `InterruptibleProcessHandle.start()` 的success/failure/cancel、terminate->kill、nestedprocess-group cleanup、handle.close后temp cleanup、no late result；AST断言production没有 `.spawn()` wrapper/call。
- `tests/runtime/test_interruptible_process.py` 只作为现有helper lifecycle的read-only baseline运行，不在修改allowlist；若helper defect成立则先停下重新plan/review。

**Stop condition**

所有deterministic barrier测试证明可控路径child PID结束、temp tree清理、producer thread join、stream唯一terminal和无半发布；重复运行无flaky。静态检查证明runtime helper只被import/use未被修改、真实API为 `start()`。若process target不可pickle、close无界、正常SIGINT依赖CLI/consumer `task.cancel()`、owner cancel后遗留thread或terminal先于cleanup，停止并修owner，不进入review。

### Slice 4 — Storage concurrency 与 integrity repair（DL-F08、DL-F10）

**Allowed production files**

- `dayu/fins/storage/source_integrity.py`（new）
- `dayu/fins/storage/__init__.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_pipeline.py`

**Exact changes / data flow**

1. 同process per-ticker reservation/condition与cross-process blocking writer lock；recovery try-lock保持非阻塞；所有batch出口统一release/notify。
2. 在现有 `SourceDocumentRepositoryProtocol`、`FsSourceDocumentRepository` wrapper与 `_FsSourceDocumentCore` 同步添加published/staged typed integrity query；不新增capability Protocol或compat path。
3. SEC/CN按§5.6执行最多3轮的candidate -> classify -> policy gate -> lock外prefetch -> begin_batch/latest-copy -> staged identity-first recheck。latest identity/revision变化时不看status直接释放并回Phase A；相同才按latest integrity+`overwrite_existing`决定apply/skip。显式overwrite不得因并发修复变成skip，陈旧prefetch不得跨revision发布。
4. 保持complete validator、atomic swap和strict read；冲突耗尽/下载/publication失败均rollback保留latest old目标；HTTP/PDF/Docling不得出现在writer/publication lock区间。

**Invariants**

- 同ticker两个writer不fail-fast、最终均terminal；第二个staging基于第一个已发布视图，无lost update。同target两个overwrite按writer顺序形成合法last-writer结果，后者必须在revision变化后重新prefetch；不同target最终published集合为两者并集。
- writer锁无任意业务timeout；锁顺序固定，commit/rollback/cancel/exception均release writer/local reservation并notify。
- 不同ticker不共享condition；SEC throttle不变，CN/HK无新增throttle。
- size/digest/missing physical三类均独立于overwrite触发repair；失败保留old bytes/meta/manifest及非目标。
- `COMPLETE + overwrite_existing=False` 在Phase A直接skip且不做target网络I/O；`COMPLETE + overwrite_existing=True` 必须进入正常overwrite，不能被latest COMPLETE短路。任何identity/revision变化都先重试，不能把陈旧prefetch用于latest target。
- typed classification不泄漏absolute path，不把integrity映射为user input。

**Non-goals**

- 不增加CLI retry/delete；不放宽snapshot/read validator。
- 不重构为operation-wide transaction或新storage backend。

**Allowed test files / owner tests**

- `tests/fins/test_fins_storage_atomicity.py`：同process/cross-process同ticker等待、different ticker并行、crash lock release、old/new atomicity、三类integrity classification、path-free error，以及repair后production `read_source_snapshot`可读。
- `tests/fins/test_fins_storage_provider.py`：protocol/public wrapper contract。
- `tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_sec_pipeline_download_stream.py`、`tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`：overwrite false/true repair、Phase A COMPLETE+False零target HTTP、identity变化到COMPLETE/REPAIR_REQUIRED/MISSING均丢弃旧prefetch、retry后COMPLETE分别按False skip/True重新fetch+overwrite、同target双overwrite last-writer、不同target并集、3轮冲突耗尽、下载失败rollback、production snapshot可读。barrier/fake须记录每轮prefetch payload与revision，证明最终从未发布陈旧payload。
- Protocol影响检查allowlist（若仅继承无需编辑，若type/override断言需同步）：`tests/fins/test_read_runtime_semantic_ownership_guards.py`、`tests/fins/test_processor_read_consistency.py`、`tests/fins/test_docling_upload_service.py`；所有列明subclass/spy都必须通过pyright，禁止用fake默认返回掩盖新contract。

**Stop condition**

多进程barrier测试稳定证明同target双overwrite都成功且最终为后writer基于新revision重新prefetch的payload、不同target集合并集保留、waiter被notify；race矩阵覆盖latest三种status的identity变化、same-identity integrity+overwrite决策、retry后COMPLETE的False无新增target HTTP/True重新overwrite，以及3轮耗尽且latest不变。corruption矩阵证明repair后strict snapshot通过、失败不改变任何published字节。AST/call-graph与barrier双证据证明所有外部I/O在writer/publication lock外；`rg`穷举Protocol production implementation/composition wrapper/test subclasses。若identity变化后仍发布旧prefetch、overwrite=True被转成skip、skip产生额外target网络、batch在HTTP/Docling期间持锁、出现lost update、合法writer因timeout失败、漏release/notify或为通过而弱化validator，立即停止。

## 7. 文件、文档与边界总表

### 7.1 预期新增文件

- `dayu/fins/download_contract.py`
- `dayu/fins/pipelines/cn_docling_process.py`
- `dayu/fins/storage/source_integrity.py`
- `tests/fins/test_cn_docling_process.py`

### 7.2 README decision

- `dayu/fins/README.md`：必须更新。删除当前“download adapter消费 `rebuild_processed`”陈述，记录已实现的local-only rebuild、typed summary/cancellation、UA gate、storage waiting与integrity classification；只写实现后的稳定事实。
- 根 `README.md`：必须更新。`--rebuild`、SEC User-Agent prerequisite、usage error零副作用与用户可见final summary属于最终用户工作流/排障变化；修改前遵守其最终用户边界。
- `tests/README.md`：必须更新现有Fins测试事实段，删除“download persisted-summary消费 `rebuild_processed`”并补充新owner coverage；不新增测试层级或未来计划。
- `dayu/README.md`：预计不改。`UI -> Service -> Host -> Engine`、Fins direct边界和runtime层中立关系均不变化；implementation结束时回读确认。
- `dayu/host/README.md`、`dayu/engine/README.md`、`docs/host/design.md`、`docs/engine/design.md`：不改，无contract变化。
- `docs/cli_ci.md`、两个registry：implementation阶段不改；只在DL-G发现新动态分支时先补inventory，registry仍须等待用户Oracle裁决。

实现完成后的documentation closeout allowlist仅为 `README.md`、`dayu/fins/README.md`、`tests/README.md`；只有回读证明跨包稳定边界实际变化时才先replan并加入`dayu/README.md`。

### 7.3 Forbidden files throughout implementation

- `dayu/host/**`、`dayu/engine/**`
- init/prompt/interactive product files与其frozen registries
- PR 190相关artifact或branch
- 任何production timing hook/harness infrastructure

若实现必须越出某slice allowlist或触及forbidden boundary，先停止、补充直接证据与plan review，不能顺手修改。

## 8. Review gates

1. 两路独立plan review已完成：AgentMiMo `docs/reviews/plan-review-20260809-232233.md`、AgentDS `docs/reviews/plan-review-20260809-232123.md`；原始artifact保持不可修改。
2. finding由AgentCodex按owner/root cause裁决并在§14留痕；本次修订后原reviewer分别rereview，只有两路均明确accepted且无未裁决blocking finding才可进入implementation。
3. 每个implementation slice完成后，两路独立code review；修复后回原reviewerrereview。
4. 四个slice与文档完成后执行aggregate `deepreview`：重点检查adversarial failure、反向依赖、semantic ownership drift、取消terminal race、process cleanup、storage atomicity/concurrency、contact泄漏、LLM-facing自足性、过度设计与coverage gaps。
5. 本轮只到plan-fix gate，不自动进入implementation。

## 9. Test / static validation plan

每次代码修改后先 `source .venv/bin/activate`。各slice先跑其owner tests；review前执行受影响union；aggregate前执行：

```bash
pytest tests/cli/test_arg_parsing.py \
  tests/runtime/test_interruptible_process.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_output.py \
  tests/service/test_fins_direct.py \
  tests/service/test_fins_wait_adapter.py \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_sec_downloader.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_docling_process.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_docling_upload_service.py -q

python -m pyright dayu/ tests/ utils/
python -m ruff check <本WU全部changed-python-files>
python -m compileall dayu tests
python -m json.tool docs/cli_ci_oracles.json >/dev/null
python -m json.tool docs/cli_ci_scenarios.json >/dev/null
git diff --check
```

覆盖率使用同一affected union生成data，再对每个修改production文件分别执行 `coverage report --include=<file> --fail-under=80`；不能用union总体百分比掩盖单文件不足。新增process/concurrency tests必须使用deterministic Event/barrier和bounded deadline，不使用sleep猜时序。AST/static检查至少包含：

- `dayu.runtime` 未import Fins/Host/Engine/Service/UI；
- CLI未import storage私有实现；
- `rg -n "FinsDownloadRequest" dayu tests` 穷举的所有import/construct site都指向 `download_contract.py`，`ingestion_runtime.py`无兼容re-export；
- production download path无 `rebuild_processed`，但preprocess/upload现有同名字段保留；
- download专用builder拒绝CSV ticker，`_parse_ticker_csv` body与upload/preprocess alias调用保持；`cn_form_utils.py`无 `_TOKEN_TO_PERIOD`；
- SEC普通download无stale cleanup调用；
- Docling production path无 `asyncio.to_thread(convert_pdf...)`；
- AST证明runner调用 `InterruptibleProcessHandle.start()`且production无 `.spawn()` wrapper/call；`dayu/runtime/interruptible_process.py`未修改；
- `rg`穷举 `SourceDocumentRepositoryProtocol` implementation、`FsSourceDocumentRepository` composition subclass/test spy；wrapper/core均实现published+staged classification且无 `getattr`/compat shim；
- call graph/AST与barrier证明provider/PDF/Docling调用不在 `begin_batch` 至commit/rollback区间；
- public/log文本无contact canary、absolute path和provider raw payload。

## 10. DL-G01～DL-G05 执行顺序与 Oracle pause

真实运行只能在所有slice、owner/static validation、双路code review与aggregate deepreview通过后的exact commit上开始；每次使用新的CI-owned run root，不覆盖第一轮evidence。

### DL-G01 focused-real

按handoff 11组完整执行：静态非法输入/CSV/last-wins；US/CN/HK alias与bare canonicalization；显式SC13窗口；历史source non-deletion；SEC与CN/HK rebuild四组合；missing periods；UA configured/unconfigured与真实transport failure；同/异ticker并发及SEC throttle evidence；very-early/provider/file/Docling Ctrl+C；US与CN/HK size/digest corruption repair；全部screen/final summary与repository对账、quiet/debug/log及secret scan。

每场景保存 exact argv/cwd/非秘密env/按键时间线、stdout/stderr/screen、exit/signal、filesystem before/after、关键bytes/digest、Fins public state、logs，以及Host/runtime SQLite/EventLog/Tool Trace“已查询不存在”证明。

### DL-G02 高成本默认窗口

默认CN与HK都要各自运行一次不带forms/start/end的bare default，因为二者虽然共享 `cn_download_workflow.py`，但provider-specific discovery、页面解析与PDF来源不同，不能仅凭共享pipeline判等价。唯一例外：DL-G01已分别用真实run覆盖CNInfo与HKEX的candidate discovery/provider分支，且直接代码证据证明从候选进入高成本阶段后，两市场使用exact同一downstream owner、无market/provider branch、发出exact同一event schema，并且DL-G01运行证据证明该共同入口前的typed candidate fields满足同一contract；此时可用一个市场的bare高成本run代表“共同downstream”而非代表另一个provider。报告必须逐项列出两市场DL-G01 run refs、函数调用链/branch证据、event schema对账与被省略的唯一高成本阶段；任一条件不成立就补跑另一市场。记录candidate、Docling、耗时、counts和production read/process可消费性。

### DL-G03 partial provider failure

先调查真实、无伤害、可重复的downloaded+failed公开路径。存在则真实运行；不存在则登记 `defensive/unreachable`，附source contract不可达证明与deterministic owner test。fake provider只能是test evidence，绝不标full-real。

### DL-G04 atomic publication interruption

“公开稳定产品路径”仅指：不加production hook、sleep或private timing控制，只用正常argv/env/OS signal即可在重复run中稳定命中同一commit前/swap/commit后窗口并取得可对账证据。先调查该路径；若只能依赖wall-clock猜测、私有函数/测试hook或不可重复竞态，则登记 `defensive/unreachable`，不加production hook，并用storage进程级atomicity/recovery owner tests关闭；若可达则证明old/new二选一、无半目标且fresh restart恢复。

### DL-G05 calibration-real 与报告

DL-G01～G04合法终态后，按`docs/cli_ci.md` download mandatory inventory重跑完整calibration-real，生成新的immutable observed-behavior report。每项固定格式：

1. 运行了什么；
2. 观察到什么；
3. Agent裁决建议；
4. evidence refs/digests；
5. gap或residual risk。

报告生成、secret scan通过后立即进入 **Oracle pause**：只把编号观察交用户复核，不更新`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`或readiness。用户接受后才进入registry/readiness gate；拒绝任一predicate则回到对应owner fix/review/rerun loop。

## 11. 风险与控制

| 风险 | 控制 / residual |
|---|---|
| process start导致Docling冷启动与临时磁盘成本增加 | 只隔离不可协作取消的conversion；父子用system-temp文件交换大payload，handle close后parent finally清理；DL-G02记录成本。parent SIGKILL可能留下system-temp残留，不在workspace加scavenger。 |
| 取消请求撞上同步provider/storage边界 | HTTP/PDF依赖既有30s request timeout与前后checkpoint，Docling可terminate/kill/close，queue有50ms poll，runtime owner等待thread/resource quiescence后才发terminal。底层文件系统永久I/O或OS失效仍可能使取消等待；CLI不以timeout/强杀/合成130制造假终态。 |
| blocking writer等待活但卡住的合法batch | 强制远端/转换在batch外，transaction只含本地staging/publication；crash由OS lock/recovery释放；owner test+static proof验证边界。仍保留底层I/O永久卡死这一平台风险，不用任意业务timeout或fail-fast掩盖。 |
| 同ticker并发请求基于较旧remote payload | Phase B先比target identity/revision；变化就释放并丢弃旧prefetch。同targetoverwrite后writer重新prefetch并形成last-writer，different-target writer从latest tree只改自身target并保留集合并集。 |
| integrity repair在预取期间publication identity连续变化 | 任一latest status只要identity/revision变化都回Phase A，最多3轮；新状态COMPLETE时False直接skip且不新增target网络，True重新prefetch。耗尽后typed conflict且latest published不变；普通writer等待不受该重试上限影响。 |
| 一个ticker存在多个独立corrupt source | 本WU保证被本次选中的repair target；complete-tree validator仍可能因另一个未选中corrupt source fail closed。报告保留该严格validator风险，不通过放宽校验或删除非目标解决。若真实G01命中，需独立owner裁决。 |
| public relative locator含storage-private component | locator只作为定位标签，row同时给document ID且禁止据其推理；由storage owner产生，不成为schema业务identity。 |
| provider partial failure与publication timing不稳定 | 严格执行DL-G03/G04真实优先、不可达证明次之，不加后门、不把fake冒充real。 |
| SEC contact泄漏 | exact canary扫描stdout/stderr/log/evidence；日志仅configured boolean；报告只写变量名/类别/计数。 |
| request contract迁移影响awaiting tools | CLI与tool path共用builder；Service wait adapter test验证LLM-facing结果；不保留旧schema。 |
| broad `ingestion_runtime.py`修改回归其它operation | download contract抽离；preprocess/upload owner tests纳入受影响union，deepreview检查无semantic drift。 |

## 12. 无过度设计说明

- 三个新增production模块各自对应唯一缺失owner：download contract、Docling process boundary、storage integrity classification；不是generic framework。
- 复用现有runtime child-process primitive的 `start/wait/terminate/kill/close` 与SEC throttle；Fins operation task只是收口现有thread/queue ownership，不新造process manager、job系统、global scheduler或download lane。
- 并发只修storage writer coordination，不锁整条command；integrity把published/staged closed classification加到既有source repository owner，并以3轮局部重验证处理race，不新造capability Protocol或通用repair engine。
- public summary只覆盖用户已要求的download事实和bounded rows，不暴露raw payload或建立新observability平台。
- Host/Engine无contract变化，因此保持零修改。

## 13. 后续每个 gate 的最终报告格式

每次 implementation/review/real-run closeout 必须按以下顺序报告：

1. **Gate / commit / scope**：当前gate、exact HEAD、允许文件与实际changed files。
2. **改了什么**：按DL-F编号映射到owner、contract与data flow。
3. **验证了什么**：owner tests、affected union、单文件coverage、pyright、Ruff、compileall、JSON、diff check；真实CLI与unit/static严格分栏。
4. **Review 状态**：两路review、rereview、aggregate deepreview finding与裁决。
5. **真实观察**：只在DL-G阶段列run root、scenario/evidence/digest/secret scan，不把fake写成real。
6. **Oracle / registry状态**：明确写 `pending user adjudication`、`accepted`或`not updated`，不得把Agent建议写成用户接受。
7. **README decision**：说明实际更新与未更新原因。
8. **Residual risks / gaps / blocking questions**：逐项列出owner、影响与下一动作；无则写“无”。

## 14. Review Adjudication / Revision

裁决对象是两份不可修改的独立review：AgentMiMo `docs/reviews/plan-review-20260809-232233.md` 与AgentDS `docs/reviews/plan-review-20260809-232123.md`。disposition均以当前代码、正式task/handoff和用户主控裁决为准，不把review建议机械写入实现。

### 14.1 AgentMiMo findings

| Finding | Disposition | 直接证据、理由与本次revision |
|---|---|---|
| F-01 `InterruptibleProcessHandle.spawn` 不存在 | **接受** | `dayu/runtime/interruptible_process.py`公开入口是 `start()`，随后才是 `wait/terminate/kill/close`。§4、§5.5、Slice 3、static/AST测试均改为真实API；明确禁止新增spawn wrapper。 |
| F-02 Slice 1过宽 | **部分接受** | Gateflow允许本WU最多四个slice，Docling与storage必须独立，不能拆第五个。Slice 1新增不可交换的S1-A typed contract/CLI-Service prevalidation checkpoint与S1-B pipeline checkpoint，各自有tests/static stop，降低review耦合。 |
| F-03 rebuild集成欠规格 | **接受** | `SecPipeline.download_stream`与 `CnPipeline.download_stream` 已有 `rebuild` 参数和正确host实例；SEC `_rebuild_download_artifacts`、CN `run_cn_download_stream_impl` 已按真实签名调用各自helper。§5.3写全request -> adapter params -> existing pipeline host -> helper -> events -> strict summary路径，并删除processed读写。 |
| F-04取消终态有界性 | **部分接受** | 接受“终态有界性欠规格”，拒绝CLI 30/60s timeout、local 130或强杀建议：当前terminal validator只在raw source clean exhaustion放行，CLI合成会再次越过owner。§5.5改为Fins-owned operation task/thread/queue与owner-only abort cleanup，列出queue/HTTP/retry/Docling/storage边界；CLI只request+await。 |
| F-05缺独立Goal Confirmation artifact | **拒绝** | 用户确认发生在AgentController会话；正式task引用完整handoff，二者是binding source。仓库没有独立artifact且任务未要求生成，虚构路径反而破坏审计；§1明确此事实。 |
| F-06 blocking writer timeout | **部分接受** | 接受持锁外I/O、锁序/release/notify证明缺口；拒绝任意5～10分钟业务timeout，因为DL-F08要求两个合法同tickerwriter都成功。§5.6改用barrier+AST/call-graph双证据，记录底层永久I/O residual。 |
| F-07 request迁移影响未穷举 | **接受** | `rg -n "FinsDownloadRequest" dayu tests` 直接列出production imports/constructs与五个test文件；§5.1、Slice 1 allowlist/tests/stop check全部补齐，禁止compat re-export。 |
| F-08 temp crash cleanup | **接受** | §5.5固定system-temp per-run唯一目录、parent owner、handle close后finally清理、primary outcome优先与安全warning；可控路径无残留，parent SIGKILL残留列为residual，workspace不留staging。 |

### 14.2 AgentMiMo open questions

| Open question | Disposition | Resolution |
|---|---|---|
| OQ-1 runner Protocol位置 | **已解决** | `CnDoclingConversionRunner` Protocol放现有 `cn_download_protocols.py`；production实现与pickle target放 `cn_docling_process.py`。 |
| OQ-2 integrity Protocol owner | **已解决** | published/staged方法加入现有 `SourceDocumentRepositoryProtocol`；wrapper/core共同实现，直接证据与全量implementer/test subclass见§5.6/Slice 4。 |
| OQ-3 Slice 2/4重复改Protocol | **已解决** | Slice 2只增加locator query，Slice 4只增加integrity query；分别做slice review，aggregate deepreview检查最终Protocol/wrapper/core union，无需合并slice或新增共享facade。 |

### 14.3 AgentDS findings

| Finding | Disposition | 直接证据、理由与本次revision |
|---|---|---|
| DL-PR-01 integrity repair/持锁HTTP矛盾 | **接受并二次修订** | §5.6采用race-safe two-phase：短publication guard分类并返回revision；锁外HTTP/PDF/Docling；`begin_batch`复制latest后在staging复核。主控回读进一步收紧为identity-first：任一revision/identity变化都释放、丢弃旧prefetch并回Phase A；只有same identity才解释latest integrity+overwrite policy，耗尽typed failure且不丢latest。 |
| DL-PR-02 Docling temp owner | **接受** | 与MiMo F-08合并收敛：parent/system-temp/close-before-finally-cleanup/安全日志/primary precedence/SIGKILL residual全部进入§5.5与Slice 3 tests。 |
| DL-PR-03 DL-G02等价门槛 | **接受** | §10默认CN/HK都需真实provider-specific evidence；只有DL-G01已分别覆盖provider分支，且高成本阶段exact owner/branch/event schema相同时，一次bare高成本run才可仅代表共同downstream，报告必须列代码与run refs。 |
| DL-PR-04 Protocol破坏影响 | **接受** | `rg`显示production直接实现只有 `FsSourceDocumentRepository` wrapper，委托 `_FsSourceDocumentCore`；列出六组test subclass/spy与pyright/allowlist，禁止getattr/default/compat shim。 |
| DL-PR-05 runtime allowlist措辞 | **接受** | Slice 3明确 `dayu/runtime/interruptible_process.py` 可import/use但禁止修改；若通用defect需停下重新plan/review。 |
| DL-PR-06 `_parse_ticker_csv` 回归 | **接受** | download使用专用builder；共享 `_parse_ticker_csv` 的upload/preprocess alias语义不改，Slice 1新增upload CSV回归与AST check。 |

### 14.4 AgentDS open questions与主控收敛

| Open question | Disposition | Resolution |
|---|---|---|
| DL-G04“公开稳定路径” | **已解决** | §10定义为无production hook/sleep/private timing且能仅以正常argv/env/signal重复命中；否则defensive/unreachable。 |
| preprocess/upload中的 `rebuild_processed` | **已解决** | 只从download contract/adapter/rebuild路径删除；preprocess/upload同名业务字段保持。 |
| CN/HK alias mapping迁移 | **已解决** | `_TOKEN_TO_PERIOD`迁到domain parser后从 `cn_form_utils.py`删除；request/workflow共用真源。 |

### 14.5 主控回读增量裁决

| Finding | Disposition | 直接证据、理由与本次revision |
|---|---|---|
| CTRL-R01 Phase B latest COMPLETE无条件skip吞掉显式overwrite | **接受，已修复** | `cn_download_filing_workflow.py` 的公开参数契约明确 `overwrite=True` 时禁止复用和skip，`_resolve_fast_skip_result` 也在overwrite时返回None；SEC fast-skip owner同样显式接收overwrite。旧计划按latest COMPLETE直接skip违反request owner。§5.6现改为先比Phase A/latest identity/revision：变化时不论latest COMPLETE/REPAIR_REQUIRED/MISSING都rollback并回Phase A；same identity才按integrity+overwrite决策。Slice 4同步加入same-target overwrite last-writer、different-target union、零额外skip网络与stale-prefetch禁令。 |

### 14.6 Revision verification gate

本次revision必须满足：只修改本plan artifact；两份review artifact与产品代码零diff；`git diff --check`通过；read-only `rg`验证plan内API名、真实rebuild签名、FinsDownloadRequest callsite清单、Protocol实现/测试subclass清单、runtime文件“可用不可改”及四slice/allowed files自洽。若rereview发现新correctness/stability finding，继续在本节追加disposition/revision，不删除历史裁决。

## 15. 当前 plan gate 结论

- Code-generation-ready：是；但plan gate仍须等待两位原reviewer对本revision分别accepted，不能自动进入implementation。
- Blocking questions：无。公开 `--limit` 不存在，按现有parser contract不新增；DL-F01的limit落实为输入长度/数量bounds。取消超时、writer timeout、integrity protocol、runner位置、G02/G04与processed/alias范围均已owner-level收敛。
- 下一合法动作：两位原reviewer独立rereview本revision；本turn不自动推进implementation。
