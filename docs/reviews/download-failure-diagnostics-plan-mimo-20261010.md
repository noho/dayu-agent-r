RUNTIME/PROVIDER/MODEL: codex/mimo/mimo-v2.6-pro
CANARY=mimo-7c0f29eb

# 下载失败诊断计划独立 Plan Review

## Reviewed Target And Scope

- Reviewer：`dfdiag-plan-review-mimo-20261010-01`；本文件为唯一写入 artifact。
- Review target：`docs/gateflow/download-failure-diagnostics-plan-20261010.md`。
- Goal binding：`docs/gateflow/download-failure-diagnostics-goal-20261010.md`。
- 目标范围按已确认 goal 与用户指令执行：只修完整失败诊断不可取得；候选身份、来源提供的日期/表单/期间与安全失败原因必须同源；所有失败候选（包括位于前 10 项之后、总数超过 10）必须可取得；LLM-facing bounded summary 不得变成无界数组；保留现有 45 个来源；实际下载故障、生产重跑和新观测不在本 slice。
- 已知治理状态按用户/总控输入接受：当前 goal、plan、state 未提交且归属已确认；state 归属冲突不构成本 review 的 scope blocker。计划中“实时查询先另确认”是计划 Agent 的保守表述；总控已有 `workspace/tmp/download-failure-diagnostics-20261010/old-evidence-owner-read.json` 证据，本 review 不重复生产查询，也不把该保守表述升级为阻塞 finding。

## Frozen Identity And Evidence

身份首部核验：

