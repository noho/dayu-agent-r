# WU-CLI-INTERACTIVE-01 Calibration Adjudication

## 状态

- command：`dayu-cli interactive`
- phase：第一轮 observed-behavior calibration / 用户逐项裁决
- target commit：`ae6bb96f7b500f5af88fdc5ca5cf63f52b282d74`
- observed report：`/Users/leo/workspace/.dayu-cli-ci/interactive-20260731T142441Z-ae6bb96f/evidence/observed-behavior.md`
- 本文状态：`partial`；行为项 1–28、30 已完成裁决，行为项 29 等待 F13 修复后重跑实际 provider identity 证据
- formal oracle：`docs/cli_ci_oracles.json` 中的 `cli.interactive.core-execution@1` 已增量冻结行为项 1–28、30
  明确接受或由用户给出 replacement behavior 的 predicates；不得把该 partial decision当作完整interactive oracle
- formal scenarios：尚未生成；实现修复并完成行为项 29 裁决后，依据 accepted oracle 建立并真实重跑；行为项 30 的
  public-contract不可达分支使用已接受的owner-level static proof closure，不伪造动态 succeeded/no-final

## 已接受行为

1. `##1` parser/help 的通用行为与 prompt 对齐，裁决为正确；但下述已经裁决为不存在的参数必须从 help/parser inventory
   删除后再冻结。
2. `##3` 已进入 REPL 后的真实 provider rejection/network unreachable 只使当前 Run failed 并恢复 `dayu>`；测试进程
   最终 exit 0 来自随后输入 EOF，裁决为正确。未知 model、credential 缺失或 runtime/config assembly 在 REPL 建立前
   exit 1 是另一 surface，不扩入本项。
3. `##4` 中除 `--ticker`、`--label` 新语义外，其它运行参数若与 prompt 共用同一 owner/contract，裁决为正确。
4. `##5` 日志等级、快捷入口、互斥、`--debug-stream` 与 `--log-file` 行为与 prompt 已冻结 contract 对齐，裁决为正确。
5. `##6` 现有 composer 的 Unicode、多行、编辑、paste 与 exact-buffer 提交行为裁决为正确；需补 Shift+Enter，见 F05。
6. `##7` non-TTY pipe 采用 whole-stdin batch contract：首 byte 到真实 EOF 是一个 draft，内部换行属于内容，EOF 提交
   整个 draft且只创建一个 Run；裁决为正确目标语义，当前逐行多 Run 行为需修改，见 F06。
7. `##8` 同进程 history / Ctrl+R 行为裁决为正确。
8. `##9` external editor 行为裁决为正确；功能 owner 说明见“代码核实”。
9. `##10` idle Ctrl+C 清 draft、空 draft 连按两次 exit 130 与 pending reset 行为裁决为正确。
10. `##17` Ctrl+T hide/show activity 行为裁决为正确。
11. `##19` Run 中 suspend/resume、resize、窄终端与 terminal mode 恢复裁决为正确。
12. `##21` 当前 fresh invocation、label reconnect 与 cursor 行为暂按正确记录，但 label owner 语义变化后必须重跑，且需补
    queued Run 退出/重连路径。
13. `##22` Host 的单 Session 单一 READ_WRITE attachment、其余 READ_ONLY observer 语义符合
    `docs/host/design.md`；该 Host contract 不因 CLI UX 调整而改变。
14. `##11` Ctrl+D/EOF 采用 prompt_toolkit/Unix 通行语义，当前观察裁决为正确：空 composer exit 0；非空且光标下
    有字符时删除该字符；非空末尾 no-op；active Run 中不取消、不退出，Run terminal 后再由空 composer Ctrl+D exit 0。
    non-TTY 真实 EOF、TTY Ctrl+D、literal `0x04` 与 PTY master close 继续作为不同 input class。
15. `##12` idle standalone Escape、CSI、Alt、bracketed paste 与 Ctrl+Z/SIGCONT 当前行为裁决为正确：不创建或取消
    Run；paste 进入 draft；suspend/resume 保留 draft 并恢复 terminal。测试 PTY 的 CPR warning 不属于产品 oracle。
16. `##13` standalone Escape 在所有 active-turn 阶段都应取消当前 Run、等待 Host canonical cancelled 后恢复 composer，
    Escape 本身不退出 interactive；very-early pre-accept 丢失属于修改项 F07。
17. `##14` Run 中只有 standalone Escape 表达 cancel；完整 CSI、Alt 与 bracketed-paste sequence 必须被完整解析并进入
    composer 编辑/导航/draft 语义，不得因首 byte 为 ESC 而取消 Run。当前误取消属于修改项 F07。
