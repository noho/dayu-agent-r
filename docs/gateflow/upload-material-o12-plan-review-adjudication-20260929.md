# UM-O12-F01 首轮 plan review 总控裁决

- MiMo `docs/reviews/plan-review-20260929-033734.md`：进程 exit 0、结构化 `subtype=success/is_error=false`、canary `mimo-6b8c4c4d` 匹配、stderr 仅白名单模型提示；结论 **fail**。Kimi 403 无有效第二路。Sol 原计划派发两条失败 command，`agent_status=failed`，计划只作候选。
- 总控按当前代码核对：`stage_company_meta_for_upload` 会重新加载并重新决策，`UploadCompanyNameRequiredError` 可在 started 后落入 material generic `unexpected_runtime`；`_run_upload_job` 泛异常保存无 typed code，而 direct 泛分类仅 `USER_INPUT`。已有 filing `stage_upload_company_meta_decision` 携带已核决策并在 commit guard 校验 observed state；storage 同版 published state 窄 facade 与 filing 既有模式相称，动机与 owner 均成立。不能把并发状态变化后的失败当作“新输入缺公司名称”。

| Finding | 总控裁决 | 修 plan 和验收 |
| --- | --- | --- |
| F1 高：后置状态漂移降级 | **accepted；先修 owner 契约** | admission 产生 immutable `MaterialUploadAdmission`，包含 canonical 身份、同版 observed state 与 `UploadCompanyMetaDecision`，经 explicit typed handoff 到 runner/workflow；公开独立 pipeline 调用在首事件前由同一 helper 做初始 admission。已接收请求在执行前/发布前状态变化归**发布冲突**，不能再次作为输入缺名 usage，也不能落 generic `unexpected_runtime`；复用 filing 的 state-dependent usage→publication conflict 思路和 `stage_upload_company_meta_decision`，在 batch 内携带已校验决策，storage commit guard 最终裁决，不做第三次“需名”重判。direct/job/observation/CLI/tool 的 typed conflict 必须从同一 Fins failure 真源投影，job failed record 不只写原文 message。测试注入 admission 后至 job 执行前及 pre-yield 至 batch 之间变化，断言无业务发布且非 generic 失败；接收时稳定缺名仍在 started/job/observation 前 typed `COMPANY_NAME_REQUIRED`。若当前 public failure code 无法准确表达冲突，先在 owner 边界明确最小 public contract，不能借通用 runtime 码掩盖。 |
| F2 中：tool 测试白名单遗漏 | **accepted** | 补 `tests/fins/test_fins_ingestion_tools.py`，并在 plan 列全仓 `FinsIngestionRuntime.create` 调用点；新仓储依赖为显式必填 keyword，不用 optional/fallback 逃避机械调用方更新。 |
| F3 低：切片偏粗 | **接受事实，保留一个端到端行为切片** | 该公开契约要求 CLI/tool/Service、direct/job/独立 pipeline 同时保持正确错误事实；拆成 runtime pass 与 pipeline 仍降级的中间提交不满足用户已确认 goal。plan 承认一次成型成本并列按 storage→Fins admission→workflow→公开入口逐层审查/验证清单；若实施发现不可在一次 slice 审清，返回 plan gate，不把半成品 commit。 |
| F4 低：CLI 预检与提交双构造 | **accepted** | 复用单一 CLI args→`FinsUploadMaterialRequest` 构造，Service 接收同一 request 对象（参照 filing），增加 `dayu/service/fins_direct.py` 与受影响测试到白名单，枚举其它调用点并迁移；预检/提交两次读取可保留，但请求字段与 owner validator 不分叉，不通过额外 payload 透传。 |

计划的稳定状态零业务发布与并发漂移需分开承诺：前者无 job/observation，后者可能已有 job/observation，但必须安全 typed 冲突终态。O05/O16 静态校验先于状态读，O14/O15 目标状态先于公司缺名的依赖仍成立。下一 gate Sol 仅修 plan，再 Kimi/MiMo 双路有效 re-review；产品不得实施。

