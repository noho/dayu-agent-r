# CLI CI 第一轮 Oracle Readiness S1 Implementation

## Artifact Metadata

- Gate：`implementation`
- Work unit：CLI CI 第一轮 Oracle readiness handbook contract
- Slice：S1
- Scope：`docs/cli_ci.md`
- Status：implementation complete，code review passed

## Changed Contract

1. 第一轮被定义为完整 calibration campaign；允许多个补证 run，但不能以局部覆盖结束。
2. Scenario/oracle registry `ready` 必须由 machine-verifiable readiness proof 派生。
3. Parser inventory 与 dynamic interactive branch inventory 分离 ownership；新发现 branch 使 readiness 保持或回到
   calibration。
4. Mandatory matrix 覆盖 precondition、每个 option/interactive branch、input class、pairwise/high-risk
   combination、cross-command consumption 和 required evidence。
5. `dayu-cli init` 明确覆盖空/已有/部分/冲突 workspace、每个合法和错误选项、取消/EOF、重复执行、关键文件内容、
   secret 状态、SQLite 及后续真实加载。
6. Applicable 通用 CLI/UI 必须真实观察 Codex reference；对齐交互语义，不要求精确文案或逐像素样式。
7. Observed report 必须内嵌关键 screen/transcript、生成物内容/diff、SQLite delta 和跨命令消费结果；exit code、
   CLI summary、digest 或 raw ref 不能替代。
8. 相关 CI-owned SQLite 对 stateful mandatory scenario 是 required bounded read-only observation，但不成为
   Host/Fins/EventLog public truth 或唯一 oracle。
9. Observation completeness、registry readiness 和 product verdict 被明确为正交维度；产品 failure 不短路剩余
   observation，也不阻止用户定义 accepted oracle。

## Decisions

- 不修改当前空的 calibration registry JSON；handbook 允许空 calibration placeholder 暂无 readiness proof，任何
  `ready` registry 必须包含并通过 proof。
- 不执行参数笛卡尔积；每个单维 obligation 独立覆盖，并采用 pairwise + 高风险组合。
- Validation worktree 不直接修改稳定 registry；用户裁决后通过正式 work unit 写入，且第一轮 campaign 在写入和
  readiness validation 完成前不能结束。

## Validation

- `git diff --check`：通过。
- 旧语义残留扫描：
  - 未发现 minimal-positive 作为 coverage completion owner；
  - 未发现 Codex applicable UI 为可选；
  - 未发现 public evidence 完整时禁止 SQLite observation；
  - 未发现只凭 `registry_status` 认定 ready。

## README Decision

只修改内部 CLI CI handbook，没有改变实际用户 CLI 命令、参数、输出、安装流程或分层装配；不更新 README。

## Residual Risks

- R1：文档较长且交叉引用多，需要 deep review 检查同义状态和 readiness 条件是否仍有冲突。
- R2：实际 calibration harness 尚未实现 readiness validator；本 work unit 只拥有 handbook contract，不把未来实现
  伪装为已完成。
- R3：实际 Codex observation 受本机版本和登录环境影响；执行期必须冻结 identity，当前 handbook 不预设结果。

## Completion Signal

S1 允许范围内的 handbook 修改已完成；CR-01 至 CR-05 已修复并通过 re-review，可创建 accepted slice commit。
