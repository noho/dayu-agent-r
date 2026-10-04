# PR197-R1/F4 user-scope plan fix：保全现成裁决

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-c242e290

历史校验修订（F4-PV01）：上行是上一 label `pr197-f4-planfix-sol-20260930-02` 的实际文件值；原报告误写 `gpt-6-sol-c242e29`，漏末位 `0`。上一任务虽外层 exit0 / turn.completed、工具读取正确，仍因报告不匹配被总控 rejected；本次更正文档不改变旧拒收事实，也不作为本轮校验证明。修复报告见 `docs/gateflow/pr-197-r1-f4-report-validation-fix-20260930.md`；须先由总控独立验收新交付，再送同版双路 Planreview，候选仍未 accepted。

## 身份、允许写入与 gate

- Label `pr197-f4-planfix-sol-20260930-02`，WU `fins-hk-download-identity-batch-read`；应用 Gateflow 的 plan fix 要求，用户明确本轮交付后停止，不顺延自动推进。
- branch `codex/upload-material-oracle`；起始/末核 HEAD 均 `60307c15947e2f89457e03126b1251aeb4264c53`。唯一 cwd 为本仓库。未创建分支/树、stage/commit/push/PR/merge、网络、真实下载/OCR或读取私人材料。
- 上一任务通过工具读取 `sub-agents.AC1pAZ/canary.txt` 得到完整值 `gpt-6-sol-c242e290`，但原最终报告与两个 artifact 均写成 `gpt-6-sol-c242e29`，不满足逐字匹配，旧 task rejected。本文上行仅更正历史实际值；本轮独立校验与身份见新修复报告，不以历史标记代替本轮证明。
- 唯一正式写入：修订 `docs/gateflow/pr-197-r1-f4-plan-20260930.md`；新增本文。临时 probe/config/end-check 均在 `workspace/tmp/pr197-f4-planfix-sol-20260930-02/`。源码/tests/README/goal/controller/queue/旧 fix/旧 review 只读。
- **作者完成 plan fix，候选待 re-review；产品未实施，计划未 accepted，F4 产品 finding 未修复。** 由总控对本文登记项回队列并冻结新 plan，安排 MiMo/Kimi 同版 Planreview，总控裁决后才可 accepted plan commit；本轮不派发、不审查、不推进 gate。

这不是 provider 重试。上一任务因用户明确 steering 令旧 goalhash/错误迁移接受失效而 blocked，历史候选已保存在 commit60307与字节副本；本轮按新授权重新设计，不删除/改写旧失败事实。用户现成裁决优先于 reviewer 建议与总控自加技术路线。

## 用户权威、输入与旧新 SHA

| 对象 | SHA256 / 状态 |
| --- | --- |
| binding goal | `d1f374b9adb053761c66e9dd04e2a27ae6cdb4e299b715f70d9f91ee99d9d05e`，首尾不变 |
| 本轮原 plan / 旧 blocked candidate | `0ebe0291215a63df2c2d0a41361dda76cdee9789b5f0b4a63c6e4fa606fb3a80`，旧件保存在 `workspace/tmp/pr197-f4-oldscope-planfix-inputs-20260930/` 与60307 |
| 上一任务新 plan（本次报告修订前原字节） | `e972b900adfd62e8ff27fc9bc0fa72f94f296beef9a903927cf85160a3186c6d`，上一任务唯一允许修改的 frozen产物；本次修订后 SHA 见新修复报告 |
| 旧 fix（只读） | `c0d7cd213fc2b0f03ee63c0dca225dfccb0d34cd182abfbb45c197580cbdaccc`，首尾不变 |
| 用户原完整PR裁决 | `b712698078bc4c59e0d2ec5bd379f8b6c4dce29eaa8745352ebef57d0bd18c50`，F4行49/68动机与owner修法 |
| MiMo report212523 | `d1e987e7498ba7c04e05927509502c7a7d1c19749a0cdb01b7c71debc26eb2d8`，只读证据，不能授权变更行为 |
| Kimi report212525 | `68963a5df8061e2d22dfd45a9486e7b6af1201bef9d99c5856bf8b6030b987ad`，同上 |

首核 frozen manifest23项全部匹配。末核除 plan 外22项全部匹配，包含相关 source/tests/README、当前 goal 与旧 fix；详情 `workspace/tmp/pr197-f4-planfix-sol-20260930-02/end-input-check.json`。不对非冻结 controller/queue/handoff 追加及已公告 F3/F7 产物加不变断言。末核出现 F3五utils及F3/F7/controller/handoff文档dirty属已公告并发范围，未报 F4 source漂移；HEAD本次没有改变。

## 第一性原理结论及关键方案变化

