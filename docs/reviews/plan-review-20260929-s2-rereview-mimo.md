# Issue #198 S2 未知下载异常安全诊断 implementation plan — adversarial plan re-review（MiMo 第二路）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-cff2015e

- reviewed target：`docs/gateflow/issue-198-unknown-download-diagnostics-plan-20260929.md`（当前修订候选，实测 SHA-256 `bed6c924b7ecb43c591ff05af39e9803a04590a349e4ef2761fe13e8d881798f`，与派发预期一致，无漂移）
- scope：F1 自定义秘密类型/安全指纹/深外部栈可信 Dayu 帧的可实现性，F2 S1→S2 七项映射与实际相容性，F3 EXECUTION sibling direct/job 事件矩阵，OQ1 `handler.handleError` 自诊断与隐式异常链泄漏，OQ2 S1 accepted+integrated 硬前置；并独立搜寻 plan 与现有 owner control flow、`safe_exception_trace` 可实现性、公共失败/durable job 同源、切片白名单/验证/README 之间的反例。不受总控既裁方向束缚。
- 边界：不修改 plan/goal/既有 review/裁决/产品/测试/README/主工作区；不实施、不 commit/push/PR/merge、不派发子 Agent、不发外部消息；只新建本 artifact。
- artifact timestamp（系统时钟）：`20260929-062537`。本文件名按派发指定，不使用 skill 的 `plan-review-${ts}.md` 命名。

## 证据基线与 S1 状态区分（stop condition 核查）

| 锁定项 | 实测值 | 结论 |
| --- | --- | --- |
| 本 checkout HEAD | `8d8d494fbbce0052372fb1b42097c9f7222cfa28`（S1 accepted plan 提交） | 与 goal/plan 声明一致 |
| S2 计划 SHA-256 | `bed6c924b7ecb43c591ff05af39e9803a04590a349e4ef2761fe13e8d881798f` | 与预期一致，未漂移 |
| 主工作区 S1 fix10 计划 SHA-256 | `2d18014ce605c8368d53247a43669f6ba597ecc875fe6d5a7b2ce558c0d92cd7` | 与 plan 第 22 行锁定一致 |
| 主工作区三产品文件未提交 diff SHA-256（`git diff -- dayu/fins/direct_events.py dayu/fins/ingestion_runtime.py dayu/cli/output.py \| shasum -a 256`） | `d9af4d09c3226616ccae2a9f2bd44281d1ad48021f9ced1d14b49291cf580783` | 与 plan 第 22 行锁定一致 |
| 主工作区 HEAD | `8d8d494f…`（`codex/upload-material-oracle`） | 未变 |

S1 实际状态：**未 accepted、未集成**。主工作区存在 `docs/gateflow/issue-198-s1-implementation-20260928.md`（label `issue198-s1-implement-sol-20260928-01`）与三产品文件未提交 hunk，但 `docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md` 判定 S1 review loop 未通过（MiMo F1–F5 accepted、未修复），此后 fix10 仍在「Kimi/MiMo 双路 plan re-review 前」，其正文自述「未进入 S1/S2 implementation」。当前三产品 diff 只含四值 `FinsDownloadFailureReason`/`reason_code` 投影（首轮被拒候选），`dayu.runtime.log.safe_exception_trace`、S1 typed job catch、`output.py` 唯一提示常量均未落地（两工作区 grep 无符号命中）——与 plan 第 22 行陈述一致。**OQ2 的「S1 尚无 accepted+integrated 实施」成立，任务所述与实际无矛盾；SHA 无漂移，stop condition 未触发。**

## Assumptions tested（结论）

