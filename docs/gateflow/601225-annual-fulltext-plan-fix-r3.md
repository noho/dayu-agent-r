# 601225-annual-fulltext：plan fix r3 规格澄清交付

- Gate / work unit：`plan re-review → fix（r3）` / `601225-annual-fulltext`；仅 fix 交付，不是 re-review pass / accepted plan，不更新总控 state。
- 仓库 / branch / HEAD / base：`/Users/leo/workspace/dayu-agent-r` / `fix/601225-annual-fulltext` / `7637bb0b4fbca212a4db0f4cfc09655e66516695`，本轮前后均不变。
- Binding scope：[已确认目标](601225-annual-fulltext-goal-confirmation-20261012.md)；普通公开非 overwrite 三全文、官方原文财年、摘要不冒充/不阻挡、合法完整源增量复用；不扩财务提取、OCR、一般日期、历史恢复或调用方工程。
- 必读输入：AGENTS.md、binding goal、[r2 plan 修复记录](601225-annual-fulltext-plan-fix-r2.md)、当前 plan、[MiMo r2 review 153909](../reviews/plan-review-20261012-153909.md)、[DS r2 review 153910](../reviews/plan-review-20261012-153910.md)、[r2 总控裁决](601225-annual-fulltext-plan-rereview-r2-adjudication.md)，均已读取。两路实际退出 0/completed 的事实依据是总控裁决，本轮不查看或操作 runner / 其它 Agent。
- 唯一文档变更：[plan](601225-annual-fulltext-plan.md)与本文；新增临时副本、差异、保护记录和 SDK 字段探针仅在 `workspace/tmp/601225-plan-fix-r3/`。
- 旧 plan SHA256：`5b506a9dca7af364e8b85f7ba3d12f38dc84b972bbb476f1c1150e420a4c4ae8`。
- 新 plan SHA256：`7a2acac94ca5592b5848a3ca78c77be55e2f79766f69f83db558f0017d615aaf`。
- 权限边界：未实施生产代码/测试/依赖/README，未 commit/push/PR，未操作其它 Agent/任务，未修改原证据、其它 review/adjudication/state 或调用方目录。只使用 Gateflow 当前 fix 约束；本轮用户限定覆盖技能自动推进规则。

## 第一性原理与语义 owner

修订动机成立，但仅是 code-generation-ready 表述缺口。现有 writer 已有正确的 JSON canonical 表示，没有新证据证明生产增量一定失败；MiMo 原高严重性及“所有合法增量都会失败”的判断被总控降为低，不能据此重设计已经闭环的方案。

直接代码事实：`dayu/fins/pipelines/cn_download_models.py:171-202` 定义并校验 candidate 的 canonical tuple；`cn_download_source_upsert.py:260` 已写 `list(candidate.period_projection.covered_periods)`；`cn_download_filing_workflow.py:198` 的 HK 已按同一 list 表示比较。既有 writer 是持久表示 owner，candidate period projection 是期间内容/顺序真源，新 P4 私有 publication helper 是 candidate 与本地 meta 匹配的唯一业务 owner。P3 共享原件读取 owner 只验证两份 raw JSON 的同版关系，不承担 candidate 投影。

原四项 accepted（MiMo-r1-01/02/03、DS-r1-01）保持 r2 双路及总控已确认的计划层「已修复」，不重开 facts GET、异常作用域、原件读取/witness 或 HK 回归方案。新 MiMo-r2-01 仍沿总控 `accepted / 低 / 未修复` 原记录；本轮已提交对应规格修订，最终状态须总控在新同版双路 re-review 后回写，本文不自行放行。

## 精确修订位置（plan 旧行 → 新行）