Sol plan fix `o12-plan-fix-sol-20260929-01` 进程 exit 0、JSONL `turn.completed`、canary `gpt-6-sol-e5f5ff33` 匹配、stderr 空，但 `.venv` 文件检查 exit 1 与 `git diff --no-index` 的差异退出 1，按协议 **agent_status=failed**，落盘计划 SHA-256 `e9eca9fa3a728b9a65a1356c75b89d95c016b594553756c32d663d5d9b0abcbb` 只作候选。总控初核它确实把同版 observed state、immutable decision、后置 `source_publication_conflict`、batch guard、job typed failure、CLI 单 request、tool/Service 白名单及两个竞态窗口写入，但新增 batch-scoped precondition 与 keep/skip 无 intent 时的原子性成本须由独立计划复审从代码反证，不能先实施。Kimi 额度尚未恢复；MiMo 可先作本候选独立审查，双路 gate 仍缺 Kimi。

## MiMo 第二次 plan re-review 裁决

`docs/reviews/plan-review-20260929-042002.md`：预检 ok、显式 `/private/tmp/dayu-upload-o12`、独立 output/stderr；exit0、Claude JSON `subtype=success/is_error=false`、59 turns、canary `mimo-3b252c71` 匹配，stderr 仅白名单模型提示，`agent_status=completed`。首轮高 finding 的 typed admission/decision carry/commit precondition 必要性由当前代码独立复证，批次前置检查并非无依据过度设计。新增两项中等 finding **accepted**，当前 gate 仍 `plan review -> fix`，Kimi 403 仍无有效第二路。

1. **F1：必须单 batch 原子收拢**。现 SEC/CN material 均先 commit 公司、再准备并另 commit 材料；已确认的“已接收状态漂移零公司/材料业务发布”无法在两次 commit 中成立。plan 将其定为不可条件化的实施要求：`prepare_upload` 后仅一次 `begin_batch`，在同一个 batch 注册 observed-state precondition、stage 原 admission 的公司 decision 和 prepared material mutation，最后同一次 commit。原公司 commit 与材料 commit 间的注入点要纳入回归，断言任何 pre-commit 漂移/失败均零业务发布；若 storage 无法提供该形状按 stop condition 回 plan，不允许每个旧 batch 各自 guard 后半发布。
2. **F2：比较 owner 与次序必须封闭**。precondition 注册只记录 expected typed snapshot；storage batch/publication owner 在同 ticker guard 内、物理 swap 前重读并用唯一纯比较函数判定，不能在 workflow 提前比。比较采用严格同版：`CompanyMeta` 五个字段的 immutable typed 值全等（含 `updated_at/resolver_version`），exact material source meta 的严格验证后 canonical 完整字段值全等（含 revision/时间）；presence、tombstone、字段任一变化均为已接收状态漂移 typed `source_publication_conflict`。这种保守策略可能使仅时间刷新的良性并发也冲突，但避免 silent stale publication，与已接受“状态变化归发布冲突”一致；并发调用者可基于新状态重试，storage I/O/损坏仍不能伪装为冲突。alias/identity guard 先于 precondition；二者同轮都冲突时保留既有 `ticker_alias_conflict` 优先级。`prepare_upload(previous_meta=admission.observed_state.source_meta)`，删除 workflow 第三次自由读取。计划测试覆盖仅 updated_at 漂移、source revision 漂移、alias+drift 同时命中、guard 内 check/swap 注入及单 batch 业务原子性。

该选择仅定义本 WU 已确认的并发冲突边界，不改 O14/O15 的目标动作表，也不新增通用乐观重试框架。Sol 只修 plan，之后 Kimi/MiMo 有效双路 re-review；产品未实施。

## Sol 第二次 plan fix 候选

