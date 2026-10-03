# Issue #198 S2 未知下载异常安全诊断 implementation plan — adversarial plan re-review（Kimi 第二路，第二轮同版复审）

RUNTIME/PROVIDER/MODEL: claude/kimi/kimi-k3[1m]
CANARY=kimi-ac5cdf23

- reviewed target：`docs/gateflow/issue-198-unknown-download-diagnostics-plan-20260929.md`（当前修订候选，实测 SHA-256 `f3643583a29577e6aedbc87e52243028453c38dbd5834607011abd43ab1da4b8`，与派发预期一致，无漂移）
- scope：MiMo 第二轮 F1–F4 修复闭合的反证（unknown 与 direct unsupported 逐字 hint 分流；event-append/progress/typed/generic/unsupported 二次 WARN 安全且同源；`sys.exc_info` 与 try/finally 时序避免 handler 原异常链；RESULT+handler 双故障；non-typed adapter cause direct/job 矩阵）；首轮 F1–F3 与 OQ1/OQ2 闭合；S1→S2 supersession 与 accepted+integrated 前置；goal drift、切片/白名单/覆盖率/README/pyright/真实入口证据、LLM-facing 文字、安全栈单行语法。不受总控既裁方向束缚。
- 边界：不修改 plan/goal/adjudication/产品/测试/README/既有 review/主工作区；不实施、不 commit/push/PR/merge、不派发子 Agent、不发外部消息；只新建本 artifact。
- artifact timestamp（系统时钟 `date +%Y%m%d-%H%M%S`）：`20260929-100231`。本文件名按派发指定，不使用 skill 默认命名。

## 证据基线与 SHA 锁定核查（stop condition）

| 锁定项 | 实测值 | 结论 |
| --- | --- | --- |
| 目标 plan SHA-256 | `f3643583a29577e6aedbc87e52243028453c38dbd5834607011abd43ab1da4b8` | 与派发预期一致，未漂移 |
| 本 checkout HEAD | `8d8d494fbbce0052372fb1b42097c9f7222cfa28`（S1 accepted plan 提交） | 与 goal/plan 声明一致 |
| 主工作区 S1 fix10 计划 SHA-256 | `2d18014ce605c8368d53247a43669f6ba597ecc875fe6d5a7b2ce558c0d92cd7` | 与 plan 第 22 行锁定一致 |
| 主工作区三产品文件未提交 diff SHA-256（`git diff -- dayu/fins/direct_events.py dayu/fins/ingestion_runtime.py dayu/cli/output.py \| shasum -a 256`） | `d9af4d09c3226616ccae2a9f2bd44281d1ad48021f9ced1d14b49291cf580783` | 与 plan 第 22 行锁定一致 |
| 主工作区 HEAD / 分支 | `8d8d494f…` / `codex/upload-material-oracle` | 未变 |
| 本工作区 `.venv` | 不存在（`ls .venv` → No such file or directory） | 与 plan 第 22/85 行陈述一致 |

S1 状态区分：本 checkout `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md` 为 HEAD 已接受版；主工作区同名文件为 S1 **在世候选 fix10**（其正文自述「未进入 S1/S2 implementation」，待双路 re-review），三产品文件为未提交候选 diff。`dayu.runtime.log.safe_exception_trace`、S1 typed job catch、`FinsSourceDownloadAdapterFailure`、`output.py` 唯一提示常量在本 checkout 代码中均无符号命中（grep 实测）——plan 第 22 行的「候选计划与当前代码分别观察，不冒充集成态」属实。SHA 无漂移，stop condition 未触发。

## Assumptions tested（结论）