1. **「未知判据 `kind == EXECUTION` 且非 `_UnsupportedDownloadSourceError`」可从现有投影 owner 实现** — 成立。`ingestion_runtime.py:6823-6877` `_download_public_failure_from_exception` 的 default 分支给 EXECUTION/「下载执行失败」；`_UnsupportedDownloadSourceError(RuntimeError)`（:421）确实落入该分支，故排除谓词必要；`OSError`→STORAGE（:6862-6870）、`FinsDownloadProviderError`→PROVIDER/CONFIGURATION（:6841-6861）自动排除。但该 default 分支同时是 unsupported-in-direct 的投影分支，见 F1。
2. **`safe_exception_trace` 指纹与信任校验可实现且不泄漏** — 成立。`vars(builtins).get(name) is class` 身份证实可防伪造类名冒充内建；指纹只出 `SHA-256(module + NUL + qualname)` 前 16 小写 hex，元数据异常回 `redacted`，即便元数据含秘密也只出哈希；`walktb` + `f_globals is sys.modules 中 dayu.* 模块 dict` + 模块 `__file__` 与 `co_filename` 解析同一 + 受信包根 + 标识符片段的逐帧校验可挡住伪造 `co_filename`。`dayu/` 全部模块路径片段均为合法标识符（awk 全量核对无命中），常规布局不会永久降级。无 `.venv`（已核实），奇异布局降级留 closeout 的登记合理。
3. **深栈「保留最深可信 Dayu 帧 + 末端帧」策略可实现** — 基本成立；选帧规则（替换尾窗最早非末端槽位、按原序输出、`[external]`/`truncated` 固定标记、≤16 帧标记 + 总长度上限）足以指导实现，但栈列表语法（分隔、`truncated` 落位）未逐字钉死，见残余。
4. **deferred-emission（离开活动 except 后发射）与现有 owner control flow 相容** — 成立且优于我最初的竞态怀疑。`_run_direct_stream_producer`（:4286-4345）是 `try/except/finally`（finally 发 Done），`_run_direct_stream_operation`（:4209-4261）在消费 Done 后 `finally` 中 `thread.join`，发射放在 try 语句之后即可同时满足「RESULT 先于日志」「无进程退出竞态」；job 路径同步收口无此问题。但「离开活动 except」未排除 finally/传播期发射的链复制残余，见 F3。
5. **公共失败与 durable job 同源** — 成立。`_save_failed`（:5902-5942）的 `result_summary or dict(_EMPTY_SUMMARY)` 空字典陷阱已排除：`_EMPTY_SUMMARY = {}`（:169），generic job 落 `result_summary={}` 与 plan/现有测试（`result_summary == {}` 断言多处）一致；`failure_summary` 走 `_bounded_text` 校验后原子保存，S2 改 message 来源为 `safe_message` 不改形状。
6. **F3 矩阵与 S1 契约相容** — 基本成立。S1 fix10 第 49 段限定 `FinsSourceDownloadAdapterFailure` 只持 `SourceIntegrityPreflightError | SourceIntegrityRevisionConflictError` typed cause 并单点 unwrap，矩阵 2/4/5/6 行与代码路由吻合；裸 revision conflict/repair blocked 落 generic catch（S1 typed catch 只收 adapter failure 与裸 preflight）与矩阵 3 行吻合。缺口是防御形状，见 F4。
7. **S2-U 切片白名单/验证/README 覆盖所需改动面** — 成立。四个生产文件含 helper/投影/job/CLI 全部落点；`tests/runtime/test_log.py` 存在；`_OperationFailureDownloadAdapter`（tests…:4161）、`_HoldingExecutor`（:3842）真实存在；旧 CLI raw traceback 断言（tests/cli/test_fins_commands.py:3089-3128）与 direct 秘密注入只查 RESULT（tests…:6055-6101）均属实。`dayu/runtime/` 无 README，plan 的条件判定正确；`dayu/README.md`/`fins/README.md`/根 README 均含更新约束段，plan 的触发判定与 goal 边界一致。
8. **OQ1 收窄后的可测边界可实现** — 成立（handler 自身 stack 允许、`Message:`/`Arguments:` 限安全串、`exc_info/stack_info is None`、threading.excepthook 无原异常），但 plan 的「离开活动 except 后发射」措辞存在一个未封死的传播期角落，见 F3。

## Findings