`o12-plan-fix2-sol-20260929-01`：预检 ok、显式 `/private/tmp/dayu-upload-o12`、独立 output/stderr，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-bb73bb73` 匹配、stderr 空；一条 `git diff --no-index --check` 对新文件返回 1，按 sub-agents 严格协议 `agent_status=failed`。总控核对候选计划 SHA-256 `bbbb35f6614fdb9e4ca63a7af10119c6033e29d6d77f7f2e6461d50b98ea6d30`：明确 storage snapshot 将完整 canonical business meta 与私有 revision 分开保留、单 batch/单 commit、guard 内严格比较、alias 先行、prepare 不自由读旧 meta，并补旧双 commit 窗口及更新时间/revision 测试。候选内容可供独立复审，不能作为已通过 gate；Kimi/MiMo 有效双路 plan re-review 前不实施产品。

## 跨项复审新增修复项：COMPLETE tombstone 的 source meta 合同

O14/O15 MiMo 第二次同版复审 `docs/reviews/plan-review-20260929-054535-state-mimo.md` 指出 O12 候选 §storage 状态把 `source_meta=None` 写成“无有效 active meta”，却用它作 `resolve_upload_action(auto, source_meta)` 和 `prepare_upload(previous_meta=source_meta)` 的唯一输入。总控核对代码证据后 **accepted，高严重性**：若 COMPLETE tombstone 被投影为 None，auto 会从 update 恢复误转 create；显式 update 会把 `document_version` 重置 v1、`first_ingested_at`/`created_at` 重置。此缺口必须在 O12 storage owner 计划修复，不能由 O14 消费者猜测补偿。

Sol 下一轮仅修本计划：同版 `MaterialUploadPublishedState` 对可信 COMPLETE tombstone 必须保留完整 canonical business `source_meta`，包括 `is_deleted=true`、`deleted_at`、版本和首次时间，以及独立 opaque revision；`None` 只给真正无可信 meta 的状态。状态类型/仓储 owner 约束 presence/tombstone 与 meta 一致，若 REPAIR_REQUIRED 不能取得可信完整 meta则 fail closed，不伪装 missing。写明该 meta 同时供 auto 解析、`prepare_upload` 连续性和 guard 严格比较使用；owner 测试覆盖 auto+tombstone→update、显式 update 恢复的 `first_ingested_at`/`created_at` 不变且 `document_version` 递增、`is_deleted` 复位，以及 missing/unsafe 的 fail closed。O14/O15 实施前核对此最终合同，不满足回 O12 gate。Kimi/MiMo 复审须针对修订同版，产品未实施。

`o12-plan-fix3-sol-20260929-01` 预检 ok、绝对 cwd/独立 output/stderr/last-message，process exit0、JSONL `turn.completed`、canary `gpt-6-sol-bc57e844`、stderr 空；但两条对未跟踪文件的 `git diff --no-index --check` exit1，严格 `agent_status=failed`。总控独立实读候选 SHA `cf39265253676c63b65a6e29f41bee0e0c7193c1853e40392b02675e15f979cb`：COMPLETE tombstone 全量 meta/revision、auto 恢复、prepare 时间/版本连续性、storage/owner 测试及停止条件均已入文。此为可供复审的候选，不是 gate pass；代码未实施。

## 总控跨 O34 已接受行为反证：O12 单 batch 方案阻断（2026-09-29）

主工作区 `docs/reviews/upload-material-um-o34-oracle-adjudication.md` 明确记录用户已接受：F19/S19 的 material 转换/内容失败及 L02 取消时，已合法提交的 AAPL 公司 identity/meta **保留**，材料无 manifest 条目故文档未成功；公司与材料是独立业务事实，不能在 CLI 反向删除公司。当前 `sec_upload_workflow.py:520-562` 和 CN 同构路径确实先公司 batch commit、后 `prepare_upload` 转换、最后材料 batch commit。O12 binding goal 只要求 fresh 缺名在 `upload.started` 与公司/材料业务写入前 typed 拒绝，以及 alias 冲突不污染公司；没有要求**有效公司名称已提交后**的材料内容失败/取消回滚合法公司事实。

当前 O12 计划 §3 却强制 `prepare_upload` 后才唯一 `begin_batch`，把公司与材料放进同一 batch/一次 commit；F19/S19/L02 类输入在转换失败或取消时将**没有公司事实**，直接改写 O34 accepted 行为。此前 MiMo F1 单 batch 建议与总控接受的“post-admission drift 零公司/材料发布”是由 O12 计划复审引入的过宽成功条件，不是用户已确认的 O12/O34 共同目标。按第一性原理与语义 owner，**O34 已接受的独立公司事实必须保持**，不能为 O12 公司名称前置校验引入跨事实原子化。此项记为 **F3 严重 / plan gate blocking**，覆盖此前 F1 的单 batch 裁决；不是让 CLI fallback 回滚公司。

Sol 须重新修 O12 plan：先在 Fins admission 对缺名做同源 prevalidate、携带同版 state/typed company decision；合法公司决策依现有独立公司 batch 在转换前由 storage alias/identity guard 提交，取消/内容失败可保留公司事实。材料发布在其**自己的** batch/guard 使用同版 expected material source precondition；接收后公司或 source 漂移如何投影 typed conflict 应逐阶段明确，不能声称一律零公司发布或重判为缺名。alias 冲突仍不得污染公司；材料目标与 manifest 在材料 commit 正常返回前不算成功。现有 O12 计划的单 batch contract、原子验收与 stop condition 需撤回/重写；O14/O15 所谓“消费 O12 唯一单 batch”也同步阻断并重审。若实际 storage 不能同时保持 O34 公司独立持久化与 O12 typed 安全，带最小反例回 goal，不私改已接受行为。

当前运行的 MiMo `o12-plan-rereview3-mimo-20260929-01` 对旧 SHA 仍可提供独立反证，但其结论不能使旧版本过 gate；后续必须对修订版重新 Kimi/MiMo 同版审查。产品未实施。

## 恢复版本断言范围修正（覆盖早期措辞）

早期跨项 F8 段的“显式 update 恢复版本递增”只在**新指纹不同于旧 `source_fingerprint`**时成立；这是当前 O12 plan §测试已写明的条件。已接受 UM-O13 A09 的同内容 `auto` 恢复保持旧 ID、旧版本 v3，不得因 tombstone 或“旧 meta 非 None”本身递增。两格都应保留 `first_ingested_at`/`created_at` 并清删除态；后续实施测试不得从早期未限定措辞引入相反断言。本修正不解决上节 O34 单 batch blocking；先重订公司独立持久化的 plan。

## MiMo 第三次旧版复审新增修复项（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-o12-rereview3-mimo.md` 对旧 SHA `cf392652...` 结构化 success、canary `mimo-d4fefe05` 匹配，结论 fail；未纳入 O34，旧版仍被 F3 阻断。总控接受其 F1/F2，并合并进入下一轮 Sol 计划修订：

