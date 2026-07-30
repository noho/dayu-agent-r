# CLI CI 第一轮 Oracle Readiness Handbook 修改计划

## Gate 与 Work Unit

- Gate：`plan`
- Work unit：收紧 `docs/cli_ci.md` 的第一轮 oracle 建立、全量覆盖、Codex UI 对齐和 registry readiness 契约
- 计划状态：待 plan review
- 允许修改范围：
  - `docs/cli_ci.md`
  - 本计划与对应 review / closeout artifacts
- 不修改范围：
  - Dayu 生产代码与测试代码
  - `docs/cli_ci_scenarios.json` 与 `docs/cli_ci_oracles.json` 的实际场景/oracle 内容；本 work unit 只在 handbook
    中定义后续写入这些 registry 时必须满足的字段与校验契约
  - CLI 实际行为

## 目标、动机与成功信号

### 目标

把第一轮 CLI CI 明确定义为一次完整的 oracle calibration campaign：

1. 从真实 parser inventory 派生完整 mandatory 场景矩阵；
2. 在不同前置状态下真实运行所有 CLI command leaf，并覆盖合法选项、交互分支、错误输入、边界输入和高风险组合；
3. 记录终端、生成物、日志、Host/EventLog/Tool Trace、memory、runner input、Fins 和相关 SQLite 前后状态；
4. 先冻结人类可读的 observed-behavior report，再由 Agent 提供裁决建议，最终由用户确认正确行为；
5. 把用户确认的语义不变量写成 accepted oracle，把完整场景写入 scenario registry；
6. 只有两个 registry 都满足强 readiness gate 时，第一轮才结束。

### 动机

当前实现只能说明“现在发生了什么”，不能自行定义“应该发生什么”。如果第一轮只跑每个命令的一条
minimal-positive，或者只根据 exit code、CLI summary 和日志判断，就无法覆盖 workspace 状态、交互选项、错误输入、
生成物和跨命令传播，也无法形成完整、可重复的产品正确性定义。

### 成功信号

- Handbook 明确区分：
  - observation completeness；
  - oracle/scenario registry readiness；
  - 当前产品 pass/fail。
- 第一轮存在任何 mandatory coverage/evidence/adjudication gap 时，禁止结束 calibration 或把 registry 标记为
  `ready`。
- 产品实际行为即使违反已确认期望，也可以在完整观察和用户裁决后形成 accepted oracle 与 implementation finding；
  failure 不会短路其余场景。
- 通用 CLI/UI 的 Codex 对齐由“可选参考”改为用户已指定的 mandatory reference policy，但只约束交互语义，不要求
  精确文案或逐像素复制。
- 报告直接展示足够的人类可读证据，不能只提供 digest、raw ref、exit code 或 CLI 自报 summary。
- 后续每次完整 CI 都执行完整 mandatory 矩阵；focused rerun 只能形成局部结论。

## 第一性原理判断与直接证据

### Work unit 成立

- `docs/cli_ci_scenarios.json` 与 `docs/cli_ci_oracles.json` 当前均为 `registry_status=calibration` 且记录为空。
- 当前 handbook 第 5.1 节虽然定义参数 pairwise 覆盖，但 calibration 主流程仍以
  `help/minimal-positive/negative` 为主要 leaf 粒度，没有把前置状态、每个交互选项、重复执行和跨命令消费组成
  mandatory readiness 矩阵。
- 当前第 7.1 节把 Codex / Claude Code 定义为“可选参考”，与用户已经明确的“适用的通用 CLI/UI 行为应对齐
  Codex”冲突。
- 当前第 11.2 节只允许在 public observability gap 或 contradiction 时查询 SQLite，不能满足状态型命令必须记录
  相关 SQLite before/after 的完整人工验收模型。
- 当前 observed-behavior schema 允许 bounded summary + raw ref，但没有充分禁止把关键 screen、生成配置内容、
  SQLite delta 或跨命令加载结果隐藏在 raw artifact 后面。

### 语义 Owner

