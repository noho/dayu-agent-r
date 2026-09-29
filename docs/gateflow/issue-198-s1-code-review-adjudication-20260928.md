# issue #198 S1 code review 总控裁决

- Gate：`code review -> fix`；work unit：`issue-198-download-failure-projection`，slice：S1。
- Reviewed target：`codex/upload-material-oracle` HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28` 上未提交的 S1 允许代码、测试、README 句子；点号元数据 hunk 与 oracle docs 不属于本 review。
- 双路 artifact：`docs/reviews/code-review-20260928-203426.md`（Kimi）、`docs/reviews/code-review-20260928-222640.md`（MiMo）。总控已读取两份完整 artifact、原 plan、S1 实施记录及相关代码/README diff；两路都报告 450 个受影响测试通过、pyright 0 错误。总控另以 Coverage.py 验证 `dayu/cli/output.py` 84%、`dayu/fins/direct_events.py` 87%、`dayu/fins/ingestion_runtime.py` 91%。真实 CLI 属 issue 后续验证，未由 S1 review 证明。

## 外部派发结构化核验

| label | runtime/provider | setup_status | agent_status | tool_evidence | canary_status | warnings | retry_class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `issue198-s1-review-kimi-20260928-01` | `claude/kimi` | ok | completed | yes | match | `[claude-code:unrecognized_model]` 精确白名单提示 | none |
| `issue198-s1-review-mimo-20260928-01` | `claude/mimo` | ok | completed | yes | match | `[claude-code:unrecognized_model]` 精确白名单提示 | none |

两路各用独立 `--cwd /Users/leo/workspace/dayu-agent-r`、output/stderr 与 canary；均退出 0、Claude JSON `subtype=success`、`is_error=false`、有 `result`，Kimi 70 turns、MiMo 106 turns。总控核对报告 token 与各自 `canary.expected` 一致；无非白名单 stderr。review agent 不修改 S1 产品代码。

## Findings 与修复登记

| 来源 | 裁决 | 理由、修复 owner 与完成信号 | 当前状态 |
| --- | --- | --- | --- |
| MiMo F1：CN/HK 单 filing 的 `SourceIntegrityPreflightError` 被 `cn_download_workflow.py` 宽 except 变成 `filing_execution_failed` | **accepted** | 直接调用链表明 typed reason 在 Fins 唯一投影点之前丢失，违背已确认的 preflight 保真目标；不能只缩窄 README。先修订 approved plan 的 S1 allowed files 与测试，Kimi/MiMo plan re-review 后，由 Sol 在 CN workflow 的错误边界透传该 typed preflight，并以走真实 workflow 的测试固定 public storage reason；再双路 code re-review。 | 未修复；plan amendment pending |
| MiMo F2：公共 enum 缺反向全集断言 | **accepted** | public reason 四值封闭是 S1 合同；在 owner 测试断言映射值全集恰等于公共 enum，全量映射双向防漂移，不在运行时加第二份白名单。 | 未修复 |
| MiMo F3：CLI `reason=` 同时表示文档自由文本与失败枚举码 | **accepted** | 同一输出中的两个语义同名，改失败详情标签为 `reason_code=`，与 public JSON 字段一致；文档行 `reason=` 保持旧语义。先更新 plan S1 的 CLI 合同与 README 句，再改实现和测试。 | 未修复；plan amendment pending |
| Kimi F1 / MiMo F4：`reason_code=None` 的 CLI 占位分支无断言 | **accepted** | 恢复 EXECUTION 无细分原因的 CLI 渲染用例，固定 `classification="execution"` 与 `reason_code="-"`（随 F3 标签裁决），并保留 storage reason 用例。 | 未修复 |
| MiMo F5：相邻 README 句不能用 `git add -p s` 按 hunk 拆开 | **accepted** | S1 实施 artifact 的“可按 hunk”表述错误；改为“同一 hunk，可通过 patch 编辑按行分别 stage”。提交前检查 staged patch 只含 issue 句，不含点号句。 | 未修复；artifact/staging 待核 |

MiMo 所述统一 retry hint 对 repair-required 原因是否足够具体：**needs-more-evidence**，当前四值均提示检查并修复来源状态，不存在直接证据证明错误；不在 S1 凭推测拆分提示。Kimi 指出的 storage 异常构造器无 runtime enum 校验：**deferred-with-owner** 至 `fins-direct-projection-failsafe` 的 owner 审查，当前生产 raise 点为 enum 且 S1 已有全量映射测试。计划已列 S2 与其它三项独立 residual work unit，保持原分类。

## 当前 gate 与下一步

S1 review loop **未通过**。当前 gate 为 `code review -> fix` 的 plan amendment 前置：Sol 先修订已接受 plan，使 F1/F3 所需新增文件、接口标签和真实 workflow 测试明确归属已确认 goal；Kimi/MiMo 并行 plan re-review 通过后，Sol 修 S1 代码/测试/实施 artifact，双路 code re-review，并完成 staged hunk 核对及 accepted slice commit。不得在 plan 未扩容时直接修改 `cn_download_workflow.py`。S2 尚未开始。

残余风险分类：未知异常脱敏日志由同一 issue 的 S2 覆盖；`fins-direct-projection-failsafe`、`fins-download-storage-sibling-errors`、`fins-other-raw-diagnostics-audit`、`fins-download-no-source-retry-hint` 分配给后续 work unit；点号元数据归独立 storage work unit；真实隔离 CLI 与网络/provider 条件属于 issue 级待取得验证证据。无未分类风险。

## S1 plan amendment 第一次双路复审追加裁决

Kimi artifact：`docs/reviews/plan-review-20260928-225425.md`，结构化成功、canary 匹配；MiMo artifact：`docs/reviews/plan-review-20260928-230609.md`，结构化成功、canary 匹配。两路均独立核实 CN workflow 的 typed 吞点、透传链、enum 双向全集、CLI `reason_code=` 与 `None`、README 同 hunk 按行 staging。Sol amendment 派发虽退出 0、canary 匹配，但有一条失败的 `apply_patch` 工具事件与对应非白名单 stderr；按 sub-agents 协议 **agent_status=failed**，落盘 plan 仅作经总控和两路 reviewer 独立核验的候选，不计为派发成功。

| 新 finding | 裁决 | 修复要求与状态 |
| --- | --- | --- |
| MiMo R1：多 filing 中途 typed abort 的摘要归零与已发布状态冲突 | **accepted** | 直接代码证据：CN pipeline event collector 在异常时丢弃已收集结果，producer 用 `_empty_download_summary_from_request` 发全零摘要，可能已有前一份文档发布。不能采用 reviewer 给出的“公共摘要归零、重跑 skip 收敛”的最小选项；它会违反 AGENTS.md 的 durable/RESULT 同一业务事实一致性和既有守恒合同。Sol 必须在 plan 中选出正确 owner，定义中途 typed 失败时如何保留已完成文档事实与失败原因的同源 typed 投影、是否终止后续候选、如何避免重复/丢失 RESULT；以真实多候选测试固定 durable state、public summary、进度与 retry/skip。若需扩展 S1 文件清单，在 plan 内说明与原 goal 的直接对应并重新双路复审；不得从日志、展示行或时间顺序反推部分进度。**未修复，plan review 阻塞**。 |
| MiMo R2：Phase B staged UNSAFE 测试触发配方不明确 | **accepted** | 测试通过 fake discovery 的下载回调在 Phase A 后、`begin_batch` 前写入真实仓储非法条目，使真实 storage classifier 抛 typed 异常；不得 monkeypatch classifier 返回 UNSAFE 冒充 owner 事实。断言路径穿过新透传边界、无普通 `filing_execution_failed` 行、batch 回滚与已发布文件不变。**未修复**。 |
| Kimi R1：透传边界 Raises docstring 未更新 | **accepted** | 在 S1 allowed code fix 中同步更新 `run_cn_download_stream_impl` 中文 Raises，声明 typed preflight；既有 revision-conflict 传播可一并准确列出。**未修复**。 |

MiMo 关于 commit-time whole-kind typed failure 的入口：**needs-more-evidence**，Sol plan 应沿现有 storage batch owner 判定可否同一多候选测试覆盖，并在 S1 code review 明确实际覆盖或免测理由。Phase B 回滚后提示是否仍可操作保持前述 **needs-more-evidence**，不得凭推测拆分公共 hint。当前 gate 仍为 S1 `code review -> fix` 的 plan amendment/re-review 前置；S2 不得开始。

## S1 plan amendment 第二次双路复审追加裁决

Kimi `docs/reviews/plan-review-20260928-234908.md` 与 MiMo `docs/reviews/plan-review-20260928-235129.md` 已完整读取，均为 `pass-with-risks`。两路进程退出 0，Claude JSON `subtype=success`、`is_error=false`，分别 61/77 turns，canary 与各自 expected 逐字匹配，stderr 仅精确白名单 `[claude-code:unrecognized_model]` warning；显式 `--cwd /Users/leo/workspace/dayu-agent-r`、独立 output/stderr。Sol 第二次 plan fix 的 JSONL 结构化通过、无失败事件；此派发状态与第一次失败 amendment 分开登记。两路与总控独立代码核对均确认：私有 typed abort → adapter 已验证 summary → Fins 唯一 public failure/RESULT 的主链在现有单向依赖上可实现；`FAILURE + PARTIAL_FAILURE` 放宽只作用于 owner 合同；Phase B mutation 不会在 `begin_batch` 或循环前 whole-kind 预检提前失败。以下是仍必须落盘的修复项：

| 新 finding / question | 裁决 | 直接依据、owner 与下一步状态 |
| --- | --- | --- |
| Kimi F01：后台 download job 在中途 typed abort 后将 `result_summary` 写为 `{}` | **accepted** | `_run_download_job` 的宽 catch 经 `_save_failed_from_exception` 默认空摘要，而前一候选可能已发布；这与 direct RESULT 使用已验证部分摘要、durable state 使用同一业务事实的 AGENTS 约束冲突。**拒绝**“保留空摘要并列残余”方案。S1 plan 明确 job typed 收口消费 `FinsSourceDownloadAdapterFailure.persisted_summary.to_json_summary()`，以现有 typed owner 校验后的对象保存 failed record，不从事件/日志重建；真实多候选 job 测试断言 durable result_summary 与已发布/失败事实守恒、安全 failure message。允许文件/测试须相应列明。**未修复，plan 前置阻塞**。 |
| Kimi F02：post-repair gate/company meta commit 在至少一 filing 后仍可能 typed 逃逸并归零 | **accepted** | `cn_download_workflow.py:332-355` 位于单 filing catch 外，filings 已有终态行；“whole-kind 必在首候选前”只适用于初始 preflight。**拒绝**“保留 raw 透传与零摘要”作为本轮残余。S1 plan 把后置 typed preflight/commit 的收口归 CN workflow，同样用当前 `filings` 快照形成私有 abort，原 storage reason 仍由 Fins 投影；真实可控 mutation 测试核对已发布事实与单一失败 RESULT/后台 record，或如机制无法安全注入则给出明确可审的 owner 级测试与未覆盖风险。初始循环前无 filing 的 typed 仍可 raw 透传与零候选摘要。**未修复，plan 前置阻塞**。 |
| MiMo F1 / Kimi OQ1：fresh 候选二 Phase B 注入目标目录取得方式不明确 | **accepted** | `get_source_document_locator` 需要已发布 meta，不能定位未发布候选；误放其它目录会使 exact-target 仍 MISSING 并把失败推迟到 commit whole-tree。测试可调用 storage 的私有 identity 派生 helper，**不能在测试重算哈希**；plan 钉死目标目录构造及 `classify_staged_source_integrity`、batch begin/rollback、无 reset/commit 的断言。**未修复**。 |
| MiMo OQ：“adapter 启动前”限定、同步 `CnPipeline.download` Raises | **accepted（计划文字/契约）** | 零摘要还有 adapter 已启动后的初始 whole-kind typed；修 plan 限定为“尚无已处理候选的其它异常”，不凭启动时点猜状态。同步包装同样透传私有 abort，中文 Raises 与实际路径一致。**未修复**。 |
| Kimi OQ3：commit-time whole-tree typed 多候选测试 | **needs-more-evidence** | 保持既有要求：实施/code re-review 用直接 storage 调用链说明能否真实命中；不能用 classifier monkeypatch 伪造。若可命中，采用同源 abort/summary；若不在可控当前 slice 测试范围，明列免测理由与残余去向。 |

上述 F01/F02 是同一 S1 typed failure 透传后的消费者/收口完整性，不新增 issue 目标或独立 slice。直接代码链证明若只修单 filing direct RESULT，会形成“显示正确但 durable 错误”；小概率 post-repair 窗口也不能保留已知不一致。Sol 仅修 plan，扩充 S1 allowed files、调用链、测试和 stop condition；Kimi/MiMo 对新增点再双路 re-review 后进入代码 fix。当前 gate 仍为 S1 `code review -> fix` 的 plan 前置，S2 仍未开始。

## 第三次 plan re-review 派发异常（2026-09-29）

Sol 第三次 plan 修订 `issue198-s1-plan-fix3-sol-20260928-01` 的 Codex JSONL 结构化完成、无失败 event，canary 匹配；只修改 plan，既有 S1 产品 diff 指纹未变。Kimi `issue198-s1-plan-rereview3-kimi-20260929-01` 预检通过且独立 `--cwd /Users/leo/workspace/dayu-agent-r`、output/stderr，运行 47 turns 后退出 1；Claude JSON `is_error=true`、`terminal_reason=api_error`、`api_error_status=403`，原因明确为 Kimi 五小时额度耗尽。虽然 `subtype=success`，该派发按协议 **agent_status=failed**，不能当作第三次 plan review 通过；stderr 的模型名白名单提示不是本次失败原因。MiMo 同轮尚在运行，待其结束并经结构化检查后读取完整 artifact。Kimi 可用后以新 label 修复性重派；在双路复审与总控裁决完成前，S1 code fix 和 S2 均不得开始。本节只登记派发事实，不把 plan 文本状态冒充代码已修复。

修复性同 provider 重派 `issue198-s1-plan-rereview3-kimi-codex-20260929-02` 使用 `codex-agent-run --provider kimi`、显式绝对 `--cwd`、独立 output/stderr，预检 `setup_status=ok`；进程退出 1，JSONL 连续五次 `403 Forbidden` 重连后 `turn.failed`，未产生 regular final message 或 review artifact，`agent_status=failed`、`tool_evidence=no`、`canary_status=not_run`。这证实 Claude 与 Codex 两个 runner 都受当前 Kimi 服务额度/授权 403 阻断；本窗口不继续无限重派。仍以 MiMo 独立结果和总控证据分析推进不依赖 Kimi 的计划裁决准备，双路 gate 待外部额度恢复。两次 Kimi 失败都不是产品/计划 finding。

## 第三次 plan re-review 的 MiMo 裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-003021.md` 已完整读取；进程退出 0，Claude JSON `subtype=success`、`is_error=false`、73 turns、canary 匹配，stderr 只有模型名白名单提示，独立绝对 `--cwd`/output/stderr，`agent_status=completed`。该路确认 fix3 对前轮 job 空摘要、post-repair typed、fresh Phase B 目标与 Raises 的计划层修复方向成立，但报告四项仍须裁决的漏洞。Kimi 本轮两次 403 失败，**没有有效第二路 review**，不能把 MiMo 的 `pass-with-risks` 冒充双路 gate pass。

