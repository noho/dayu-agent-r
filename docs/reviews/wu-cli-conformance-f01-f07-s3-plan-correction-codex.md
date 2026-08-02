# WU-CLI-CONFORMANCE-F01-F07 S3/F03 Plan Correction（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S3 / F03`
- Gate：`plan correction after blocked implementation -> adjudicated fix`
- Entry HEAD：`16c6ddc8`
- 分支：`codex/interactive-oracle`
- 执行日期：2026-08-02（Asia/Shanghai）
- 用户裁决：已明确批准 S3 最小 plan correction；不重新打开 F03 产品语义或 frozen oracle。
- 状态：`FIX COMPLETE — controller accepted actions 已落实，等待两路 plan re-review`
- Artifact path：`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-codex.md`
- Controller adjudication：`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-controller-adjudication.md`

## Scope 与禁止动作

本 correction gate（含本次同gate follow-up）只完成以下三项：

1. 更新 `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` 的 S3 strategy；
2. 新增并按controller裁决修订本 durable plan-correction artifact；
3. 新增 `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-fix-codex.md` 记录两路finding的最终状态。

本 gate 没有修改 production、test、README、frozen oracle/scenario、设计真源或 repo 外 immutable evidence；没有 stage、commit、push 或 PR 操作。进入 gate 时唯一 dirty path 是用户要求保留的未跟踪 blocked artifact：

```text
?? docs/reviews/wu-cli-conformance-f01-f07-s3-implementation-codex.md
```

该文件未被覆盖、删除、移动或改写。本次follow-up进入时还存在controller adjudication与两路plan-review artifact；它们均保持只读。

## 第一性原理与 owner 裁决

修订动机成立，且严重性评估准确。冻结 F03 要求 active Run 中只有 standalone Escape 表达取消，完整 CSI、Home/Delete、Alt、SS3 与 bracketed paste 不得因 ESC prefix 误取消。当前 resolved dependency 的 public parser直接证明：Alt+X不是一个带“Alt”标志的单callback，而是同一public `feed` resolution中的Escape callback后接X callback。若在Escape callback现场立即投递`CANCEL_RUN`，Alt必然误取消。

root cause owner 是 CLI reader thread 内的 **public parser callback batch 到 typed local intent 的投影边界**：

- `Vt100Parser`拥有终端sequence解析；Dayu不得写第二套raw-byte parser。
- CLI `run_keys`拥有把完整public parser resolution投影为`RunningKeyAction`的语义。
- `_ActiveTurnCloseout`只消费typed cancel intent，不解析bytes或`KeyPress`。
- Host继续唯一拥有Run acceptance、graceful cancel和canonical terminal；CLI不得伪造`CANCELLED`。

因此最小正确修复不是改Host、延长cancel timeout或增加下游fallback，而是在同一个reader thread、同一个public parser resolution boundary暂存provisional Escape，待该batch完整后再分类。

## 直接证据

### Resolved dependency

- Python：3.11
- `prompt_toolkit==3.0.52`
- public API：`Vt100Parser(callback)`、`feed(data: str)`、`flush()`
- installed source：`.venv/lib/python3.11/site-packages/prompt_toolkit/input/vt100_parser.py`
- public sequence map：`.venv/lib/python3.11/site-packages/prompt_toolkit/input/ansi_escape_sequences.py`
- exact upstream tests：`https://github.com/prompt-toolkit/python-prompt-toolkit/blob/3.0.52/tests/test_inputstream.py`

源码与上游测试共同证明：

- `feed("\x1b")`保持prefix pending，不产生callback；deadline后`flush()`才产生单一`KeyPress(Keys.Escape, "\x1b")`。
- `feed("\x1bhello")`产生Escape后接普通字符；上游`test_escape`显式断言该行为。
- `feed("\x1b")`后再`feed("[D")`产生单一Left；中间`flush()`则先固化Escape，再把`[D`解析为普通字符；对应上游`test_flush_1`/`test_flush_2`。
- 已知meta arrow等映射会产生tuple callbacks，Escape携带完整sequence data，后续key data为空；对应上游`test_special_double_keys`。
- bracketed paste由同一个parser维护paste mode并在end marker到达后产生单一`Keys.BracketedPaste` callback。