18. `##15`、`##16` Ctrl+C 在所有 active-turn 阶段采用同一 graceful lifecycle：第一次取消，连续第二次登记
    exit-after-cancel，等待 canonical cancelled 与全部本地清理后 exit 130；当前 pre-accept/closeout 偏差属于 F08。
19. `##18` active Run 中的 composer/type-ahead 采用默认 QUEUE：未按 Enter 的 draft 在当前 Run terminal 后仍保留；
    按 Enter 后创建一个 queued follow-up，不 steer 当前 Run，待当前 Run terminal 后按 Host queue contract 执行且恰好一次。
    STEER 只允许由未来显式 UI action 选择。当前丢弃输入属于 F09。
20. `##20` startup 尚无 Run、composer 尚未建立时，一次 SIGINT 直接完成可用资源清理并 exit 130，不要求双击；不得显示
    traceback。Host `lost` 表示当前 durable execution 已无法安全继续，明确显示错误并 exit 1，当前观察裁决为正确。
21. `##23` active client crash 后同 label 重连必须触发 Host attachment recovery。当前 I0552 在 SIGKILL 后重连等待
    180 秒、Run/Attempt 始终 `running`，不符合设计真源，登记为 F10。
22. `##24` cancelling 重连的目标行为由设计真源确定：已经 durable accepted cancel intent 的 `CANCELLING` Run 只继续
    cancel watchdog/closeout并最终 `CANCELLED`，不得创建 recovery Attempt或恢复业务执行；已经 terminal `CANCELLED` 的
    Run 永不恢复。I0508 没有真实捕获 durable cancelling 窗口，只是 coverage gap G04，不能据此宣称通过。
23. `##25`、`##26` interactive 的跨轮 memory、用户纠正、真实财报读取、Tool Trace request/response 与最终回答 grounding裁决为
    正确。AAPL 2025 10-K 的真实`read_section(s_0013_c03)`返回Total net sales 416,161 million，回答与工具结果一致。
    I0523使用removed `interactive --ticker`，不能原样进入scenario，需按G05重跑；download/preprocess独立CLI命令不由本项
    裁决。
24. `##27` tool not_found、handshake timeout、failed-batch `raise_error`/`force_answer`、provider failure与cancel只影响当前
    Run；REPL/同一Session可继续下一轮，per-Run失败阈值不污染后续Run。没有accepted tool result/final answer的失败或取消
    不得伪装成历史业务事实，当前观察裁决为正确。
25. `##28` 真实长会话触发soft-threshold proactive compaction、真实compactor proposal manifest、真实失败后的
    deterministic recent-window fallback，以及fallback后旧财报事实/新口径连续性，均是有效观察；但它只证明failed
    compaction fallback，不证明成功compaction。当前`proactive_operation_invalid_or_exhausted`不是场景故意注入的失败，而是
    wake-driven promotion与periodic owned-session reconciliation并发进入同一Run pre-start governance造成的实现故障，见
    F12。同一operation随后又写`stale_compaction_result`第二个canonical failed terminal也不正确，见F11。真实成功
    `CONTEXT_COMPACTED`、compact artifact、memory projection与compact后跨轮连续性仍未覆盖，见G06。
26. `##30` 成功必须携带非空 final answer，裁决为正确。Engine 对空白 final fail closed 为
    `runner_empty_final_content`，Host只能映射为`RUN_FAILED`；Host public `SUCCEEDED` event也要求存在final answer。
    因此CLI的`succeeded/no-final -> exit 1`只是最终防御，不是可通过public contract真实构造的产品状态。用户接受I0554的
    三条owner-level tests与静态owner chain作为该不可达分支的scenario closure；禁止为追求动态覆盖伪造Host response、
    直接写SQLite或调用private API。

## 已冻结产品语义

### Label 是跨入口 conversation alias

- `--label` 是 Session/conversation 的用户别名，不是 prompt/interactive 各自独立的 namespace。
- `prompt` 不带 label 时保持 one-shot，不承诺后续恢复；带 label 时，本轮挂到该 label 对应的 durable conversation。
- `interactive` 不带 label 时，每次 invocation 创建 fresh Session；带 label 时显式复用该 durable conversation。
- 同一 label 必须能在 `prompt --label <label>` 与 `interactive --label <label>` 之间双向续问。
- Session id 是 durable identity；label 是用户可读 alias。UI/Service 负责 alias resolution，Host 继续只拥有 Session/slot、
  Run/Attempt 与 attachment truth。

### 未终结执行恢复与 cancel 不复活

恢复的定位前提是 fresh `READ_WRITE` attachment 重新绑定同一个 durable Session；当前 CLI 通过同一 `--label` 满足该条件。
无 label interactive 依既定 oracle 创建 fresh Session，因此不能用另一个无 label invocation 声称恢复旧 Run。