原 F4 问题成立：HK每候选list+D次public get，各自guards且四处消费；不是原整run必须数学linear、不是来源集合新uniqueness需求。现有 get 的语义是身份一致的可读meta、去私有revision与普通读取异常；它不承诺物理publication完整性。直接复用 list/get 的 unguarded owner 可以实现更窄同guard批量观察，不必改业务错误。

新计划选择 `read_source_meta_view(ticker,source_kind)`，返回有序成功前缀+首个原get异常；完整读成功才可当完整身份集合查询。identity owner一次建索引、依candidate保持“前缀缺internalID → 原read error → 扫完duplicate → existing/digest/allocated”顺序。避免 eager batch把后项读错提前覆盖前项缺ID，也避免部分成功被当MISSING。

旧 inventory-first/typed拒绝方案、prepare/PhaseA必需参数、start前typedabort、postrepair重算accepted、raw不可信字段新typedobservation、stagedAPI均撤出候选。新 plan 保留原preflight/PhaseA/B/previous_meta/commit闸门、原repair簿记、direct stream入口与三轮retry签名。批初accepted/repair一次复用；start、stream隔着用户可消费yield，分别新读，原异常catch位置不迁移。这样保留stream普通失败后的继续与原取消对象/rows。无churn同ID、有外部变更原start标签与实际streamID可不同，不新增事件原子性承诺。

该方案减少身份逐条public读取/guards和批初重复消费，保留每实际窗口O(D)meta/CPU成本；典型全HK `1+2n+r`批量读取，n为候选、r为内部新增retry。没有冒称消除了既有完整性扫描或整run变linear。F5的可信年度证据由其独立设计，不把本meta可读取view伪装成F5 trust API。

## 修复项立即登记（交总控回队列）

下面状态是本轮文本修复/证据分类，不代替双路复审或产品修复。Gateflow作者交付状态用“部分修复”；旧失效授权不得标记已成立业务选择。

| 登记项 / 来源 | 本轮修订及定位 | 状态与回队列要求 |
| --- | --- | --- |
| F4-PF-B01 用户现成裁决优先 | plan§1/§2/§7：撤回错误迁移/prepare前移/提前abort；ordinary读取异常不统一typed；无需新的用户选择 | **部分修复**，scope恢复候选已写，需同版re-review验证；产品未修 |
| A1 / MiMo4-1 / KimiF1 度量漂移 | §2/§9：同guard观察计数、W0共享、实际窗口账；不承诺整runlinear/零边际身份I/O | **部分修复**，原全run目标证据失效，新计数待实施验证 |
| A2 / MiMo4-3 / KimiF2(b) 新鲜绑定与target-only | §6：每stream/retry新view，W0不传写绑定；Phase B/commit不动，F4-R01保持后续候选 | **部分修复**；新uniqueness建议未接受，不将其要求做成当前阻断 |
| A3 / MiMo4-2 / KimiF3 错误投影/损坏身份 | §4/§5/§7：复用get契约，前缀+原错保顺序，不从trusted-only丢失raw-readable身份 | **部分修复**；“ValueError→UNSAFE已接受”证据失效；MiMo持久duplicate影响按原总控反例驳回保留 |
| A4 / MiMo4-4/4-5 / KimiF4 成员/事件/取消 | §3/§6/§7/§9：同list枚举、start/stream原边界、普通failure继续、rows/cause守恒；不因库存枚举更严格改拒绝 | **部分修复**，direct/stream/retry精确接口与测试范围已写；无新start前typedabort方案 |
| A5 / F5路径 | §3/§10：source_integrity真实storage路径、F5独立trust读取，无F4强制前置 | **部分修复**，旧基础能力依赖推断不再强制；不修F5 |
| F4-PF-O3 本轮自发现：eager batch错误先后 | §4/§5：A缺internalID、Z坏meta，X与Y触发不同原错误；保留成功前缀及原exception对象 | **部分修复**，已由合成真实读取probe支持；新API正式owner test待实施，不新增业务规则 |
| F4-PF-O4 本轮范围判断：PhaseA共享非必需 | §2/§6：保留start yield前后两个观察，避免迁移exception catch/取消边界 | **部分修复**，候选方案待review；不是删除原业务约束或新增blocker |

两路旧报告fail/旧candidate blocked不改写。MiMo额外raw typedobservation与Kimi staged集合断言/统一typed投影建议未自动采纳；是否纳入需用户权威，本轮通过窄owner方案无需该新选择。

## 实际验证、所有错误/恢复与局限

读取工具均只读实际源码/测试/裁决；大组合输出曾截断，按owner/函数与finding小段补读。AGENTS/Gateflow、原F4裁决/current goal、controller最新steering、旧candidate/旧fix、两报告均作为输入核对。轻量memory registry仅确认“观察/裁决/实施分离”的通用原则，本轮F4事实全部由当前source/裁决验证，不将历史memory当当前代码证据。

