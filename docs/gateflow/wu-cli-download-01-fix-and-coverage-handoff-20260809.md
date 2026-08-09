# `dayu-cli download` 第一轮裁决后的修复与补跑交接

## 状态

- Work unit：`wu-cli-download-01`
- 阶段：第一轮 observed behavior 已完成用户裁决；实现尚未符合全部 accepted predicates。
- 工作范式：先修复，再以真实 CLI 重新运行覆盖；总控只记录观察，最终 conformance / oracle readiness 仍由用户裁决。
- 第一轮事实报告：`workspace/tmp/download-observed-behavior.md`
- 第一轮裁决清单：`workspace/tmp/download-oracle-adjudication.md`
- 第一轮 evidence root：`/Users/leo/workspace/.dayu-cli-ci/download-20260809Tjbv3bg`
- Handbook inventory：`docs/cli_ci.md` 的 `dayu-cli download` 第一轮 Mandatory Matrix。

第一轮已经运行并裁决的行为项均已有结论。下面列出的不是新的产品设想，而是用户裁决后仍需让实现符合的 predicates，以及修复后必须补跑的 coverage。`download` 在这些项目完成、真实观察报告交用户复核、正式 oracle/scenario registry 与 readiness proof 更新前，不得标记为 closed/ready。

## 已冻结且无需修复的主要语义

- 公开 CLI 不存在 `--source`；source 由 canonical ticker 的 market 自动解析。
- 默认 workspace 与 `--base/-b/--workspace` resolution、US/CN/HK canonicalization、重复单值 option 的 last-wins、合法 zero-match exit 0、正常 repeat/overwrite、rejected-only/mixed 的 operation success、SIGKILL 后原子恢复、download 不创建 Host Run/EventLog/Tool Trace/SQLite、后续 process 能从 Fins storage 消费 source，均按已观察行为接受。
- US/CN/HK canonicalization 已真实覆盖：`600519.SH`、`SH600519`、裸 `600519` 均为 `600519`；`000333.SZ` 为 `000333`；`0700.HK`、`HK.700`、裸 `0700` 均为 `0700`。
- 裸 US download 使用按 form family 有界的默认 lookback，当前默认 forms 集合（包括 8-K/SC13）已接受。
- `--overwrite` 是匹配 source target 的替换，不是 ticker 级清空。
- `--rebuild` 的业务语义已冻结为：**仅基于本地 source 重建 download-owned meta/manifest；不访问远端，不等同于 `--overwrite`，不触发 process，也不修改 processed/reprocess 状态。**
- source physical bytes 与 meta size/digest 不一致时，不论是否带 `--overwrite`，都应由 download 自动重新获取并原子修复该 source target。
- 并发没有“同 ticker 不允许并发”的产品语义。只有 SEC 外部请求有来源政策要求的共享限速；CN/HK 不需要 SEC 式业务限流。仓储原子发布可以短暂串行，但不能把普通并发请求作为业务错误拒绝。

## 待修复 findings

### DL-F01：公开输入验证发生得过晚

Accepted behavior：CLI 能从 argv 独立判定的 ticker/forms/date/limit/范围错误必须在 Service/Fins storage 装配和 primary operation 前失败，exit 2，给出一致、可行动的中文 usage error，并且不创建 workspace/Fins 目录。包括空/非法/超长 ticker、ticker CSV、多 ticker、空/非法/超量 forms、非法/超长 date、`start > end` 等。

Root cause evidence：当前 `_run_fins_direct_command_async()` 先解析 workspace、构造 `FinsDirectCommandService`，再由 `_open_direct_stream()` / runtime/source workflow 验证部分参数；因此静态 usage error 已产生 storage side effects，且同类错误在 SEC/CN/HK 被分成 exit 0/1/2。

Owner：CLI command input contract；跨市场共用的 form/date typed normalizer 可位于其直接上游 Service request validation，但不得由各 source adapter 重复解释。