| 新 finding / question | 总控裁决 | 直接依据、owner 与完成信号 | 状态 |
| --- | --- | --- | --- |
| MiMo F1：post-repair revision conflict、非 typed commit 失败仍让既有 filings 归零 | **accepted** | `cn_download_workflow.py:332-355` 在已完成行后仍可抛 `SourceIntegrityRevisionConflictError`；`_validate_complete_source_kind_tree` 可抛 ValueError，后置 release 可抛非 typed。sibling 异常的**业务分类**延期不等于允许已发布摘要归零。计划应在这一后置窗口用同一私有 filings 快照收口所有异常，保留原 cause，由 Fins 唯一分类（非 preflight 仍按现有 EXECUTION/STORAGE），direct/job 同源；不得从日志/事件反推。post-commit release 的文档行已完成事实仍保留，若出现不能判定 durable 文档状态的实际路径则触发 stop condition，而非假造摘要。真实 revision conflict + precommit ValueError/typed 测试与后置 release 代码边界说明。拒绝仅把已知归零列残余，理由同前轮 F02。 | 未修复，plan 前置 |
| MiMo F2：`FinsResultSummary` 放宽谓词对 OSError-STORAGE 不够精确 | **accepted** | owner 校验必须要求 `failure.reason_code is not None` 且为封闭公共 enum；仅 `failure.kind=STORAGE` 不够。测试明确拒绝 `STORAGE + reason_code=None` 的 `SUCCEEDED/PARTIAL_FAILURE` 失败摘要。 | 未修复 |
| MiMo F3：`FAILURE` 与 document `SUCCEEDED` 同帧进入 LLM-facing wait JSON | **accepted** | 文档行的机械终态与整体请求失败是不同事实，不能用错误计数篡改。计划把含 `download.terminal_disposition` 的失败 JSON 投影交给 `dayu/service/fins_wait_adapter.py`，加一条固定、业务可读的 scope 说明：download 只统计已处理文档，`status`/`failure` 是整体结果；同时断言这条说明、失败状态和修复提示同帧。不得要求 LLM 从内部类型名推理；如必须新增公开 schema 字段则停下重新 goal 裁决。 | 未修复，新增直接投影文件需列 S1 scope |
| MiMo F4：job typed catch 二次保存失败可逃出 `_run_download_job` | **accepted** | 复用 `_save_failed_from_exception` 的终态幂等与二次落盘失败 WARN 收口 pattern，仍从 `persisted_summary.to_json_summary()` 得唯一摘要；测试注入保存失败确认不逃出、不能虚称 record 已终态。 | 未修复 |
| MiMo OQ1：fresh 候选 identity 前提 | **accepted（测试配方）** | 写明候选二 fresh、无既有 source_id 绑定、非 period-corrected；若 HK/纠正场景使用生产绑定结果，不在测试重算 hash。 | 未修复 |
| MiMo OQ2/OQ3：company meta 与非点号注入 | **accepted（测试断言/措辞）** | 后置失败测试核对 company meta 旧值；非法条目必须非点号，避免独立点号元数据 work unit 的忽略规则改变触发位置。 | 未修复 |
| MiMo OQ4：commit-time whole-tree typed 可真实触发 | **accepted（实施证据）** | reviewer 已追到 root stray 在 exact-target/MISSING 未升级、copytree 入 staging、whole-kind commit 抛 typed 并 precommit 回滚；S1 code fix 应以此真实测试或更强直接证据，不再把可行性留成泛泛问号。 | 待实施 |

