# Issue #198 S2 未知下载异常安全诊断 implementation plan — 同版二轮 adversarial plan re-review（MiMo 第二路 rereview2）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-712e84dd

- reviewed target：`docs/gateflow/issue-198-unknown-download-diagnostics-plan-20260929.md`（当前修订候选，实测 SHA-256 `f3643583a29577e6aedbc87e52243028453c38dbd5834607011abd43ab1da4b8`，与派发预期一致，无漂移，未触发任务级停止条件）
- scope：反证前轮 MiMo F1–F4 修复（unknown 与 direct unsupported 逐字 hint 分流；event-append/progress/typed/generic/unsupported 二次 WARN 安全且同源；`sys.exc_info` 与 try/finally 时序避免 handler 原异常链复制；RESULT+handler 双故障；non-typed adapter cause direct/job 矩阵），以及 S1→S2 supersession 映射与 accepted+integrated 硬前置；实读 owner 代码核对 goal drift、切片/白名单/覆盖率/README/pyright/真实入口证据、LLM-facing 文字、安全栈单行语法（OQ-C）。独立复核，不受总控既裁方向束缚。
- 边界：不修改 plan/goal/adjudication/产品/测试/README/已有 review；不实施、不 commit/push/PR/merge、不派发子 Agent、不发外部消息；只新增本 artifact。
- artifact timestamp（系统时钟）：`20260929-100903`。文件名按派发指定 `plan-review-<ts>-s2-rereview2-mimo.md`，不使用 skill 的 `plan-review-${ts}.md` 命名。
- 前置文档已读：本 checkout goal、本 plan 全文、`docs/reviews/plan-review-20260929-053621.md`（首轮）、`docs/reviews/plan-review-20260929-s2-rereview-mimo.md`（前轮 MiMo）、`docs/gateflow/issue-198-s2-plan-review-adjudication-20260929.md`（总控裁决与 Sol 二轮修订记录）、主工作区 S1 真源计划 `issue-198-download-failure-projection-plan-20260928.md`（fix10）与 S1 实施报告、双路 S1 复审 artifacts。

## 证据基线与 S1 状态区分（stop condition 核查）

| 锁定项 | plan 第 22 行声称 | 本轮实测 | 结论 |
| --- | --- | --- | --- |
| 本 checkout HEAD | `8d8d494f…`（S1 accepted plan 提交） | `8d8d494fbbce0052372fb1b42097c9f7222cfa28` | 一致 |
| S2 计划 SHA-256 | `f3643583…`（派发预期） | `f3643583a29577e6aedbc87e52243028453c38dbd5834607011abd43ab1da4b8` | 一致，无漂移 |
| 主工作区 S1 fix10 计划 SHA-256 | `2d18014c…` | `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md` = `2d18014ce605c8368d53247a43669f6ba597ecc875fe6d5a7b2ce558c0d92cd7`（第 3 行 label `issue198-s1-plan-fix10-sol-20260929-01` 确认身份） | **一致，未漂移**；映射行合同基线仍有效 |
| 主工作区三产品文件未提交 diff SHA-256（`git diff -- dayu/fins/direct_events.py dayu/fins/ingestion_runtime.py dayu/cli/output.py \| shasum -a 256`） | `d9af4d09…` | `29c2e5856f43cd901f5fe9693ba458a92ee241530ba5d8d083c931218cfcf3ef` | **已漂移**（见 Finding 1） |
| 主工作区 HEAD | `8d8d494f…` | `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`（新提交 `docs: accept issue 198 S1 download failure plan`） | **已漂移** |
| 本工作区 `.venv` | 无 | `ls .venv` 无输出 | 一致 |
| `dayu/runtime/log.safe_exception_trace` | 未落地 | 两工作区 grep 无符号命中 | 一致 |
| CLI 唯一提示常量 / `fins.py` 旧常量退役 | 未落地 | `fins.py:104` `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE` 仍在 | 一致 |
| S1 typed job catch | 「均未在当前代码落地」 | **已落地**：主工作区 `ingestion_runtime.py:4992-4993` `except (FinsSourceDownloadAdapterFailure, SourceIntegrityPreflightError) as exc: self._save_typed_download_failure(...)`；`:4997-5035` `_save_typed_download_failure` 含固定 WARN `fins.download.typed_failed_record_save_failed`（`:5033`，无动态字段） | **plan 陈述已假**（见 Finding 1） |
| 两个事件名、未知 hint 逐字 | 未落地 | grep 无命中，`_download_public_failure_from_exception` default 分支仍旧 hint（主工作区 `:6987-6988`） | 一致 |