| durable boundary | 正常关闭/crash/SIGKILL 后同 Session 重连 | 已接受 cancel intent 后重连 |
|---|---|---|
| `RUNNING` | positive orphan proof 成立后，旧 Attempt `LOST`，同一 Run 进入 `RECOVERING`，以新 Attempt/new `execution_id` 恢复 | 不进入 recovery；走 `CANCELLING -> CANCELLED` |
| `QUEUED` | 保持同一 queued Run identity，fresh writer 唤醒 ordinary governance，按 FIFO promotion并恰好执行一次 | queued cancel 直接 `CANCELLED`，不创建 Attempt |
| durable accepted `STEER_REQUESTED` | 保持同一 Run，按最新已接受 steer candidate重建输入，以新 Attempt继续；不接管旧 Attempt | cancel优先按canonical commit order收口，已取消的steer continuation不恢复 |
| terminal `CANCELLED` | 不恢复、不重新派发、不重复执行 | 幂等保持 `CANCELLED` |

只有已经 durable append `USER_INPUT_ACCEPTED` 及必要 canonical facts 的 input才具备恢复语义；在 durable acceptance 前丢失的
键盘输入不能由 Host 猜测恢复。正常 opener close/进程退出本身不是用户 cancel，不得写伪造 cancel facts；但 interactive
双 Ctrl+C 已明确表达 cancel intent，因此该路径应先优雅完成 `CANCELLED` 再 exit 130，后续重连不得恢复。

## 代码核实

### C01：当前 `prompt --config` 并未删除

直接运行当前 target 的 `dayu-cli prompt --help` 仍展示 `--config`；`dayu/cli/arg_parsing.py` 仍把 prompt 与 interactive
都注册在含 `--config` 的 runtime parent 上。正式 prompt registry 里有 17 条 invocation 实际携带 `--config`，21 条
scenario 声明 config parameter coverage。因此 F01 必须同时清理 prompt/interactive parser、help、实现引用以及 prompt
registry 中的 legacy config invocation/claim；不能只改 interactive。

### C02：prompt 已覆盖 label，但没有覆盖新冻结的跨入口语义

`prompt.P11-empty-label`、`prompt.P36-label-first-tool-call`、`prompt.P37-label-followup` 已覆盖空 label、首次带 label 和
prompt→prompt 跨进程 continuity；pairwise 也包含 label present/default assignments。不存在“prompt 完全没有覆盖 label”的
gap。

但 `P36/P37` 都是 prompt invocation；其 `cross-command:label-session-reuse` 实际没有证明 prompt↔interactive。
当前 `dayu/cli/host_context.py` 还分别生成 `cli.prompt.<label>` 与 `cli.interactive.<label>`，当前实现不能满足新冻结语义。

### C03：History / Ctrl+R 是 Dayu 显式启用，搜索实现来自 prompt_toolkit

`PromptToolkitInteractiveComposer` 显式选择 `InMemoryHistory`、`enable_history_search=True`；Dayu 又显式绑定 `c-r` 到
`start_history_lines_completion()`。历史存储、Up/Down 编辑和 completion/search engine 由 prompt_toolkit 实现。

### C04：External editor 是 Dayu 显式启用，进程执行来自 prompt_toolkit

Dayu 显式设置 `enable_open_in_editor=True`，并显式绑定 `Ctrl+X Ctrl+E` 调用
`current_buffer.open_in_editor(validate_and_handle=False)`；editor 选择、临时文件和子进程执行由 prompt_toolkit 实现。

### C05：Ctrl+D 是 prompt_toolkit 默认 key contract，Dayu 只消费 EOFError

Dayu 没有显式绑定 Ctrl+D。prompt_toolkit 在非空且光标前有文本时把 Ctrl+D 绑定为 delete-char，在默认 buffer 为空时
抛 `EOFError`；Dayu REPL 捕获 EOFError 并返回 exit 0。该来源不能被报告成 Dayu 自研 editor command。

### C06：模型/provider 失败不会自动退出当前 interactive REPL

真实 provider rejection/network unreachable 发生在已进入 REPL 的单轮 Run 时，当前行为是该 Run failed、恢复
`dayu>`；证据中的最终 exit 0 来自 harness 随后发送 EOF 做测试收尾，不是 provider failure 导致进程退出。
未知 model id、credential 缺失或 runtime/config assembly failure 发生在 REPL 建立前，当前仍会 exit 1；若用户要求这类
startup failure 也进入可恢复 REPL，需要另行裁决，不能与“Run 中 provider 不可达”混为一条行为。