| 修订 | 旧位置 → 新位置 | 当前唯一规格及验证归属 |
| --- | --- | --- |
| MiMo-r2-01：P4 canonical covered periods | P4.2 `:188` → `:192` / 新增 `:194` | meta 必须有非空 canonical JSON list，严格 `type(value) is list`；与 `list(candidate.period_projection.covered_periods)` 完全相等。缺失/非 list（含 tuple）/空/重复/未知/乱序/值不一致统一 period_metadata_mismatch；不转换持久 tuple、不 sort/deduplicate、不新增 schema/枚举/helper。A/B 共用原规划 publication helper。 |
| P3 同 snapshot 比较边界 | P3.2 `:115` → `:115` / 新增 `:117` | expected_meta=同窗 entry.source_meta，和 snapshot.source_meta 比 raw JSON 原值；与 candidate 无关，不将 tuple 投影混入同版检查，不转换或重排持久值。 |
| P5 真实 Fs 正例、direct owner 负例、HK 回归 | 原 P5.1 `:262` / P5.2 `:274` / P5.3 `:301` / P5.4 `:317` 各段其后新增 → `:269-270` / `:283` / `:311` / `:329` | 真实 Fs COMPLETE 读回 `['FY']` 对 candidate `('FY',)` 合法 skip，GET/转换/source 写为 0，meta/revision/两 SHA 不变；缺字段及非法容器/期间由 direct owner 拒绝，tuple 不经 JSON serializer 变成 list 后冒充负例。A/B 失败沿原作用域；HK 原 list(...) 正向及 mismatch 行为保留。这里只修改测试规格，没有实现或运行测试。 |
| 非阻塞 OQ1：本地 locator | P3.2 `:115` → `:115` / 新增 `:119`；测试规格 `:269` | `type(source_url) is str and source_url != ''`；缺失/非 string/空 string 为既有 CnAnnualReportSourceError。非空 string 原样保留实际取得时 locator，含空白也不 trim/normalize，不参与身份/HTTP、不反推 source/year；远端 URL 由原 provider owner 消费，不增一般 URL 框架。 |
| 非阻塞 OQ2：三真实年报 Docling 最小内容 sanity | P6.2a item3 `:395` → `:407`；item6 `:398` → `:410` | 实际 JSON 先 model_validate_json；原 origin/pages 保持。三目标另要求 bool(doc.body.children) 且 texts 中至少一项 item.text.strip() 非空；空 body/无文本/全部空白失败并输出数量/状态。仅内容存在性，不做财务表/数字提取或准确性研究，不改产品/来源 schema。 |
| 版本与复审责任 | `:1-7` → `:1-7`；P7 `:425` → `:437` | 标注 r3、引用 r2 裁决/本 artifact，保持原四项闭环，新 accepted 与两个 OQ 交双路聚焦复核；不更新 state。 |

行号只用于定位，section/符号仍是实施依据。此次不改变 binding boundary，无需扩大目标或重新定义成功信号；若后续实际 API/内容不能满足既有三目标验证，应给总控具体 blocker，不能自行扩产品或来源 schema。

## 真实验证与明确未运行项

| 本轮实际动作 | 实际结果与证据 | 证据限度 |
| --- | --- | --- |
| Preflight / final git 核对 | branch/HEAD 与给定值一致；`git diff --exit-code HEAD`、`git diff --cached --exit-code` 前后退出 0；记录于 protected-before/after.json。 | 证明 tracked 内容及 index 未改，不是代码验证。 |
| 只读 owner / SDK 源码 | 核对 tuple 校验、writer list、HK list 比较；SDK `document.py:191-196` 是 body / texts，`items/node.py:27` 是 children，`items/text.py:40` 是 text。 | 不运行新的 P3/P4 owner（尚未实施）。 |
| 激活 venv 后 `PYTHONDONTWRITEBYTECODE=1 python workspace/tmp/601225-plan-fix-r3/probe_docling_content_contract.py` | **实际进程退出 0**；docling 2.127.0 / core 2.96.0 / pydantic 2.13.2。empty_body、empty_text、whitespace_text 均 schema-valid、origin/pages 非空但 sanity false；nonempty_text schema-valid 且 sanity true。`docling-content-contract-probe.json/.log` 保存字段/结果。 | 合成 SDK 模型/API 探针，没有读取官方 PDF、运行 PDF→Docling 或证明三真实年报产物。 |
| 文档边界检查与 diff | `document-check-preartifact.json` / `document-check.json`、`plan-r2-to-r3.diff`：冻结段落逐字相等，新增字段/predicate/测试规格存在，hash 与本文一致。 | 机械检查不是正式 planreview 或 accepted 状态证据。 |
| 精确文件保护 | protected-before/after.json：44 个既有本任务产物/AGENTS 的 SHA256，只允许 plan 变化；其余 43 个逐项相等，无缺失，原 review、裁决、goal、root-cause、state、r1/r2 fix 与临时记录不变。新增 docs 只有本文。 | 不重新建立或重算旧 10k 文件清单；本轮不访问调用方目录、不重新读取官方原件，其未修改依据是全部写入路径限于两份文档及新临时目录，不声称对它们做了独立全量复核。 |