本 gate 复验的关键 resolution batches：

| 输入与boundary | callback batch | S3 typed action |
|---|---|---|
| `feed(ESC)` | `[]` | 无 |
| deadline `flush()` | `[Escape(data=ESC)]` | `CANCEL_RUN` 一次 |
| `feed(ESC + x)` | `[Escape(data=ESC), x]` | 无 cancel |
| 跨chunk `feed(ESC)` / `feed(x)` | 第二个feed为`[Escape(data=ESC), x]` | 无 cancel |
| 跨chunk `ESC [ A` | 最终feed为`[Up(data=ESC[A)]` | 无 cancel |
| 跨chunk `ESC O H` | 最终feed为`[Home(data=ESCOH)]` | 无 cancel |
| `ESC [ 3 ; 3 ~` | `[Escape(data=完整sequence), Delete(data="")]` | 无 cancel |
| 跨chunk bracketed paste | end所在feed为`[BracketedPaste(data=payload)]` | 无 cancel |
| `feed(ESC + x + Ctrl+T)` | `[Escape, x, ControlT]` | 只`TOGGLE_ACTIVITY`一次 |
| `feed(ESC + Ctrl+T)` | `[Escape, ControlT]` | 只`TOGGLE_ACTIVITY`一次 |
| paste end后同batch接Ctrl+T | `[BracketedPaste, ControlT]` | paste no-op；只`TOGGLE_ACTIVITY`一次 |

## Corrected S3 strategy

### 单一 parser / decoder 与 resolution batch

`TtyRunningKeyMonitor._read_loop()`只在reader thread内构造：

- 一个public `Vt100Parser`；
- 一个标准库UTF-8 incremental decoder；
- 一个只供该线程使用的`list[KeyPress]` callback collector。

只允许public imports：`prompt_toolkit.input.vt100_parser.Vt100Parser`、`prompt_toolkit.key_binding.KeyPress`和`prompt_toolkit.keys.Keys`。禁止第二套raw-byte parser、private parser API、`KeyProcessor`和跨线程parser调用。

一个同步public `parser.feed(decoded_text)`或`parser.flush()`调用就是一个resolution batch：调用前collector为空；callback只append；调用返回后冻结完整batch、清空collector，再由模块级typed helper分类。callback现场不得向event loop投递action。

### Provisional Escape 分类

batch分类规则固定为：

1. 每个Escape callback先视为provisional，不能现场cancel。
2. 同一resolution batch出现后续callback时，它证明前一个provisional Escape是Alt/meta/invalid-prefix continuation的一部分；只抑制该Escape。
3. 后续callback继续独立分类：`Keys.ControlT`仍产生一次`TOGGLE_ACTIVITY`；普通字符、CSI/navigation、Home/Delete、SS3、paste callback不产生running action。
4. `CANCEL_RUN`只允许来自ambiguity deadline触发的flush batch，且batch长度精确为1，唯一member必须同时满足`key is Keys.Escape`与`data == "\x1b"`；只检查其中一个字段不合格，known-meta中携带完整sequence data的Escape callback不得取消。
5. feed batch永不直接把Escape投影为cancel；flush batch含任意continuation时也不cancel。
6. `Keys.BracketedPaste`自身始终是no-op；同一batch中paste callback之后的`Keys.ControlT`仍独立投影为一次`TOGGLE_ACTIVITY`。

因此Dayu仍完全委托public parser决定sequence边界，只在parser公开callback投影层解决其Alt callback shape，不读取或重建raw sequence。

### Ambiguity deadline