### C07：PR #189 未承诺 interactive 二次中断产品语义

PR #189 的 prompt work unit 明确把独立 interactive 语义列为非目标。它为 prompt 建立了等待 canonical cancel terminal 的
专用路径；interactive 仍保留 `_cancel_run_waiting_for_terminal_or_second_sigint(...)`，第二次 SIGINT 会取消 canonical
cancel waiter并本地退出。因此当前结果是 interactive 新 oracle 下的明确 finding，但不是“已冻结 interactive 修复发生
回归”的证据。

### C08：I0552 是 recovery reclassification 缺失，不是“180秒仍不足以 stale”

I0552 setup 在 Run `running` 后 SIGKILL owner process，原 Host instance最后 heartbeat为
`2026-07-31T15:50:30.684020Z`；fresh同label进程于`15:50:31.933106Z`建立第二个Host instance，并持续heartbeat到
`15:53:30.455910Z`。当前默认`SessionAttachmentRecoveryPolicy.stale_after`为30秒，因此180秒观察窗已远超阈值。

当前`Host.attach_session(...)`只在fresh READ_WRITE allocation激活前用一个fixed `now`执行一次target recovery scan；
I0552的immediate reconnect发生在旧heartbeat尚未stale时，此次scan只能保守跳过，attachment存活期间没有在阈值到达后
重新分类。原owner已由setup明确SIGKILL、旧Run/Attempt却始终`running`且无`ATTEMPT_LOST/RUN_RECOVERING/RUN_LOST`，
所以F10的owner边界是Host attachment recovery后续reclassification/wake，而不是CLI展示或harness等待时长。

### C09：I0523 的真实工具链与报告措辞

原frozen observed report写成`list_documents/read_document`，但当前产品不存在本次成功路径所调用的`read_document`。
Tool Trace显示真实链路为`list_documents -> get_financial_statement(partial) -> get_document_sections/search_document ->
read_section`；最后`read_section(document_id=fil_0000320193-25-000079, ref=s_0013_c03, ticker=AAPL)`返回2025 Total net
sales 416,161 million。frozen evidence bundle不回写改digest；本裁决记录作为正式erratum，后续scenario/report使用真实工具名。

### C10：I0543 的 compact failure 是同 Host pre-start governance 并发重入

I0543只通过CI-owned config把soft threshold降至`0.015`以真实触发compaction；compactor使用真实`qwen-plus`，operation冻结
`max_compaction_attempts_per_operation=5`，没有注入无效proposal、provider failure或timeout。场景目标明确包含成功artifact
projection与compact后财务连续性，因此当前failure不是预期测试结果。

同一Host scheduler中，正常promotion wake与每`dispatch_poll_interval_seconds=0.2`秒运行的owned-session reconciliation
都会调用`_run_queue_promotion_with_lease(...)`。`SessionWorkLease`只拥有attachment close/drain计数，不提供同Session
single-flight。首条治理在事务外等待真实compactor时，periodic task于约196ms后再次读取仍为`ACCEPTED`的同一Run并重入：

```text
15:55:05.654  attempt 1 proposal manifest已提交，首条治理等待compactor
15:55:05.850  periodic reconciliation再次进入同一Run治理
15:55:05.857  错误提交proactive_operation_invalid_or_exhausted
15:55:05.873  首条compactor结果返回，又提交stale_compaction_result
```

periodic reconciliation的原始活性动机是：旧opener完成existing Attempt后，本地promotion wake不能跨opener通知当前RW owner；
当前RW owner需要从durable truth发现active slot已经释放。该动机不授权第二个governance executor。正确owner contract应是多个
wake/reconcile signal合并到唯一per-Session pre-start governance single-flight；in-flight时后续signal只登记再次检查，不得
并发resume、重建或终结同一operation。这个约束尚未在`docs/host/design.md`明确冻结，F12修复必须同步补充设计真源。

### C11：accepted `not_found` 后下载并再次查询的当前实现边界

- `list_documents(MSFT)`返回业务`error="not_found"`时，工具执行本身可以正常通过Host accept barrier并产生
  `TOOL_RESULT_ACCEPTED`。`dayu/host/memory.py`对每个该事件无条件生成selected recent evidence；普通RunInput再把它放入
  首条system envelope的evidence section。因此它表达的是“上一轮该次查询没有找到”，不是未accepted的工具运行故障。
- 当前memory projection没有按ticker、query或Fins repository revision使旧negative observation失效的规则；新的accepted
  download结果只会再追加一条evidence。旧`not_found`会一直保留到recent-window预算淘汰或被后续compaction覆盖，代码不会
  因download成功自动删除、改写或标记它为stale/superseded。