- **F4 中：MISSING/UNSAFE 状态不变量与分类。** `FilingUploadPublishedState` 已约束 MISSING/UNSAFE 的公开 `source_meta=None`，即使底层保留私有业务 meta 也不能当可信 source；material 应复用该同版约束。`UNSAFE` 且底层仍有 meta、`REPAIR_REQUIRED` 有或无可信完整 meta，均不能按普通动作继续发布。O14/O15 已裁所有动作 fail closed；Fins owner 要给 material 业务可读 typed source-integrity 失败，不以目标缺失/通用 runtime 码伪装。若现有 `SOURCE_INTEGRITY_UNSAFE` 文案只适合 filing，在 owner 边界改为适用 material 的文案或明确最小新 closed code，不能让 workflow 拼字符串。owner 测试覆盖 UNSAFE 保留私有 meta、REPAIR_REQUIRED 可信/不可信 meta 及无业务发布。
- **F5 低：验证白名单遗漏。** 将 `tests/fins/test_filing_upload_publication.py` 加入受影响测试命令，以防共用 storage 状态/guard 改动破坏 filing。

以上 F4/F5 与 F3/O34 一起修 plan；旧 reviewer 对单 batch 的支持不适用已接受 O34。Kimi/MiMo 必须审新同版，产品未实施。

## Sol 第四次修订候选与总控实读（2026-09-29）

`o12-plan-fix4-sol-20260929-02` 预检 ok、绝对 `/private/tmp/dayu-upload-o12`、独立 JSONL/stderr/last-message；进程 exit0、`turn.completed`、canary `gpt-6-sol-cb475c63` 匹配。但两条 `rg` 无匹配 exit1，stderr 有非白名单 `apply_patch verification failed`，严格 **agent_status=failed**，只采纳总控独立核对的候选内容。plan SHA-256 `45b6478a3e94d5a63f3dee752a81d850c68c78d84190b05f77f44ad888e7c20e`。