**S1 当前实际状态（与 plan/前轮 review 陈述的差异）**：S1 fix10 计划经 Kimi `plan-review-20260929-092908-issue198-s1-kimi.md`（pass-with-risks）等双路复审后，已被主工作区提交 `47a9cb64`（`docs: accept issue 198 S1 download failure plan`）**接受**；`docs/gateflow/issue-198-s1-implementation-20260928.md` 是 S1 **实施报告**（label `issue198-s1-implement-sol-20260928-01`，「Gate：implementation；下一 gate：code review」，自述 450 tests passed、pyright 0 errors），产品 hunk 在主工作区工作树**未提交**。即：**S1 plan accepted、implementation 已完成但未 accepted（待 code review）、未 commit、未 integrated**。plan 的 OQ2「S1 尚无 accepted+integrated 实施」结论仍然成立且更强（连 implementation 都未过 code review），但第 22 行的候选状态描述与部分事实陈述已过期。任务级停止条件（目标 plan SHA 漂移/依赖不可读）未触发；plan 第 22 行自设条款「若上述计划/代码候选版本在本轮复审前漂移，停止并重新裁定基线」对其中两项触发，见 Finding 1。未把 S1 候选当集成 HEAD。

## Assumptions tested（结论）

1. **未知诊断判据 `kind == EXECUTION` 且非 `_UnsupportedDownloadSourceError` 可从现有投影 owner 实现** — 成立。本 checkout `_download_public_failure_from_exception`（`ingestion_runtime.py:6823-6877`）default 分支给 EXECUTION/「下载执行失败」+旧 hint；`_UnsupportedDownloadSourceError(RuntimeError)`（`:421`）必落该分支，排除谓词必要。主工作区 S1 实施后同函数（`:6925`）default 形态未变（`:6987-6988`），且 `FinsSourceDownloadAdapterFailure.cause` 类型标注（`:592`）只允许 `SourceIntegrityPreflightError | SourceIntegrityRevisionConflictError`，adapter 不会包 unsupported，谓词作用于 unwrap 前的 exc 与 unwrap 后的 cause 等价。
2. **unknown 与 direct unsupported 逐字 hint 分流（F1）** — 成立，见反证节。
3. **`safe_exception_trace` 指纹与信任校验可实现且不泄漏** — 成立（前轮已验证 `vars(builtins).get(name) is class` 身份证实、SHA-256(module+NUL+qualname) 16 hex、逐帧 globals/`__file__`/包根/标识符校验；本轮复核 decision 3 与 S1 fix10 计划第 29-30 段逐字同构，「内建 custom_type=redacted」「整体降级 `[unavailable]`」一致）。
4. **深栈选帧与单行语法（OQ-C）** — 成立。decision 3 的选帧规则（保留末端抛出帧+尾窗，另留最深可信 Dayu 帧，替换尾窗最早非末端槽位，按原序输出）与逐字示例 `stack=dayu/fins/ingestion_runtime.py:4320 truncated [external]` 自洽：对「1 个可信 Dayu 帧 + >16 连续外部帧」的场景，规则推导出的输出正是该示例形态，同时保留可信帧与末端 `[external]`，满足裁决「>16 外部帧时仍保留可信 Dayu 调用帧」。
5. **deferred-emission 与现有 owner control flow 相容** — 成立。`_run_direct_stream_producer`（本 checkout `:4304-4343`）`try/except/finally`（finally 发 Done），发射置于整个 try 语句之后即「RESULT 与 Done 之后」且无进程退出竞态（`_run_direct_stream_operation` 消费 Done 后 `thread.join`）；RESULT 构造/投递失败时异常传播、后置位置不可达、跳过 S2 事件，与决策 4 一致。job 侧 `_run_download_job`（主工作区 `:4970-4995`）except 分支不 return，落到函数尾发射自然可行。CLI 侧存在控制流表述缺口，见 Finding 2。
6. **公共失败与 durable job 同源** — 成立。`_save_failed`（本 checkout `:5902-5942`）`failure_summary={"message": _bounded_text(...)}`、`result_summary or dict(_EMPTY_SUMMARY)` 空字典陷阱已排除（`_EMPTY_SUMMARY = {}`，`:169`），generic 落 `result_summary={}` 与既有测试断言一致；S2 改 message 来源为 `safe_message` 不改形状。主工作区 `_save_typed_download_failure` 已示范「同源 safe_message + 结构化 summary」形态，S2 generic 收口与其同构。
7. **F3/F4 矩阵与 S1 契约相容** — 成立。主工作区 except 顺序（unsupported → typed → generic）与矩阵 2/3/5/6 行吻合；`_download_exception_cause`（`:6909`）单点 unwrap 已落地并被 direct（`:4337`）与 typed job（`:5018`）共用，矩阵「单点 unwrap 后投影」属实。矩阵行 3 的「按 EXECUTION 投影」以非 typed cause 非 provider/非 OSError 为前提，见 OQ-D。
8. **S2-U 切片白名单/验证/README 覆盖所需改动面** — 成立。四个生产文件含 helper/投影/job/CLI 全部落点；`tests/runtime/test_log.py` 存在；`_OperationFailureDownloadAdapter`（`tests/fins/test_fins_ingestion_runtime.py:4161`）、`_HoldingExecutor`（`:3842`）真实存在；旧 CLI raw traceback 断言（`tests/cli/test_fins_commands.py:3089-3128` `test_unknown_fins_direct_failure_logs_traceback_and_hides_exception_from_stderr` 断言 caplog 含 `Traceback`/`RuntimeError`/原始 marker）与 direct 秘密注入只查 RESULT（`tests/fins/…:6055-6101`）均属实。`dayu/runtime/` 无 README（`ls` 空），plan 条件判定正确。
9. **二次 WARN 收口范围（F2）** — 成立，见反证节。实读确认 `_append_job_event_warn`（本 checkout `:6337-6350`）与 `_emit_progress_event`（`:6078-6092`）在 download 失败链可达处输出动态 `type(exc).__name__`，plan 收口范围与威胁面一致。
10. **goal drift** — 未发现。六决策、矩阵、S2-U 的每个验收点均可映射 goal 三条成功信号或已裁决边界；「共享 event-append/progress WARN 收紧」已被总控 F2 裁决纳入且属 goal1「日志不得复制原始异常消息……」的直接延伸；「CLI download 命令层安全栈」属 S1 计划第 28 段两点诊断模型的第二点。无 future-slice work 或新验收标准混入。

