# S2 双审 findings 即时登记

## 身份与当前状态

同一统一修复 WU、同一 S2 code review。HEAD/base `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，唯一 workspace `/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`。冻结 diff SHA `282ae054d01718602e31a17a30984e2452f1ad96a46537bc5172d2a33b8e0ccc`。

ds-flash runner94324 已 actual outer0/result.success；MiMo runner30598 尚在途，不改其冻结输入、不提前进入 fix。此记录为即时登记，最终双审核收和所有 findings 总裁决尚未完成。ds-flash 原报告 `docs/reviews/code-review-20261003-025726.md` 保持原字节。

## US2-R02：多原件候选排序与 published identity 不一致

来源：ds-flash Finding01。**accepted / 未修复 / 中**，阻塞 S2 放行；属于既定 O33/V11–V12，不增加业务规则或 slice。

总控直接读取 `docling_upload_service.py:_describe_material_candidate`：D 的 originals tuple 保输入顺序；读取 `_fs_source_integrity.py:_project_material_upload_publication_identity`：storage 按 descriptor.name 排序；读取 `material_upload_publication.py:arbitrate_material_upload_publication`：精确 identity 比较 tuple 因而不同。另实际读取评审 `probe_candidate_order.py` 及 `probe-02-candidate-order.stdout.txt`：D 为 b/a、published 为 a/b，前者 CONFLICT、后者 IDENTICAL_SKIP。该定向探针用受控 converter、真实 D/市场/Fs owner，仅证同源排序错误；不冒称生产 Docling 或真实双 CLI 已覆盖多文件。

修复必须在 **MaterialUploadPublicationIdentity 公共值合同的规范顺序 owner / 其直接构造处**，统一按原件 name 规范化 tuple；D 与 storage 复用同一真源，不在 arbiter 用集合/忽略顺序/重读/宽比较补救。保身份、角色指纹、原件内容摘要、primary、amended、版本及请求事件输入顺序的既定合同；规范身份的 tuple 顺序不等于重排 CLI 事件。不为此新增解析器、业务字段或大范围模块拆分。

验证：真实 owner 多文件 b/a 旧受理竞争，显式 primary 为非首项（例如 a）；实际 D 候选与 published 身份匹配，一 ok 一 skipped，winner→loser 业务字节/revision/time 零差异。必要真实双 CLI 用同一多文件/非首项 primary，保原单文件证据和全部失败票据。受影响测试、全量 pyright、触及产品逐文件覆盖率及同版双复审按当前 gate 一起完成。

## US2-R03：重复财期集合及已有运行时常量未复用

来源：ds-flash Finding02，**accepted（最窄现有 owner 复用部分）/ 未修复 / 低**。总控直接读到 D `_describe_material_candidate` 手写 FY/H1/Q1–Q4，而 storage 使用既有 FISCAL_PERIODS；R 同一模块已存在状态常量而新校验又重复字面量；publication 已直接依赖 R，却重复现有 auto token。按项目唯一真源/禁止魔法字符串约束，随同本次 R02 集中修复复用既有 domain 集合、当前 owner 常量；新增 metadata_updated 的必要具名常量按原状态 owner 管理。

评审提及未来扩展风险不构成新产品 goal；不要求全仓字面量整理、新 shared status 模块、D→R 反向依赖、兼容 re-export、跨层 getter 或 wire/schema 变化。schema/type Literal 允许值声明保留其自足性。只在当前 S2 触及的产生/校验处作最窄真源复用，行为及 filing 合同不变；不为低项增加独立 slice/gate/宽测试批次。

## 下一入口

等待 MiMo actual 终态并核完整双路结构化轨迹/证据，再合并全部成立 findings，gpt-6-sol 一次集中 fix → 同版 MiMo/ds-flash re-review → root 裁决 → accepted S2 commit。所有 slices/aggregate 后正式 PR197 review；修复 WU closeout 后独立完整 upload_material CLI CI 与 oracle/scenario 登记。