### 1-未修复-中-未知 retry_hint 的适用判据未钉死，与 unsupported-in-direct 共享分支的「文案不改」承诺自相矛盾
- **位置**: 计划「语义 owner、合同与实现决策」第 6 条、映射表第 4 行（retry_hint 承接）、证据表第 17 行（`_save_download_unsupported`「unsupported 正常失败和文案不改」）、事件矩阵第 6 行（`_UnsupportedDownloadSourceError`「前者走 unsupported 路由」）、S2-U「按 EXECUTION 矩阵……unsupported……断言事件数和公开形状」；总控 OQ3 裁决（「不在安全诊断 S2 改公开业务文案」）。
- **问题类型**: 契约缺失 / open question 未收敛（实施歧义可直接违反裁决边界）。
- **当前写法**: decision 6 写「未知 `EXECUTION` 的 `_download_public_failure_from_exception` 逐字使用「请保存脱敏诊断并排查失败原因后重试。」」；decision 1 只给诊断谓词（`kind == EXECUTION` 且非 `_UnsupportedDownloadSourceError`），未声明 hint 是否同谓词适用；row 17 与矩阵第 6 行承诺 unsupported 文案不改。
- **反例/失败场景**: 现有代码 `_download_public_failure_from_exception`（ingestion_runtime.py:6871-6877）的 default 分支同时服务未知异常与 `_UnsupportedDownloadSourceError`（后者是 RuntimeError，direct 路径无独立「unsupported 路由」，必落此分支，当前 hint 逐字「请重新发起下载；若持续失败，请检查运行日志中的脱敏分类。」）。实施 Agent 按 decision 6 字面替换该分支 hint → unsupported-in-direct 的公开 hint 变为「请保存脱敏诊断……」：(a) 违反 OQ3 总控裁决「不在安全诊断 S2 改公开业务文案」与本 plan 自己的「unsupported 文案不改」；(b) 对一个矩阵第 6 行明言「不记」诊断事件的路径给出「请保存脱敏诊断」的指向，制造新误导文案。若 Agent 自行拆分支保旧文案，则拆分位置、unsupported 旧 hint 逐字文本均无 plan 依据，属实施期无据设计决策。
- **为什么有问题**: 同一代码分支承载两种语义（未知 vs unsupported），plan 既没钉死 hint 判据与诊断判据同构，也没把「unsupported 保留旧 hint 逐字」写进实施前核对清单（第 66 行只核「未知 hint」「无来源独立 hint」，不核 unsupported 文本存活）。该缺口不会被「任何差异先回本 plan 重基线」捕获——它表现为核对项缺失而非核对不符，会直接漏进实施。
- **直接证据**: ingestion_runtime.py:6871-6877（共享 default 分支与旧 hint 原文）；:421 `_UnsupportedDownloadSourceError(RuntimeError)`；:4957-4958 job 侧独立 unsupported 路由（direct 无对应路由）；本 plan decision 1/6、row 17、矩阵第 6 行、核对清单第 66 行；总控 OQ3 段「direct/job unsupported source 文案差异登记独立 `fins-download-unsupported-source-public-consistency`，不在安全诊断 S2 改公开业务文案」。
- **影响**: 用户可见 hint 被静默改到错误指向，或违反已裁决边界；S2-U「公开形状」断言若不钉逐字文本将无法发现；后续 code review 必打回返工。
- **建议改法和验证点**: 在 decision 6 明确 hint 判据与 decision 1 诊断判据同构（`EXECUTION ∧ ¬_UnsupportedDownloadSourceError`），在投影 owner 内拆分支让 unsupported-in-direct 保留旧 hint **逐字**（或经总控重新裁决后允许共用新 hint，并同步收窄 OQ3 残余边界与 row 17 措辞）；实施前核对清单增「unsupported-in-direct 公开 message/hint 逐字未变」；S2-U 对 unsupported 断言完整公开形状逐字（message 与 hint）。验证点：注入 `_UnsupportedDownloadSourceError` 走 direct，断言公开 failure 文本逐字等于现状；注入未知异常断言新 hint 逐字。
- **修复风险（低/中/高）**: 低（计划一段文字 + 一处窄分支规格）。
- **严重程度（低/中/高/严重）**: 中。