| 语义 | 唯一 owner | Handbook 中的投影 |
|---|---|---|
| 命令与参数 inventory | `dayu.cli.arg_parsing.build_parser()` 与真实 CLI help | 场景矩阵的静态输入 |
| 动态交互 branch inventory | 命令拥有的交互声明、当前提示和真实运行发现 | 版本化 branch obligations；新发现 branch 使 readiness 回到 calibration |
| Mandatory coverage matrix | 版本化 scenario registry | 每个场景的覆盖维度、前置状态、输入和 evidence requirement |
| 进程事实 | 真实 CLI process / PTY | argv、stdin、screen、stdout/stderr、exit/signal |
| 文件与生成物事实 | CI-owned filesystem before/after | manifest、关键内容和 diff |
| Host/Tool/Memory/Runner 事实 | 各自 public contract / canonical artifact | 跨层关联和人类可读投影 |
| Fins 文档状态 | `dayu.fins.storage` 仓储 contract | public read 结果和证据 |
| SQLite 内部状态 | 只读 bounded database observation | internal diagnostic observation，不替代 public owner |
| Observed report | 当前 run 的 immutable human-readable projection | 汇总并链接上述 owner，不成为新业务真源 |
| Codex reference | 冻结的实际 Codex 版本/环境/终端 observation | 适用通用 UI predicate 的参考依据 |
| 产品正确性与允许变体 | 用户裁决后的 accepted oracle | 版本化 oracle registry |
| 当前实现是否满足正确性 | full-real CI verdict | accepted oracle 与真实 observation 的比较 |

## Contract 与状态机修改

### 第一轮完成条件

第一轮可以包含多次执行和补证，但只有以下条件全部满足才可结束：

1. parser inventory 已冻结且没有未分类 leaf/parameter/interactive option；
2. mandatory scenario matrix 覆盖全部要求的状态、选项、错误类别、边界和高风险组合；
3. 每个 mandatory scenario 都真实执行并有 sufficient evidence；
4. observed-behavior report 已冻结；
5. Agent suggestions 与用户裁决均引用该 frozen report；
6. 每个 mandatory scenario 的每个 correctness surface 都映射到至少一个适用的 accepted oracle，或明确适用的
   objective/hard contract；
7. rejected candidate 留下的 correctness gap 已由 replacement predicate 或明确的 out-of-scope 用户裁决关闭，
   不能仅因不存在 `unadjudicated` 就认为正确性已定义；
8. accepted scenarios 与 accepted oracles 已写入对应 registry，引用完整且 schema/readiness proof 校验通过；
9. 两个 registry 的 `registry_status` 都由上述校验结果派生为 `ready`，而不是手工翻转。

产品存在 failure 不阻止 readiness；coverage/evidence/adjudication gap 阻止 readiness。

### Mandatory 场景矩阵

每个 command leaf 至少从以下维度派生场景：

- 前置状态：空、已存在、部分完成、重复执行、与当前命令相关的冲突/损坏状态；
- 参数与交互：默认值、每个合法值/分支、显式选项、互斥/依赖关系；
- 输入类别：合法、空值、非法、边界、重复、EOF、取消、中断；
- 组合：pairwise + 人工识别的高风险组合，不执行无收益的全笛卡尔积；
- 跨命令：生成配置或状态必须被真实后续命令加载、查询或消费；
- 执行层级：真实 CLI/Host/provider/tool/Fins/external dependency，禁止 mock/fake 替代。

第一轮与后续 full-real 都必须执行完整 mandatory 矩阵。Focused rerun 只用于复现或修复验证，不能更新全量 coverage、
registry readiness 或 full-real verdict。

Parser inventory 只拥有 command/parameter IDs。动态 interactive branch inventory 必须独立冻结：来源包括命令拥有的
交互声明、当前 help/提示和真实运行发现。任一新发现 branch 都必须获得 stable branch ID、扩展 mandatory
obligations，并使当前 readiness 保持或回到 `calibration`，直到对应状态、输入、证据和用户裁决闭环。

Scenario registry 中每条 coverage claim 必须使用稳定 ID 表达 command/parameter、precondition state、
interactive branch/option、input class、combination policy/high-risk combination、cross-command assertion 和 required
evidence。Registry-level readiness proof 必须记录 inventory/version/digest、mandatory obligation 总数、covered 数、
gap 数、用户裁决 identity 和引用的 frozen report digests。`registry_status=ready` 只是该 proof 校验通过后的投影。

Oracle registry 必须能从每个 mandatory scenario/correctness surface 追溯到 accepted predicate 或
objective/hard-contract authority。Dangling scenario、dangling oracle ref、uncovered correctness surface、
`unadjudicated` candidate 或 unresolved rejected gap 都使 readiness 校验失败。

### Codex UI 对齐