ambiguity常量固定为`_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1`。raw bytes只用于驱动唯一incremental decoder，并在chunk中出现ESC时设置/刷新monotonic deadline；不得从raw bytes识别具体sequence。deadline已armed时，每个后续非空chunk都将它刷新为“本次feed时刻 + 0.1s”；chunk read size只是非语义性能参数，不得改变resolution batch。

- deadline采用 **conservative armed until one flush**：含ESC后保持armed，不能从callback batch为空、非空或具体callback推断public parser private pending state，也不能在feed后提前清除。
- fd readable与deadline同轮成立：先read/decode/feed并刷新deadline；只有本轮无新字节才flush。`select`等待取poll interval与deadline剩余时间的较小值。
- deadline flush：形成独立batch、分类恰好一次；该次`flush()`同步返回后无条件清除deadline。
- resolved完整sequence后的空flush是预期no-op，不产生cancel、不重新armed、不循环flush；同一feed即使已有callback但尾随ESC，deadline也仍保持armed，0.1s后该次flush必须解析尾随standalone Escape。
- close/EOF：不以teardown flush合成用户intent；pending ambiguity被丢弃。

### 不可区分事实与语义边界

终端层无法区分以下两种操作：

```text
ESC 后在 ambiguity window 内输入普通字符 X
Alt+X
```

二者产生相同bytes与相同`Escape, X` public callback batch。S3遵守已冻结“Alt不得误取消”语义，因此该batch不cancel。此记录只承认terminal ambiguity，不新增“ESC+普通字符”的产品功能、oracle、scenario或兼容承诺；本 gate不修改任何frozen truth。

### Typed key 与 Ctrl+C owner

`RunningKeyAction`保留为`run_keys`唯一typed key contract，仅包含既有`CANCEL_RUN`与`TOGGLE_ACTIVITY`投影；prompt/interactive driver直接消费它，不新增`_PromptControlKey`或任何等价enum。Ctrl+C不属于VT input语义，**只由SIGINT monitor产生、计数和区分first/second signal**；public parser callback classifier不得识别、投影或合成Ctrl+C，避免形成第二个signal owner。

### `_ActiveTurnCloseout` method contract

共享coordinator只拥有acceptance、cancel intent、exactly-once Host cancel task与canonical terminal observation。构造时只冻结turn identity以及完成相应prompt/interactive Host cancel request所需的直接typed输入；submit task由outer driver拥有。它不得持有composer、display、cursor、attachment、key/signal monitor、generation、queued draft或history。

| method | coordinator-owned effect | 明确禁止的副作用 |
|---|---|---|
| `publish_accepted(run_id: str) -> None` | 发布唯一exact Run id；同id幂等、冲突id fail fast；cancel intent已存在时只唤醒唯一cancel path | 不render、不切composer phase、不关闭资源 |
| `request_cancel(*, reason: str, exit_after: bool) -> _LocalCancelIntent` | 首次调用冻结reason并将`NONE -> CANCEL_REQUESTED`，确保至多一个acceptance/cancel waiter；只有SIGINT monitor观察到的第二次Ctrl+C可单调升级为`EXIT_AFTER_CANCEL`，其余重复调用幂等 | 不本地取消submit、不OS强杀、不立即返回130 |
| `wait_accepted_then_cancel() -> EntrypointRunTerminalResult` | 等exact accepted id后创建恰好一个Host graceful cancel task并等待canonical terminal；terminal先成立则保留真实结果、不得发迟到cancel | 不finish thinking/runtime display，不render cancel/terminal |
| `observe_terminal(result: EntrypointRunTerminalResult) -> None` | 记录本turn唯一Host canonical terminal；同结果幂等、冲突terminal fail fast并唤醒waiter | 不映射exit code、不advance cursor |
| `wait_closeout() -> EntrypointRunTerminalResult` | 等acceptance/cancel task与canonical terminal协调完成后返回唯一terminal truth | **不等待或执行** composer/display/cursor/attachment/key/signal cleanup |