F1 的后置窗口守恒与 F3 的 LLM-facing 消歧均是同一个 S1 失败摘要 contract 的直接消费者，属于原 goal 的保真目标，不新增业务分类或 schema。Sol 下一步只修 plan（包括 allowed files/测试/stop 条件），再取 Kimi/MiMo 双路有效 re-review；现有产品代码仍只是一轮 S1 候选，S2 不得前移。

## Sol fix4 stop 与 RESULT owner 补充裁决

`issue198-s1-plan-fix4-sol-20260929-01` 预检通过，Codex JSONL 68 events/30 个成功 command、无失败 event、`turn.completed`、空 stderr、canary 匹配，`agent_status=completed`；**按任务 stop condition 主动停止且未修改 plan**。直接冲突：前节 F1 要后置 revision conflict / 非 typed 异常也保留已完成 document rows，而前节 F2 错把 `FAILURE + SUCCEEDED/PARTIAL_FAILURE` 的准入限定为 `reason_code` 非空。revision conflict 为 EXECUTION、OSError 为 STORAGE 且均可 `reason_code=None`；两者在已发布行后仍须守恒。Sol 停止是正确的，不可用空摘要或强造 FAILED 行绕过。

总控重新核对 `FinsDownloadPublicSummary.__post_init__` 的 counts/terminal 机械校验与 `FinsResultSummary.__post_init__` 的外层组合校验后，**修订 F2 裁决**：失败请求可以携带任一已验证的、由已处理 document rows 派生的 `FinsDownloadPublicSummary`，其 `terminal_disposition` 可为 `FAILED`、`PARTIAL_FAILURE` 或 `SUCCEEDED`；外层 `status=FAILURE` 必须有 `FinsPublicFailure`，成功/取消组合仍按原契约拒绝。此放宽不按 `failure.kind` 或 `reason_code` 猜测已处理事实。reason_code 只描述失败原因家族，不能充当“摘要已验证”的凭据；封闭 enum 也不能证明发布进度。真正 provenance 在 CN workflow 持有的 filings 快照、adapter 的严格 `FinsDownloadResultSummary` 投影和 Fins owner 的公共 summary 构造链。该模型既接受 `OSError-STORAGE + reason_code=None` 在**真实后置失败**时的 SUCCEEDED 摘要，也允许构造者提供同形 typed public result；结果 dataclass 本来无法独自证明外部 durable 事实，测试必须覆盖 owner 调用链与同源状态，而不是增加伪证明 flag/额外 payload。无 failure、无 download、错误 counts/disposition、成功/取消与 failure 混用仍须拒绝。前节 F2 的“拒绝 OSError-STORAGE 无 reason”断言**撤销**，以此新契约为准；这不是放宽 storage 分类，而是把文档终态与操作终态分开。

F1 后置窗口仍按原 accepted 守恒要求执行；F3 的 wait adapter 给 LLM 的 scope 说明可作为仅该投影的业务可读文本，不改变 `FinsResultSummary` / `FinsDownloadPublicSummary` 的持久或公共字段。若 `commit_batch` 后置 release 失败导致**文档 durable 事实**不确定，保留 stop condition；不能用现有 filings 列表猜测尚未确认的发布。Sol 以新 label 修 plan 后需重新双路 review，S1 代码仍不得先改。

边界澄清：上文“后置窗口所有异常”指应形成 **FAILURE** 的普通/typed 异常；`CnDownloadCancelledError` 是现有取消控制流，外层已保留 `filings` 构造 cancelled 摘要，不得被 broad `except Exception` 抢先改成 FAILURE。任何计划中的后置 catch 必须先保留取消语义及既有单一终态事件合同。

## Sol fix5 stop 与 storage 不确定发布状态边界

`issue198-s1-plan-fix5-sol-20260929-01` 预检 ok、进程退出 0，JSONL 105 events/49 个成功 command、无失败 event、`turn.completed`、空 stderr、canary 匹配，`agent_status=completed`；按任务 stop condition **未修改 plan**。Sol 的直接证据成立：company `commit_batch` 可先把现有 ticker 目录移到 backup、再在 target swap/journal 失败；`_rollback_precommit_batch` 自身也可能失败并保留 journal/backup/staging。`tests/fins/test_fins_storage_atomicity.py:2879` 有 commit+rollback 同时失败的 owner 级测试。该窗口中文档已发布目录可能暂时缺失或恢复未定，不能拿进入 company batch 前的 `filings` 快照承诺当前 durable 文档仍完整。`_fs_storage_infra.py:534-612,676-715,1328-1358` 是直接事实边界；通用 `except Exception` 一律保留行的前节建议过宽，Sol 停止正确。

总控据此**缩窄 F1 的 S1 实施范围**：post-repair 分类阶段的 `SourceIntegrityRevisionConflictError`、`SourceIntegrityPreflightError` 发生在 company batch 前，文档 durable 已由先前单 filing commit 确认；company `commit_batch` 的 `SourceIntegrityPreflightError` 由 `_validate_complete_source_tree` 在 physical swap 前抛，storage 在失败时回滚，若 rollback 自身失败则仍须按不确定状态 stop。仅对这类可由 storage owner 证明文档状态的封闭路径使用私有 filings 快照；取消保留原控制流。**不得**按 `Exception` 泛捕 company commit 后的物理错误并假称 snapshot 仍是 durable 真相。此前 F1 表中“后置窗口所有异常”的普遍化要求由本段取代；revision conflict 的守恒仍为 S1 accepted，sibling 的公开分类仍延期。

