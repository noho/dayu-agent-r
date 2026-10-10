RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6.1-sol
CANARY=gpt-6-sol-1bbb6ea8

# 下载失败诊断：plan fix 记录

- Work unit：download-failure-diagnostics-20261010。
- Task label：dfdiag-plan-fix-sol-20261010-01。
- Gate：plan fix；Completion status：限定文档修订完成，交总控 re-review；不声明任何 gate 已 pass。
- Branch：fix/download-failure-diagnostics-20261010。
- 冻结 base / 修改前后 HEAD：c65c2aa28fae9c47ad947783d63f7559db7768c4。
- 修改前 plan SHA256：e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca。
- 修订后 plan SHA256：7de77259a5ca545ef959376471f7d902c48fd31dece024b3ce04468b7e18c9f9。
- Changed files：仅修改 `docs/gateflow/download-failure-diagnostics-plan-20261010.md`，新增本 artifact `docs/gateflow/download-failure-diagnostics-plan-fix-20261010.md`。
- Design document / issue / issue association：N/A。
- 本轮 canary 由工具直接读取 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.p84mXh/canary.txt`，内容逐字记于首部。旧 canary 不作本轮证明。
- 模型证据边界：本轮任务提供的 runner gpt-6-sol 配置 model=gpt-6.1-sol，自报名与配置一致；没有独立可验证的物理后端型号证据，不以 Node 元数据、默认继承环境或自报证明实际物理型号。

## 依据、范围与动机判断

已读取 AGENTS.md、gateflow SKILL.md、goal、原 plan、总控 adjudication、mimo 与 ds-flash 本 unit plan review，以及总控归档 old-evidence JSON。冻结分支、HEAD、修改前 plan hash 均匹配；必要证据可读，未触发停止条件。

直接证据支持当前动机：完整 typed 结果已有，CN/HK adapter 丢安全说明、公开摘要只取前 10 行。解决完整失败诊断缺口所需的 owner 链与一个行为 slice 沿用原 plan，不重新设计框架。P1 修订不实声明，不扩大已确认 0700、2018-01-01 至 2026-10-10 的 CN/HK 原因保真目标；通用接口机械用于所有 source 的决定保留。

总控已核清全部本 unit dirty ownership，原 plan Agent 的 postflight ownership blocked 已解除。goal/state/old-evidence/adjudication 属总控、plan 属计划 Agent、review 属各 reviewer；总控继续更新 state 不算 ownership blocker。本次没有读调用方 workflow/gate/审核包/范式，没有子 Agent、生产 query、网络观测、下载、overwrite、recovery、生产/测试/README 修改或 commit/push/PR/merge。

## P1—P4 修订与逐项 validation

以下“已修复”仅指本次计划文本修订；accepted findings 的最终修复状态仍须总控 re-review 独立验证，不能据此放行 implementation。

| 裁决 ID | 文档修订状态 | 修改与证据位置 | 本次 validation 与后续实施断言 |
| --- | --- | --- | --- |
| P1 | 已修复（计划文本，待 re-review） | plan §1/§2/§5.1.3/§8/§9 删除 SEC 现有 adapter 原因保真的承诺，明确 CN/HK 真实安全原因保真；SEC 保留现有 typed 安全投影，生产允许范围仍为原五文件，不含 SEC。 | 只读复核 `sec_pipeline.py:1933-1973,2092-2114` 的通用说明与 `sec_download_filing_workflow.py:314-325,614-623` 上游原因，证实旧声明不实。文本检查旧肯定句已消失；SEC 验证仅完整性、身份、既有分类/安全说明不变，禁止把 workflow 原因等值断言作为当前验收。 |
| P2 | 已修复（计划文本，待 re-review） | plan §3.2/§3.3 写死所有合法下载 terminal 必有 download_result，None 只代表无下载结果的合法非下载 terminal，诊断方法遇 None 抛 ValueError；§3.5 给出 activation 路径 exact 改法，复用现有 `_observation_failure_result`，不新增 operation 字段/wrapper/fallback。 | 只读复核 activation 唯一调用、`_mark_observation_failed` 裸 result 构造、现有 failure/cancel helper 与 `_empty_download_summary_from_request`，确认持有 request 的 runtime 是 owner。明确删除 mark helper 冗余 error_kind 参数及唯一 EXECUTION 实参，保留锁/收口/原异常同对象传播。§5.1.3/4 明确 submit OSError/ValueError、prepare cancel、adapter 启动前失败及非下载拒绝，断言 request 身份/filters、typed 空 FAILED/CANCELLED、whole failure/空 failed_documents；测试尚未执行。 |
| P3 | 已修复（计划文本，待 re-review） | plan §6 改为引用总控已完成的 old-evidence JSON/hash，逐项更新 8 missing，保留 45 来源；§8/§9/§10 删除再次 query、再次等待同一授权及尚未独立核验的旧状态。 | 实测 JSON SHA256=`008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2`；解析断言 8 行 missing、原原因/日期 null、source_count=45，plan 每 ID 恰一行。说明常规 publication 治理锁不修改来源，当前 meta 核查不证明旧失败原因；本轮只读文件，不重复生产 query、不新观测。 |
| P4 | 已修复（计划文本，待 re-review） | plan §5.1.1 写入 DOWNLOAD RESULT 缺结果、每个非 DOWNLOAD operation 带结果的 owner 负例；§5.1.2 独立断言 period_metadata_mismatch 为 FAILED；§5.1.5/8 按固定 diagnostics 前缀筛出唯一 JSON 行。 | 只读复核 `FinsEvent.__post_init__` 现有 RESULT 边界、`cn_download_filing_workflow.py:196-222` mismatch failed 与 integrity_complete skipped 的不同分支，以及 CLI 既有 summary/document 输出。负例其它字段必须合法；mismatch 必须进入 failed_documents；stdout/stderr 可有其它行，只对 `Fins download diagnostics: ` 前缀计数并剥离后 json.loads。 |

P1 的跨来源原因修复扩范围请求沿用总控 rejected-with-reason 裁决；SEC 原因治理作为后续风险列明，不改为本轮 obligation。P2 未更改 executor 生命周期或治理状态机；仅在既有 runtime owner 收口下载事实。其余 typed/public projection、共享 row JSON、bounded LLM/durable、单 slice、五个生产文件、coverage、固定 CLI 离线加载与 README 设计继续沿用。

## 本次验证结果与未执行验证

- Preflight：`git branch --show-current`、`git rev-parse HEAD`、`git status --short`、修改前 plan `shasum -a 256` 均匹配交接；canary 真实文件读取成功。
- 关键代码复核使用限定路径的 rg/sed，只复核 P1—P4 所需分支、owner helper、现有 activation/prepare cancel 测试，不重新全仓探索。`_mark_observation_failed` 在固定 HEAD 仅有 activation 一处调用，现有分类为 EXECUTION。
- 只读 `python3 -B` 文档检查退出 0：证据 SHA256、8 missing/45 来源、8 个唯一 ID 表格行、Markdown fence 配对、示例 JSON 可解析且 failed count/完整数组对齐、P1—P4 必要语句与旧不实状态删除均通过。此检查只验证文档，不证明生产行为已修复。
- 收尾 branch/HEAD 未变；`git diff --exit-code` 与 `git diff --cached --exit-code` 均退出 0，已有 tracked 生产/测试/README 无差异。goal、old-evidence、adjudication、两份原 review 的前后 SHA256 均一致；state 没有被本 Agent 写入，沿用总控 ownership。
- 没有运行 pytest、pyright、coverage、fixed CLI smoke 或真实下载。当前仅修 Markdown，实施验证命令及 >=80% 逐文件覆盖率要求保留在 plan §5.2；不把 review 的离线装配证据冒充修复后验证。

## Docs decision

本 gate 只修订 plan 并新增 fix artifact，未修改代码、测试、用户入口或实际输出，因此不触发 README 更新。后续 implementation 的根 README、dayu/fins/README、tests/README 职责内更新及 dayu/README 不更新决定沿用原 plan §8；实施者按实际变更与已读取约束执行。goal/state/adjudication 与原 review 不由本 Agent 改写。

## 分类 residual risks 与未覆盖项

| 风险 / 未覆盖项 | 分类 | Owner / destination / 处理边界 |
| --- | --- | --- |
| P1—P4 的计划不实声明、终态歧义、旧核查状态、断言不具体及旧 ownership blocker | fixed in current slice（本次 plan fix 文本修订） | 本 Agent 已修订；总控双路 re-review 验证最终状态，不据此宣称 gate pass。 |
| CN/HK 原因丢失、完整/有界一致性、取消前缀、activation typed 结果、CLI 转义、类型与 coverage、固定入口修复后加载 | fixed in current slice（原 plan S1 计划处理，尚未实现/验证） | 后续 implementation owner；仅 re-review 与 accepted plan 后进入，当前没有实施证据。 |
| SEC 原因泛化及 upstream 安全治理 | assigned to later work unit | Dayu 维护侧；另定 SEC 原因 owner work unit，不改 SEC 生产、不自行建 issue、不把 raw exception 透传。 |
| 旧 8 项原原因、URL、日期、表单/覆盖信息不可由现有证据恢复 | requiring explicit user decision（仅未来新观测） | 巡检线已授权如实未知；当前用已完成 owner-read 归档结论，不等待重问授权。新观测范围由巡检线另确认。 |
| 新观测、实际下载缺陷扩范围与来源业务影响 | requiring explicit user decision | 巡检线/用户；先报直接证据、最小修法与影响，当前无生产行为。 |
| SIGKILL/崩溃/未消费或提前关闭流/未捕获标准流后的历史不可追回 | requiring new issue or explicit user decision | 用户/总控；当前只承诺合法 consumed RESULT，不引入历史仓储。 |
| 极端规模性能、完整 repr 的日志体积 | assigned to later work unit | Dayu 维护侧；真实扩展压力出现时另定，当前无规模压测、不增分页/框架；原 S1 保留 LLM/durable 有界断言。 |
| 部署漂移或实施验证失败需要超范围改动；merge/approve/ready/reviewer/外部 comment | requiring explicit user decision | 总控/用户；draft PR 已授权属于后续 gates，当前禁止 commit/push/PR，不由此推导其它授权。 |

没有未分类 residual risk，没有已知 blocking open question；上述代码行为、类型/coverage 与部署验证未覆盖并已归属后续实施验证。未创建 issue、没有 design_doc、没有扩大已确认目标。

## 交接与停止

Completion：plan fix 的两份限定文档已完成；P1—P4 文档修复证据已记录，最终状态由 re-review 验证。下一未完成 gate / next entry point：**re-review**，交总控派发两路独立复审。本 Agent 正常停止，不进入 re-review/accepted plan commit/implementation 或其它 gate，不声明整个 work unit 或任何 gate 已通过。