- `dayu.fins.tools.read_runtime.FinsReadRuntime`明确不依赖processed产物，`list_documents`直接从source repository的filing/material
  published documents构造结果。因此本次状态变化链路在download accepted后可以直接重新discovery/read，没有预处理环节；
  不应插入`start_fins_preprocess`或独立`preprocess/process`命令改变被测前置条件。
- duplicate governance只在当前Attempt内治理重复调用；后续Run重新调用`list_documents(MSFT)`会被当作新的工具请求，不会因
  上一轮同参数调用而被阻断或自动复用。当前Host也不会强制发起该刷新；模型是否根据新下载证据重新查询，取决于实际
  runner input与模型/tool-selection行为。
- `docs/host/design.md`和handbook已有temporal update/conflict与“需要刷新时重新调用”的目标，但没有证据证明上述具体链路。
  该事实只支持登记G07；在真实运行并由用户裁决前，不新增“应如何刷新”的accepted oracle，也不登记实现修改项。

## 修改项

### F01：彻底移除 prompt/interactive `--config`

- help、parser、typed args consumption 和文档中都不存在该参数。
- prompt/interactive 只通过 workspace root 解析 workspace config 或 package fallback。
- 不为 removed `--config` 创建 accepted scenario；当前 legacy prompt config scenarios/claims 在正式 registry 下一版本中移除，
  不能保留为兼容路径或 unknown-option oracle。

### F02：彻底移除 interactive `--ticker`

- interactive help、parser、command implementation/context-slot assembly 中都不存在 `--ticker`。
- 不为 removed `interactive --ticker` 创建 accepted scenario。
- prompt 是否保留 `--ticker` 不由本项改变。

### F03：统一 prompt/interactive label alias owner

- 同一 `<workspace, label>` 解析到同一个 durable conversation/Session slot，不再使用互不相通的
  `cli.prompt.*` / `cli.interactive.*` namespace。
- 无 label 的 prompt 保持 fresh one-shot；无 label 的 interactive 每次 invocation 创建 fresh Session。
- 修改后真实运行 prompt→interactive、interactive→prompt、同命令跨进程和无 label fresh identity。

### F04：补 prompt label registry gap

- prompt 已有同命令 label continuity，不重跑为“首次覆盖”。
- interactive 处理完成后，补充 prompt→interactive 与 interactive→prompt 的双向 cross-command scenarios，并纠正
  `prompt.P37` 当前过宽的 `cross-command:label-session-reuse` claim。

### F05：Shift+Enter 换行

- 除 Ctrl+J 外，终端能够提供可区分 key sequence 时，Shift+Enter 也必须在 composer 中插入换行而非提交。
- prompt_toolkit 当前把部分 xterm Shift+Enter sequence 映射成普通 ControlM/Enter，因此不能把依赖库默认行为误记为已支持；
  实现和 scenarios 必须记录 exact bytes 与 terminal capability。

### F06：non-TTY whole-stdin batch

- non-TTY 中，整个 stdin 到真实 EOF 是一个 draft；内部换行保留为用户内容，EOF 是唯一提交边界。
- CRLF/CR 规范化为 LF；沿用 TTY 首尾空白规则；空或纯空白不创建 Run并 exit 0。
- 非空 batch 只创建一个 Run；terminal 后结束进程，不进入第二轮 REPL；stdout 不显示 `dayu>` composer prompt。
- 流中的 literal `0x04` 是普通数据；非法 UTF-8 输出稳定、脱敏错误，不得透出 Python codec exception。
- 当前按行创建多个 Run 的行为不冻结。未来多轮 pipe 必须使用显式 framing，不能复用普通换行作为 turn delimiter。

### F07：Escape 在所有 active Run 阶段一致取消，但不退出 interactive

- standalone Escape 在 pre-accept、provider wait、tool loop、closeout 前的所有 active-turn 阶段都表达取消当前 Run。
- Run cancel 完成后返回 composer；Escape 本身不退出进程。
- running input owner 必须区分 standalone Escape 与完整 ESC-prefixed sequence；CSI、Alt 和 bracketed paste 分别进入
  composer 编辑/导航或 draft，不得因首 byte 为 ESC 而触发取消。
- 原报告中的“后续 EOF exit 0”只是 harness 在已恢复 prompt 后结束进程，不是 Escape 的用户行为。

### F08：统一 interactive Ctrl+C lifecycle

- 用户已提交 turn 后，无论 pre-accept、provider wait、tool loop 还是 closeout，第一次 Ctrl+C 都合并为一次 graceful
  cancel intent；若 Run 尚未返回 id，必须跨 acceptance barrier 收口，不能遗留 orphan Run。