### 2-未修复-中-映射表 supersession 声称 download 二次 WARN 全部收回，但 job 事件追加失败 WARN 的动态 `error_type=异常类名` 既未修也未登记
- **位置**: 映射表第 7 行（「S2 将……与 download 二次 WARN 收回本 slice；`fins-other-raw-diagnostics-audit` 仅余非 download CLI/job 原文面」）、decision 5（generic/unsupported 二次失败「只记各自固定事件标识……均无动态 `error_type`、异常串……」）、S2-U「generic 与 unsupported 二次失败只记各自固定 WARN，无主/次异常动态线索」；对照 S1 fix10 第 93 段 audit 登记与第 53 段 typed WARN 合同。
- **问题类型**: 语义 owner 收口不完整 / 测试缺口（验收断言证明不了自己的 supersession 声明）。
- **当前写法**: decision 5 只列两个固定 WARN（`fins.download.failed_record_save_failed`、`fins.download.unsupported_failed_record_save_failed`）加 S1 的 `fins.download.typed_failed_record_save_failed`；row 36 据此宣称 download 二次 WARN 面已全部收回、audit 仅余非 download。
- **反例/失败场景**: `_save_failed`（:5935-5941）保存成功后调用 `_append_terminal_job_event_warn` → `_append_job_event_warn`（:6299-6347）；后者 `append_job_event` 抛任意异常时日志 `"… payload_keys=%s error_type=%s error_summary=%s"`，其中 `error_type=%s` 填 `type(exc).__name__`（:6342）——**动态异常类名**，与 S1 typed WARN 合同（「不记录任何动态异常信息（包括异常类名……）」）和 S2 decision 5（「均无动态 error_type、异常串……」）明令禁止的形态完全相同，且发生在 download 失败收口的同一 helper 链上。`_emit_progress_event`（:6083）同类。S1 第 93 段 audit 登记只点名 `_save_failed_from_exception`/`_save_download_unsupported` 的 `exc_info=True` WARN，不含 event-append WARN。S1/S2 自己的威胁模型把异常类名当敏感（S2-U「两类不同自定义异常的类名及模块名分别含不同秘密」、S1 测试「类名及异常内容分别含可识别秘密……无该类名」）。
- **为什么有问题**: 按项目自身威胁模型，含秘密的自定义类名可经该 WARN 进入 operator 日志；S2-U 的「无主/次异常动态线索」若只在 read/save 处注入二次失败（计划现状）将假绿通过，row 36 的「仅余非 download」成为不实声明，closeout/audit 记账漏项。
- **直接证据**: ingestion_runtime.py:5935-5941（`_save_failed` 内 event 追加）、:6299-6347（`_append_job_event_warn` 的 `type(exc).__name__`）、:6083（`_emit_progress_event` 同型）；S1 fix10 第 93 段 audit 枚举；本 plan row 36、decision 5、S2-U 二次失败断言。
- **影响**: download 收口路径残留类名泄漏通道；supersession/audit 双向漏账；验收断言假绿；后续 deepreview/code review 返工。
- **建议改法和验证点**: 二选一并在计划里写死：(a) 把 download 路径 event-append/progress 追加失败 WARN 纳入同一固定标识合同（去 `type(exc).__name__` 与动态字段）；(b) 收窄 row 36 为「读取/保存 WARN」，把 event-append WARN 类显式登记进 `fins-other-raw-diagnostics-audit` 并把「仅余非 download」改为「另余 download event-append WARN」。验证点：向 `job_store.append_job_event` 注入类名含秘密的自定义异常，断言 download 失败收口日志无该类名；S2-U 二次失败注入点补 event-append。
- **修复风险（低/中/高）**: 低（固定 WARN 文案替换或一行残余登记）。
- **严重程度（低/中/高/严重）**: 中。