## 旧 F1–F4 逐项反证

### F1（unknown 与 direct unsupported 逐字 hint 分流）— 已修复，反证成立

- decision 6 现写「只对 `kind == EXECUTION` 且非 `_UnsupportedDownloadSourceError` 的异常逐字使用「请保存脱敏诊断并排查失败原因后重试。」」，并明确「此判据与决策 1 的安全诊断判据同构，在唯一投影 owner 内窄分支处理共享 default 分支」——hint 判据与诊断判据钉为同构谓词，消除了前轮 F1 的「实施者猜测」缺口。
- direct unsupported 逐字保留：decision 6 与矩阵第 6 行承诺 `safe_message="下载执行失败"`、`retry_hint="请重新发起下载；若持续失败，请检查运行日志中的脱敏分类。"` 不变；实读本 checkout `:6871-6877` 与主工作区 `:6987-6988` 确认该逐字文本是当前真实值，且 `_UnsupportedDownloadSourceError` 必落共享 default 分支（`:421` 继承 RuntimeError，非 OSError/非 provider）。
- 验证闭环：S2-U 前置核对清单含「未知与 direct unsupported 的逐字 message/hint」；S2-U 断言「尤其 direct `_UnsupportedDownloadSourceError` 的 `safe_message=…` 与 `retry_hint=…` 逐字不变，未知异常使用新 hint 逐字文本」。plan 还写明 unsupported 诊断事件「不记」且「不承诺不存在的安全事件」，与 OQ3 裁决（不改 unsupported 公开业务文案）一致。
- 反证尝试：若 hint 分支误拆为「所有 default EXECUTION 用新 hint」，S2-U 逐字断言直接失败；若漏拆，未知 hint 断言失败。两个方向都有验收锚点。