- 后续连续 Ctrl+C 表达“取消完成后退出”的意图；不得取消 canonical cancel waiter或强制关闭 Host。
- CLI 等待 Host canonical terminal、attachment/display/key monitor/lock 清理完成后 exit 130；Run/Attempt 不得残留 running。

### F09：Run 中保持 composer/type-ahead

- Run 中未按 Enter 的输入必须保留在可见 composer draft，当前 Run 完成后仍可继续编辑。
- Run 中按 Enter 必须以 QUEUE 提交一个 follow-up，不得静默丢弃或 steer active Run；当前 Run terminal 后按 Host queue
  contract 执行且恰好一次。STEER 只允许由未来显式 UI action 选择，不能根据时序猜测。
- printable、Enter、完整行、Unicode、paste、光标编辑及 active Run 终态 race 均需真实覆盖。

### F10：active RUNNING 在 owner SIGKILL 后未恢复

- I0552 已建立同 label active `RUNNING` Run，SIGKILL owner进程后用 fresh interactive重连；新进程等待180秒，旧
  Run/Attempt仍为`running`，没有positive-orphan recovery或明确`LOST`收口。
- 默认stale threshold为30秒；immediate attach的首次scan早于threshold，当前attachment lifecycle没有在threshold到达后
  重新分类。修复应在positive proof尚未成立时安排同一fresh writer的bounded delayed rescan/reconcile，不能要求用户等待
  后再次手工重启interactive。
- 修复必须落在Host attachment recovery/positive orphan proof owner；不得由CLI重发原prompt、篡改SQLite或把旧Attempt
  takeover来伪造恢复。
- 正确结果是同一Run在proof成立后以`ATTEMPT_LOST -> RUN_RECOVERING -> RUN_STARTED(start_reason=recovery)`创建新
  Attempt/new `execution_id`，最终进入明确terminal；不能无限等待或重复执行多个recovery Attempt。

### F11：同一 compaction operation 出现两个 canonical terminal

- I0543对同一`operation_id`先提交
  `CONTEXT_COMPACTION_FAILED(reason=proactive_operation_invalid_or_exhausted)`，随后又提交
  `CONTEXT_COMPACTION_FAILED(reason=stale_compaction_result)`；同一operation只能有一个canonical terminal。
- late/stale compactor result只能被拒绝或记录为不改变业务状态的diagnostic/audit，不能再追加第二个
  `CONTEXT_COMPACTION_FAILED`，也不能改写已提交的fallback/start outcome。
- 修复必须落在Host compaction operation terminal/CAS owner，不得在projection、Tool Trace、memory或CLI展示层去重掩盖。
- owner-level并发测试必须冻结首个terminal commit与迟到result的顺序，断言EventLog精确一个terminal、Run只启动一次、
  fallback/accepted outcome不被迟到结果改变。

### F12：pre-start governance 缺少 per-Session single-flight

- 正常promotion wake与periodic owned-session reconciliation只是同一Session需要重新检查durable state的两个signal source，
  不得成为两个可并发执行的pre-start governance owner。
- 同一live RW attachment下，每个Session任一时刻最多一个pre-start governance invocation；后续wake/reconcile必须coalesce，
  in-flight结束后按durable truth决定是否需要再检查。
- 对已提交`CONTEXT_COMPACTION_REQUESTED`且live owner仍在执行的operation，periodic reconciliation不得把它当作crash resume、
  不得重建attempt schedule、不得消耗attempt budget或提交failed/fallback。只有owner停止/crash后的fresh RW attachment才按
  design truth恢复同一durable operation。
- 修复必须同时更新`docs/host/design.md`，明确single-flight owner、signal coalescing、live in-flight与fresh-owner recovery
  边界；不得把`SessionWorkLease`这个生命周期计数器隐式解释为互斥锁，也不得简单删除periodic reconciliation破坏跨opener
  queued/accepted liveness。
- 测试必须用真实async barrier冻结compactor await，令periodic tick和重复wake到达，证明只有一次operation execution；另覆盖
  in-flight完成后coalesced signal重新读取并no-op，以及owner crash后fresh attachment恢复同一operation。

### F13：compactor成功response缺少可审计的实际provider identity

- 当前Service assembly只证明ordinary default与compactor配置的`provider`、provider model、endpoint和credential ref属于
  同一模型家族；compactor proposal manifest只证明真实runner input在调用前被准备和记录。这两者都不能单独证明某次
  compactor成功response实际来自哪个provider/model调用。