### 3-未修复-低-「离开活动 except 后发射」未排除 finally/异常传播期发射，RESULT 二次失败叠加 handler 失败时 handleError 沿 `__context__` 链复制原异常
- **位置**: decision 4（「实际日志发射必须在原业务异常的活动 `except` 结束、`sys.exc_info()` 不再持有它之后进行」「direct 发射仍在唯一 RESULT 之后」「现有队列 Done 顺序以 owner 测试固定」）、decision 5（「离开所有原业务与二次失败的活动 `except` 后才发射，防止 handler 自诊断沿隐式异常链复制原秘密」）、S2-U OQ1 断言（「整个 stderr 无……原异常链」）。
- **问题类型**: 状态机漏洞 / 并发恢复风险（发射位点约束不完备）。
- **当前写法**: 要求发射在 except 结束之后、RESULT/Done 之后，但未说明不得位于 `finally` 或其它异常传播路径上。
- **反例/失败场景**: `_run_direct_stream_producer` 的 `except` 末尾 `_emit_direct_result` 若抛错（plan 自己登记的 `fins-direct-projection-failsafe` 场景），实现者若把发射放在 `finally` 内（「RESULT 之后」字面可容纳此读法），`finally` 运行时新异常正在传播且其 `__context__` 为原业务异常；此时 handler `emit` 失败 → stdlib `handleError` `traceback.print_exception` 打印完整链（含原异常消息与原始 traceback），秘密直达 stderr——即便发射外包窄 catch 吞掉二次异常也无法收回已打印内容。S2-U OQ1 只测「handler 单独失败」，测不出该双失败角落，「整个 stderr 无原异常链」会假绿。
- **为什么有问题**: OQ1 的核心威胁恰是隐式异常链复制；plan 已识别该机制（decision 5 文字）但封堵条件（「离开活动 except」）弱于威胁（「不在任何异常传播期」）。job 路径无逃逸合同基本安全；direct 的 finally 结构（:4339-4345）使该角落真实存在。
- **直接证据**: ingestion_runtime.py:4304-4345（except 末 `_emit_direct_result`、finally 发 Done）；stdlib `logging.Handler.handleError` 打印 `sys.exc_info()` 及 `Message:`/`Arguments:` 且 `print_exception` 会展开 `__context__` 链；本 plan decision 4/5 与 S2-U OQ1 断言清单。
- **影响**: 双失败场景下原异常消息/原始 traceback/链经 stderr 泄漏，违反 goal「公开结果不泄漏原始 traceback」与 OQ1 边界；因与 failsafe 残余叠加，暴露窗口小，但断言盲区使它可静默通过。
- **建议改法和验证点**: decision 4/5 把发射位点钉为「try 语句正常结束后的语句位置（不得在 `finally`、except 内或任何异常传播路径）」；S2-U OQ1 增双失败用例（RESULT 投递失败 + handler 失败）断言 S2 发射被跳过、stderr 无本 S2 事件行与原异常链（RESULT 自身 failsafe 泄漏仍归 `fins-direct-projection-failsafe`，分开记账）。
- **修复风险（低/中/高）**: 低（两句话 + 一个测试用例）。
- **严重程度（低/中/高/严重）**: 低。

### 4-未修复-低-事件矩阵未覆盖 `FinsSourceDownloadAdapterFailure` 非 typed cause 的防御形状，「按矩阵断言事件数」对该形状无据
- **位置**: 事件矩阵第 2 行（仅列「包含 revision conflict」）与第 4 行（仅列 preflight）、S2-U「按 EXECUTION 矩阵对 adapter 包裹与裸 sibling……分别断言事件数」；对照 S1 fix10 第 49/57 段。
- **问题类型**: open question 未收敛 / 测试缺口（断言歧义）。
- **当前写法**: 矩阵行按 S1 允许的两种 typed cause 划分；对 adapter failure 携带非 typed cause 只字未提。
- **反例/失败场景**: S1 第 57 段的测试合同明确要求「私有 adapter failure 另断言……非 typed 不获 reason」——即非 typed cause 形状是 S1 契约内被测试的防御形状。该形状经单点 unwrap 后非 provider/非 OSError → EXECUTION：direct 按谓词记一次，job 被 S1 typed catch 收口不记。S2-U 要求「按矩阵」断言事件数，但矩阵无此行，实施者只能猜测；若猜成「两边都记」，与 typed catch 收口事实冲突。
- **为什么有问题**: F3 裁决要求矩阵固定测试政策；行缺失使该政策对一个 S1 明文测试的形状留白。生产暴露受限于 S1「只允许 typed cause」的构造约束，故降为低。
- **直接证据**: S1 fix10 第 49 段（「只允许这些既有 typed cause」「非 typed 不获 reason」）、第 57 段测试合同；本 plan 矩阵第 2/4 行、S2-U 矩阵断言句。
- **影响**: 测试断言无据或与 owner 路由冲突，review 争议；诊断观测在防御形状下不一致。
- **建议改法和验证点**: 矩阵补一行「adapter failure 携带非 typed cause：direct 记一次 / job 不记（typed catch 收口），防御形状，业务分类残余仍归 sibling work unit」，S2-U 断言据此钉死；或显式声明该形状仅 S1 测试面、S2 不断言并给出理由。
- **修复风险（低/中/高）**: 低（矩阵一行）。
- **严重程度（低/中/高/严重）**: 低。