1. **「未知判据 `kind == EXECUTION` 且非 `_UnsupportedDownloadSourceError'` 可在现有投影 owner 内窄分支实现」** — 成立。`_download_public_failure_from_exception`（`dayu/fins/ingestion_runtime.py:6823-6877`）的 default 分支（:6871-6877）同时服务未知异常与 direct `_UnsupportedDownloadSourceError`（:421，`RuntimeError` 子类，非 provider/非 OSError 必落此分支）；函数与异常类同模块，`isinstance` 窄分支可实现；direct unsupported 旧文案（`safe_message="下载执行失败"`、`retry_hint="请重新发起下载；若持续失败，请检查运行日志中的脱敏分类。"`，:6875-6876）与 plan 第 33/47/72 行逐字引用逐一比对一致。
2. **「取消不会误入 EXECUTION 未知诊断」** — 成立。direct 取消为轮询式（`_DirectCancellationChecker.__call__` 返回 bool，:2617-2650；`:4379-4385` 取消后 `_emit_direct_cancelled_result` 正常返回），不向 producer catch 抛异常；`FinsIngestionStartCancelledError` 仅在 durable job 创建前抛出（:9093），不到 producer。判据无取消误报。
3. **「deferred emission（业务 try 语句结束后、`sys.exc_info()` 干净时发射）与现有 owner 控制流相容」** — 成立（有实证）。`_run_direct_stream_producer`（:4304-4343）为 try/except/finally，finally 发 Done，post-try 语句位置在 RESULT 与 Done 之后、仅 `_emit_direct_result` 成功时可达；`_run_download_job`（:4936-4960）无 finally，except 后存在 post-try 语句位置；`run_fins_direct_command`（:176-222）末支 `except Exception` 可改为暂存标量后置发射。实证（python3 直跑）：外层 except 结束后 post-try 语句处 `sys.exc_info()` 为 `(None, None, None)`；异常对象在 except 内计算安全串后只暂存字符串可绕过 `except ... as exc` 的隐式删除。RESULT 投递失败则 post-try 不可达、S2 事件跳过——plan 第 45/73 行双故障断言与此结构一致。
4. **「共享 event-append/progress helper 的固定 WARN 收口可实现」** — 部分成立，存在一个未封死的内部矛盾，见 F1。代码事实属实：`_append_job_event_warn`（:6337-6350）与 `_emit_progress_event`（:6078-6092）均以 `error_type=%s` 填 `type(exc).__name__`；同一事件名 `fins.ingestion.job_event_append_failed`，可信枚举 `event_type`（terminal 由 `_terminal_event_type_from_status` 给出、progress 固定 PROGRESS）可区分两调用点。
5. **「公共失败与 durable job 同源、`result_summary={}` 形状可行」** — 成立。`_save_failed`（:5924-5942）`result_summary or dict(_EMPTY_SUMMARY)`，既有测试 `:5529/:10580/:11073` 断言 `result_summary == {}`；`failure_summary={"message": _bounded_text(..., reject_path_separators=False)}` 形状不变、仅 message 来源改 `safe_message`；`_run_download_job` generic catch（:4959-4960）处 `request` 在作用域内，新 helper 签名 `_save_download_failed_from_exception(job_id, request, exc)` 可落地。
6. **「S1→S2 七项映射与 S1 fix10 合同逐字相容」** — 成立。S1 fix10（主工作区，只读）§27 hint 逐字「请保存脱敏诊断并排查失败原因后重试。」与 `output.py` 独占提示、§28 两事件名/COMMAND_DOWNLOAD 分流/退役 `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`/非 download 文案逐字不变、§29 `safe_exception_trace` 指纹与帧校验合同、§49 adapter 私有 cause 白名单（`SourceIntegrityPreflightError | SourceIntegrityRevisionConflictError`）与单点 unwrap、§53 typed job catch 先于 generic + 固定 WARN `fins.download.typed_failed_record_save_failed`、§57 非 typed cause 防御测试形状、§91–94 四个残余登记，均与 plan 映射表/矩阵/决策的承接或取代声明一一对应；supersede `fins-other-raw-diagnostics-audit` 的 download 切片有书面声明并交总控同步索引。
7. **「安全栈单行语法已钉死且当前布局不退化」** — 成立。逐字格式与单行示例（`exception_type=RuntimeError custom_type=0123456789abcdef stack=dayu/fins/ingestion_runtime.py:4320 truncated [external]`，标注示例值）覆盖分隔符、`truncated` 落位、≤16 帧标记与总长度上限；实测 `dayu/**/*.py` 全部路径片段均为合法标识符（无命中反例），当前布局不会因标识符校验永久降级；`fins.download.*` 事件名在现有生产代码无冲突。
8. **「CLI 入口链与白名单闭合」** — 成立。`COMMAND_RUNNERS[COMMAND_DOWNLOAD]=run_fins_direct_command`（main.py:68）、`--log-file` 装配（main.py:99-109）、`_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`（fins.py:104）、外层 `_LOGGER.exception`（fins.py:216-222）、Service 链 `from_workspace_root`→`download`→`runtime.download`（fins_direct.py:151/163/183）全部属实；改动落点均在四个白名单生产文件内，`main.py` 无需改且不在白名单；`tests/cli/test_output.py`、`tests/service/test_fins_direct.py`、`tests/service/test_fins_wait_adapter.py`、`tests/runtime/test_log.py` 均存在；旧 CLI raw traceback 断言（test_fins_commands.py:3089-3128，含 `Traceback`/`RuntimeError`/秘密 marker 入 caplog）与 direct 秘密注入只查 RESULT（test_fins_ingestion_runtime.py:6055-6101）属实，迁移必要且已列入。
9. **「`dayu/runtime/log.py` 承载层中立 helper 不违反分层与模块政策」** — 成立。该模块仅依赖 stdlib 与 `dayu.contracts`/`dayu.runtime.log_levels`；模块政策要求层中立日志辅助显式接收调用点 logger——`safe_exception_trace` 只返回字符串、由调用点用自有 logger 发射，不冲突；`dayu/runtime/` 无 README，plan 的条件判定正确。
10. **「goal drift 检查」** — 未见漂移。共享 helper 日志收紧经 MiMo 二轮 F2 裁决纳入 owner 边界；未知 hint、事件名、深栈策略均直接映射 goal 信号 1/2；覆盖率/pyright/README/真实入口均为既有门禁的重述，未新增验收标准或未来 slice 工作。
11. **「发射 guard 的字面与语义」** — 字面不成立、语义在共享 helper 上有反例，见 F1/F2。