outer-driver side-effect contract与时序固定为：

- prompt outer driver消费`RunningKeyAction`，并独立消费SIGINT monitor；它拥有thinking/runtime display finish、cancel-requested/terminal render、prompt key/SIGINT monitor teardown与既有exit mapping。`wait_closeout()`返回后仍需完成这些副作用，最后才返回cancel result/130。
- interactive outer driver拥有`InteractiveComposerPhase.CANCELLING/RUNNING/IDLE`切换、thinking/runtime display finish、cancel-requested/local-exit/terminal render、`advance_cli_terminal_cursor`、queued promotion，以及composer/key/signal/attachment teardown；只有canonical terminal已观察且这些cleanup完成后才决定130。
- canonical terminal observation与outer cleanup是两个明确的时序点。不得把composer/display/cursor/attachment引用塞进coordinator，也不得让`wait_closeout()`伪装成全invocation cleanup barrier。

统一时序为：local `RunningKeyAction.CANCEL_RUN`或SIGINT monitor的first Ctrl+C登记`request_cancel(..., exit_after=False)`；pre-accept时submit继续跨barrier；accepted后恰好一次Host graceful cancel。只有SIGINT monitor的second Ctrl+C升级`exit_after=True`，但继续等待canonical terminal。outer driver在`wait_closeout()`返回后完成各自UI/resource cleanup，最后才根据intent与既有terminal mapping决定130。

## 原计划保持不变的语义

本 correction只替换parser callback分类前提，以下内容保持原计划：

- standalone Escape与第一次Ctrl+C都可在pre-accept阶段登记cancel intent，并跨acceptance barrier等待exact accepted Run id；
- submit task不被本地取消来冒充Host cancel；accepted后Host cancel恰好一次；
- 第二次Ctrl+C只登记`EXIT_AFTER_CANCEL`，不得取消canonical cancel waiter或触发OS强杀；
- provider wait、tool execution与closeout阶段共用同一个graceful cancel owner；
- Host canonical terminal先于CLI推断；非`CANCELLED`真实terminal不得被覆盖；
- exit 130只能发生在Host terminal observation以及watcher、attachment、renderer、composer/key monitor、runtime、日志和锁全部cleanup完成后；
- Escape不累计double-Ctrl+C的exit intent；Ctrl+T不改变Run、tool或terminal语义。
- Ctrl+C继续只由SIGINT monitor拥有；parser correction不改变first/second Ctrl+C计数或Host closeout语义。

## Owner-level test matrix

| owner surface | 必测输入/竞态 | 精确断言 |
|---|---|---|
| public seam | `feed(ESC)` + `flush`；Alt+X同/跨chunk | callback batch与3.0.52 public evidence一致；seam变化fail closed |
| batch classifier | deadline flush batch长度1，member为`Escape(key=Escape, data=ESC)` | key与data双重命中时cancel恰好一次；错误key/错误data均为0 |
| batch classifier | feed `[Escape, x]`、known meta tuple | cancel为0 |
| batch classifier | `[Escape, CtrlT]`、`[Escape, x, CtrlT]` | cancel为0，toggle恰好一次 |
| decoder/parser | Alt+Unicode在每个UTF-8 byte boundary切分 | 一个decoder；无decode丢失；cancel为0 |
| sequence parser | CSI arrows、Home/Delete、SS3同/跨chunk | cancel为0 |
| paste parser | start/content/end跨chunk；payload内Ctrl+T；`[BracketedPaste, ControlT]`同batch | paste callback本身no-op；后续独立Ctrl+T只toggle一次 |
| deadline constant | 可控monotonic clock/select seam推进`0.099s -> 0.1s` | 到期前不flush；0.1s到期恰好一次flush；禁止wall-clock sleep |
| conservative deadline | complete sequence产生非空callback；同一feed有callback且尾随ESC | 不从callback推断pending；前者到期一次空flush后清除，后者到期flush并cancel一次 |
| deadline race | readable与deadline同时ready | continuation先feed并刷新0.1s；不抢先cancel |
| close race | pending ESC与close同时发生 | close优先；零late action；termios恢复 |
| ownership | parser create/feed/flush/callback、decoder、collector | 全部在同一reader thread；各精确一个instance |
| queue boundary | 任意batch | provisional Escape不越界；action只经`call_soon_threadsafe` |
| acceptance barrier | pre-accept Escape/first Ctrl+C | submit不被local cancel；accepted id后Host cancel一次；等canonical terminal |
| double Ctrl+C | pre-accept/provider/tool/closeout | 一个Run、一个cancel owner、一个terminal；cleanup后130 |
| Ctrl+C owner | VT control byte与SIGINT monitor first/second signal | VT classifier不产生Ctrl+C intent；只有SIGINT monitor驱动状态迁移 |
| closeout methods | publish/cancel/terminal重复与冲突；terminal-before-cancel | idempotency/fail-fast、reason冻结、exactly-once Host cancel、真实terminal保留 |
| outer side effects | prompt与interactive canonical terminal -> cleanup -> exit | coordinator不调用UI/resource接口；outer完成display/composer/cursor/attachment/key/signal teardown后才决定130 |
| terminal/key race | 两种event-loop调度顺序 | typed intents先登记；terminal truth不覆盖；下一turn无stale intent |