### F2（event-append/progress/typed/generic/unsupported 二次 WARN 安全且同源）— 已修复，反证成立

- 威胁面实证：`_append_job_event_warn` 的 except 输出 `error_type=%s` 填 `type(exc).__name__`（`:6348`），`_emit_progress_event` 同型（`:6090`）；`_save_failed_from_exception` 二次失败 WARN 带动态 `type(exc).__name__` 与 `exc_info=True`（`:6006-6011`）；`_save_download_unsupported` 同型（`:5978-5982`）。plan 决策 5 对这四类全部规定固定事件标识、无动态异常线索。
- 同源覆盖：三类下载终态二次 WARN 统一固定强度（generic `fins.download.failed_record_save_failed`、unsupported `fins.download.unsupported_failed_record_save_failed`、typed `fins.download.typed_failed_record_save_failed` 保留），共享 event-append/progress 收回为固定 `fins.ingestion.job_event_append_failed` + 可信枚举 `event_type`（progress 固定 `PROGRESS`）；映射行 7 明确「S1 typed job 结构化形状及其固定 WARN 原样保留……`fins-other-raw-diagnostics-audit` 仍跟踪非 download」——覆盖范围与总控 F2 裁决逐项对应，supersession 声明可被 S2-U 断言证明（「向真实 download 失败链的 `job_store.append_job_event` 与 progress event 保存注入类名、模块名和异常消息含不同秘密的自定义异常，断言固定事件和可信枚举参数之外无动态字段」）。
- 主工作区 S1 已落地的 typed WARN（`:5033` 纯固定字符串、无 `exc_info`）与映射行 6「消费并保留」一致，S2 不触碰。
- 反证尝试：若共享 helper 收紧遗漏 event-append，S2-U 的「注入类名含秘密断言无动态字段」直接失败。裁决「其它操作沿共用 helper 的日志也变安全，但不改变其业务状态/结果」已在 plan 决策 5 复述（「共享 helper 的非 download 调用仅改变日志材料，不改变事件追加、状态或结果」）。

### F3（`sys.exc_info` 与 try/finally 时序、RESULT+handler 双故障）— 已修复（残余见 Finding 2），反证基本成立