## Open questions

- **OQ-A（S1 合同真源仍在动）**: S1 fix10 自身尚待 Kimi/MiMo 双路 plan re-review，七项映射的「S1 合同」是候选而非 accepted 合同；S2 的逐行核对/重基线机制已覆盖，但映射行与逐字文案在 S1 终审后重排的成本应由总控在排期时计入（本 review 不作实施期断言）。
- **OQ-B（terminalize 包装三重并存）**: S1 typed catch、S2 `_save_download_failed_from_exception`、非 download `_save_failed_from_exception` 将共享「读最新 record→终态仲裁→`_save_failed`→不逃逸 WARN」控制流而不共享实现，与 AGENTS.md「重复逻辑必须抽取」有张力；抽取共享核又会把 S2 slice 耦合进尚未落地的 S1 typed 实现。倾向：保持现状窄 helper，在 closeout 或 `fins-download-storage-sibling-errors` 登记去重候选；交总控裁决。
- **OQ-C（栈列表语法）**: 帧标记的分隔符、`truncated` 的落位、`[external]` 压缩后的精确单行样例未逐字给出；同一合同可产出不同可接受串。建议 fix 时补一行样例（如 `stack=dayu/fins/ingestion_runtime.py:4320 truncated [external]`）以稳定 operator grep 与跨实现断言。

## Residual risks 与建议跟踪去向

| 残余 | 去向 |
| --- | --- |
| direct RESULT 自身二次失败 / 线程钩子输出原始 traceback（含与 F3 双失败角落的叠加） | `fins-direct-projection-failsafe`（已登记；F3 修法把 S2 发射从该链上摘出） |
| 非 download CLI 外层 raw traceback、非 download job `str(exc)` durable message、`_save_failed_from_exception`/`_save_download_unsupported` 旧 `exc_info=True` WARN 的非 download 面 | `fins-other-raw-diagnostics-audit`（row 36 收窄后口径以 F2 修法为准） |
| 异常链 cause/context/notes 全排除：根因在链中时诊断只剩表层 | `fins-other-raw-diagnostics-audit` 后续判断（总控已裁） |
| revision conflict / repair blocked 落 EXECUTION 档分类与 direct/job 观测不对称 | `fins-download-storage-sibling-errors`（已登记） |
| unsupported source direct/job 公开文案差异 | `fins-download-unsupported-source-public-consistency`（已登记；F1 修法不得扩大其面） |
| 无来源文档 hint 在默认临时日志下欠可操作 | `fins-download-no-source-retry-hint`（已登记） |
| 跨奇异安装布局全部可信帧降级 `[external]` | closeout 记录（plan 已登记） |
| 默认临时日志退出即清理、`--quiet` 显式抑制 | 报告披露，不修（goal 允许） |
| 外部 provider/network 真实烟测可能阻塞 | 实施报告标注验证缺口，不冒充成功 |
| terminalize 控制流三重并存的去重 | OQ-B，closeout 或 sibling work unit |
| 栈列表语法实现自由度 | OQ-C，fix 时补样例即可 |

## Final plan review conclusion

**fail**（须小范围 plan fix 后 re-review；方向、单切片与 S1 硬前置均无需推翻）。

与首轮（F1/F2 高项）相比，候选已实质收敛：指纹方案、深栈可信帧、七项 supersession 映射、sibling 矩阵、OQ1 测试边界、OQ2 硬前置全部落文本，且三处 SHA 锁定与代码证据抽查全部属实。剩余两项中等 finding 均是「合同钉死缺失」而非方向错误：F1（hint 判据/unsupported 共享分支）不修则实施必在违反 OQ3 裁决边界与无据拆分支之间二选一；F2（event-append WARN）使 row 36 的 supersession 声明与 S2-U「无主/次异常动态线索」证明不了自己。两项加 F3/F4 的修法合计约十行计划文字与三个测试用例，建议总控裁决后交 Sol 一次性修订，再进 Kimi/MiMo 同版 re-review。OQ2 前置依旧未满足，本轮结论不构成实施许可。