对其余 company commit 失败（包括 precommit ValueError、OSError、post-commit release）及 rollback 失败，当前公开结果形状缺少能区分“已确认回滚/已提交/状态不确定”的 storage owner outcome。只凭 Python exception 类型或字符串、再读工作树时序都不能替代 batch 状态机事实，不能在 S1 猜一个数或加 UI fallback。登记独立后续 work unit **`fins-download-indeterminate-publication-state`**：先让 storage batch owner 提供 typed terminal publication certainty，再由 Fins 结果 owner 决定确定/不确定状态下的摘要/公开失败/后台 job/LLM 投影，并以真实 swap+rollback 双失败测试锁定。该 work unit 属本次总修复清单，不能在 #198 S1 closeout 中宣称所有 post-repair 异常都与 durable 摘要守恒；现有泛异常零摘要是明确残余缺陷，非正确行为。#198 S1 可仅承诺其可证明的 typed source-integrity 路径并继续推进，不把未知发布状态混入当前已接受 issue goal。

前节关于 `FinsResultSummary` 放宽的独立结论仍成立：外层 FAILURE 与已验证已处理文档的 SUCCEEDED/PARTIAL_FAILURE 可共存，不依赖 reason_code。但实际生产构造必须由 storage 确认发布事实；公开 dataclass 的机械守恒检查不代替 storage certainty。Sol 下一步只按此边界修 plan，新增 work unit 保留在总控队列，Kimi/MiMo 有效双路复审前不改 S1 代码。

`issue198-s1-plan-fix6-sol-20260929-01` 已按上述缩窄边界修订**计划候选**，未改产品。预检 ok；进程退出 0，JSONL 120 events/48 个成功 command、无失败 event、`turn.completed`、空 stderr、canary 匹配，`agent_status=completed`。总控核对 plan 的 S1 允许文件新增 wait adapter、post-repair revision conflict/commit pre-swap typed 的证明条件、RESULT 文档/整体终态分离、job 二次保存边界及真实 Phase B/commit 测试配方。三产品候选 diff 指纹仍为 `d9af4d09c3226616ccae2a9f2bd44281d1ad48021f9ced1d14b49291cf580783`，HEAD 仍 `8d8d494f`；这些都是计划层事实，Kimi/MiMo 有效 re-review 前不得实施。独立不确定发布状态 work unit 仍开放。

## MiMo 第四次 plan re-review 与总控裁决（2026-09-29 01:28）

MiMo `issue198-s1-plan-rereview4-mimo-20260929-01` 退出 0、Claude JSON `subtype=success`、`is_error=false`、`terminal_reason=completed`、canary `mimo-11cf5e14` 匹配，stderr 仅白名单模型名提示。完整 artifact `docs/reviews/plan-review-20260929-012525.md` 已读；其首尾 HEAD、三产品 diff 与候选 plan hash 一致。该路确认 fix6 的可证明发布边界、机械文档终态、wait scope、job 二次保存与 Phase B 配方主体成立，但报告两项低严重度规格 finding 和四个 open question。Kimi 本轮仍无有效第二路，不能据此宣告 plan pass。

| 新项 | 总控裁决 | 直接 owner 理由与完成信号 | 状态 |
| --- | --- | --- | --- |
| F1：「缺必要 download 继续拒绝」误述 `FinsResultSummary` 现状 | **accepted，选择 reviewer 方案 b** | `direct_events.py:FinsResultSummary` 是跨操作公共结果，当前 `FAILURE + failure + download=None` 在 owner 并不拒绝；唯一拒绝是 `fins_wait_adapter.py:_failure_message` 的 download wait 投影。S1 只放宽机械终态，不新增跨操作强制 download 不变量；从 owner 反例删除此项，改由 wait adapter 测试断言 download 失败帧缺 summary 会拒绝。其它无 failure、counts/disposition、成功/取消混用仍按实际 owner 规则验证。 | 计划待修 |
| F2：真实 commit-time 与 company commit 覆盖分工未写明 | **accepted** | 真实 root stray 配方命中候选单 filing `commit_batch`，证明 storage pre-swap typed/rollback 与已发布文档字节保持；company `commit_batch` 的 workflow 快照行为用受控 spy，durable 保证还需引用 `_validate_complete_source_tree` 在 publication guard 前的 owner 调用序。两侧合成验收，不能互替，不能把 spy 冒充真实 classifier。 | 计划待修 |
| OQ1：typed pre-swap + rollback cleanup 失败链 | **accepted，固定消费规则** | storage typed 只在 pre-swap `_validate_complete_source_tree` 产生，既有 target 未被物理替换；即使 cleanup rollback 失败并挂为 `__cause__`，已发布文档的旧字节仍可信。S1 可用同一已确认 filings 快照，但不能声称 rollback/cleanup 成功；保留原异常链与安全公共文案，测试注入 typed+cleanup 双失败锁定。若 owner 证据显示 target 已动则停止转独立不确定发布 WU。 | 计划待修 |
| OQ2：LLM wait scope 文案未定 | **accepted** | scope 文案是已确认 F3 的 LLM-facing 交付，需在唯一 wait 投影处使用固定命名常量及逐字测试；不从内部类型名要求模型推理。可沿现有示例句定稿。 | 计划待修 |
| OQ3：历史被撤销谓词无行内标记 | **accepted（文档卫生）** | 在旧 fix3 句旁标明已由 fix6 后续契约取代，不删历史证据、不让实施者误读旧理由。 | 计划待修 |
| OQ4：SEC typed 归零与 generic job raw `str(exc)` | **deferred-with-owner** | SEC typed 已处理行丢失属已知范围外 source/workflow 收口缺口，归 `fins-download-other-source-summary-conservation`；generic job `str(exc)` 可达 job failure record，需在 `fins-other-raw-diagnostics-audit` 中优先审查其 Service/LLM 投影并修安全文案，不能把 #198 S1 的 CN typed 持久摘要或 S2 direct 日志描述成覆盖它们。主修复队列同步登记。 | 未修复，独立 WU |

本轮不改产品；下一步 Sol 仅修 plan 精度与测试配方，然后 Kimi/MiMo **有效双路** re-review。若 Kimi 五小时额度仍 403，保留 blocked-by-provider 的 gate 状态，同时推进不依赖本 gate 的 work unit，不把单路 pass 当成闭环。

## Sol 第七次 plan fix 派发裁决（2026-09-29 01:50）

`issue198-s1-plan-fix7-sol-20260929-01` 退出 0、JSONL 到 `turn.completed`、canary 匹配、stderr 空，但一条记忆索引 `rg` 无匹配退出 1；按 `$sub-agents` 协议 **agent_status=failed**，落盘计划只能作候选，其完成声明不当作 gate 证明。总控对照上述 F1/F2/OQ1–OQ4 与计划最新第七次 fix 段及 S1 正文、storage owner 调用序，确认候选已把跨操作 summary 与 wait adapter 校验分开、单 filing 真实 commit 与 company spy 验收分开、pre-swap cleanup cause 与 physical swap 不确定状态分开，并固定 wait 文案。三份产品候选 diff 仍为 `d9af4d09c3226616ccae2a9f2bd44281d1ad48021f9ced1d14b49291cf580783`；本轮无产品实施。候选进入新的 Kimi/MiMo 双路 plan re-review，不能复用第四次报告或先修 S1 产品。

## MiMo 第五次 plan re-review（2026-09-29 02:03）

MiMo `docs/reviews/plan-review-20260929-020207.md` 退出 0、JSON `subtype=success`、`is_error=false`、canary `mimo-f60f7077` 匹配、stderr 仅白名单模型提示；独立审查结论 **pass-with-risks，无新增 finding**。总控接受其已逐点核实 F1/F2/OQ1–OQ4 计划收口与 storage pre-swap 调用序；physical swap/restore 双失败仍是明确未修复独立 work unit，不能因本单路通过而隐去。实施/code review 时对照 reviewer 追加的 `FAILURE + download + failure=None` owner 负例，并保留 `download=None` 跨操作合法形状。Kimi 此候选尚无有效第二路；下一 gate 仍是 plan re-review，不进入 S1 实施。
## 第五次双路 plan re-review 总控裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-020207.md` 与 Kimi `docs/reviews/plan-review-20260929-022743.md` 均为退出 0、结构化 success、canary 匹配；stderr 仅白名单模型提示。Kimi 独立发现 F1–F5，故本轮是 **plan review → fix**，并非 accepted plan pass。Sol 第七次修订因一条失败 `rg` event 按协议仍是 failed candidate；两路审查重证了内容，但不改变派发状态。