- 时序钉死：decision 4/5 加粗规定「**只在各自业务 `try` 语句及其 `finally` 正常结束后的语句位置**检查 `sys.exc_info() is None` 并发射；不得在 `except`、`finally` 或任何原/次异常传播路径发射」，并要求「只把固定事件名与安全串暂存为标量，不能把原异常对象存入待发记录」——从位点与数据两方面封堵 handler 自诊断沿隐式异常链复制原秘密。
- 双故障：「若 RESULT 构造/投递失败，正常后置位置不可达，跳过 S2 事件；RESULT 自身 failsafe 泄漏独立归 `fins-direct-projection-failsafe`」；S2-U 明确「另注入 direct RESULT 投递失败 + handler 自诊断失败的双故障，断言因后置正常路径不可达而**没有 S2 事件行、S2 handler 未被调用**」，且把 RESULT 自身的 `threading.excepthook` 泄漏残余「不把该残余混入 S2 handler 隐私断言」分开记账——与裁决逐字对应。
- OQ1 边界：handler 自身 stderr stack 允许、`Message:`/`Arguments:` 限固定事件名与安全串/可信枚举、`exc_info/stack_info is None`、`threading.excepthook` 不收到原业务异常，另覆盖「logger 直接抛错而非自行 `handleError`」路径——完整。
- 反证尝试：direct 的 `finally` 发 Done 结构下，若实施者把发射放进 `finally`，被「不得在 finally……发射」禁止；若 RESULT 失败后仍在传播路径发射，被「不得在任何原/次异常传播路径发射」+「后置位置不可达则跳过」双重禁止，且双故障测试锁定。残余是 CLI 命令层发射与 stderr 形成顺序的控制流形态未写明（Finding 2）。

### F4（non-typed adapter cause direct/job 矩阵）— 已修复，反证成立

- 矩阵补行「`FinsSourceDownloadAdapterFailure` 携非 typed cause（S1 防御测试形状），S1 typed job catch | 记一次 | 不记 | 单点 unwrap 后按 EXECUTION 投影，direct 记一次；job 已由 typed catch 收口，不误当 STORAGE preflight。该形状的业务分类仍归 sibling work unit」——与主工作区路由吻合：`_run_download_job` 的 typed catch 收 `FinsSourceDownloadAdapterFailure`（含任意 cause）在 generic 之前（`:4992`），direct 经 `_download_exception_cause` unwrap 后按 cause 分类（`:4337-4357`）。
- S2-U 断言「按 EXECUTION 矩阵对 adapter 包裹 typed/非 typed cause、裸 sibling、preflight、provider、unsupported、无来源非异常路径分别断言 direct/job 事件数和公开形状」已把该行纳入验收。
- 残余：「按 EXECUTION 投影」的前提（cause 非 provider/非 OSError）与 S1 防御形状测试在主工作区 tests 中的落地情况，见 OQ-D。

## Findings