## Findings

### 1-未修复-中-共享 event-append/progress WARN 的发射 guard 在异常驱动终态化路径恒不成立，与 S2-U 注入断言及「非 download 仅收紧日志材料」承诺相互矛盾

- **位置**: plan「语义 owner、合同与实现决策」第 5 条（「两者须在自身 append 的 `try/except` 正常结束且 `sys.exc_info() is None` 后发射」「共享 helper 的其它操作仅随之收紧日志材料，不改变业务状态或结果」）、S2-U owner 流断言（第 72 行「向真实 download 失败链的 `job_store.append_job_event` 与 progress event 保存注入……断言固定事件和可信枚举参数之外无动态字段」）；映射表第 7 行 supersession 声明。
- **问题类型**: 契约缺失 / 状态机漏洞（发射位点约束与调用上下文冲突）/ 测试缺口（断言措辞预设了 guard 下不可能出现的记录）。
- **当前写法**: 共享 `_append_job_event_warn`/`_emit_progress_event` 在 helper 自身内层 try/except 结束后、且 `sys.exc_info()` 干净时发射固定 WARN；download 失败链注入 append 失败要断言固定事件记录；非 download 调用只改日志材料。
- **反例/失败场景**: terminal event append 发生在 `_save_failed` 尾部（:5941 `_append_terminal_job_event_warn(saved)`），而 download 失败收口时整条调用链处于 `_run_download_job` 的 `except Exception` 动态作用域内（:4959 → `_save_download_failed_from_exception` → `_save_failed` → `_append_job_event_warn`）。实证（python3 直跑）：外层 except 活跃时，内层 helper 在其自身 try/except 结束后的语句处 `sys.exc_info()` 仍返回**外层业务异常**（`(<class 'RuntimeError'>, RuntimeError('business-secret'), ...)`），非 `(None, None, None)`。因此按 plan 字面，helper 级 guard 在 download generic/unsupported、S1 typed、乃至 upload/preprocess 的异常驱动终态化中**全部抑制该 WARN**——而 S2-U 第 72 行对「真实 download 失败链」的 append 失败注入要求断言固定事件记录（预设发射），二者不可同时成立。若实施者为让断言可观测而撤掉 guard，则 append 失败后立即发射时 emit 异常的 `__context__` 沿动态作用域链回业务异常，handler 自诊断 `handleError` 的 `print_exception` 会把业务异常消息/traceback 打到 stderr——MiMo F3 要堵的泄漏原样复活。
- **为什么有问题**: guard 是防泄漏的承重墙（实证：无 guard 时 post-try 立即发射仍经 `__context__` 复制业务异常），但 plan 没有陈述「活动异常期 append 失败 WARN 被抑制」这一取舍，也没有给 terminal-append WARN 指定经 owner 链暂存到 job 后置发射点的机制（`_save_failed` 被 success/upload/preprocess 共用，暂存机制会扩大其合同，plan 明文说不动其它操作）；同时「非 download 仅收紧日志材料」在抑制读法下不成立（upload/preprocess 终态化期的既有 WARN 会消失，属行为变化而非材料收紧）。
- **直接证据**: `dayu/fins/ingestion_runtime.py:5941`（`_save_failed` 内 append）、:6015-6036、:6299-6350（helper 内层 try/except 与 WARN）、:4936-4960 与 :4912-4913/:5051-5052（download/upload/preprocess 三条异常驱动收口路径）；本 review「Assumptions tested」第 3/4 条的 python3 实证输出；plan 第 46/72 行原文。
- **影响**: 实施 Agent 必须在「静默丢弃终态化期 append 失败诊断（且未披露、殃及非 download）」与「撤销 guard 复活 handler 链泄漏」之间无据二选一；S2-U 断言按现措辞可对 terminal-append 注入空转通过（无记录可断）或硬失败；code review 必打回。
- **建议改法和验证点**: 在 decision 5 钉死发射条件矩阵，二选一：(a) 明示「活动异常期的 append/进度保存二次失败 WARN 一律抑制，作为防链泄漏取舍」，把 S2-U 的 terminal-append 注入断言改写为「无 `fins.ingestion.job_event_append_failed` 记录且无任何秘密字节」、把进度事件注入限定在正常执行流（无活动异常）断言固定字段，并在残余段披露该观测损失（含非 download 终态化路径）；(b) 规定 append 失败在 helper 内层 catch 只暂存固定标识，由 download 收口 owner 沿既有「helper 返回待发标识 → outer job catch 暂存 → 业务 try 后发射」机制统一后置发射，并说明共享 `_save_failed` 链的暂存边界不涉及非 download 行为。验证点：注入 terminal-append 失败 + handler 自诊断失败双故障，断言 stderr 无业务异常链且发射行为与所选矩阵逐字一致。
- **修复风险（低/中/高）**: 低（数行计划文字 + 断言对齐；选 (a) 不改控制流，选 (b) 需把暂存边界写清）。
- **严重程度（低/中/高/严重）**: 中。

