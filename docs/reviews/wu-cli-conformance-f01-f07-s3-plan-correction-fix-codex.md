# WU-CLI-CONFORMANCE-F01-F07 S3 Plan Correction Fix（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S3 / F03`
- Gate：`plan review fix`
- Entry HEAD：`16c6ddc8`
- 分支：`codex/interactive-oracle`
- 执行日期：2026-08-02（Asia/Shanghai）
- Controller adjudication：`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-controller-adjudication.md`
- 修订目标：
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-codex.md`
- 状态：`FIX COMPLETE — 等待两路 plan re-review`

## Scope 与 owner 结论

本次只修订计划artifact，不修改production、tests、README、frozen oracle/scenario或design truth，不stage、commit、push。用户要求保留的blocked implementation artifact `docs/reviews/wu-cli-conformance-f01-f07-s3-implementation-codex.md`保持原样。

两路review与controller裁决没有推翻核心方案：root cause仍位于reader thread内public `Vt100Parser` callback batch到`RunningKeyAction`的投影边界。修订继续保持一个public parser、一个incremental decoder，不引入第二套raw-byte parser、private API或`KeyProcessor`；Host仍唯一拥有Run acceptance、graceful cancel与canonical terminal。

## Finding 最终状态

最终状态使用Gateflow允许值；`证据失效`表示controller基于直接证据拒绝该functional finding，不表示遗漏修复。

| 来源 | 原finding | Controller裁决 | 最终状态 | 落实结果 |
|---|---|---|---|---|
| MiMo-001 | Ambiguity常量未指定 | `accepted` | `已修复` | 两份计划固定`_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1`；owner test用可控monotonic clock/`select` seam，不使用wall-clock sleep。 |
| MiMo-002 | Chunk read size未指定 | `rejected-with-reason` | `证据失效` | 不硬编码非语义read size；明确correctness由incremental decoder与public parser resolution boundary拥有，代表性分块由owner matrix覆盖。 |
| MiMo-003 | Ctrl+C未显式排除classifier | `accepted`（clarity） | `已修复` | 明确Ctrl+C只由SIGINT monitor产生、计数和区分first/second signal；VT classifier不得识别或合成Ctrl+C。 |
| MiMo-004 | ESC+普通字符与Alt不可区分 | `accepted-as-residual` | `已修复` | 两份计划显式分类为terminal物理限制：0.1s window内相同bytes统一不cancel；S3 owner test与S8 PTY留证，不新增oracle/scenario或产品语义。 |
| MiMo-005 | Deadline后continuation到达 | `accepted-as-residual` | `已修复` | 固定0.1s有限边界；S3覆盖正常/代表性跨chunk，S8覆盖真实PTY timing；不扩张为网络terminal protocol。 |
| DS-F1 | `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS`值未指定 | `accepted` | `已修复` | 与MiMo-001同一action：常量固定0.1s并加入确定性clock/select边界测试。 |
| DS-F2 | 完整sequence后deadline未清除 | `rejected-as-functional-finding; accepted-as-clarity-fix` | `已修复` | 拒绝从callback空/非空推断private pending；改为conservative armed：含ESC后持续armed，新data优先feed/refresh，到期只flush一次并清除；resolved sequence的一次空flush是预期no-op。functional推断部分的证据失效，clarity action已落实。 |
| DS-F3 | `_ActiveTurnCloseout`隐式副作用边界 | `accepted-in-part` | `已修复` | 补齐五个method的state/side-effect contract与prompt/interactive时序；coordinator只拥有acceptance、intent、exactly-once Host cancel task、canonical terminal observation。拒绝部分未纳入：composer/display/cursor/attachment/key/signal cleanup继续由outer driver拥有，cleanup后才决定130。 |
| DS-F4 | Known-meta需要精确data检查 | `accepted`（clarity/test） | `已修复` | standalone Escape要求flush batch长度1且唯一member同时满足`key is Keys.Escape`、`data == "\x1b"`；加入错误key/data反例与known-meta完整sequence data测试。 |
| DS-F5 | `RunningKeyAction`与`_PromptControlKey`重复 | `accepted` | `已修复` | 删除计划中的`_PromptControlKey`；保留现有`RunningKeyAction`作为唯一typed key contract，driver直接消费。 |
| DS-F6 | Paste end与Ctrl+T同batch未显式覆盖 | `accepted` | `已修复` | 明确`Keys.BracketedPaste`自身no-op，`[BracketedPaste, ControlT]`同batch仍只toggle一次，并加入owner-level test。 |

## 修订后的关键 invariants

1. reader thread内精确一个public `Vt100Parser`、一个UTF-8 incremental decoder和一个callback collector；一个`feed`/`flush`同步调用就是一个resolution batch。
2. 0.1s deadline一旦被ESC armed，就保持到一次`flush()`返回；callback batch为空、非空或具体shape都不能作为parser private pending的代理。
3. deadline与readable同轮时先feed并refresh；deadline与close同轮时close优先；一次flush后无条件清deadline，不循环空flush或重复cancel。
4. provisional Escape不越过reader-thread boundary。只有deadline flush batch长度为1且`key`与`data`同时精确匹配standalone Escape时投影`CANCEL_RUN`。
5. batch suppression只抑制对应provisional Escape；后续`ControlT`独立分类。`BracketedPaste` no-op也不能吞掉同batch后续`ControlT`。
6. `RunningKeyAction`是唯一typed key contract；Ctrl+C只由SIGINT monitor拥有。
7. `_ActiveTurnCloseout`不拥有composer/display/cursor/attachment/key/signal cleanup；`wait_closeout()`返回只证明Host closeout协调完成，outer cleanup完成后才能决定130。
8. acceptance barrier、double Ctrl+C、exactly-once Host graceful cancel和canonical terminal优先语义保持原计划不变。

## Acceptance barrier 与 test matrix 增量

- parser/deadline：可控时钟推进`0.099s -> 0.1s`；complete sequence非空batch后仍发生一次no-op flush；同一feed已有callback且尾随ESC时仍在deadline flush出一次cancel。
- classifier：standalone key+data双重正例、错误key/错误data反例、known-meta完整sequence data、`[Escape, ControlT]`、`[Escape, x, ControlT]`。
- paste：跨chunk start/content/end、payload内Ctrl+T，以及同batch`[BracketedPaste, ControlT] -> TOGGLE_ACTIVITY`恰好一次。
- signal ownership：VT control byte不产生Ctrl+C intent；仅SIGINT monitor驱动first/second Ctrl+C状态迁移。
- closeout：逐method覆盖publish冲突、cancel reason冻结、exactly-once cancel task、terminal冲突/terminal-first；用spy证明coordinator不触碰UI/resource接口，并分别记录prompt/interactive的`canonical terminal -> outer cleanup -> exit decision`偏序。

进入implementation前，除原accepted plan barrier外，还必须证明以上增量全部通过，active diff中不存在第二parser、private prompt_toolkit API、`KeyProcessor`、第二typed key enum或frozen truth修改。

## Residual risk disposition

- ESC后普通字符与Alt字符在0.1s内不可区分：`covered in S3 owner tests + S8 real PTY evidence`，不扩张产品语义。
- continuation晚于0.1s：`covered by representative S3 chunk tests + S8 real PTY timing`，不承诺任意延迟transport。
- resolved dependency将来改变public synchronous callback shape：`fail closed at S3 public seam contract test`，不得以private API、依赖pin或兼容分支规避。

没有unclassified residual risk，也没有blocking open question。

## Validation 与 next entry point

已完成以下只读/文档校验：

- `git diff --check`通过，三份目标artifact无trailing whitespace；
- required-clause检索覆盖固定0.1s、conservative armed、SIGINT-only Ctrl+C、`RunningKeyAction`唯一contract、key+data精确条件、paste+Ctrl+T与outer cleanup边界；
- finding表包含MiMo-001..005与DS-F1..F6共11项；
- frozen SHA-256保持不变：oracle为`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`，scenario为`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`；
- blocked implementation artifact仍为未跟踪文件，当前SHA-256为`7215691f29d2a6cf3a1a8e94bb62b8508c8c07d61ce7718a5bd1f32d64c8670a`；
- dirty scope没有production、tests、README、oracle/scenario或design truth路径。

因为没有production/test修改，不运行implementation pytest、coverage或pyright。

下一合法入口是controller要求的两路plan re-review。只有re-review与后续controller确认通过后，才可恢复S3/F03 implementation。