### 1-未修复-中-plan 第 22 行证据基线与 S1 状态陈述失真，自设「漂移即停止重裁」条款已触发
- **位置**: plan「直接代码与真实入口证据」节第 22 行（三项 SHA 锁定与状态陈述）；连带影响「S1 → S2 supersession」节引言（「S1 候选或本 checkout 已接受旧版计划均不等于 S1 accepted+integrated HEAD」）与风险节 OQ2（「S1 尚无 accepted+integrated 实施」）的状态时点。
- **问题类型**: 其它（证据基线失真 / plan 自设停止条件触发）。
- **当前写法**: 「主工作区 S1 fix10 计划和三个产品文件仍是未提交候选。本轮只读锁定候选 plan SHA-256 `2d18014c…`、三个产品文件未提交 diff 的 SHA-256 `d9af4d09…`，主工作区 HEAD 仍为 `8d8d494f…`。`dayu.runtime.log.safe_exception_trace`、S1 typed job catch、CLI 唯一提示常量均未在当前代码落地。……若上述计划/代码候选版本在本轮复审前漂移，停止并重新裁定基线。」
- **反例/失败场景**: 本轮实测：三产品 diff SHA 已为 `29c2e585…`（S1 实施 hunk 落入工作树），主工作区 HEAD 已为 `47a9cb64`（`docs: accept issue 198 S1 download failure plan` 提交，含 Kimi/MiMo S1 双路复审 artifacts 与裁决）；`issue-198-s1-implementation-20260928.md`（37 行实施报告）表明 S1 implementation 已完成（自述 450 tests passed、pyright 0 errors、下一 gate code review）；主工作区 `ingestion_runtime.py:4992-5035` 的 typed job catch 与固定 WARN `fins.download.typed_failed_record_save_failed` **已落地**。实施 Agent 若按第 22 行字面「S1 typed job catch 未落地」设计前置核对，会把已存在的 S1 合同误判为缺失（或反之试图重写 typed catch）；S2-U 前置「逐项标符合/需重审」虽会暴露不符，但按其自身规则「任何一项不符先修本 plan、双路 re-review」，实际仍要回到 plan 修订——即漂移必须先重基线。
- **为什么有问题**: plan 自设条款明文规定候选版本漂移时「停止并重新裁定基线」；三项锁定中两项已漂移，且状态陈述含可验证的假句（typed job catch、fix10 计划「未提交候选」——实际已被 accept 提交）。plan 的证据表、supersession 映射与 OQ2 状态都以第 22 行时点为锚；锚失真使 plan 不可直接验收，与「不冒充 S1 集成态」的自我要求冲突。**但合同实质未受影响**：fix10 计划 SHA `2d18014c` 未漂移（映射行所依据的 S1 S2 预设计合同逐字核对仍一致：两个事件名、hint 文本、CLI 提示归属、typed WARN 固定标识、helper 签名均与映射行 1-6 吻合），映射行七项经本轮对 fix10 计划与当前 S1 实施产物的独立核对相容，未发现一处合同冲突。
- **直接证据**: 实测三产品 diff SHA `29c2e585…` 与主工作区 HEAD `47a9cb64`；`git show --stat 47a9cb64`（accept 提交含 S1 双路复审 artifacts）；`docs/gateflow/issue-198-s1-implementation-20260928.md` 第 3-6 行（Gate：implementation；下一 gate：code review；范围含「封闭预检原因公共投影」）；主工作区 `ingestion_runtime.py:4992-4993/4997-5035`（typed catch + `_save_typed_download_failure` + `:5033` 固定 WARN）；`issue-198-download-failure-projection-plan-20260928.md` SHA `2d18014c`（未漂移）；本 plan 第 22 行原文。
- **影响**: plan 证据基线不可验收、按自设条款须重裁；实施 Agent 对 S1 现状判断错误；但因映射实质相容且 S2-U 前置强制逐项核对，最终代码错误风险被兜底——返工点在 plan 修订与重复 re-review 的 gate 成本。
- **建议改法和验证点**: 按 plan 自设条款重基线后小修订：第 22 行重锁当前三产品 diff SHA（或改为「实施后以 S1 accepted+integrated HEAD 为准，不锁未提交候选 SHA」的动态核对表述）、更新主工作区 HEAD 与 S1 状态（plan 已 accept、implementation 已完成待 code review、未 commit 未集成）、把「S1 typed job catch 未落地」改为「typed catch/typed WARN/同源 safe_message+结构化 summary 已落地（附主工作区行号）；`safe_exception_trace`、两个事件名、未知 hint、CLI 唯一提示仍未落地」；映射行 1-7 不需改（已核相容）。修订后由 Kimi/MiMo 对新 SHA 同版复审。验证点：`shasum -a 256` 三文件 diff 与 plan 记录一致；grep 确认 typed WARN/`safe_exception_trace` 落地状态与陈述一致。
- **修复风险（低/中/高）**: 低（记录性修订，约十行状态与 SHA 更新）。
- **严重程度（低/中/高/严重）**: 中。