- 根因在Engine成功outcome边界：Runner iteration已经观察到可选`provider_request_id`和client correlation identity，
  但`FinalAnswerData`与`EngineRunOutcomeFinalAnswer`没有保留这些字段；`LLMContextCompactor`消费该降维outcome后，Host无法把
  实际response identity与同一compaction operation/attempt/proposal manifest/accepted compact outcome做durable绑定。
- 修复必须在Engine成功terminal/outcome owner保留同源调用identity，并由Host compactor durable projection机械消费；不得在
  CLI、Tool Trace analyzer或报告层根据workspace配置重新推断，也不得把本地run id伪装成vendor request id。
- durable/public evidence至少要把安全的effective provider/model identity、始终可用的client correlation identity，以及
  provider确实返回时的`provider_request_id`绑定到同一compactor operation、attempt、proposal manifest和output outcome。
  endpoint只保存按既有脱敏contract允许的identity，credential只保存ref，禁止secret/header明文。
- `provider_request_id`允许provider不提供，因此不能成为唯一成功判据；缺失时必须保留明确的unavailable状态，并仍用
  effective identity + client correlation + actual output linkage证明执行链。owner-level测试覆盖request id present/absent、
  success/failure、repair attempt和多attempt，防止identity串到ordinary Run或相邻compactor attempt。
- F13修复并重跑真实成功compaction前，`##29`保持public-observability/evidence gap，不能裁决为“实际使用相同provider”或
  “实际使用不同provider”。

## 覆盖缺口

### G01：queued Run 退出/重连恢复

- 在 active Run 期间通过 Enter 创建真实 queued Run，随后退出当前 interactive。
- 用同 label 重连，验证既有 queued Run 由 fresh READ_WRITE attachment 自动 promotion/执行、只执行一次、并保留
  原 run id/user input，以及最终 terminal/memory/cursor。
- 若没有自动执行，即为 conformance finding，不再交用户重新裁决；不得由 harness 重发文本冒充自动恢复。

### G02：RUNNING 的正常关闭/crash/SIGKILL恢复矩阵

- I0552 只证明 SIGKILL 当前失败；还必须分别构造正常 opener/process close（没有用户 cancel facts）、可诊断 crash 与
  SIGKILL，并用同 label fresh writer重连。
- 每行记录 owner host-instance liveness、positive orphan proof、旧/new Attempt identity、execution id、EventLog顺序、provider
  request、terminal、memory与是否重复执行；proof未成立前等待是正确安全行为，但proof成立后不得无限停留`running`。

### G03：durable accepted steer 的恢复矩阵

- 分别在 steer input durable accepted后的旧 Attempt收口前、新 Attempt启动前和新 Attempt running时构造正常关闭、crash、
  SIGKILL，再用同 label重连。
- 断言同一Run按最新accepted steer candidate重建、新Attempt/new execution id执行且恰好一次，旧Attempt不得takeover。
- 当前 interactive 没有已冻结的显式 STEER gesture；在该UI action建立前，只能把本项标记为CLI surface blocked，或使用
  public Host setup建立durable precondition后观察真实interactive recovery，不得发明隐藏按键或写private SQLite。

### G04：accepted cancel 与 terminal cancelled 不复活

- 对 RUNNING、QUEUED 和 durable accepted steer，分别在 `CANCEL_REQUESTED`/`CANCELLING` 与 terminal `CANCELLED` 后构造正常
  关闭、crash、SIGKILL并用同 label重连。
- accepted cancel只允许watchdog/closeout推进到`CANCELLED`；terminal cancelled保持幂等，不创建recovery Attempt、不发
  provider请求、不再次执行queued/steer input，也不重复投影旧terminal。
- I0508只观察到`waiting -> CANCEL_REQUESTED -> RUN_CANCELLED`相邻提交，没有捕获fresh writer attach到durable
  `CANCELLING`，因此不能用于关闭本项。

### G05：去除 interactive `--ticker` 后重跑真实财报/memory/Tool Trace

- I0523当前argv包含已裁决为不存在的`interactive --ticker AAPL`，因此业务观察可支持oracle，但原scenario不能accepted。
- F02修复后，由用户prompt明确提供AAPL，在同一Session重跑真实
  `list_documents -> get_financial_statement(partial) -> get_document_sections/search_document -> read_section`，再追问数值、
  期间、单位和来源。
- 同时核对final answer、Tool Trace request/response、accepted tool EventLog、memory、runner input与Host SQLite；不得用旧
  I0523或CLI ticker context填补新运行的输入来源。
- `dayu-cli download`与`dayu-cli preprocess/process`的UI、生成物和退出语义属于各自command campaign，不在interactive
  oracle中裁决；本项只要求真实财报corpus已存在且interactive读取成功。

### G06：真实成功 compaction 与 compact 后连续性

