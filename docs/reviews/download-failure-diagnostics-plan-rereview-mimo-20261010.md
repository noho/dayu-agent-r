RUNTIME/PROVIDER/MODEL: codex/mimo/mimo-v2.6-pro
CANARY=mimo-5e57ea67

# 下载失败诊断：修订计划独立复审

- Reviewer：`dfdiag-plan-rereview-mimo-20261010-01`
- 生成时间：`2026-10-10 12:49:59 +0800`
- Review target：`docs/gateflow/download-failure-diagnostics-plan-20261010.md`
- Plan fix：`docs/gateflow/download-failure-diagnostics-plan-fix-20261010.md`
- Goal：`docs/gateflow/download-failure-diagnostics-goal-20261010.md`
- 总控共同输入：`docs/gateflow/download-failure-diagnostics-plan-adjudication-20261010.md`
- 本路初审：`docs/reviews/download-failure-diagnostics-plan-mimo-20261010.md`
- 本文件是本轮唯一写入 artifact。

## 冻结身份

- Branch：`fix/download-failure-diagnostics-20261010`
- HEAD/base：`c65c2aa28fae9c47ad947783d63f7559db7768c4`
- 修订后 plan SHA256：`7de77259a5ca545ef959376471f7d902c48fd31dece024b3ce04468b7e18c9f9`
- 旧证据归档 SHA256：`008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2`
- `git rev-parse HEAD`、`git branch --show-current` 与冻结输入一致；写报告前 tracked diff 和 staged diff 均为空。
- 本轮 canary 来自 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.WFMs0A/canary.txt` 的真实读取，已逐字记录于首部。

## 范围与证据边界

本轮独立验证 P1-P4 是否已由修订计划解决，并检查该计划是否仍足以生成代码。总控 adjudication 只作为共同输入，不替代本轮对计划文本、冻结代码路径和归档证据的复核。只读取了本路初始 review，没有读取另一路初始或复审报告。

P1 的原因保真范围按用户约束限定为 ticker `0700` 所在的 CN/HK 共用 owner 链。完整 typed 诊断接口仍可机械服务所有来源，但 SEC 既有原因治理属于另行确定范围；本轮不宣称 SEC workflow 原因已经保真。

本轮没有读取调用方 workflow、gate、审核包或范式，没有生产 storage 查询、网络访问、下载、overwrite、recovery、新观测、代码修改、测试执行、pyright、coverage、commit、push、PR、merge 或子 Agent。模型身份按本轮 runner 配置记录，不以模型自报或 Node 元数据证明物理后端型号。

## 假设与反例验证

1. 修订后的范围声明是否与 goal 一致，且没有残留“SEC 原因已保真”或跨来源原因修复承诺。
2. 所有合法下载 terminal 是否在计划中被定义为必有 typed `download_result`，`None` 是否只表示无下载结果的非下载 terminal。
3. activation submit 失败是否落在持有 `download_request` 的 runtime owner，是否复用 `_observation_failure_result`、删除冗余 `error_kind`，并保留原异常对象。
4. 旧 8 项证据是否只引用已完成的 owner-read 归档，准确表达 8 missing、45 来源和历史不可恢复边界。
5. P4 的 owner 负例、`period_metadata_mismatch=FAILED` 和唯一诊断前缀解析是否被写成可直接实施和可验证的契约。
6. 完整结果、bounded LLM/durable 摘要、取消前缀、typed abort、固定 CLI 与测试覆盖是否形成闭环，允许 implementation 不再重新设计关键语义。

## Accepted Findings 最终状态

| ID | 最终状态 | 独立证据 | 尚未覆盖 |
| --- | --- | --- | --- |
| P1：SEC 保真声明不实 | **已解决，仅计划声明与范围层面** | plan §1 行 24、§2 行 40、§5.1 行 201、§8 行 305、§9 行 328 已一致限定 CN/HK，并明确 SEC 只保留既有 typed 安全投影。静态复核 `sec_pipeline.py:1933-1973,2092-2114` 的通用文案及 `sec_download_filing_workflow.py:314-325,614-623` 的上游原因，支持“SEC 尚未保真”的修订事实。全文检索未发现残留肯定式 SEC 保真承诺。 | SEC 生产原因治理仍未实现，且不属于本 slice；没有声称下游产品行为已修复。 |
| P2：`download_result=None` 与 activation failure 归属含糊 | **已解决，仅 owner 契约与实施计划层面** | plan §3.2 行 62-88 定义完整 typed 字段、派生 `download` 和 event 排他不变量；§3.3 行 99 规定诊断方法遇 `None` 抛 `ValueError`；§3.5 行 143-147 给出唯一 helper 改法。固定 HEAD 上 `_mark_observation_failed` 仅在 `ingestion_runtime.py:4009` 被 activation 调用，现有 `_observation_failure_result` 已持有 request 语义，`_empty_download_summary_from_request` 已支持 typed 空 FAILED/CANCELLED。计划要求删除 helper 的 `error_kind` 参数和唯一 EXECUTION 实参，保留锁、收口和裸 `raise` 同对象传播。 | activation、prepare cancel、adapter 启动前失败、非下载拒绝及原异常对象均尚未由新测试实际验证。 |
| P3：旧 owner evidence 状态表述过时 | **已解决，仅事实归档层面** | plan §6 行 241-275 已直接引用 `docs/gateflow/download-failure-diagnostics-old-evidence-20261010.json`。本轮只读实测其 SHA256 为 `008ecadf...61bd2`；解析得到 `failed_documents=8`、`source_count=45`、8 项均 `published_meta=missing`，原因、日期、form、report_date、coverage 为 null，`record_sha256=6d42a496...15fce7`。计划正确限定为当前 owner-read 状态，不把它当成历史失败原因，并明确不重复 query 或新观测。 | 原始异常、URL、日期、表单和覆盖信息仍不可恢复；未来新观测仍需巡检线另行确认。 |
| P4：负例、mismatch 分类和诊断行解析不具体 | **已解决，仅测试规格层面** | plan §5.1 行 199 明确 DOWNLOAD 缺 typed result、非 DOWNLOAD 携带 result、非下载调用诊断三类 owner 负例；行 200 明确 `period_metadata_mismatch` 必须是 workflow `failed`、typed `FAILED` 且进入 `failed_documents`。固定 HEAD 的 `cn_download_filing_workflow.py:201-215` 已产生 `status="failed"` 和 `FILING_FAILED`，与计划要求相容。行 204 明确按固定前缀筛选后恰有一条诊断物理行，剥离前缀后 `json.loads`，不要求 stdout/stderr 总共只有一行。 | 这些是待实施断言，当前没有新测试结果，不能写成运行时行为已验证。 |

P1-P4 的“已解决”均表示 accepted finding 所指向的**计划缺陷已消除**。本次没有生产代码和测试实现，因此不表示下载诊断产品缺陷已经修复，也不把计划中的预期断言当作实际验证结果。

## 新实质 Findings

未发现新的实质 finding。修订计划已经把 P1-P4 的 owner、文件边界、失败状态机、测试负例、证据边界和停止条件写到可实施粒度。SEC 原因治理、历史不可恢复、极端规模和部署漂移均已作为残余风险明确归属，不再构成本计划的隐含实现义务。

## 风险与未覆盖项

| 风险 / 未覆盖项 | 合法分类 | Owner / destination / 当前边界 |
| --- | --- | --- |
| CN/HK 原因丢失、完整/有界一致性、activation typed 结果、取消前缀、CLI 转义、类型与 coverage、固定入口加载 | `fixed in current slice` | S1 implementation owner；这里仅表示计划已安排，当前尚未实现或验证。 |
| P1-P4 的计划文本、事实归档和测试规格修订 | `fixed in current slice` | 本 plan fix 已处理；本报告只裁决计划层最终状态。 |
| SEC 原因泛化与 upstream 安全治理 | `assigned to later work unit` | Dayu 维护侧的后续 SEC 原因 owner work unit；本轮不改 SEC 生产代码，不透传 raw exception。 |
| 旧 8 项原始原因、URL、日期、form、report_date、coverage 不可恢复 | `requiring explicit user decision` | 巡检线已允许如实未知；只有未来新观测需要另行确认具体范围，当前不重查、不猜。 |
| 实际下载根因、来源业务影响、覆盖判断和任何新观测 | `requiring explicit user decision` | 巡检线/用户；实际下载 defect 若显现，先报直接证据和最小修法，再裁决范围。 |
| SIGKILL、崩溃、未消费或提前关闭流、未捕获标准流导致历史不可追回 | `requiring new issue or explicit user decision` | 用户/总控另定 durable diagnostics 需求；本计划只承诺合法 consumed RESULT。 |
| 极端结果规模性能、完整 operator JSON 长度和日志体积 | `assigned to later work unit` | Dayu 维护侧；真实扩展压力出现时另定，当前不增分页、流式诊断或日志框架。 |
| 固定 binary 部署漂移、真实远端下载和生产验证 | `requiring explicit user decision` | 总控/巡检线；计划中的 editable 与 isolated binary 检查不冒充生产下载或部署成功。 |
| merge、approve、ready、reviewer、外部 comment 和最终 commit | `requiring explicit user decision` | 用户/总控后续 gate；本报告不执行，也不由 plan review 授权。 |

没有未分类 residual risk，没有 blocking open question。原初审的 scope、历史 evidence、`download_result=None` 和旧核查表述四个 open question 均已在修订计划中收敛。

## 计划可生成代码判断

结论：**code-generation-ready = 是**。

理由：修订计划明确了一个行为 slice、五个生产文件、owner 级字段与不变量、CN/HK strict 投影、runtime activation exact 改法、完整 JSON schema、CLI 前缀协议、测试负例、固定 executable 离线验证、pyright/coverage 命令、README 职责和停止条件。实现 Agent 可以据此直接生成代码，不需要重新决定 SEC scope、诊断入口状态机或旧证据是否仍待查询。

Plan review conclusion：`pass-with-risks`。该结论只表示计划已达到可生成代码状态，**不表示任何 gate pass，也不表示生产缺陷已修复**。本报告不自行宣布 gate pass。

## 未执行验证

- 未运行受影响 pytest、pyright、coverage 或固定 CLI subprocess；计划中的命令是 implementation gate 的待执行项。
- 未证明新诊断方法、typed constructor 迁移、strict CN/HK reason、activation failure、period mismatch、唯一诊断行或 bounded wait 已在运行时通过。
- 未证明修复已由 `.venv/bin/dayu-cli` 加载，未做真实下载或生产部署验证。
- 未恢复旧运行的原始异常或候选元数据，也未执行任何新观测。

## 尾部身份核验

- Branch：`fix/download-failure-diagnostics-20261010`
- HEAD/base：`c65c2aa28fae9c47ad947783d63f7559db7768c4`
- 修订后 plan SHA256：`7de77259a5ca545ef959376471f7d902c48fd31dece024b3ce04468b7e18c9f9`
- 旧证据归档 SHA256：`008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2`
- CANARY=`mimo-5e57ea67`

本轮复审到此停止。