### 2-未修复-低-CLI 命令层「发射先于 stderr 形成」与「try 后发射」的组合隐含控制流重构，形态未写明
- **位置**: decision 4（「CLI 仅在 `run_fins_direct_command` 最后一个 `except Exception` 且 `args.command_name == COMMAND_DOWNLOAD` 时准备 `fins.download.command_unexpected_failure` ERROR……**只在各自业务 `try` 语句及其 `finally` 正常结束后的语句位置**检查 `sys.exc_info() is None` 并发射……CLI 发射仍在固定 stderr/退出码形成之前」）。
- **问题类型**: 契约缺失（实施形态歧义）。
- **当前写法**: 「准备」在 except 内、「发射」在 try 语句正常结束后、「发射在固定 stderr/退出码形成之前」三句并列；但现有 `run_fins_direct_command`（`fins.py:176-222`）每个 except 分支直接 `render_cli_error(...)` + `return`，try 语句之后没有可达的后置收尾位置。
- **反例/失败场景**: 实施者若在 generic except 内「emit→render→return」，顺序句满足但违反加粗禁令（handler `emit` 失败时 `handleError` 沿 `sys.exc_info()` 复制原异常链到 stderr，F3 威胁复活）；若保持「render→return」只把标量暂存却不重构渲染位置，则发射永远不可达，unknown download 异常无诊断日志，违反 goal 信号 1。唯一同时满足三句的结构是：generic except 只暂存事件标量与待渲染消息/退出码，try 语句之后统一「检查 exc_info → 发射 → render stderr → 返回」，但 plan 未写出该重构，实施者需自行推导。
- **为什么有问题**: 与前轮 F1 同性质的「实施期无据设计决策」缺口；job 侧 decision 5 写了「outer job catch 只暂存……发射」动词分工故无此问题，CLI 侧缺对等表述。有验证兜底（S2-U「日志调用时断言 `sys.exc_info() is None`」会抓住 except 内发射；unknown 必留日志的 owner 流断言会抓住漏发射），故降为低。
- **直接证据**: `fins.py:216-222`（generic except 的 `render_cli_error` + `return EXIT_FAILURE`）；decision 4 原文；S2-U handler 自诊断断言的 `sys.exc_info() is None` 检查项。
- **影响**: 实施 Agent 可能在违反 F3 时序与漏发诊断之间二选一，或自行发明重构形态导致 review 争议与返工。
- **建议改法和验证点**: decision 4 补一句明确形态：「`run_fins_direct_command` 的 generic except 分支只暂存（安全串、固定事件名、待渲染错误消息、退出码）并在异常被 except 正常收口后落至 try 语句之后统一收尾，收尾顺序为检查 `sys.exc_info() is None` → 发射安全事件 → `render_cli_error` → 返回退出码；typed except 分支保持现有 render/return 行为不变」。验证点：S2-U 的 CLI 外层注入用例同时断言安全事件先于 stderr 输出形成、`sys.exc_info() is None`、退出码与 stderr 文本不变。
- **修复风险（低/中/高）**: 低（一段文字 + 一个既有断言细化）。
- **严重程度（低/中/高/严重）**: 低。

## Open questions

- **OQ-A（S1 实施形态待 code review，映射核对基线仍在动）**：S1 implementation 已完成但下一 gate 是 code review；其产品 hunk 未提交，code review 可能再改 typed catch/摘要形态。S2-U 前置的「逐行核对+不符即回 plan」机制已覆盖，但总控排期应把「S1 code review 后可能触发 S2 重基线」计入（本轮不作实施期断言）。
- **OQ-D（矩阵行 3 的 EXECUTION 前提与防御形状测试落地）**：矩阵行 3「单点 unwrap 后按 EXECUTION 投影」以非 typed cause 非 provider/非 OSError 为前提；本轮 grep 主工作区 `tests/` 无 `FinsSourceDownloadAdapterFailure` 直接构造，S1 计划第 57 段「非 typed 不获 reason」的防御形状测试未见落地。S2-U 断言需自行构造该形状（选 RuntimeError 类 cause 即满足前提），并注意若 S1 code review 补写了不同 cause 类别的防御测试，事件计数须按矩阵前提复核。
- **OQ-E（栈压缩自由度）**：decision 3「连续外部帧**可**压缩为固定 `[external]`」使同一选帧结果可产出不同可接受串（如 3 个外部帧可压成 1 个或保留多个 `[external]`）；S2-U 断言应按语法性质（含可信帧、`truncated`、`[external]`、总长有界、无原文）断言，不锁精确字节串，否则测试会固化偶然实现。建议 fix 时在 decision 3 注明「断言语法性质，不逐字锁压缩密度」。
- **OQ-B（terminalize 三重并存去重）**：依总控裁决留 S1/S2 集成后的 code review，本轮维持。
- **OQ-C（栈列表语法）**：已由 decision 3 逐字示例收敛，关闭。