1. **F1 accepted，修计划并纳入 S1**：初始 whole-kind typed 在 direct/job 均从 Fins 同一公共映射取得安全消息和结构化零候选摘要；job 不再走 generic `{}` + `str(exc)` 路径。断言 direct/job 同一 reason/message、零候选结构、无泄漏，且 no-source 与普通异常形状不误改。已有 `ingestion_runtime.py` 白名单足够。
2. **F2 accepted，修计划**：私有 adapter failure 类型定义在 `ingestion_runtime.py` 的 Fins 边界；它持有原 `SourceIntegrityPreflightError` 对象和经验证的 partial summary。adapter 抛私有类型；Fins 内部在唯一分类/公共映射调用点先解出原 cause，再复用对 storage typed 的四值映射；direct/job 不各自解析异常链或字符串。测试断言原 cause 身份、四值同源、非 typed 不伪装。
3. **F3 accepted，修计划**：把 `_summary_from_pipeline_result` 的纯投影部分抽为内部共享 helper，私有 abort 的 `integrity_failed` 快照经严格校验后调用该 helper，公开正常入口仍只接受 `ok/cancelled`；不以临时伪 `ok` 绕过。
4. **F4 accepted，修计划**：wait adapter 失败 JSON 帧固定使用 `scope_note` 字段承载已定逐字业务说明；测试逐字断言字段、文本、typed failure 与 download summary。该字段只在 LLM-facing wait 投影，不扩展公共 schema。
5. **F5 deferred-with-owner**：job 二次保存 WARN 的既有 `exc_info=True` 及 traceback 进入 operator 日志的审计，明确加入 `fins-other-raw-diagnostics-audit`，连同 generic job `str(exc)` 的 Service/LLM 投影一起检查。S1 不修改该既有日志路径，不能声称已完成审计。

下一 gate：Sol 按以上修计划，然后 Kimi/MiMo 双路 re-review；任何一项未落定仍不实施 S1。

## Sol 第八次 plan fix 派发裁决

`issue198-s1-plan-fix8-sol-20260929-01` 进程退出 0、JSONL `turn.completed`、全部 command execution 退出 0、无 error event、stderr 空，canary `gpt-6-sol-b5e0d60d` 与预检逐字一致，按 `$sub-agents` 协议 **agent_status=completed**。总控仅采纳其指定 plan 文件变更，SHA-256 `5f71cb6712d3cdb7d62bf93f44f5f0a94a4c6a08c0c8a3b4158aa9d99b2dfc80`；三产品候选未因本计划修订变化。现行 S1 正文已具体写入 F1–F4 裁决，F5 留在独立审计队列。下一 gate：第六次 Kimi/MiMo 独立 plan re-review，不提前实施。

## MiMo 第六次 plan re-review 裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-030329.md` 结构化成功、canary `mimo-b6e0ff47` 匹配，结论 `pass-with-risks`；Kimi 同轮调用遇 403 额度限制，没有有效第二路。总控按 `tests/fins/test_cn_download_runtime.py` 的 `_summary_from_pipeline_result` 现有测试、`cn_download_filing_workflow.py` 的 mid-filing revision conflict 抛点和 `cn_download_workflow.py` 宽捕获、以及 job 现有 WARN `exc_info=True` 路径，接受下列三个 plan finding；不把单路 `pass-with-risks` 算作 gate pass。

1. **F1 accepted，plan fix**：S1 允许测试文件与实际验证命令都补 `tests/fins/test_cn_download_runtime.py`，该 owner 文件断言正常 `ok/cancelled`、私有失败快照和坏 row/locator/status。漏列它会造成实施越界或漏测。
2. **F2 accepted，选择 reviewer 方案 b**：`cn_download_filing_workflow.py` 中 mid-filing identity churn 耗尽抛出的 `SourceIntegrityRevisionConflictError` 目前被 workflow 的宽捕获记成普通 filing 执行失败并继续循环；此业务分类属于已登记的 `fins-download-storage-sibling-errors`。S1 不扩大该路径；plan 的 Raises 只列真实裸出口（初始 whole-kind preflight 与私有 abort），实施测试锁定 mid-filing 现状并明确标记为未修复残余，不能误称 typed 保真。后续独立 WU 负责正确分类。
3. **F3 accepted，选择 reviewer 方案 a**：新加的 typed job catch 二次保存 WARN 不使用 `exc_info=True` 或异常原文，只记固定安全标识/可信 error_type；注入二次保存失败的 owner 测试断言日志无 traceback、路径或秘密。既有两处 WARN 的 raw `exc_info` 仍在 `fins-other-raw-diagnostics-audit`，本次不声称已修复。

MiMo 三个 open question 作为实施注意事项：共用 unwrap 须在 code review 验证唯一入口；私有摘要校验失败属于已登记 generic 零摘要残余；首候选前 company publish 的 pre-swap typed 按零候选处理。下一步 Sol 仅修 plan，然后有效 Kimi/MiMo 双路 re-review；产品候选与 S2 不因此推进。

Sol 第九次 plan fix `issue198-s1-plan-fix9-sol-20260929-01` 进程退出 0、JSONL `turn.completed`、canary `gpt-6-sol-47275d42` 匹配，42 条 command exit 0；但记忆索引 `rg` exit 1 且 stderr 有 `apply_patch verification failed`，按协议 **agent_status=failed**。其计划落盘只能作候选。总控检查指定文件的三项修改：owner 测试文件已同时进白名单/pytest 命令，mid-filing revision conflict 的现状与 Raises 收口一致，新 typed WARN 不带 `exc_info` 且有注入断言；首候选前 company pre-swap typed 亦写明零候选。当前计划 SHA-256 `2e4bce410bbcb9f0711f0ec4bf8bbb96bf24162786069fb38a7836dc5346231f`，三产品候选仍未进入实施。候选进入新的独立 plan re-review，不能把派发失败状态或单路结论当 gate pass。

## MiMo 第七次 plan re-review 裁决

`docs/reviews/plan-review-20260929-033643.md`：exit 0、结构化 success、canary `mimo-d601c973` 匹配、stderr 仅白名单模型提示。第六次三项主体收口成立，第八次 F1–F5 未回退；但新增两项低 finding，当前仍不得实施。

1. **F1 accepted**：首候选前无 repair 的 company pre-swap typed 与 post-repair 调用复用 `_publish_cn_company_after_repair`，catch 只能在后者调用点/已处理路径，不能把前者空 `filings` 快照派生为 `terminal_disposition=SUCCEEDED`。plan 增真实初始 company typed 零候选测试，direct/job 必须得到请求级 `FAILED` 摘要且无伪 filing 行；post-repair 已处理行走私有快照。测试区分两个调用点。
2. **F2 accepted，简化为固定诊断事实**：新增 typed job catch 二次保存 WARN 仅记录固定事件标识 `fins.download.typed_failed_record_save_failed`，不记录 `error_type`、动态异常类名、`str/repr`、`exc_info`、路径或 traceback。二次失败已经是固定诊断类别，当前目标不需要再发明异常类型集合；注入自定义异常类测试逐字断言其类名与秘密均不出现，WARN 事件存在，失败不逃逸、不虚称 record 已保存。既有 WARN 的原始诊断仍留 `fins-other-raw-diagnostics-audit`。
3. **OQ1 accepted 为计划精度**：post-repair catch 覆盖 `classify_source_integrity_preflight` 及其后显式抛 revision conflict 的整块，不误称 classifier 自身抛 revision conflict。**OQ3 accepted 为测试精度**：mid-filing churn 用真实 owner 可控并发触发或明确受控注入点只锁 workflow 宽 catch，两者不能互冒充；计划须说明所选配方与证据边界。共用 unwrap 函数名可留实施选择，但行为只能一处、direct/job 测试固定同原 cause。

下一步 Sol 第十次仅修 plan；Kimi 403 无有效第二路，不能凭 MiMo pass-with-risks 进入 S1。S2 与独立残余 WU 顺序不变。