总控实读 §1–3、白名单和测试：旧公司+材料唯一 batch 与“任意失败零公司发布”已撤销；稳定缺名在首事件/业务写入前拒绝，合法公司先独立 commit，转换失败/取消后可保留 O34 公司事实；材料用自己的 batch/同版 source 与 post-company guard，权威 manifest 与材料 commit 成功绑定。MISSING/UNSAFE 公开 meta=None，REPAIR_REQUIRED/UNSAFE fail closed，COMPLETE tombstone 保留可信 meta/revision，同指纹恢复版本不增、异指纹按既有规则增。`test_filing_upload_publication.py` 已列入命令。该形状符合已接受裁决方向，仍须 Kimi/MiMo 对同 SHA 从实际 storage owner 反证 alias 优先、两批 guard、typed 分类和过度设计；不得把候选称 plan pass 或开始产品实施。

## 第四修订版双路复审与待修清单（2026-09-29）

Kimi `docs/reviews/plan-review-20260929-094058-o12-rereview4-kimi.md` 和 MiMo `docs/reviews/plan-review-20260929-094433-o12-rereview4-mimo.md` 都对 SHA `45b6478a...888e7c20e` 预检匹配、进程 exit0、结构化 success、canary 分别 `kimi-f4b6be16` / `mimo-4e8a490c` 匹配，stderr 仅白名单提示。Kimi pass-with-risks；MiMo fail。总控按直接 owner 证据接受以下 **全部未修复** 项，不能单路放行：

- **O12-PR4-F1（中，MiMo）**：共享 `fins_upload_failure_from_exception` 当前把 `CompanyMetaConcurrentUpdateError` 归 `storage_io`，filing 真实可达。计划须钉死 material 语境把该异常及两个 guard conflict 归 `source_publication_conflict`，filing 仍保持旧 `storage_io`，明确语境分叉的唯一 owner，并用 filing/material 两端断言锁定；禁止全局改共享映射导致 filing 漂移。
- **O12-PR4-F2（低，双路）**：CLI `FinsUploadPrevalidationError` catch 在 `dayu/cli/commands/fins.py:204-207` 硬编码 `upload_filing`；材料 UNSAFE/REPAIR_REQUIRED 会误标。计划点名按 `args.command_name` 渲染与记录，并在 CLI hermetic 测试断言实际 `upload_material` 命令名、双流和 exit。
- **O12-PR4-F3（低，MiMo）**：upload job typed 失败记录改造不得污染 `_save_failed_from_exception` 的 download 共用收口。计划定死 upload job catch 处的 typed 构造/保存边界，保留 download 既有形状并补回归。
- **O12-PR4-F4（低，Kimi）**：删去两个 workflow 对 `stage_company_meta_for_upload` 的生产调用后，该旧函数及 `__all__` 导出成为死代码。总控选择删除：计划白名单补 `dayu/fins/pipelines/upload_company_meta.py`，删除该函数和导出，将白名单内两处测试引用迁至新的 decision helper 或仓储直写夹具；不能留可误用的发布期重读/重判路径。

Kimi 的 admission 签名、storage conflict 异常名、selection carry 三个 OQ 按最小 typed admission 接口在计划修订时明确，不增双形态 optional/fallback。MiMo 的 REPAIR_REQUIRED 人工构造及 writer lock 竞态注入方式作为实施验证配方，不把 fake 证据冒充真实 owner。O34 公司独立提交和 manifest 成功边界不变。**plan gate fail；下一 entry 为 Sol plan fix、同新版双路 re-review。**

## Sol 第五次计划修订候选与总控核证（2026-09-29）