- 适用的通用 CLI/UI 行为必须采集真实 Codex reference，不再是可选项。
- 对齐对象是交互语义：prompt/input、running/thinking/activity、流式显示、终端清理、final screen、错误反馈、
  Ctrl+C/Esc/EOF、取消后继续、多轮与恢复。
- 不要求品牌、财报领域文案、动态内容、耗时、随机标识或逐像素样式一致。
- Dayu-specific Fins、Host、Tool Trace、Memory 与财报分析语义不强套 Codex。
- Codex 版本变化只产生新 reference candidate，不自动重写既有 accepted oracle。

### SQLite 与报告证据

- 对可能读取或写入 durable state 的 mandatory scenario，相关 CI-owned SQLite before/after 是 required observation；
  与场景无关或数据库不存在时才可 `not-queried`，并记录理由。
- SQLite 仍是内部只读观察，不能替代 Host public read、EventLog、Fins storage 或 accepted oracle。
- 报告必须直接展示能够支持用户裁决的 bounded evidence：
  - 交互步骤和关键 screen/transcript；
  - 用户选择与响应；
  - 关键生成文件的脱敏内容和 diff；
  - SQLite schema/关键 rows 或聚合的 before/after；
  - 日志、EventLog、Tool Trace、memory 和 runner input 的关键人类可读内容；
  - 跨命令实际加载/查询结果。
- Digest 和 raw ref 只用于完整性与深入复核，不能替代报告中的关键事实。

## Implementation Slice

### S1：一次性收紧完整 handbook 语义闭环

- 允许文件：`docs/cli_ci.md`
- 修改：
  - 入口/profile/goal-discovery/registry lifecycle；
  - 第一轮结束条件与 machine-verifiable readiness proof；
  - parser inventory 与 dynamic interactive inventory 的独立 ownership；
  - mandatory 场景矩阵与 full-real/focused-real 边界；
  - observation completeness、readiness 与 product verdict 的正交关系；
  - 通用 CLI/UI mandatory Codex reference 与语义等价边界；
  - observed report 的 inline human-readable evidence；
  - stateful scenario 的 bounded SQLite before/after；
  - 禁止 CLI summary/exit code/raw ref 替代真实状态检查。
- 非目标：
  - 写入实际 scenario/oracle records；
  - 规定 Codex 的 exact 文案、颜色或像素布局。
- 完成信号：
  - 全文不再允许局部 calibration 被描述为第一轮完成或 registry ready；
  - 用户无需运行命令，也能从报告主体完成逐项裁决；
  - 单次文档 checkpoint 内 coverage、evidence、Codex、SQLite 和 readiness 语义一致。

## Tests 与验证

- `git diff --check`
- 校验 Markdown 关键 contract 一致性：
  - `registry ready` 只在完整 coverage/evidence/adjudication 后出现；
  - Codex mandatory / optional 语义无冲突；
  - SQLite required observation 与 private diagnostic owner 无冲突；
  - focused rerun 不升级全量状态；
  - report 不允许只给 exit code、summary、digest 或 raw ref。
- 使用 Python 3.11 环境解析两个 registry JSON，确认 handbook 修改没有破坏现有 JSON。
- `source .venv/bin/activate` 后运行 `pyright`，确认无新增或扩散类型错误。
- 文档-only 变更没有直接受影响的 pytest 测试；若 review 发现可执行校验 owner，则补充最小验证。

## README Decision

本 work unit 只修改内部 CLI CI handbook，不改变用户可见 Dayu 安装、CLI 参数、实际输出、运行入口或分层装配，因此不触发
根 README、`dayu/README.md` 或其它包 README 更新。

## 不做的过度设计

- 不建立第二套 parser inventory。
- 不枚举所有参数笛卡尔积。
- 不把 SQLite private schema 升级为公共 contract。
- 不把 observed report 升级为 durable business truth。
- 不在 handbook 修改阶段预填未真实执行、未由用户裁决的 scenario/oracle JSON。
- 不把 Codex 精确文案或像素样式固化为 Dayu oracle。

## 风险与未决问题

- 当前无 blocking open question。
- 后续实际 calibration campaign 仍可能因真实 provider、credential、外部写入授权、成本或时间受阻；这些属于执行期
  coverage gap，不能由 handbook 预先豁免。

## 交付说明格式

最终说明必须列出：

- 修改了哪些 handbook contract；
- 运行了哪些验证及结果；
- review finding 状态；
- 未覆盖项与后续 owner。