### DL-F02：单 ticker 参数静默截断 CSV

Accepted behavior：`--ticker` 当前只接受一个 ticker。`AAPL,MSFT` 必须 exit 2，不能静默只使用第一项；重复 `--ticker` 保持 argparse 标准 last-wins，并在 resolved output 中显示最终 canonical ticker。

Root cause evidence：当前 `_parse_ticker_csv()` 保留 alias 形态并把第一项作为 canonical，导致第二个业务主体被静默忽略。

Owner：CLI ticker input contract。

### DL-F03：显式日期窗口被 SC13 补拉扩大

Accepted behavior：用户显式提供的 start/end 是硬边界。SC13 retry/browse 补拉只能在未显式提供 start、使用默认 lookback 时扩展候选；任何本轮实际 selected/downloaded/rejected filing 均不得越过显式窗口。

Root cause evidence：真实精确窗口 `2025-10-31..2025-10-31` 纳入了 `2025-07-29` 的 SC 13G/A；source-specific retry helper 没有保留“start 是否显式提供”的业务事实。

Owner：SEC filing collection/filter policy；显式边界事实从 typed request 同源传入，不得从日期值反推。

### DL-F04：普通 download 隐式删除旧 filing

Accepted behavior：普通 download（带或不带 overwrite）只处理本次匹配 target，不删除本轮未选择的既有 source。`keep_latest_sc13_per_filer` 只控制本轮候选选择，不拥有 repository prune 语义。若未来需要清理，必须另设显式 prune 操作并展示删除集；不在本 work unit 增加该能力。

Root cause evidence：这不是 skip。`sec_download_workflow.py` 在所有 filing 处理后开启 maintenance batch；`_cleanup_stale_filing_dirs()` 以本轮 downloaded/skipped document ids 为 valid set，再调用 `cleanup_stale_filing_documents()` 删除 active forms 下不在该集合中的历史 filing。旧 SC13 因 `keep_latest_sc13_per_filer` 未入选，随后被静默删除，screen/summary 也不投影删除。

Owner：SEC download workflow 的 target mutation policy。删除普通 download 对 stale cleanup 的调用；不要仅在 CLI 隐藏或补一个展示提示来保留错误的破坏语义。storage maintenance API 若仍有其它合法显式 owner 可保留，否则由实现审查决定最小清理范围。

### DL-F05：`--rebuild` 被错误映射到 processed 治理

Accepted behavior：`download --rebuild` 仅扫描符合 filters 的本地完整 source，并重建 download-owned meta/manifest；不访问远端、不下载/overwrite source bytes、不运行 process、不创建或修改 processed/reprocess 状态。`--overwrite` 与 `--rebuild` 彼此独立；组合时仍执行 local meta/manifest rebuild，不得把 rebuild 解释为 processed invalidation。

Root cause evidence：SEC/CN adapter 都把 pipeline 参数硬编码为 `rebuild=False`，然后将公开 `request.rebuild_processed` 仅应用到本轮 written document ids 的 processed 标记。仓库中已有 `sec_rebuild_workflow.py` 与 `cn_download_rebuild.py`，OLD 的 pipeline contract 也明确 `rebuild` 是“仅基于本地已下载数据重建 meta/manifest”，但当前 adapter 没有调用。

Owner：public download request schema + source-specific local rebuild workflow。删除 `rebuild_processed` 这一错误下载语义，使用语义准确的 typed 字段；不得保留兼容 alias/shim。

### DL-F06：CN/HK missing period 被计为 discovered/skipped

Accepted behavior：请求的 period 没有实际 provider candidate 时，该 period 不计入 discovered 或 skipped；合法零结果 exit 0。缺少哪些 requested periods 应通过独立 bounded missing-period details/notes 展示。

Root cause evidence：真实 HK 无候选时仍报告 discovered 6 / skipped 6，计数对象是请求窗口占位而不是 provider 实际发现的候选。