Sol 第十次 plan fix `issue198-s1-plan-fix10-sol-20260929-01` 已落指定文件，计划 SHA-256 `2d18014ce605c8368d53247a43669f6ba597ecc875fe6d5a7b2ce558c0d92cd7`；进程 exit 0、JSONL `turn.completed`、canary `gpt-6-sol-ebb097d2` 匹配、stderr 空，但 `rg` 无匹配 exit 1 与自写静态检查 exit 1 共两条失败 command，按协议 **agent_status=failed**，内容仅作候选。总控核对现行 S1 正文与测试段：循环前 company pre-swap typed 走请求级 FAILED 零候选，post-repair catch 限共享函数的后调用点并覆盖 classify+显式 revision conflict；新增 typed WARN 只有固定事件标识且自定义类名/秘密全不出现；mid-filing 注入测试不冒充真实 owner churn 事实。三产品候选 diff 未变。下一 gate 候选的有效 Kimi/MiMo 双路 plan re-review，额度恢复前不再把单路 pass 当实施授权。
## 总控独立静态候选验证（2026-09-29）

在主工作区 HEAD `8d8d494f` 的 #198 S1 未提交候选仍未获当前计划双路 review 时，总控只作不改变 gate 的独立验证：`source .venv/bin/activate` 后运行 `python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_atomicity.py tests/cli/test_output.py tests/service/test_fins_wait_adapter.py -q`，结果 **622 passed**、3 条 edgartools 第三方 deprecation warning，exit0；随后 `python -m pyright dayu/ tests/ utils/` 返回 **0 errors/0 warnings/0 informations**，exit0；`git diff --check` exit0。该证据只覆盖现有候选和所列测试，不替代尚未实施的 S1 plan 新增 CN/HK typed abort/后台 job 等路径，也不构成 plan/code/deepreview gate pass。待有效 Kimi/MiMo 同版计划复审后，按最终实施文件重跑受影响测试、逐改动文件覆盖率、pyright 和真实 CLI。

## Kimi 第十次计划同版复审（2026-09-29）

`issue198-s1-plan-rereview-kimi-20260929-02` 预检 ok、绝对主工作区、独立 JSON/stderr/canary；进程 exit0、结构化 `subtype=success/is_error=false/terminal_reason=completed`、60 turns、canary `kimi-07f71790` 匹配，stderr 仅白名单模型提示，`agent_status=completed`。artifact `docs/reviews/plan-review-20260929-092908-issue198-s1-kimi.md` 对 SHA `2d18014c...` 结论 `pass-with-risks`：MiMo 第七次 F1/F2/OQ1/OQ3 和 typed snapshot、physical swap、WARN、安全 wait、测试/README 范围均按当前 owner 复证成立；未运行产品测试，此为 plan review。

**新增低 finding K-F1，accepted 但实施配方须闭合**：首候选前公司 pre-swap typed 的真实触发用例必须保证公司 stage 非 `None`，否则 `stage_company_meta_for_cn_download` 见 identity 不变会跳过 commit，测试无法触发计划要验证的 storage typed 失败。实现者应选 fresh ticker、新 alias 或确实改变 company profile 的 fixture，并在测试前断言待提交 company mutation 存在；code review 须核对真实 `commit_batch` 到达。此为计划测试可达性精度，不扩 S1 业务目标；MiMo 同版结果未到前，不决定是否需 Sol 再修 plan。现有候选仍未获双路 plan pass，产品代码未继续实施。

## 第十次计划双路复审总控裁决（2026-09-29）

MiMo 同版 review `docs/reviews/plan-review-20260929-094111-issue198-s1-mimo.md` 对 SHA `2d18014ce605c8368d53247a43669f6ba597ecc875fe6d5a7b2ce558c0d92cd7` 进程 exit0、结构化 success、canary `mimo-2425aaa9` 匹配、stderr 仅白名单模型提示，结论 pass-with-risks、无 surviving material finding。总控复核其 owner 链证据：whole-kind inspect 可在 pre-swap 透传 typed；`_run_async_download_sync` 不吞该异常；空 `filings` 派生 `SUCCEEDED` 的陷阱已有请求级 `FAILED` 零摘要断言封闭；post-repair catch、job/direct 公共失败、固定 WARN 与 wait scope_note 均在计划及测试清单中。MiMo 的初始 whole-kind 抛点归因与 helper 控制流两项 open question 作为实现检查点，泛异常发布不确定性等残余保持独立 WU。

**K-F1 接受并设为实现验收条件**：这是测试配方静默分支造成的可达性缺口，设计 contract 不受影响；必须用 fresh ticker、新 alias 或真实变更 profile 使 `stage_company_meta_for_cn_download` 返回非 `None`，在注入前断言意图存在，并由代码评审确认真实 `commit_batch` 与 `_validate_complete_source_tree` 到达。此项保留为未完成修复项直至实现和双路 code review 验证，不得因 plan pass 遗忘。

双路同 SHA 复审均 pass-with-risks，所有 blocking plan finding 已闭合；**plan gate pass**，下一 entry 为 accepted plan commit。第十次 Sol 派发本身按失败协议记录，不把它算有效 agent 结果；总控对落盘计划独立核证并以两路有效复审作为计划 gate 证据。

## S1 Sol 实施候选与待审方法偏差（2026-09-29）

`issue198-s1-implement-sol-20260929-01` 在 HEAD `47a9cb64` 后结束，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-551d1adc` 匹配；但结构化流含多条测试、pyright、查询及预期 CLI 业务失败 command exit1，stderr 另有一次 patch verification 失败，故严格 **agent_status=failed**，仅将 diff 与 `docs/gateflow/issue-198-s1-implementation-20260929.md` 作为候选。实施者还调用了被 sub-agents 进程管理协议禁止的 `ps`；命令因沙箱拒绝，不能作判活证据。总控须独立核验最终结果，不能采信其自述为 gate pass。

候选最终自报 844 passed、六改动生产文件覆盖率 81/84/87/92/92/92%、pyright 0；总控正在独立复跑。K-F1 的 fresh ticker 非空 company intent 与真实 `commit_batch→_validate_complete_source_tree` 路径已写入测试，仍须代码审查复核。

**CLI 方法偏差/验收缺口**：accepted plan 指定 2025-03-28 窄窗口先取得至少一个真实 filing；实测 exit0 但 `discovered=0`，因此这条具体 baseline 不通过。实施者改用 2024-01-01～2026-12-31 宽窗口，在同一 fresh base 取得 3 个真实 filing，再制造 filings 根目录非点号外来文件，真实 CLI 以预期 exit1 返回 `storage/unsafe_publication`、安全双流与修复后重试提示。宽窗口验证同一 whole-kind preflight 与公开投影，但不是原命令；总控裁决前保留“窄窗口未通过”事实，并让双路 code review 明确评价此替代证据是否足够证明 S1 目标。不能在实施记录中将预期业务 exit1 当生产失败，也不能将改窗口写成原 recipe 已通过。若需保持 exact 日期，先取得来源候选事实再补跑，不凭空假定外部来源有文档。

总控独立复跑同一受影响八文件测试命令，exit0、**844 passed**；完整 `python -m pyright dayu/ tests/ utils/` exit0、**0 errors/0 warnings**。精确 14 文件 `git diff --binary` SHA-256 再算为 `f2766de5d4deb8ebfd922854892e575829d578bbd4faa2e03f38e0351239d448`，与 Sol 实施报告一致；其它脏 hunk 未并入本审查版本。Kimi/MiMo 已各自预检 `setup_status=ok`，对同一 digest 以独立 output/stderr/canary 派发 `$deepreview`，sessions `4235`/`28006` 正运行；两路未完成前 S1 代码 gate 不通过。

总控另用 Sol 留存的最终 coverage 数据文件只读复算六改生产文件：`output.py` 81%、`direct_events.py` 84%、`ingestion_runtime.py` 87%、`cn_download_workflow.py` 92%、`cn_pipeline.py` 92%、`fins_wait_adapter.py` 92%，每文件均达到 80%；该数据的运行命令排除了两项 coverage 插桩敏感的取消时序测试，普通完整受影响 suite 已独立 844 passed，二者方法边界保持分列。Kimi code review session `4235` 后因提供方五小时额度 HTTP 403、进程 exit1/JSON `is_error=true`，无有效审查结果；MiMo 同 digest 仍运行。不得把 Kimi 早期工具调用或输出当第二路 gate pass。

## S1 MiMo code review 裁决：revision conflict owner 断言

MiMo `docs/reviews/code-review-issue198-s1-mimo-20260929.md` 对精确 14 文件 diff SHA `f2766de5d4deb8ebfd922854892e575829d578bbd4faa2e03f38e0351239d448` 审查完成：进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-189b8ac5` 与预检逐字匹配，stderr 仅白名单模型提示，`agent_status=completed`。独立复跑 844 passed、pyright0；结论 **fail，1 项中 finding**。总控沿 `cn_download_workflow.py:402` 的 post-repair 显式 `SourceIntegrityRevisionConflictError` → `CnDownloadAdapter.download` 包装 → runtime `_download_exception_cause` → `_download_public_failure_from_exception` 的 EXECUTION 兜底与 `persisted_summary` 消费路径核对，当前代码确会保留已确认文档并不造 `reason_code`；但现有 workflow 测试仅断言 cause/rows，runtime direct/job 没有锁定该组合，accepted plan S1 第 57 行明示「revision conflict 沿既有分类」。**F1 accepted，未修复**：仅补真实仓储/adapter/runtime 的 direct/job owner 级测试，断言 `EXECUTION`、`reason_code=None`、已确认文档终态/ID/计数守恒及 job 安全文案；不得改正确的生产映射或给 revision conflict 私造 public reason。若建立两 candidate 的真实 selected-source 前提不可达，先留直接证据停下，不用 fake 直接构造公共失败冒充端到端。

