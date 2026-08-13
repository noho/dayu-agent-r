# UF-FIX01 validation-atomic-boundary — Implementation Review Adjudication

## 1. Gate context

- **implementation commit**：`3caca6fa0091a738c5c78cc5165a49fed82c6458`
- **review base**：`69bc9d2af91788303c839d01ad937cf9b802eb1d`
- **MiMo artifact**：`docs/reviews/code-review-20260813-114536.md`
- **AgentDS artifact**：`docs/reviews/code-review-20260813-115401.md`
- **Controller decision**：**BLOCKED → AgentCodex fix required**

两路 review 都从 CLI 真实入口追踪到 storage publication，并独立识别 authoritative request/decision 在 runner
边界丢失。MiMo 给出 conditional PASS，但 Gateflow implementation gate 不接受与冻结 plan、owner constraint
不一致的“行为当前等效”豁免；DS 的 BLOCKED 判定与直接代码证据成立。

## 2. Accepted findings

### A1 — authoritative request/decision handoff 未落地（严重，接受）

`ProductionFinsUploadRunner` fresh recheck 后把 `ValidatedFinsUploadFilingRequest` 还原成散参；SEC/CN workflow
继续独立读 source state、重算 action 与 company freshness，`prepare_upload` 又第三次读取 previous meta。
这违反 accepted plan §6.2.1/§6.5 与项目 single-owner 约束，不得以当前结果大致等效为理由保留。

修复必须按冻结 plan 收束：

1. SEC/CN facade 与 workflow 接收 typed validated request，不得重建散参；
2. workflow 在 prepare 前通过注入的同一个 `FilingUploadStateRepositoryProtocol` 读取 fresh snapshot，对
   `preflight.request` 调同一 validator，断言 canonical ticker/document identity 一致后得到 authoritative request；
3. 只有 authoritative `resolved_action`、`published_state.source_meta` 与 `company_meta_decision` 可驱动
   prepare/stage/commit；
4. `prepare_upload(previous_meta=...)` 不再读取 filing state；material 仍使用其既有 state owner；
5. filing workflow 以 `stage_upload_company_meta_decision` 替代旧 `upsert_company_meta_for_upload`，删除 filing
   链路的第二 company 决策；不新增兼容 wrapper。

### A2 — 前置冲突被投影成 generic/storage failure（中，接受）

当前 `FileExistsError`/`FileNotFoundError` 落入 `OSError → STORAGE_IO`，旧 stale-company test 还被弱化为
generic runtime 文案。A1 修复后，filing 的普通冲突应在 authoritative validator 内以 closed actionable reason
拒绝；仍可能发生的 publication/storage race 由 batch/storage owner fail closed。不得用 generic 文案或异常字符串匹配
掩盖已知前置语义。恢复 owner-level exact reason assertions。

### A3 — S3 原子状态机 owner tests 缺失（中，接受）

SEC 与 CN 至少各补一组冻结 plan 要求的真实 workflow tests：同一 `BatchToken` identity、
`begin=1/commit=1/rollback=0`；company/source stage fault 下 `rollback=1/commit=0`；fresh 与 existing state
before/after tree 和逐文件 SHA-256；preflight 后改变 state 时旧 action/company decision 被丢弃。还需覆盖
rollback failure 保留 primary cause/recovery evidence、不得补偿删除或二次 batch。

### A4 — prevalidation operational failure 可能通过 `str(exc)` 泄漏路径（低，接受）

upload_filing 在 service factory 前的 storage/identity corruption/OSError 仍须 exit 1，但 public stderr 必须经
typed bounded path-free owner 投影；`FinsUploadUsageError` 仍优先、精确映射 exit 2。不得扩大到其它 CLI 命令，
不得用字符串匹配分类。需补 permission/I/O 与 descriptor corruption CLI 级测试，断言 exit 1、具体有限 reason、
无绝对路径/traceback/repr。

### A5 — CLI docstring 失真（低，接受）

更新 `_upload_filing_stream` 的异常说明，使其与“只透传 validated request”一致。

## 3. Controller-added required fixes

### C1 — S2 frozen usage matrix 的 CLI owner evidence 不完整

现有 CLI 级 pre-factory/zero-mutation test 只覆盖一个 case；validator-level exhaustive test 不能替代真实 CLI
catch/factory/bootstrap boundary。按 accepted plan S2，对 frozen UF cases 的每个 usage code 以参数化 CLI owner test
断言 exit 2、stdout empty、stderr exact one line、factory/service zero calls、fresh tree unchanged。测试可复用同一
production validator/storage owner，不得复制规则到 fake。

### C2 — typed catch 顺序与 operator root cause 未被证明

冻结 plan §6.6 要求 cancelled → `DoclingConversionError` → storage typed/OSError → generic Exception 的可观察
分类顺序及 exhaustive marker tests。单 generic catch 再调用 mapper 尚未证明 typed failure 不落 generic；同时 workflow
没有明确 operator log 保留原始 cause。按 plan 建立 typed catch/helper 边界，public 只用 closed bounded reason，operator
log 保留内部 cause，禁止 `str(exc)` 参与 public classification。

### C3 — material non-goal 必须保持

本 WU 只修 filing。共享 helper 调整不得顺带改变 material 用户可见 failure semantics、事务或 state owner；为 material
共用路径补回归断言。如无法在不改变 material contract 的前提下共享 helper，应把 filing failure projection 保持在 filing
workflow，而不是扩大本 WU。

## 4. Rejected/deferred items

- **不要求现在执行 UF-PF01**：它仍在 implementation fix/re-review PASS 后执行，因此不构成本轮 review 缺失。
- **不要求全仓 pytest**：冻结 plan 要求受影响测试与完整 pyright；fix 后仍需重跑指定 suite、逐文件 coverage 和完整
  pyright。是否追加全仓 pytest 可作为 final residual risk，不替代 required suite。
- **不接受 deliberate deviation 文档化作为 A1 修复**：该偏离直接违反用户指定 owner boundary 与 accepted plan，必须改代码。

## 5. Next gate

AgentCodex 只修 A1–A5、C1–C3，并更新 implementation/fix artifact；不得执行 UF-PF01、PR、push、main update 或
扩大 date/year/format/action/concurrency/repair scope。完成本地 fix commit 后，MiMo 与 DS 对 fix 做双路
`/deepreview` re-review；两路与 Controller 均 PASS 才进入 focused-real evidence。