### 2-未修复-低-`sys.exc_info() is None` 字面规格在 Python 中恒为 False，与本 plan 自立的逐字精度标准不一致

- **位置**: decision 4（「检查 `sys.exc_info() is None` 并发射」）、decision 5 两处（helper 与 outer job catch）、S2-U handler 自诊断断言（第 73 行「日志调用时断言 `sys.exc_info() is None`」）。
- **问题类型**: 不可直接实施（字面规格恒假）。
- **当前写法**: 以 `sys.exc_info() is None` 作为「无活动异常」判据，共四处。
- **反例/失败场景**: `sys.exc_info()` 返回三元组，无活动异常时为 `(None, None, None)` 而非 `None`（实证：`sys.exc_info() is None` → `False`）。字面实施将使全部 S2 诊断事件与固定 WARN 永不发射；发射存在性断言会失败从而被测试捕获，但实施者被迫自行猜测正确写法（`sys.exc_info()[0] is None`），且四处措辞相同、猜测方向不一致时 guard 语义可能分叉。
- **为什么有问题**: 本 plan 对 hint 文案、事件名、单行栈格式均要求逐字钉死，唯独这个承重判断条件写成恒假字面；同一份文档的精度标准不自洽。
- **直接证据**: python3 实证输出（`literal check sys.exc_info() is None: False`、`tuple form: (None, None, None)`）；plan 第 45/46/73 行原文。
- **影响**: 实施期无据改写或局部分叉；属低风险但必须修文字。
- **建议改法和验证点**: 四处统一改为「`sys.exc_info()[0] is None`（当前线程无活动异常）」或等价精确表述；验证点：发射点单测同时断言「发射时无活动异常」与「未知异常下事件确实发射」。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## 旧 finding 闭合复核（反证结果）