- Branch：`fix/download-failure-diagnostics-20261010`。
- HEAD/base：`c65c2aa28fae9c47ad947783d63f7559db7768c4`，`git rev-parse` 与固定 base 解析一致。
- Plan SHA256：`e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca`，与用户给定值一致。
- Canary 文件 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.bawV9g/canary.txt` 已读取，内容为 `mimo-7c0f29eb`，本文件首部逐字记录为 `CANARY=mimo-7c0f29eb`。
- `workspace/tmp/download-failure-diagnostics-20261010/old-evidence-owner-read.json` 已只读核验：scope 为公开 storage repository、`create_directories=false`、`source_count=45`；8 个失败 ID 均为 `published_meta=missing`、locator 为空、原原因和日期为空。该文件的 `record_sha256` 为 `6d42a496a0fd4bbfce4a320025e77fa92758098c380ba51513a689527f15fce7`。没有执行 discovery、download、recovery、来源写入或新的生产查询。

## Assumptions Tested

1. **动机与 goal alignment**：原运行的 53 个候选包含 8 个失败，且公开有界摘要不能取得全部失败；计划的完整 typed rows、完整 failed rows 与 bounded LLM summary 分离是否真正覆盖后 10 项和超过 10 项失败。
2. **语义 owner**：候选身份/日期/期间来自 workflow typed result；失败分类和安全说明来自 workflow/downloader owner；public projection、CLI 和 wait 只能机械消费同一真源。
3. **失败分支完整性**：CN/HK normal、local rebuild、typed integrity abort，以及 SEC workflow/rebuild 的失败、跳过、拒绝和协议/执行错误是否都有必填、安全且不被 adapter 重写的 reason。
4. **执行语义**：部分失败、全失败、空成功、adapter 启动前失败、整体中止、取消前缀、取消与终态 claim 竞争、重复/缺失/后续 RESULT、stream 不干净结束是否保持单一终态和事实守恒。
5. **有界性边界**：`download_result`/完整 operator JSON 不进入 LLM-facing wait/tool summary；有界 public summary 的 rows、uncertain、omission 与 durable summary 仍受既有预算约束。
6. **最小性与切片**：一个行为 slice、五个生产文件、无 schema/job/resume 框架扩展，是否足以完成已确认目标；constructor 迁移是否覆盖全部生产与测试使用点。
7. **验证与部署**：测试是否断言 owner 级契约而非 fixture 兼容行为；固定 `.venv/bin/dayu-cli` 离线 subprocess 是否能证明新协议和实际加载路径；pyright、覆盖率和 README 触发是否有清晰验证边界。

## Findings

### 01-未修复-[高]-SEC 失败原因仍被 adapter 重写，计划范围无法满足跨来源同源要求

- **位置**: 计划 §2 的“CN/HK 对外 typed row”和“SEC 现有 adapter 原因保真”判断；§3.4 只列 `dayu/fins/pipelines/cn_pipeline.py` 为 strict reason 生产改动；§5.1 第 2、3 条要求 SEC reason 保真；§4 的生产文件允许清单。
- **问题类型**: 目标漂移 / 范围漂移 / 契约 owner 缺失 / 测试缺口。
- **当前写法**: 计划把 `cn_pipeline._project_cn_document_row` 的通用 failure/skip 文案改成 strict reason，同时宣称“SEC 现有 adapter 原因保真”，并将 `sec_pipeline.py` 排除在生产改动之外。计划还把“来源 workflow 的失败分类及安全说明同源”写入 binding 成功信号。
- **反例/失败场景**: 一个 SEC filing 的 workflow 行携带 `reason_code=provider_timeout`、`reason_message=披露易/SEC 来源请求超时` 或 `6k_prefetch_failed` 的具体安全说明。`sec_pipeline._project_sec_document_row` 仍通过 `_sec_safe_reason_message(disposition)` 生成固定的“SEC 来源未能完成该文档”“该文档按下载策略跳过”“该文档未通过来源筛选规则”，因此完整 diagnostics 中的安全说明不是 workflow 行的原字段。`sec_rebuild_workflow` 的 `rebuild_write_failed` 还把 `reason_message` 写成 `str(operation_error)`，而 `sec_download_event_mapping.normalize_download_file_result` 会从 `message/error` 选择原因文本；若为满足同源而直接改成 strict passthrough，会把原始异常文本暴露到 public contract。两种路径都不能同时满足“同源”和“安全”。
- **为什么有问题**: binding goal 明确要求候选身份、日期/期间、失败分类和安全说明由同一来源 workflow/downloader 事实投影，不允许 adapter/UI 重写或补偿。当前计划只修 CN/HK adapter，却在验收中要求 SEC reason 保真；实施 Agent 要么遗漏 SEC 使目标未达成，要么在不允许的 `sec_pipeline.py`/SEC workflow/rebuild 文件外临时补 fallback，违反 semantic owner 和修复边界。现有测试也只覆盖 CN/HK strict chain；SEC 当前公开投影的固定文案没有 owner 级等值断言。
- **直接证据**:
  - `dayu/fins/pipelines/sec_pipeline.py:1947`、`:1960`、`:1973` 分别把 upstream reason 替换成 `_sec_safe_reason_message(...)`。
  - `dayu/fins/pipelines/sec_pipeline.py:2092-2111` 只按 disposition 返回固定通用说明。
  - `dayu/fins/pipelines/sec_download_filing_workflow.py:314-325` 的 provider failure 行已有 typed `reason_code/reason_message`，`:614-623` 的 file failure 行已有 `file_download_failed` 和 file reason；这些正是 SEC adapter 当前丢弃的 owner 事实。
  - `dayu/fins/pipelines/sec_download_event_mapping.py:139-154` 从 `reason/message/error` 反推原因，`:72-104` 的 `summarize_failed_download_file_reasons` 可能把文件级文本汇总为 filing 原因；`sec_rebuild_workflow.py:427-445` 的 `rebuild_write_failed` 使用原始 `str(operation_error)`。
  - `dayu/fins/pipelines/cn_pipeline.py:1566-1589` 当前也分别用 `skip_reason`、`cn_document_failed` 和通用说明；计划只把这一个 adapter 改为 strict，不能证明 SEC 路径满足同一契约。
  - `tests/fins/test_sec_pipeline_download.py:3262-3263` 仍断言 workflow failure 说明为 `存在文件下载失败`，没有断言 public typed row 保留对应安全 reason；计划 §5.1 的“SEC 现有 adapter 原因保真”没有现有测试事实支撑。
- **影响**: 后续失败诊断中的 SEC 失败行仍不可核验真实安全原因；如果只修 CN/HK，调用方会把 SEC 通用文案误当成来源原因；如果扩大到 SEC 但不先修 owner 安全投影，可能泄漏原始异常/错误文本；计划无法作为不需重新设计的 implementation handoff。
- **建议改法和验证点**:
  - 先由总控裁决 binding scope 是“仅当前 0700/CN-HK”还是“所有 Fins download source”。若目标确为跨来源同源，将 SEC reason owner 的最小修复纳入同一 slice：在 workflow/rebuild/file-result owner 产生并校验安全 reason，`sec_pipeline` 只 strict 读取，不再按 disposition 重写；禁止把 `str(operation_error)` 或 raw `error` 直接投影。若目标明确只限 CN/HK，则删除计划中“SEC 现有 adapter 原因保真”“新增公共能力不只对 0700 / CN 生效”等验收承诺，并把 SEC 列为明确 residual risk/后续 work unit，不能继续声称本 slice 已满足跨来源 goal。
  - 测试至少增加 SEC provider timeout/http/protocol、file failure、6-K rejection、rebuild write failure 的 workflow filing result -> typed row -> diagnostics 逐字段 reason 断言，并覆盖缺字段、空字段、raw exception、URL/绝对路径的拒绝。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。

### 02-未修复-[中]-完整诊断方法的操作归属与无 typed result 的 download 失败契约没有写死

- **位置**: 计划 §3.2 的 `FinsResultSummary.download_result`/`download` property；§3.3 的 `to_download_diagnostics_json_value`；§3.5 的 runtime/observation failure helper 迁移。
- **问题类型**: 契约缺失 / 状态机漏洞 / 不可直接实施。
- **当前写法**: `FinsResultSummary` 没有 `operation_kind`，但计划要求“非下载 result 调用该方法抛 `ValueError`，下载时仅从 `download_result` 产生 JSON”；同时规定下载终态（包括启动前失败、prepare 取消）必须由 runtime 显式提供 request-scoped typed 空结果，并要求 `FinsEvent` 只对 RESULT 做 operation 约束。
- **反例/失败场景**: `ingestion_runtime._mark_observation_failed` 当前在 activation submit 失败时创建 `FinsResultSummary`，但没有传 `download_result`（`ingestion_runtime.py:7486-7521`）；它可以从 `record.context.download_request` 构造 typed 空结果，但计划只写了“observation prepare-cancel / failure helper 一次迁移”，没有明确该 helper 的 request-scoped 空结果、整体 `FinsPublicFailure`、诊断 JSON 与 `download_result=None` 的排他语义。另一个非下载 result 和一个未形成 typed result 的 download failure 在 `FinsResultSummary` 层都表现为 `download_result=None`，方法无法凭自身判断操作类型。
- **为什么有问题**: 这是公共诊断协议的字段 owner 和失败状态机边界。若实现把 `None` 当非下载而抛错，observation/activation failure 会丢失下载诊断；若用 `FinsEvent` 或消费者上下文补默认结果，就违反“完整 typed result 是唯一输入真源”；若允许两个可独立设置的结果字段，又会重新产生 full/bounded 漂移。
- **直接证据**: `dayu/fins/direct_events.py:648-718` 当前 `FinsResultSummary` 只持有 bounded `download`，没有 operation 字段；`dayu/fins/ingestion_runtime.py:7486-7521` 的 `_mark_observation_failed` 是 download observation 可达路径；`dayu/fins/ingestion_runtime.py:4005-4014` 在 executor submit 异常时调用该 helper；计划 §3.3 只规定“非下载 result 抛 ValueError”，没有定义 `download_result=None` 的 download terminal。
- **影响**: implementation Agent 可能在 generic result、event 或 CLI 层加 `hasattr`/默认空摘要/操作判断 fallback，导致完整诊断、取消快照或 LLM bounded projection 不一致；activation failure 的测试也可能只验证错误状态而漏掉 download_result contract。
- **建议改法和验证点**: 在 owner 契约中明确二选一：`download_result` 为 `None` 只代表非下载 result，并要求所有 download terminal（包括 observation activation failure）由拥有 `download_request` 的 runtime helper 构造 typed empty result；或者给诊断入口一个明确的 download-specific result wrapper。测试必须覆盖 activation submit failure、prepare cancel、adapter 启动前 failure 的 `download_result` 非空、`to_download_diagnostics_json_value` 可调用且 `failed_documents=[]`，并断言非下载 result 才拒绝。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## Open Questions

1. Binding scope 是否明确包含 SEC source？当前用户成功信号写的是来源 workflow 的身份/日期/安全原因同源，计划又明确承诺 SEC；若总控将范围收窄为当前 0700/CN-HK，应同步删除跨来源验收承诺，而不是让 implementation 自行猜测。
2. 对“完整失败诊断可取得”的交付边界是否只限本次合法 consumed RESULT/CLI 标准流？计划明确不承诺 SIGKILL、崩溃、未消费 stream 或未捕获标准流后的历史恢复；该限制与当前 goal 的“后续同类运行可取得”相容，但需总控在 closeout 中明确，不可把它描述成 durable historical diagnostics。
3. `to_download_diagnostics_json_value` 对 `download_result=None` 的 download observation failure 是否属于公共 API 的必选拒绝路径？建议在 plan fix 中把状态机规则写成 owner-level invariant，而不是留给实现 Agent 选择。
4. 总控已完成的旧证据实时核查与计划 §6 的“如需实时独立仓储核查，先报巡检线”表述如何归档？按用户指令这不是 scope blocker；只需在 closeout/evidence assessment 中引用现有 JSON，不重复查询。

## Residual Risks And Tracking

| 分类 | 风险 / 未覆盖项 | 建议跟踪位置 |
| --- | --- | --- |
| `fixed in current slice` | 后 10 项、超过 10 项的完整 failed rows 与 bounded summary 分离；需由实现测试证明 `len(failed_documents)==failed_count` 且 omission 只作用于 summary。 | 当前 work unit S1；owner contract tests。 |
| `fixed in current slice` | 取消前缀、typed abort、全失败、空成功和 terminal claim 竞争的守恒；计划已有测试意图，但需在 implementation 中保留真实 typed result，不得由 fake summary 补齐。 | 当前 work unit S1；runtime/direct stream tests。 |
| `assigned to later work unit` | 旧 8 项的原始异常和来源日期/期间不可恢复；现有 owner-read JSON 只证明当前 published meta 缺失，不证明历史原因。 | 总控 evidence assessment；报告逐 ID 的 unknown，不猜原因。 |
| `requiring explicit user decision / 巡检线` | 实际下载故障、网络/404/provider 根因、来源业务影响、任何新观测或生产下载。 | 巡检线 scope confirmation；不得由 implementation 触发。 |
| `requiring new issue or explicit user decision` | SIGKILL、崩溃、未消费/提前关闭 stream、未捕获标准流后的历史不可追回；计划当前只承诺合法 consumed RESULT。 | 后续 durable diagnostics work unit；本 slice 不新增 job/repository。 |
| `fixed in current slice` | operator JSON 随失败数增长但 LLM-facing summary 保持有界；极端规模输出长度、管道阻塞和内存压力未单独压测。 | 当前 slice 的输出 contract；必要时另开性能 issue。 |
| `requiring explicit user decision` | 固定 binary 的真实部署路径、可执行权限和生产加载漂移；当前计划提供 editable import/hash 与 isolated subprocess 验证，但不冒充真实远端下载。 | 总控 deployment/closeout；生产验证需另行授权。 |
| `requiring explicit user decision` | merge、approve、ready、reviewer、外部 comment，以及 goal/plan/state 的最终 commit 归属。 | 总控/用户 gate；本 review 不执行。 |

## Validation

- 已读取 `AGENTS.md`、goal、plan、planreview skill、Fins download contract、direct events、CN/HK workflow/rebuild、CN/SEC adapters、runtime、CLI output/command、service wait adapter 和相关测试/README 职责；未读取另一路 review artifact，未修改生产代码、测试、goal、plan、state 或来源。
- 已核验 branch、HEAD/base、plan SHA256、canary 和旧证据 JSON 的关键字段；没有执行任何生产仓储查询、网络、下载、overwrite、recovery 或业务重跑。
- 已用静态代码事实构造反例验证 finding 01；SEC provider/file/rebuild workflow 产生 reason 的路径与 SEC adapter 通用文案重写路径直接相交。
- 本次为独立 plan review，不执行实现测试、pyright 或 coverage；这些命令属于 implementation gate，不能在本 artifact 中冒充已验证结果。
- 计划的 one-slice/五文件边界本身没有被本次 review 判定为过度拆分；问题在于其中承诺的 SEC 语义没有对应 owner 文件和测试范围。

## Final Plan Review Conclusion

结论：`fail`。

Code-generation-ready：`否`。计划在 CN/HK 完整诊断、bounded LLM summary、取消/失败守恒和固定 CLI 离线验证上具备可实施骨架，但 finding 01 直接违反 binding goal 的来源安全原因同源承诺，且当前生产文件清单无法完成该承诺；finding 02 使公共诊断入口在 observation failure 边界仍有 owner/状态机歧义。应先由总控裁决 SEC scope，并按上述建议修订计划和 owner-level tests 后再进入 implementation。

身份尾部核验：Plan SHA256 仍为 `e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca`；HEAD/base 仍为 `c65c2aa28fae9c47ad947783d63f7559db7768c4`；branch 仍为 `fix/download-failure-diagnostics-20261010`。本 review artifact 是本轮唯一写入文件。