## Residual risks 与建议跟踪去向

| 残余 | 去向 |
| --- | --- |
| direct RESULT 自身二次失败 / `threading.excepthook` 原始 traceback 泄漏（含与 CLI 发射时序的叠加） | `fins-direct-projection-failsafe`（plan 已登记；Finding 2 修法把 S2 发射从该链摘出） |
| 非 download CLI 外层 raw traceback、非 download job `str(exc)` durable message 及二次 WARN 的非 download 面 | `fins-other-raw-diagnostics-audit`（映射行 7 口径） |
| 异常链 cause/context/notes 全排除：根因在链中时诊断只剩表层 | `fins-other-raw-diagnostics-audit`（总控已裁） |
| revision conflict / repair blocked 落 EXECUTION 档分类与 direct/job 观测不对称 | `fins-download-storage-sibling-errors` |
| unsupported source direct/job 公开文案差异 | `fins-download-unsupported-source-public-consistency` |
| 无来源文档 hint 在默认临时日志下欠可操作 | `fins-download-no-source-retry-hint` |
| 跨奇异安装布局全部可信帧降级 `[external]` | closeout 记录（plan 已登记） |
| 默认临时日志退出即清理、`--quiet` 显式抑制 | 报告披露，不修（goal 允许） |
| 外部 provider/network 真实烟测可能阻塞 | 实施报告标注验证缺口，不冒充成功 |
| S1 code review 改动 typed 形态触发 S2 重基线 | OQ-A，S2-U 前置核对 |
| 取消竞争 + generic unknown 场景的事件计数未列入 S2-U 断言清单（decision 5 文字已规定「发现已有终态后……准备一次」） | 建议 S2-U 断言顺带覆盖；不阻塞 |

## Final plan review conclusion

**fail**（须按 plan 自设条款做记录性重基线小修订后 re-review；方向、单切片、S1 硬前置与 F1–F4 修复均无需推翻）。

本轮对 `f3643583…` 版的反证结果：前轮 F1–F4 全部修复成立——unknown 与 direct unsupported 的逐字 hint 分流已钉为同构谓词并有双向验收锚点；event-append/progress/typed/generic/unsupported 五处二次 WARN 的固定标识合同与 supersession 范围同源闭合，且与主工作区 S1 已落地的 typed WARN 形态一致；发射时序从位点（try 后、`sys.exc_info() is None`、禁 except/finally/传播路径）与数据（只暂存标量）双维封堵 handler 异常链复制，RESULT+handler 双故障有独立断言与分开记账；non-typed adapter cause 矩阵行与主工作区 catch 路由吻合。goal drift、切片白名单、逐文件覆盖率门槛、README 触发判定、pyright 要求、两层真实入口证据、LLM-facing 边界（hint 不含 CLI flag、安全栈不进 LLM 面）、安全栈单行语法（OQ-C 示例与选帧规则自洽）均未见 material 问题。

结论定为 fail 的唯一依据是 Finding 1：plan 第 22 行的两项 SHA 锁定在本轮复审前已漂移（S1 实施 hunk 与 accept 提交），状态陈述含可验证假句（「S1 typed job catch 未落地」实际已落地），按 plan 自己的「若漂移，停止并重新裁定基线」条款必须先重基线修订再复审。该修订为记录性小修（更新锁定值与 S1 状态时点，映射行七项经实读核对相容、无需改动），叠加 Finding 2 的一段 CLI 控制流措辞，合计约十余行 plan 文字。OQ2 硬前置依旧未满足（S1 implementation 尚待 code review、未 commit、未 integrated），本轮结论不构成实施许可。