Owner：CN/HK source workflow candidate/result classification；UI 仅投影 owner 产出的 typed counts/details。

### DL-F07：动态失败、SEC User-Agent 与日志隐私不符合 accepted contract

Accepted behavior：

- network/provider 动态失败 exit 1，但屏幕须展示脱敏的 source/transport 分类与安全重试建议，不能只有“财报处理执行失败”。
- SEC 请求前必须存在满足来源政策的 User-Agent。若没有明确配置的合规身份，则在首次 HTTP 请求前明确失败且不发送 fallback 请求；若仓库已有受控合规应用身份真源，可使用该真源，但不得发明匿名/占位 fallback。
- 日志只能记录 User-Agent 的 configured/unconfigured 或脱敏 identity，不能原样记录联系值。
- 同一 command 的同一未配置 warning 只出现一次。

Root cause evidence：当前 `_resolve_user_agent()` 无配置时返回 `_UNCONFIGURED_USER_AGENT` 并继续真实 SEC 请求；`update_config()` debug 文本原样记录 `self._user_agent`；装配多次解析导致 warning 重复；CLI terminal 只投影泛化失败。

Owner：SEC downloader 配置/请求 policy 是合规身份真源；Fins typed terminal 是失败分类真源；CLI renderer 只做同源脱敏投影。

### DL-F08：同 ticker 并发被仓储 batch fail-fast 当作业务错误

Accepted behavior：同 workspace 同 ticker 与不同 ticker 都允许并发调用。Fins storage 只在必要的短 publication/recovery 临界区串行，并在竞争时等待/重试或以 typed 可恢复机制协调，不能把“跨进程活动 batch”直接作为一次 download 失败。SEC downloader 继续使用 workspace-shared throttle state + file lock 预约请求时间；CN/HK 不增加 SEC 式限流。

Root cause evidence：当前 `_acquire_storage_lock_token(..., blocking=False)` 在已有同 ticker batch 时抛出 `storage identity 已存在跨进程活动 batch`。SEC downloader 当前已经实现 `_SecThrottleState`、共享 state file、file lock、request slot/cooldown；OLD 也使用同类文件真源，因此无需另造 operation-wide mutex。

Owner：storage batch/publication concurrency policy；SEC request throttle 保持在 SEC downloader owner。不得用 CLI 全命令锁或按 ticker 拒绝来绕过。

### DL-F09：Ctrl+C 没有等待 canonical cancellation，Docling 仍在后台运行

Accepted behavior：一次 Ctrl+C 请求协作式取消；CLI 等待 Fins owner 产生唯一 cancelled terminal并完成 cleanup，然后 exit 130。very-early、provider wait、file download、Docling conversion 与 publication 前后均遵循同一语义；不得让后台线程/进程继续输出，不能把取消改写为 failed，也不能发布半文档。

Root cause evidence：CLI `_wait_for_terminal_handling_sigint()` 在首次 SIGINT 后先标记 token，随即 `event_task.cancel()` 并本地返回 130；direct producer 仍在线程中执行。CN/HK Docling 当前通过 `asyncio.to_thread(convert_pdf_to_docling_json, ...)` 调用同步第三方库，不具备终止边界，因此真实终端在 CLI 退出后继续出现 Docling/interpreter shutdown 输出。

Owner：Fins direct operation lifecycle 拥有 canonical terminal；CLI 只请求取消并消费 terminal；同步、不可协作取消的 Docling conversion 必须处于可终止、可 join/drain 的独立进程边界。实现前核对 OLD；若 OLD 没有当前所需的完整 process cleanup，也不能照搬缺陷。通用 child-process lifecycle 可复用/扩展 `dayu.runtime`，但 Fins/Docling 业务语义不得下沉到 runtime。

### DL-F10：source integrity mismatch 无法自动修复