| 实际命令/操作 | exit / 结果 / 边界 |
| --- | --- |
| cwd/branch/HEAD/status与上一任务 canary 读取 | exit0；工具实际读取完整值，但原报告漏末位，报告不匹配，旧 task rejected；起始60307；status与授权并发范围相符 |
| 首次manifest SHA核验 | exit0；23/23匹配；未将current goal dirty误报未知变化 |
| `python -m pyright --project workspace/tmp/pr197-f4-planfix-sol-20260930-02/pyright.json --verbose` 首次 | exit0，0诊断，但绝对include被pyright忽略并回退扫描本probe目录；Found 1 source file。配置警告如实记录，不能以该回退当精确include成功 |
| 同config改include为相对 `type_shape.py`、`exclude=[]` 后重跑 | exit0，**Found 1 source file / strict / 0 errors,warnings,informations**；只检查新view/index MappingProxyType/deepcopy/JsonValue、来源字段缩窄与查询顺序的真实类型形状。未检查生产新API或owner_probe，不将形状stub视为生产通过 |
| `PYTHONPATH=. python workspace/tmp/pr197-f4-planfix-sol-20260930-02/owner_probe.py`（先激活venv） | exit0；真实Fs仓储合成2source的list/get与同guard私有读取meta相等；duplicate拒绝；A缺ID/Z malformed时X先缺ID、Y抛保存的同一原read_error；坏tree commit被原COMPLETE门以ValueError拒绝并恢复。随后补充published_tree_sha256前后相等断言再运行一次，同为exit0；该新断言直接验证失败提交不改变published bytes。输出PASS；未执行真实下载/OCR |
| 错误检索恢复：查询不存在 `dayu/fins/pipelines/cn_download_runtime.py` | rg exit2，未证明runtime缺owner；随后真实文件inventory发现`ingestion_runtime.py`，逐段读取公开failure/direct projection恢复证据 |
| 错误检索恢复：使用不存在glob `cn_download_runtime*` | zsh glob exit1、未运行rg；改用已存在`download_contract.py`/`ingestion_runtime.py`/`tools`/真实runtime测试路径检索exit0；未以空结果推断行为 |
| plan `git diff --check` | exit0；无空白错误 |
| 新artifact `git diff --no-index --check /dev/null <artifact>` | exit1、无输出；1表示新文件内容差异，无空白诊断，不宣称exit0 |
| 末核manifest/branch/HEAD | exit0；22项只读输入全部不变，plan授权变更；HEAD60307；写end-input-check.json |

所有本轮Python/pyright probe运行前均 `source .venv/bin/activate`，pyright实际1.1.409；没有更新依赖。verbose的annotationlib解析提示与版本更新提示不是新增诊断，实际0 errors/warnings/informations。初次include警告已纠正，不用cat覆盖失败exit。owner_probe未纳入strict type_shape检查（它调用测试私有fixture/owner），明确不声称整目录pyright通过。

未运行pytest/full pyright/coverage/newAPI/newworkflow行为测试。用户明确无需重复全仓baseline，F3并发utils类型临时状态不属于F4plan。真实owner probe证明读取来源/顺序/commit闸门可行，不证明新API guard计数、并发barrier、全部损坏网格、事件/取消/持久投影验收。新计划§9逐项列正式实现必须完成的验证。

## README与残余风险分类

只改两计划文档，README保持只读。未来Fins手册写已实现仓储/下载观察边界，tests手册写实际owner测试；根用户手册及dayu架构总览无本slice职责变化，不机械同步。

| 风险/缺口 | Gateflow分类 | Owner / destination / 状态 |
| --- | --- | --- |
| 新API/新workflow/tests尚未实施与复审 | fixed in current slice（义务归属，未完成） | F4-S1实施/双路review/总控；不能以本文计产品已修 |
| F4-R01原跨writer另target新绑定集合唯一性 | requiring new issue or explicit user decision | storage/identity→总控后续候选；不顺带修、不新建issue |
| F4-R02每观察O(D)读取/index及原PhaseA/B/commit全tree成本 | assigned to later work unit | storage性能候选；本方案无整runlinear承诺 |
| 外部publication下start进度标签与stream实际ID分叉 | assigned to later work unit | 原事件观察边界；本slice保持并回归，不新增原子事件要求 |
| 原F3/F5/F6/F7及upload队列 | assigned to later work unit | 各已有WU/总控，不变更其产品行为或状态 |

**下一入口：总控收取本文登记项 → 冻结本版plan与current goal/source → MiMo/Kimi同版Planreview re-review → 总控裁决。** 无blocking新业务选项是本作者基于窄owner方案的判断，仍需复审；不宣告gatepass。本轮完成后停止，不派发、不实施、不提交。