冻结保持：P0/P1/P2 全段、P3.1、P3.3–P3.6、P4.1、P4.3–P4.4（含异常矩阵）、P5.5 命令/coverage、P6.1–P6.2 observer/真实 CLI、P6.3 GET 精确集合逐字不变；P6.2a item1/2/4/5 与既有 r2 probe 记录逐字不变。SDK origin、两 SHA/fingerprint、真实转换进度和公开诊断要求全部保留。

**未运行**：生产/测试实现与依赖安装、pip check、受影响 pytest/新增 owner 矩阵、coverage、pyright、README 更新；真实 Fs 新 skip/负例和 HK 回归仅有测试规格；正式 observer/verify/compare、四次真实 bare CLI、真实 Docling、仓储内容/网络对账、双路 r3 re-review 均未执行。未重采官方证据、重跑 432 测试/pyright 旧基线、旧 grammar 或 observer 探针。只改计划及本轮临时字段探针，不以它们替代实施验证。

Docs decision：只改 plan/创建本文；无能力落地或 README 触发，本轮禁止 README 实施，保留 P7 已规划的实施后文档边界。

## Classified residual risk / owner / destination

| 风险 / 未覆盖 | 分类 | owner / destination | 阻塞与处置 |
| --- | --- | --- | --- |
| 新 accepted canonical 表示及两 OQ 规格修订尚未复审 | fixed in current slice（plan fix/re-review 责任） | 本轮 Sol / 总控 / 新 plan hash、本文、两路聚焦 re-review artifacts | 本轮仅交付修订；总控实际复审回写前不自放行实施。 |
| S1 owner 实现/真实 Fs 正负例/HK 回归/依赖/类型/coverage/README | fixed in current slice（未来实施验证） | 实施 Agent / 总控 / S1 checks 与 code review artifacts | 未执行，后续必须完成。 |
| 三真实年报 schema 与内容 sanity、四次 CLI、正式 observer/对账及外部网络/pin/内容变化 | fixed in current slice（真实验收责任） | 实施/验收 Agent / 总控 / P6 原 argv/exit、真实产物、模型/content/hash/origin/进度/http/compare 记录 | 合成字段探针不能代替，真实差异交总控裁决。 |
| 隐藏损坏摘要/未知 identity/历史错年自动恢复；历史启动树/raw 缺失 | assigned to later work unit | 原 P7 Fins 完整性维护者 / 总控 / 独立历史完整性任务、根因历史边界及可追溯任务 | 不扩恢复、不补造历史事实。 |
| OCR/扫描/未知或跨行布局/其它公司；落选全文及摘要 repeat GET 成本；UTC/本地日偏差 | assigned to later work unit | 原 P7 年度事实 / 性能 / 日期维护者及总控 / 独立发现、按需性能、日期任务 | 原分类/owner/destination 保持，不重开闭环或增加 cache。 |
| SDK origin 有损 binary_hash、无 durable derived_from 的历史转换因果审计局限 | assigned to later work unit | Fins 转换/审计维护者 / 总控 / 如需的独立来源审计任务 | 原 origin、两 SHA/fingerprint、真实进度保持，不新增审计 schema。 |

没有新增业务目标、source owner 或未分类风险；没有必须改变 binding boundary 的 blocker。只有 S1，无后续 approved slice/既有 issue，不新建 issue。

## 交付状态与总控接手点

plan fix r3 规格修订交付完成；无 implementation、accepted commit、re-review pass 或 state 转移。总控需先确认本次执行者实际退出，再冻结新 plan SHA256，同时派两路仅聚焦上述 canonical/OQ 差异与闭环保持性复审。本文不执行派发、等待或操作其它 Agent，也不自行接受计划或推进下一 gate。