| 来源 | 裁决状态复核 | 直接证据 |
| --- | --- | --- |
| 首轮 F1（类型塌缩+深栈吞帧） | **闭合成立（计划层）**：内建祖先身份证实 + SHA-256 指纹 + 最深可信 Dayu 帧替换尾窗最早非末端槽位 + `[external]`/`truncated` 固定标记 + 单行逐字示例；映射表第 2 行书面声明取代 S1 仅末 16 帧策略 | plan decision 3/第 31 行；S1 fix10 §29；标识符全量核对无反例 |
| 首轮 F2（S1 合同互斥） | **闭合成立（计划层）**：七行 supersession/消费映射逐项对应 S1 fix10 §27–29/49/53/57/91–94，逐字文案一致；硬前置 + 逐行核对 + 漂移即停 | plan 第 24–36/67/94 行；S1 fix10 实读 |
| 首轮 F3（sibling 不对称） | **闭合成立**：EXECUTION sibling 矩阵第 2–4 行固定 direct/job 政策，残余归 `fins-download-storage-sibling-errors` | plan 第 51–58 行；S1 fix10 §92 |
| MiMo 二轮 F1（hint 判据/unsupported 共享分支） | **闭合成立**：decision 6 判据与 decision 1 同构、owner 内窄分支、unsupported 逐字旧文案保留且不与安全事件挂钩；核对清单与 S2-U 断言同时钉两种逐字文本 | plan 第 33/47/67/72 行；ingestion_runtime.py:6871-6877、:421、:4957-4958 |
| MiMo 二轮 F2（event-append/progress 动态类名） | **内容合同闭合、发射条件未闭合**：去 `type(exc).__name__`/动态字段的收口与 supersession 归属已钉死（:6337-6350、:6078-6092 事实相符），但发射 guard 与注入断言/非 download 承诺矛盾，见本 review F1 | plan 第 46/36/72 行；本 review F1 |
| MiMo 二轮 F3（finally/传播期发射+双故障） | **闭合成立（计划层）**：发射钉为业务 try 及 finally 正常结束后的语句位置、禁 except/finally/传播路径；RESULT+handler 双故障跳过 S2 事件且 RESULT failsafe 残余单独记账；producer/job/CLI 三处控制流实读可行 | plan 第 45/46/73 行；ingestion_runtime.py:4304-4343、:4936-4960；fins.py:176-222；python3 实证 |
| MiMo 二轮 F4（non-typed adapter cause 矩阵） | **闭合成立**：矩阵第 3 行（adapter 携非 typed cause：direct 记一次/job typed catch 不记）与 S1 §49/§57 防御形状合同一致 | plan 第 57 行；S1 fix10 §49/§57 |
| OQ1（handler 自诊断边界） | **闭合成立**：stderr 允许 handler 自身 stack、`Message:`/`Arguments:` 限固定事件名与安全串、`threading.excepthook` 无原异常、覆盖 logger 直接抛错路径 | plan 第 73 行；stdlib `handleError` 行为核对 |
| OQ2（S1 accepted+integrated 硬前置） | **未满足且如实承载**：plan 明示不得实施、只可 re-review；三处 SHA 今日复核无漂移 | plan 第 67/93-94 行；本 review 基线表 |
| OQ-B（三 helper 去重） | **处置合理**：留 S1/S2 集成后 code review 按实际 owner 裁决，不预造跨操作 god helper | plan 第 93/95 行 |
| OQ-C（栈单行语法） | **闭合成立**：逐字单行示例与分隔/截断/上限规则已补 | plan 第 44 行 |