MiMo 对窄 2025-03-28 CLI `discovered=0` 的事实判断成立；宽日期的真实 filing/whole-kind preflight/双流确与同一生产调用链同源，可证明 S1 行为，但不等于原计划那条 exact baseline 完成。总控将原日期前提登记为 **validation gap / 外部数据可用性**，后续尝试用实际发现 filing 的单日窗口补充窄窗口等价证据；在补证前不写「原命令通过」。代码 gate 仍因 F1 未修复、Kimi 第二路无效而 fail，下一 entry 为 Sol 仅补 F1 test+fix artifact，再对新 SHA 双路 re-review。

总控后续只读查询一手定位该单日差异：巨潮对 `seDate=2025-03-28~2025-03-28` 的第一页返回 `totalRecordNum=0`，对 `2025-03-27~2025-03-29` 返回当天两条，其中完整年报一条。具体方法/原始双流和独立修复项 `fins-cninfo-single-day-discovery-window` 见 `docs/gateflow/issue-198-s1-cninfo-single-day-evidence-20260929.md`。总控用三天窗口在 fresh base 真实 CLI 完整发布 `discovered=downloaded=1`、仓储完整性 `complete` 且 manifest/primary 同源，随后只加合成外来文件，重跑按预期 exit1、`storage/unsafe_publication`、安全零摘要与双流/普通日志；外来文件移除后仓储读回仍 complete。该补证提供更窄且确有候选的同路径行为证据，**不**把原单日命令改写成通过；单日发现合同作为独立 WU。F1 及 Kimi re-review 仍是代码 gate 阻断。

Sol F1 test fix `issue198-s1-review-f1-test-fix-sol-20260929-01` 进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-e1838ce7` 匹配、stderr 空，但一条 README `rg` 无匹配 exit1，按严格协议 `agent_status=failed`；实施者 fix artifact 误写「非零命令：无」，总控已在该 artifact 后附结构化纠正，不把 agent 自述当 gate pass。仅 `tests/fins/test_cn_download_runtime.py` 增 direct/job 参数化真实两来源测试，代码沿仓储二次分类→workflow revision conflict→adapter→runtime，断言既有 EXECUTION、`reason_code=None`、成功 repair 行/ID/计数与 job 安全文案。总控读代码确认没有手工公共结果，14 文件 diff SHA 从 `f2766de5...` 变为 `86aa9a2bdecdd4f9f817c555cf2eb94da668f9329a264428e192bf91f07b8cb5`；Sol 最终 846 passed、六生产文件 81–92%、pyright0。**F1 状态：部分修复，待 MiMo/Kimi 对新 SHA 的 code re-review**；在复审前不提交 S1。

## MiMo F1 同版 re-review 候选与严格执行状态

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

MiMo label `issue198-s1-f1-code-rereview-mimo-20260929-01`，显式绝对主 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、59 turns、canary `mimo-b4b44e63` 匹配；review artifact `docs/reviews/code-review-20260929-123046.md` 已实读，锁 14 文件 diff SHA `86aa9a2b...`。其独立测试 2 focused/846 受影响 passed、pyright0，内容结论 pass、F1 真实 owner 链补测成立，三天 CLI 替代证据界限也正确。但 artifact 明列一条探索性 shell 的 `echo ====` 被 zsh 解析失败（非零命令）；按本轮 sub-agents 严格执行协议，**agent_status=failed**，不能把内容 pass 计有效 MiMo code gate。候选内容可供总控核读：F1 仅测试文件增量，真实仓储枚举→post-repair revision conflict→adapter→runtime direct/job，断言 EXECUTION/no reason、已确认行/ID/计数与 job 安全文案；原单日 CLI 命令仍未通过，归独立日期 WU。需同 SHA 新 label MiMo 修复性 re-review，Kimi 有效第二路仍缺；S1 不提交、不集成。

## MiMo F1 同版修复性复审通过（2026-09-29）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- 新 label `issue198-s1-f1-rereview2-mimo-20260929-01`，显式绝对主 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、57 turns、canary `mimo-1a992a96` 匹配。artifact `docs/reviews/code-review-20260929-131006.md` 锁 HEAD `47a9cb64e63780deb568a9e2c6fdd0120441cf2f` 与精确 14 文件 diff SHA `86aa9a2bdecdd4f9f817c555cf2eb94da668f9329a264428e192bf91f07b8cb5`，本轮全部 shell 命令本身 exit0。独立 focused 2 passed、受影响八文件 846 passed、pyright 0；结论 pass，无新增 finding。
- 总控核对 F1 owner 测试及报告中的直接链：两个已发布 selected source 经真实 FS 仓储复核，post-repair 第二次枚举注入变更后取得真实 `REPAIR_REQUIRED`，workflow 的 revision conflict 经 adapter、runtime direct/job 映射为既有 `EXECUTION`、`reason_code=None`，保留已确认行/ID/计数并在 job 只给安全摘要。**F1 最终状态：已修复**，当前 S1 code review 有效 MiMo 一路通过；Kimi 对相同 SHA 的有效第二路仍缺，故 slice code gate 未通过、不得提交或汇入 PR #197。原单日 CNInfo recipe 仍未验证成功，独立日期 WU 待用户语义裁决；三天 CLI 只证明 typed 路径，不能替代该单日验收。

## Kimi 同版 S1 复审状态

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `issue198-s1-final-kimi-20260929-01` 锁 HEAD `47a9cb64` 与精确 14 文件 diff SHA `86aa9a2b...`，JSONL `turn.completed`、canary `kimi-46f56d2f` 匹配；两条 shell 非零和一次 `apply_patch` 工具失败，且会话中断后 exec session 退出码无法回读，严格 `agent_status=failed`，不计有效第二路。`docs/reviews/code-review-20260929-164741.md` 内容判 pass、无新 finding；独立复跑八文件 846 passed、pyright0，真实 FS post-repair→adapter→direct/job 仍 `EXECUTION`/reason None、守恒摘要。总控按内容接受 F1 无回退的佐证，但 S1 code gate 仍未过、未提交/集成。单日 CNInfo recipe 仍归独立日期 WU。

## Kimi Claude 同 SHA 修复性复审提供方失败

```yaml
setup_status: ok
agent_status: failed
tool_evidence: no
canary_status: not_run
warnings:
  - "Claude stderr [claude-code:unrecognized_model] 精确白名单模型名提示"