owner tests还必须记录“ESC+普通字符”和Alt+该字符在ambiguity window内不可区分且均不cancel，但不得把该测试注册为新的frozen product scenario。

## 竞态与不变量

1. 任意时刻最多一个parser、一个decoder、一个collector和一个未完成的public parser调用。
2. collector只在reader thread读写，且每个public call前后为空；callback不会异步越过batch boundary。
3. provisional Escape永不直接进入asyncio queue；只有deadline flush batch长度为1且唯一member的`key is Keys.Escape`与`data == "\x1b"`同时成立才产生cancel。
4. suppress Escape只影响该Escape，不能吞掉同batch后续Ctrl+T或把普通字符重分类为running action；`BracketedPaste` no-op也不能吞掉同batch后续Ctrl+T。
5. 0.1s deadline一旦armed就保持到一次flush返回；不能从callback batch推断private pending。fd readable优先feed并refresh，close优先于flush；resolved sequence的一次空flush是预期no-op，清除后不得重复flush/cancel。
6. parser完整sequence分类是唯一真源；raw ESC observation只拥有deadline，不拥有sequence semantic；chunk size不属于语义contract。
7. pre-accept cancel intent绑定当前turn；accepted id冲突fail fast；重复cancel/第三次Ctrl+C幂等。
8. Host terminal first-committer-wins；CLI cleanup与task cancellation不得创造第二terminal或synthetic `CANCELLED`。
9. `RunningKeyAction`是唯一typed key contract；Ctrl+C只由SIGINT monitor拥有，classifier与coordinator都不能成为第二signal source。
10. `_ActiveTurnCloseout.wait_closeout()`只承诺Host closeout协调完成；prompt/interactive outer driver继续唯一拥有composer/display/cursor/attachment/key/signal副作用与cleanup后exit决策。

## Acceptance barrier

S3 implementation必须在以下全部通过后才可进入code review：

1. public seam、batch classifier、chunk/decode、固定0.1s conservative deadline和thread ownership矩阵全部通过；
2. standalone Escape恰好一次cancel，Alt/CSI/SS3/Home/Delete/bracketed paste cancel count全部为0；
3. Ctrl+T在Escape混合batch与`[BracketedPaste, ControlT]`中仍独立toggle，paste payload中的Ctrl+T不误触发；
4. `RunningKeyAction`保持唯一typed key contract，Ctrl+C只由SIGINT monitor驱动；
5. `_ActiveTurnCloseout` method contract与prompt/interactive outer side-effect timing tests通过，coordinator未取得composer/display/cursor/attachment/key/signal cleanup ownership；
6. pre-accept Escape/Ctrl+C、四阶段double Ctrl+C、terminal/key同batch tests全部通过；
7. Host cancel、canonical terminal和outer cleanup次数满足原计划不变量；
8. focused pytest、touched-scope pyright、单文件coverage `>=80%`、`git diff --check`通过；
9. active S3 diff中没有第二parser、private prompt_toolkit import、`KeyProcessor`、第二typed key enum、synthetic terminal、frozen registry/scenario/oracle修改。