`o12-plan-fix5-sol-20260929-01` 预检 ok、显式绝对 `/private/tmp/dayu-upload-o12`、独立 JSONL/stderr/last-message；进程 exit0、`turn.completed`、canary `gpt-6-sol-f20ee392` 匹配、stderr 空，但一次文本断言命令 exit1，严格 **agent_status=failed**。不能以子 Agent 自述视为 gate pass；落盘仅是待审候选。总控实读计划与 `docs/gateflow/upload-material-o12-plan-fix5-20260929.md`、直接核对旧 helper 唯二生产调用和 CLI catch/current shared mapper：F1 material 专属映射入口保留 filing `storage_io`，F2 CLI 用实际命令名，F3 upload job 专属 typed 保存、download 共用路径不变，F4 白名单纳入 `upload_company_meta.py` 删除旧 helper/导出/测试引用；typed admission 必传、selection carry、storage conflict 单一类型也入文。O34 独立公司 commit 与 material manifest 必要条件未回退。当前计划 SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`，`git diff --check` exit0；**仍须 Kimi/MiMo 同 SHA 独立计划复审，产品未实施。**

## 第五修订版 Kimi 单路复审（2026-09-29）

Kimi `docs/reviews/plan-review-o12-rereview5-kimi-20260929.md` 对同 SHA 进程 exit0、结构化 success、canary `kimi-0e5ca311` 匹配，stderr 只有白名单 `[claude-code:unrecognized_model]`；结论 **pass-with-risks**。总控复核 reviewer 指出的 **O12-PR5-F1（低）**：新 upload job typed 异常收口必须沿 `*_if_active` 原子终态语义；正常终态或取消已落盘时不可覆写成失败。代码当前共享路径有 read-check + active-only 保存，而新路径尚在计划中未明确这一条；另需在终态落盘后注入 progress 发射失败，断言 job 终态和双摘要不变。此项先登记为实施前要钉死的 owner 契约；MiMo 同 SHA 尚未完成，不能据单路判 plan gate pass。

## 第五修订版双路复审总控裁决（2026-09-29）

MiMo `docs/reviews/plan-review-o12-rereview5-mimo-20260929.md` 对同 SHA 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-0c9ff98a` 匹配，stderr 只有白名单模型提示，结论 **pass-with-risks**。报告中的 `.venv`/输出存在性探测和一次 `rg` 无匹配均按原样保留，不把探测命令 exit 非零当产品证据。Kimi/MiMo 均独立从当前 storage/Fins/CLI 代码核证 PR4-F1～F4 已闭合，无中高严重度新 finding。

总控接受并登记两项 MiMo 低 finding，同时明确可实施的最小 owner 边界：

- **O12-PR5-F2（低，接受）**：`upload_runner is None` 的现有 upload job 失败路径会通过 `_save_failed` 写 message-only `failure_summary`，与同一 job 的 typed `result_summary.failure` 可能不同源。O12 既然在 upload job owner 中收敛 typed 终态，本次实施将此路径也纳入 upload 专属 typed 保存，使用同一 reason 投影 `failure_summary` 与 `result_summary.failure`，并增加无 runner 终态断言；不修改 download/preprocess 共享 message-only 路径。此项是同一 owner 的窄修复，不另加兼容分支。
- **O12-PR5-F3（低，接受）**：计划中 selection“校验它与动作及 request 文件一致”只指 validated admission 的构造不变量：delete selection 机械为空，upsert selection 按 request 文件保序；`delete+files` 的业务拒绝归 O16 共享 action/files owner，在 O16 已集成后 O12 消费其结果。本项不能在 selection 层重写 O16 行为，也不以 O12 旧 HEAD 的静默忽略固化测试。
- **O12-PR5-F1（低，接受）** 的实施硬条件：upload 专属 typed 保存只使用 active-only 原子终态 API；record 已 `SUCCEEDED/FAILED/CANCELLED` 时不覆写。终态落盘后注入 progress 发射失败，断言状态、`failure_summary` 与 `result_summary` 保持原值；并核对 terminal event 与既有 failed owner 的形状一致。

上述三项均落在 O12 已允许的 `dayu/fins/ingestion_runtime.py` 与对应 owner 测试内，F3 只是限定边界，没有新的文件或产品层；不改变 O34 合法公司独立 commit、材料 manifest 必要条件、O13 tombstone 版本或 filing/download 旧投影。两路均判 `pass-with-risks`，总控据代码证据及本裁决的强制验收条件判 **plan gate pass**；未实施、未验证产品。下一 entry：仅精确提交 O12 goal/plan/双路 review/本 adjudication 的 accepted plan checkpoint；产品 implementation 必须待 O16/O05 accepted+integrated 后基于实际 HEAD 重核，不能在旧 `8d8d494f` 直接改重叠 admission。