retry_class: provider
```

- `issue198-s1-final-kimi-claude-retry-20260929-01` 显式绝对主工作区、独立 JSON/stderr/canary，进程 exit1；JSON `is_error=true`、`terminal_reason=api_error`、`api_error_status=403`、最终提示 Kimi 五小时额度用尽。虽 24 turns，未形成可验收的最终 review/canary。MiMo 同 SHA pass 保持有效，但缺 Kimi 第二路，S1 code gate 仍未过，不提交/集成。额度恢复前不重派。
- 用户明确授权 Kimi 额度不足时以 `ds-flash` 备份。总控按上述 HTTP403 切换，同一 14 文件 diff SHA `86aa9a2b...` 对 `issue198-s1-final-dsflash-backup-20260929-01` 预检 ok、显式绝对主 workspace、独立 JSON/stderr/canary 派发 session `90039`。MiMo 原同 SHA pass 保持；备份终态及同源代码结论收齐前仍不得宣布 code gate 通过或集成。

## ds-flash 同版复审裁决：F2 待补测试

- `issue198-s1-final-dsflash-backup-20260929-01` 进程 exit0，JSON `subtype=success/is_error=false/terminal_reason=completed`，canary `ds-flash-04e0a6bf` 匹配；stderr 仅模型名提示白名单。review `docs/reviews/code-review-20260929-190212.md` 锁同一 14 文件 diff SHA `86aa9a2bdecdd4f9f817c555cf2eb94da668f9329a264428e192bf91f07b8cb5`，独立复跑 846 tests、pyright0；内容 `fail`，提出 F2。总控实读 accepted plan 第 57 行和现有多候选测试，**接受 F2 中／未修复**：计划明定修复 mutation 后同请求重跑，证实前次已完成候选按完整来源 skip、未处理候选正常处理；现有测试均只执行中止前半程，不能证明恢复语义。仅在 `tests/fins/test_cn_download_runtime.py` 或真实 owner workflow 测试补同仓真实 FS/adapter direct 或 job 回归，不改已审通过的产品映射，不把前次未处理候选计为已处理。修后新 SHA 必须重新双路同版 code review；当前 S1 gate 不通过、不提交/集成。
- 该 review 的 L1 双处 `integrity_failed` 私有常量属于同一状态事实重复，接受为低优先级 F3／未修复，归 `cn_pipeline`/`cn_download_workflow` 私有契约真源收敛，须避免跨层反向依赖；与 F2 一并交 Sol 评估最小改法并验证。L2～L4 import 顺序、docstring 风格、空行属于纯风格，不登记产品缺陷，也不阻断 gate。

## F2/F3 Sol 修复候选与结构化裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `issue198-s1-f2f3-sol-20260929-01` 显式绝对主 workspace、独立 JSONL/stderr/canary，进程 exit0、106 条 JSONL 可解析且 `turn.completed`、canary `gpt-6-sol-2b86f7f3` 匹配、stderr 空；一次中途 pyright exit1 的 `item.status=failed` 构成严格 agent 失败，虽随后修正并跑 846 passed/最终 pyright0，也不追认为有效实施 gate。仅采用经总控实读的内容候选。
- 总控核 `tests/fins/test_cn_download_runtime.py` 新 direct/job 参数化真实 FS/adapter/runtime 回归：首候选原先发布、损坏后真实 repair，post-repair 第二次 inventory 注入外来文件导致 typed 中止；此时第二候选无目录、未调用传输；移除外来文件，以**同一 request 对象**重跑，首候选真实 row 为 skipped、第二候选 downloaded，计数 `discovered=2/downloaded=1/skipped=1/failed=0`，仅第二候选传输，两个来源完整。F2 内容候选已修。`cn_pipeline.py` 现在同向导入 workflow 私有 `_INTEGRITY_FAILED_STATUS`，已有 abort 类型/执行函数依赖方向不变；F3 内容候选已修。14 文件精确 diff SHA `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`，细证据与 README 判定见 `docs/gateflow/issue-198-s1-code-review-f2f3-fix-20260929.md`。新快照仍需 MiMo 与用户授权的 `ds-flash` 备份同版深审，未提交/集成。
- 新 SHA `f1e1a915...` 的 `issue198-s1-final2-mimo-20260929-01` 与 `issue198-s1-final2-dsflash-backup-20260929-01` 均预检 `setup_status=ok`，显式绝对主 workspace、各自独立 JSON/stderr/canary 和不冲突的新 review artifact 路径，sessions `62380`/`48712` 并行在途。不得用 Sol 最终测试通过代替这两路内容裁决。

## F2/F3 ds-flash 新快照复审结果

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr [claude-code:unrecognized_model] 精确白名单模型名提示"
retry_class: none
```

- `issue198-s1-final2-dsflash-backup-20260929-01` 进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `ds-flash-4a996352` 匹配、stderr 仅白名单提示；但 review `docs/reviews/code-review-issue198-s1-final2-dsflash-20260929.md` 自披露一条 glob 错误 `rg` exit1、两条预期无匹配 `rg` exit1 及两条反证内层 pytest exit1，违反本轮 prompt 所定“所有 shell 探索命令自身 exit0”，严格 **agent_status=failed**，不能计有效第二路。内容 pass-with-risks、无新阻断 finding；总控实读其 F2 同请求 direct/job 回归、F3 单一常量与旧 S1 输出均为可用旁证，不替代有效 code gate。MiMo 同 SHA session `62380` 在途；若 MiMo 有效且无新 finding，另用新 label 对相同 SHA 重派一条纯只读、零失败命令的备份复审。
- 已基于明确的执行协议失败使用新 label 修复性重派 `issue198-s1-final3-dsflash-backup-20260929-01`，同一 SHA `f1e1a915...`、显式绝对主 workspace、独立 JSON/stderr/canary 与固定新 review artifact，preflight ok、session `84407` 在途；prompt 明确禁止故意失败 pytest/无匹配 rg。该次不并入旧失败审查的通过率，仍须收集结构化终态和总控内容裁决。

## F2/F3 最终同快照双路代码审查裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: ["[claude-code:unrecognized_model]"]
retry_class: none
```

- MiMo `issue198-s1-final2-mimo-20260929-01` exit0、JSON success/60 turns、canary `mimo-aa24b3b3` 匹配，stderr 仅白名单提示；review `docs/reviews/code-review-issue198-s1-final2-mimo-20260929.md` 锁 HEAD `47a9cb64` 与精确 14 文件 diff SHA `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`，内容 pass-with-risks、无 blocker。自报本轮 shell 全部 exit0，独立 2 focused/846 affected passed、pyright0、六生产文件 coverage ≥80%、diff check0。
- ds-flash 额度备份修复性复审 `issue198-s1-final3-dsflash-backup-20260929-01` exit0、JSON success/81 turns、canary `ds-flash-4d0d85f8` 匹配，stderr 仅白名单提示；review `docs/reviews/code-review-issue198-s1-final3-dsflash-20260929.md` 锁相同 HEAD/diff SHA，内容 pass-with-risks、无 blocker。其命令表及自报均为 exit0，独立 2 focused/846 affected passed、pyright0、diff check0。旧失败轮未追认。
- 总控实读两份审查中的真实 FS→workflow→adapter→direct/job 回归：中止时已确认第一候选且第二候选未开始；清除外来 mutation 后**同一 request**重跑，第一候选依仓储 COMPLETE 跳过、第二候选下载且仅第二候选传输，durable byte/meta/完整性读回；F2/F3 成立。`integrity_failed` 只有 workflow 常量一处定义，pipeline 同向消费，无下游重算。review N1 指出 fix 记录漏写“替换旧用例”，已补到 fix artifact；不改代码快照。
- N2 空行属于风格，不影响语义或测试；N3 typed job 投影构造范围是 accepted plan 已分类残余。ds-flash N4 `__all__` 不列显式跨模块导入符号没有行为影响，`__all__` 只管 wildcard import，当前不作为公共 contract；N5 内部 abort 文案当前无消费者，`cause` 是投影真源，若未来暴露 message 须由 owner 同源分类，当前不立无消费者修复项。N1 测试行数由 `FinsDownloadPublicSummary` 守恒 contract 蕴含，N2 job 摘要无逐行是既有公共上限；不为可读性做产品修补。三份 README 相邻另一 WU 点号元数据句**必须按行分开 stage**。S1 code review/re-review gate 通过，下一 gate 为只含 S1 的 accepted slice commit，之后 aggregate deepreview；S2/单日 WU 不因本 gate 通过而宣称完成。