若resolved public parser不再提供同步batch或上述feed/flush形状，或者实现必须依赖private state、第二套parser、KeyProcessor、依赖pin、Host语义修改或下游补偿，立即停止S3并回plan gate。

## Validation

本 gate 已执行只读验证：

- 完整读取Gateflow、accepted plan、blocked S3 implementation artifact；
- 完整读取F03 accepted oracle predicates、post-fix scenario requirements及相关accepted scenario records；
- 读取`docs/cli_ci.md`、Host Run/Cancel/accepted-prompt recovery与Engine cancellation commit boundary；
- 完整读取installed 3.0.52 `vt100_parser.py`、`ansi_escape_sequences.py`及exact upstream `test_inputstream.py`相关全部tests；
- 用public API复验standalone Escape、Alt ASCII/Unicode、CSI、SS3、Home/Delete、known meta、bracketed paste及mixed Ctrl+T callback batches；
- 完整读取两路plan review与controller逐项裁决，并将MiMo-001..005、DS-F1..F6全部映射到finding fix artifact；
- frozen registry SHA-256仍为：
  - `docs/cli_ci_oracles.json`：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
  - `docs/cli_ci_scenarios.json`：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- blocked implementation artifact保持未跟踪、未改写；当前SHA-256为`7215691f29d2a6cf3a1a8e94bb62b8508c8c07d61ce7718a5bd1f32d64c8670a`。

本 gate 没有代码修改，因此不运行implementation pytest、coverage或pyright；`git diff --check`、三份目标artifact trailing-whitespace检查、required-clause检索、finding 5+6完整性检查、frozen hash与dirty-scope校验通过。

## Docs decision

没有production、test、public CLI、分层关系或用户工作流变更，不触发README更新。变更只限主plan、本artifact与finding fix artifact；frozen oracle/scenario/design truth保持只读。

## Residual risks 与 uncovered areas

- `fixed in current slice`：blocked artifact记录的Alt callback shape与旧plan即时Escape分类冲突，已由feed/flush resolution batch strategy消除设计blocker。
- `covered in S3 owner tests`：ambiguity window内ESC+普通字符与Alt同字符物理不可区分；冻结语义选择两者均不cancel，不新增oracle/scenario。
- `covered by later approved slice`：continuation在固定0.1s边界后才到达是任意有限timeout都存在的residual；S3覆盖正常/代表性跨chunk，S8覆盖真实PTY timing，不扩张为网络terminal protocol。
- `covered by later approved slice`：真实PTY下的chunk timing、fd/deadline边界、terminal restoration和provider/tool/closeout信号竞态，由S3 owner tests及已批准S8 real evidence覆盖。
- `covered by later approved slice`：项目声明`prompt_toolkit>=3.0.0`而当前resolved版本为3.0.52；S3 public seam contract test负责在实际resolved dependency行为变化时fail closed，不通过private API或兼容分支猜测。
- `requiring new issue or explicit user decision`：无。ESC+普通字符与Alt字符的不可区分性是terminal物理事实，已按用户批准的最小correction记录，不扩张产品语义。

没有unclassified residual risk。

## Completion 与 next entry point

Controller required fix已完成。下一合法入口是裁决要求的 **两路 plan re-review**；只有re-review通过且controller确认后，才恢复 **S3/F03 implementation**。implementation只能按更新后的§5及本artifact实施；不得跳过gate，不得把本次plan-only diff stage、commit或push。