- F11/F12/F13修复后，在同一真实interactive REPL/Session中使用真实用户输入、真实provider与真实财报工具结果累积上下文，
  通过production config loader/Service assembly生效的CI-owned较低soft threshold触发compaction；不得注入memory、伪造
  assistant/tool result、直接写EventLog/SQLite或调用内部compactor API。
- 必须观察并同源核对
  `CONTEXT_COMPACTION_REQUESTED -> compactor_proposal manifest -> CONTEXT_COMPACTED`，且同一operation精确一个terminal；
  `CONTEXT_COMPACTION_FAILED`、deterministic recent-window fallback或`stale_compaction_result`不能替代成功证据。
- 记录compactor真实provider/model/endpoint/credential ref、输入与输出、accepted attempt number、proposal manifest ref/digest、
  compact artifact ref/digest/可读内容、source boundary、quality result和budget-after-compact；不能只从workspace config反推实际
  provider调用。
- 核对Conversation Memory的latest compaction ref/snapshot/projection、post-compact RunInputBuilder material与普通dispatch
  manifest均消费同一accepted compact truth；不得出现“EventLog成功但artifact/memory/runner input未生效”。
- compact后至少提交两个真实follow-up：一个不调用工具复述compact前AAPL财报事实的数值、单位、期间和来源；另一个改变
  分析口径并根据需要调用真实财报工具取得新证据。两轮都要核对屏幕、final answer、Tool Trace、EventLog、memory与SQLite。
- 另保留真实compactor semantic reject/repair与最终fallback场景作为独立failure coverage；不得用该failure scenario关闭本G06。

### G07：accepted `not_found` 后下载导致的current-state刷新

- 使用起初没有MSFT文档的独立workspace，在同一真实interactive REPL/Session中先由用户询问MSFT财报并取得accepted
  `list_documents(MSFT)=not_found`；保存屏幕、request/response、`TOOL_RESULT_ACCEPTED`、memory、runner input、Tool Trace、
  EventLog和SQLite。
- 下一轮用户原样输入“下载微软财报”，观察模型真实调用`start_fins_download`并等待terminal accepted result；记录Fins source
  repository与文件生成物前后变化。该链路没有预处理环节，不调用`start_fins_preprocess`，也不运行独立
  `dayu-cli preprocess/process`命令。
- 下载完成后的下一轮提出一个必须读取当前MSFT财报才能回答的问题；记录模型是否重新调用`list_documents(MSFT)`、是否继续
  调用实际read tool、旧`not_found`和新download evidence如何同时进入memory/runner input，以及最终回答是否由新入库财报
  grounding。
- 当前没有真实执行证据，也没有用户对状态变化后刷新策略的裁决。本项只登记为coverage/adjudication gap；后续不得用
  ##27已接受的“记得上一轮not_found”、已有AAPL corpus、手工预处理、harness补发工具指令或直接检查文件存在来关闭。

## Deferred issue（interactive 完成后创建，不在本次 CI 实现）

后续单独建立 Session CLI/TUI issue，至少追踪：

- `dayu-cli interactive resume <label-or-session-id>`；
- interactive 内 `/clear`；
- interactive 内 `/new`；
- interactive 内 `/resume`。

该 issue 需要先明确 label/session-id selector、当前 attachment 关闭、新/fresh Session、queued/active Run 处理和 composer
draft 所有权；不得在本次 oracle calibration 中顺带实现。

## 本批裁决状态

行为项 1–28、30 已完成裁决；行为项 29 等待F13修复后的真实compactor output identity证据。F01–F13 是已冻结目标与当前
实现/registry 的明确偏差；G01–G07 是必须补跑的coverage gap，其中恢复结果已经由用户决定与Host设计真源冻结，不能因
当前未跑就重新开放正确性裁决。##30以public-contract不可达证明关闭，不新增动态伪造场景、修改项或coverage gap。

## Host design 核实（对应 `##22`）

`docs/host/design.md` 第 1 节明确冻结：同一 Session 只有一个 READ_WRITE attachment，其余为生命周期内不可变的
READ_ONLY observer。`Host.attach_session(...)` 的 public contract 也声明跨 opener 由 per-Session mutex 决定模式，所有
mutation 必须拥有 active READ_WRITE attachment。因此本轮观察到：

- B 可以订阅并显示 A 的最终事件；
- 只有 A 的 submit 创建 Run；
- B submit 被 `Session attachment is read-only` 拒绝；

这些 durable/permission 行为与 Host 设计一致。CLI UX 是否应在 B 的 composer 前明确显示只读状态、禁用提交而不是用户
按 Enter 后 exit 1，是后续 UI 裁决，不应通过放宽 Host single-writer contract 解决。