Accepted behavior：published source physical file 与 source meta 的 size/digest 不一致时，无论是否指定 `--overwrite`，download 都把该 target 视为 repair-required，重新获取完整远端 source，并通过 staging/validation/atomic publication 替换；修复失败时保留旧损坏目标及可诊断事实，不留下半目标，也不删除非目标。该状态是 storage/source integrity failure，不是 user input error。

Root cause evidence：当前 complete snapshot validator 在 source workflow 作 overwrite/remote refresh 决策前就 fail closed，所以有无 `--overwrite` 都到不了修复路径，并被上层泛化成 user-input failure。

Owner：storage complete snapshot 提供 typed integrity classification；source workflow 根据该 classification 强制 repair。不得放宽普通 read validator，也不得由 CLI 删除文件后重试。

### DL-F11：screen/final summary 不足以让用户验收实际结果

Accepted behavior：

- progress 对真实 conversion 同时投影 `conversion_started` 与 `conversion_completed`。
- final summary 展示 resolved source、canonical ticker、effective forms/date filters，以及 bounded downloaded/skipped/rejected/failed document rows（至少包含 document id、form/period、filing/report date、结果分类和可行动 reason）。
- 对已写 source 展示相对 workspace 的业务 artifact locator，不泄漏绝对路径/provider raw payload；超过上限展示 omitted count。
- rejection 展示 category/reason；missing period 展示独立 details；普通 download 不再有隐式删除。

Root cause evidence：当前 screen 主要只有聚合计数；CN/HK 只发 conversion_started；rejection/missing/network 细节没有进入稳定 public terminal projection。

Owner：source workflow/runtime typed event/result contract 产生事实；CLI renderer 统一 bounded 展示。不能由 CLI 扫私有 storage 反推。

## 修复后待覆盖项

所有真实运行必须在 exact post-fix commit、fresh CI-owned workspace 上执行，保存 argv/cwd/非秘密环境、按键时间线、screen/stdout/stderr、exit/signal、filesystem before/after/diff、关键 source/meta/manifest/processed bytes/digest、Fins public state、日志与 secret scan；Host SQLite/EventLog/Tool Trace 对 direct download 要证明已查询且不存在。owner tests 可以使用 deterministic fake/mock，正式 observed behavior 不得用 fake provider/tool 冒充。

### DL-G01：全部 finding 的 focused-real post-fix matrix

1. 静态非法 ticker/forms/date/limit/start-after-end/CSV：exit 2 且 workspace 零副作用；重复 `--ticker` last-wins。
2. US/CN/HK alias 与 bare ticker canonicalization，包含 `600519.SH`、`SH600519`、裸 `600519`、`000333.SZ`、`0700.HK`、`HK.700`、裸 `0700`。
3. SEC 显式精确/单边窗口 + SC13 retry/browse：没有窗口外 target。
4. 预置旧 SC13/其它 active-form source 后运行普通 download、download `--overwrite`：非目标 bytes/meta/manifest 均不删除、不改写。
5. SEC 与至少一个 CN/HK source 的 rebuild 四组合：plain repeat、`--overwrite`、`--rebuild`、`--overwrite --rebuild`；证明 rebuild 只改符合 filters 的 local meta/manifest，不网络请求、不改变 source bytes、不改变 processed 状态，后续 read/process 仍可加载。
6. CN/HK requested period 全缺失与部分缺失：实际 candidate counts 对账，missing-period details 单独展示。
7. SEC User-Agent configured/unconfigured、真实 transport failure：请求发送与否、screen 分类、exit、日志脱敏、warning 次数逐项核对。
8. 同 workspace 同 ticker并发 SEC、同 ticker并发 CN/HK、不同 ticker并发：两次 operation 均有正确 terminal/产物；SEC throttle state/预约间隔可审计，CN/HK 无无关业务限流。
9. Ctrl+C 至少覆盖 very-early、SEC provider wait/file transfer、CN/HK Docling conversion；若 publication 窗口可由公开稳定 hook 命中，也覆盖 publication。断言 canonical cancelled、exit 130、child 已结束、无后续输出/半文档，原 workspace 可原样重跑。
10. US 与 CN/HK 各选一个完整 source，分别制造 physical bytes 与 meta size/digest mismatch；有无 `--overwrite` 均自动原子修复并由后续 production read/process 加载。
11. downloaded/skipped/rejected/failed/zero-match/missing/conversion 的 screen 与 final summary 逐项和实际仓储对账；debug/quiet/log-file/debug-stream 组合及 secret/contact scan。