## Open questions

- **OQ-A（S1 合同真源仍在动，沿 MiMo 二轮 OQ-A）**：S1 fix10 自身尚待其双路 plan re-review，七项映射的「S1 合同」仍是候选；plan 的重基线/重审触发机制已覆盖，但 S1 终审后映射行重排成本应由总控排期计入。本 review 对一切 S1 后置行为只作条件判断。
- **OQ-B（F1 修法选择）**：抑制（取舍披露）与暂存后置发射（机制扩展）两条修法对 shared `_save_failed` 链的爆炸半径不同，建议总控裁决时明确取舍，避免实施期再裁。

## Residual risks 与建议跟踪去向

| 残余 | 去向 |
| --- | --- |
| direct RESULT 自身二次失败 / 线程钩子输出原始 traceback（含与 handler 双故障叠加） | `fins-direct-projection-failsafe`（plan 已登记，S2 断言与报告分开，正确） |
| 非 download CLI 外层 raw traceback、非 download job `str(exc)` durable message、`_save_failed_from_exception` 既有 `exc_info=True` WARN（ingestion_runtime.py:6011，非 download 面） | `fins-other-raw-diagnostics-audit`（按映射表第 7 行收窄为非 download，closeout/文档索引同步归属） |
| 异常链 cause/context/notes 全排除：根因在链中时诊断只剩表层 | `fins-other-raw-diagnostics-audit` 后续判断 |
| revision conflict / repair blocked 落 EXECUTION 档分类与 direct/job 观测不对称、adapter 非 typed cause 业务分类 | `fins-download-storage-sibling-errors`（矩阵第 2–4 行已固定观测政策） |
| unsupported source direct/job 公开文案差异；direct unsupported 旧 hint 指向「运行日志中的脱敏分类」但该路径不产生安全事件 | `fins-download-unsupported-source-public-consistency`（plan 已登记，S2 逐字保留正确） |
| 无来源文档 hint 在默认临时日志下欠可操作 | `fins-download-no-source-retry-hint`（plan 已登记） |
| 跨奇异安装布局全部可信帧降级 `[external]` | closeout 记录（plan 已登记；当前布局 >16 外部帧保留可信帧属 blocking validation） |
| 默认临时日志退出即清理、`--quiet` 显式抑制 | 报告披露，不修（goal 允许） |
| 外部 provider/network 真实烟测可能阻塞 | 实施报告标注验证缺口，不冒充成功 |
| 活动异常期 append/进度二次失败 WARN 的处置（抑制或后置） | 本 review F1 修法落地后按所选矩阵登记 |
| S1 合同重排成本 | OQ-A，总控排期 |

## Final plan review conclusion

**fail**（小范围 plan fix 后 re-review；方向、单切片、supersession 结构与 S1 硬前置均无需推翻）。

与上一轮（MiMo F1/F2 中项）相比，本轮候选已把 hint 判据分流、二次 WARN 内容合同、发射位点与双故障、防御形状矩阵、栈单行语法全部落文本，三处 SHA 锁定今日复核无漂移，代码事实抽查（投影 owner、job 收口、两个共享 helper、CLI 三文件、测试夹具与旧断言）全部属实。剩余缺口只有两处且均为「合同钉死缺失」：F1（中）使共享 helper 的防链 guard 与注入断言、非 download 行为承诺三者不可同时成立，实施者必须在「静默丢诊断且殃及非 download」与「撤 guard 复活泄漏」之间无据二选一；F2（低）是四处恒假字面规格。两项修法合计约十行计划文字与断言对齐，建议总控裁决后交 Sol 一次性修订，再行 Kimi/MiMo 同版 re-review。OQ2 前置依旧未满足，本轮结论不构成实施许可。
