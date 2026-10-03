# S2 双路 code review：总控最终裁决及集中修复合同

## 身份、证据与状态

统一修复 WU 的 S2；workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，HEAD/base `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4` 未改。不是 PR review。accepted plan SHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea`，原冻结 diff SHA `282ae054d01718602e31a17a30984e2452f1ad96a46537bc5172d2a33b8e0ccc`；886 输入、60 候选末核零漂移。

MiMo runner30598 与 ds-flash runner94324 均托管外层 exit0、结构化 result.success、独占 canary 实际读取且匹配；完整逐调用轨迹及错误保存在 `workspace/tmp/upload-material-unified-repair-20261002/formal-s2-code-review-01/root-audit/`。持久核收索引为 `evidence/upload-material-unified-repair-20261002/s2-dual-review-root-receipt.json`。原审查报告 `docs/reviews/code-review-20261003-025726.md`（DS）和 `docs/reviews/code-review-20261003-033327.md`（MiMo）保留原字节。

实际 metadata：Claude / ds-flash / deepseek-flash[1m]；Claude / mimo / mimo-v2.6-pro（modelUsage mimo-v2.6-pro[1m]）。DS 报告表头字段错位，以 stream 为准。两个 stderr 精确 unrecognized_model 前缀仅 warning。DS 七次未引号 shell 分隔符错误及一次探针 async 调用错误已后续源读取/同步探针恢复，报告“其余命令均0”与轨迹不符，该声明 rejected-with-reason；不是七项产品 finding。MiMo 两次 Bash 失败是同时轮不存在可选 business-diff 文件与 coverage dict 排序 TypeError；真实 result 明记 business_diff=null，随后正确 coverage 字段读回。完整轨迹保存并核对，不把未跑证据写通过。

**三个 accepted findings 均未修复，S2 不放行、不提交。下一 gate：fix S2。** gpt-6-sol 一轮完成全部成立项；同版 MiMo/ds-flash 双 re-review 后才可 accepted slice commit。不得新增 slice、提前正式 PR review 或完整 campaign。

## US2-R02：原件身份顺序

DS Finding01 = MiMo F1，合并计数；accepted / 未修复 / 中。根因与最窄修复依据先前 `upload-material-unified-s2-review-findings-root-register-20261003.md`；初始登记的 MiMo 在途状态是历史事实，不回写抹除。

唯一规范 owner 为 `MaterialUploadPublicationIdentity.__post_init__`：先沿现合同验证原件 descriptor 集及唯一 name，再按 name 建立 canonical tuple。不改传入请求/处理事件顺序。D/storage 构造该类型自动共用一处真源；移除 storage 该 identity 投影的重复排序。保 exact arbiter 相等，不集合比较、过滤字段、重读、宽容解析。输入 b/a、primary=a（非首项），保 role/fingerprint/content/amended/company/version 精确合同。

验收：owner 级真实 D 候选→Fs publication→loser verified skip，以及独占新目录的真实多文件双 CLI、生产 Docling/Fs、双方旧 MISSING 受理/实际 consumer binding/双 wait/restore/source hashes。顺序放行 winner→loser 全业务 bytes/revision/time diff={}，同时放行只声称正常双终态，不编造未测得 diff。不同 primary/内容/角色/amended/company、I/O 仍遵循原拒绝合同。

## US2-R03：既有值域/常量真源复用

DS Finding02 + MiMo F3，accepted 最窄部分 / 未修复 / 低。D 复用既有 `FISCAL_PERIODS`，删除同模块重复 FiscalPeriod import；R 当前 S2 校验复用本模块既有 status 常量，metadata_updated 必要命名常量放同 owner；publication 复用已依赖 R 的 auto 常量。schema/类型 Literal 的自足允许值和公开值测试断言保留，不全仓 token 整理、不新 shared status 模块、不兼容 re-export、不 D→R 反向依赖、不改 wire。

## US2-R04：已有公司阶段的材料双读窗口

MiMo F2，accepted / 未修复 / 低；属于既定 O33 的受控 auto 竞争承诺，不是新增业务目标。总控直接核 `execute_material_upload_company_stage` 的独立 read→validate 两个 guard，以及 `_fs_material_upload_state_core.validate_material_upload_state` 的重读与严格状态比较、protocol/public Fs 透传链：已有公司、相同旧 MISSING 受理时，winner 在 loser 第一次读之后提交 COMPLETE；公司未变，但 validate 的第二次读与第一次材料 state 不等，提前 source conflict，没进入 writer arbiter。此为同路径确定代码反例，**尚未声称实际 Fs 窗口复现**；修复必须保留修前真实 owner 定向反例与修后恢复票据。

语义 owner：storage 的 guarded 校验负责公司快照/alias；材料 source 竞争归 writer view、纯 arbiter、登记及最终 publication guard。生成可用的最窄合同如下：

1. protocol/core/public Fs 的 `validate_material_upload_state` 中 `expected_source_state: MaterialUploadPublishedState | None` **仍必填、无默认值**。显式 None 只表示该次只要求公司/alias 条件，不表示 source MISSING、不允许 fallback、不省略仓储、不改变返回的完整 typed current state。
2. 沿现 recovery→identity→publication 锁顺序与真实 alias owner。每次都严格比较 `fresh.company_meta` 与显式 `expected_company_meta`；expected_source_state 非 None 时再沿原严格 source 比较。不得吞异常/重试。现 `_require_material_state_matches`、registration、batch commit/final guard 保持严格非空完整 source 类型。
3. 公司阶段删除独立 fresh 材料读。只有 requested auto 且非 overwrite 的公司阶段显式传 None；其它动作仍 observed source。existing-company keep/stage 严格观察公司快照；initial None 的等价无增量公司 commit 例外仍按 C01/R01，不能放宽。
4. D 的 skip/redelete 复验、writer registration/commit/final guard 继续传具体完整 state，不能以 None 跳过材料条件。
5. 中文完整 docstrings 与 Fins README 写明 explicit 公司阶段条件的含义。不要新 getter、第二锁、通用 retry、更改公开 upload schema/状态。

必要验证：真实 Fs 的确定性 interleave（A 独立 guard 返回后 B 完整发布，无 A 持 writer 等 B 的死锁），展示修前误冲突、修后 A 到 writer arbiter verified skip；已有公司 snapshot/名字/更新时间/alias 漂移仍拒；非 auto/overwrite source 仍严格；registration/最终 guard 不可 None 绕过；真实 I/O/release、坏 winner 不能 skip。补真实双 CLI 已有公司变体（新独占 base，真实种子公司/材料），保初始缺席路径与全部旧票据，不把 mock converter 的 owner 探针当生产 Docling 证明。

## Open question 裁决

MiMo create-on-tombstone 最小测试：不是待裁业务。按 plan §6.4 只补一条最小 owner 回归锁既有非 overwrite create 拒绝（无自动 restore、不新 typed code、不升 oracle）；列入同轮集中 fix，不为它新 gate。当前 storage_io 迟拒文案是已批准保旧 storage owner 边界，不另修用户语义。

DS 关于最终单文件测试 delta 未重宽 suite：rejected-with-reason 为新门禁请求。前后产品哈希不变，final-owner-12 覆盖四个实际修改 paramcases、full pyright03 通过；宽 suite2643pass/3skip 的产品证据仍有效。本轮真实产品 fix 后按其影响集中做必要回归，不为报告机械重复。

## Residual risks 分类与去向

- R02 多文件与 R04 已有公司竞争：fixed in current slice（待 fix/re-review，不冒已修）；owner storage value/guard + publication，destination 同 S2。
- 深冻结 JSON 不能直接 dumps：既有合同约束非 defect；storage JSON owner/README 已说明，未来调用必须消费公开投影，无本轮新实现项。
- tombstone create 迟拒：既定 scope，最小测试锁现行为；不新产品目标。
- Windows 两项及 optional PDF skip：assigned to later work unit，平台 CI/可选 PDF 集成 owner；不得声称通过。跨平台 XBRL 按用户 goal amendment 另期。
- S3/XBRL/UP-RR-T01：covered by later approved slice S3；不是提前实现。
- 完整 upload_material CLI CI/registry：assigned to later stage（用户指定修复 WU 后），controller owner。
- Raw EOF 无损包装：covered by aggregate/PR 收口，保字节/SHA、引用同步，不 trim。
- 私有 prepared union 消费、最窄白盒 final-guard 故障测试：已批准结构/验证方式，不当独立未来硬化目标；owner pipelines/tests。

## 验收与推进

保留当前 S2 全部工作与 Raw；只修本文件成立项。每改代码更新真实 owner 测试，source .venv 后受影响 tests、full pyright、每实际触及产品 ≥80%，README 只按职责更新。普通 caller/严格 typed fixture 的最窄白名单迁移自主完整，禁止微 gate。gpt 完成→root 全轨迹/退出/源证据核收→同版双复审→root 裁决→S2 accepted commit→S3。所有 slices/aggregate 后才正式 PR197 review；修复 WU final closeout 后再完整 CLI CI/登记。用户手工 merge，main 不动。