### DL-G02：高成本默认窗口代表性真实运行

CN 或 HK 至少选择一个市场，执行不带 forms、start、end 的裸 download，观察完整默认窗口、实际 provider candidates、Docling 产物、计数、时长与可消费性。另一个市场若由同 owner、同代码分支和已有 pairwise evidence 可等价覆盖，必须在报告中给出直接代码/运行证据，不能仅称“相似”。

### DL-G03：单次 operation 的真实 partial provider failure

优先寻找不修改 production code、不伪造 provider、不会伤害外部服务的真实 downloaded+failed 路径，观察 partial terminal、exit、已成功 source 与失败 detail。如果 source/provider contract 没有可授权、可重复的真实触发方法，则登记为 `defensive/unreachable`，附 owner-level deterministic test 与不可达证明；不得注入 fake provider 后宣称 full-real PASS。

### DL-G04：极短 atomic publication 中断

先调查是否存在公开、稳定且产品真实的 barrier/hook 能让 Ctrl+C/SIGKILL 命中 commit 前、swap 中、commit 后。如果没有，不为 CI 发明 production delay 或私有 backdoor；登记 `defensive/unreachable`，用 storage owner 的进程级原子性/recovery tests 关闭防御性证明。若可真实命中，则验证旧/新完整二选一、无半目标、下次启动恢复。

### DL-G05：全量 calibration-real 重跑与 registry 候选

focused-real 全部通过后，按 `docs/cli_ci.md` 当前 download inventory 重跑完整 mandatory matrix，生成新的 immutable `observed-behavior.md`。报告逐项列出“运行了什么、观察到什么、Agent 裁决建议”，但 Agent 不替用户接受 oracle。用户复核后才允许：

1. 在 `docs/cli_ci_oracles.json` 增加 accepted download oracle；
2. 在 `docs/cli_ci_scenarios.json` 增加全部 accepted/defensive scenario；
3. 生成 download inventory/coverage/readiness proof，确认 mandatory obligations、gaps、dangling refs 均为合法终态；
4. 将 download 标记为可进入第二轮 CI。

## Non-goals

- 不修改 init/prompt/interactive 已冻结 oracle/scenarios。
- 不处理 process/upload 命令自身 UI 与 oracle；只把它们作为 download 产物可消费性证明。
- 不新增 `--source`、multi-ticker、显式 prune、后台 job 或 Host Run。
- 不为兼容当前错误行为保留 alias、wrapper、双 schema 或下游补偿。
- 不把 `docs/host/design.md` / `docs/engine/design.md` 当成 download 业务 owner；只有确实触及 Host/Engine contract 时才允许修改。主要 owner truth 是 CLI public contract、Fins runtime/workflow/storage 以及 `dayu/fins/README.md`。

## 完成条件

- DL-F01..DL-F11 全部从 owner boundary 修复，accepted semantics 无 scope drift。
- 受影响 owner tests、pyright、Ruff、compileall、JSON、diff check 通过；单文件覆盖率满足项目要求。
- DL-G01 完整真实补跑；DL-G02..DL-G04 获得真实 evidence 或合规的 defensive/unreachable 终态。
- 完整 calibration-real report 已生成且 immutable，secret scan 通过，无 fake/mock 冒充。
- Agent 只报告 observation 与建议；正式 oracle/scenario/readiness 仅在用户最终复核后更新为 ready。
