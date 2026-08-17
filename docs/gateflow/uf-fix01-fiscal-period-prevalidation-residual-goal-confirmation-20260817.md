# UF-FIX01 fiscal-period prevalidation residual — Goal Confirmation

## Gate 元数据

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- gate：`goal confirmation`
- 日期：2026-08-17
- design sources：`docs/host/design.md`、`docs/engine/design.md`
- direct evidence：`/Users/leo/workspace/.dayu-cli-ci/upload-filing-postfix-all-20260817-p26wBp/observed-behavior.md`、`cases/UF-A21-us-invalid-period`
- current gate：`plan`
- next entry point：`plan`
- completion status：`confirmed-by-user`
- artifact path：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-goal-confirmation-20260817.md`

## Preflight

- 当前分支：`codex/upload-filing-oracle`，不是 protected trunk。
- 工作树：preflight 时 clean。
- merge / rebase / cherry-pick：均未进行。
- remote refresh：已执行 `git fetch github main`；项目远端名为 `github`，不存在 `origin/main`。
- main fast-forward：`main == github/main == 256786b2`，双向 ancestor 检查均通过；当前分支包含
  `main`，`git rev-list --left-right --count main...HEAD` 为 `0 83`。
- tmux discovery：AgentMiMo=`ai-0:1.1`、AgentCodex=`ai-0:1.4`、AgentDS=`ai-0:1.5`；三者已按
  `$init-agents` 分别 `/clear` 并回到 idle。后续每个新 gate / slice 仍须重新 discovery、clear、wait-idle。

## 第一性原理判断

问题成立，且严重性判断准确。`fiscal_period` 是调用方在 operation、converter 与业务 workspace mutation
之前就能确定的封闭业务值；非法值进入 operation 后才成为 generic runtime failure，会同时破坏退出码、可行动原因、
operation lifecycle 与零副作用边界。该事实不依赖日志迹象：冻结 case 的 exact argv、stdout/stderr 与 production
调用链共同证明 US 非法值绕过了静态 admission。

正确修复不应位于 US adapter、CLI renderer 或异常捕获。财期闭集与 canonicalization 的业务 owner 已存在于
`dayu.fins.domain.filing_semantics.normalize_fiscal_period`；upload 静态 admission 是它的直接上游 usage projection
boundary，负责在 workspace state read 前把 domain `ValueError` 投影为 closed `FinsUploadUsageError`。

## 直接代码与数据证据

1. `cases/UF-A21-us-invalid-period/result.json` 记录 US `DELTA`、`--fiscal-period BANANA` 返回 exit `1`；
   stdout 已出现 `upload.preparing`、`upload.started`、`upload.completed_with_failures`，stderr 为
   `failure_kind=runtime failure_code=unexpected_runtime`，不是 usage error。
2. 同一 evidence 报告记录 CN/HK 非法 `9M` 当前已 exit `2` 且零 mutation，证明差异来自 market 分支，
   不是 CLI 参数解析或统一 error projection。
3. `dayu/fins/domain/filing_semantics.py` 已声明唯一 `FiscalPeriod`、`FISCAL_PERIODS` 与
   `normalize_fiscal_period(...)`：统一执行 `strip().upper()`，只接受 `FY/H1/Q1/Q2/Q3/Q4`。
4. `dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static` 是任何 workspace read/mutation 前的
   request admission；但当前实现只在 CN/HK 调用 pipeline 层 `normalize_cn_fiscal_period`，US 分支直接使用
   `request.fiscal_period.strip().upper()`，因此 `BANANA` 被写入 `normalized_fiscal_period` 并参与 SEC identity。
5. `dayu/fins/pipelines/docling_upload_service.py::normalize_cn_fiscal_period` 自行维护同一字面量闭集，构成
   domain owner 之外的第二真源；ingestion runtime 反向依赖该 pipeline helper 也扩大了 adapter 语义所有权。
6. CLI `dayu/cli/commands/fins.py::_prevalidate_upload_filing_request` 与 tool
   `dayu/fins/tools/upload_tools.py::_upload_request_from_arguments` 都构造同一个 `FinsUploadFilingRequest`；
   `_filing_upload_request_identity -> _validate_fins_upload_filing_static` 在 workspace repository 创建/read 与
   direct Service factory / observation / operation 之前运行。因此修正这一共享 admission 可覆盖 CLI 与 tool，
   也覆盖 US/CN/HK，而无需入口特例。
7. SEC 与 CN/HK workflow 都只接收 `ValidatedFinsUploadFilingRequest` 并消费
   `normalized_fiscal_period`；它们不应重新解析 raw fiscal period。
8. `docs/host/design.md` 与 `docs/engine/design.md` 明确 Host/Engine 不拥有财报业务语义；本 work unit 不应
   修改 Host、Engine 或把 Fins usage validation 提升为通用 runtime 机制。

## 目标与成功信号

- `FiscalPeriod`、`FISCAL_PERIODS`、strip/uppercase 与闭集判断继续只有
  `dayu.fins.domain.filing_semantics` 一个业务真源。
- filing upload 静态 admission 对 US、CN、HK 及 CLI/tool raw request 统一消费该 owner；不再按市场解析。
- 合法 `FY/H1/Q1/Q2/Q3/Q4` 原样 canonical；合法小写与首尾空白统一 canonical 化。
- 其它值产生新的通用 closed usage code 与精确、可行动、market-neutral reason，exit `2`。
- 非法值不读取/创建业务 workspace state，不构造 Service，不启动 operation/observation/job，不调用 converter，
  不产生业务 workspace mutation，普通 stdout/stderr 不含 traceback。
- 合法 fiscal period、现有 action/publication 行为、其它 usage/prevalidation/runtime failure projection 保持不变。
- owner contract、Fins admission、CLI exit/reason/zero-mutation、tool/shared entry、US/CN/HK 一致性测试闭合；
  受影响测试、单文件 coverage 目标与全仓 pyright 通过。

## Scope boundary

允许修改：Fins fiscal-period domain owner 的 contract tests；filing upload shared static admission 与其 closed usage
code/message；删除 pipeline 内重复 CN fiscal-period parser 并让仍需财期分类的 consumer 直接消费 domain owner；
CLI/tool/shared-market contract tests；职责范围内 README；Gateflow / review artifacts。

只有 `upload_filing` / `start_fins_upload` filing request 属于本 work unit。`upload_material` 的可选 metadata、
download filter aliases、`upload_filings_from` 扫描推断，以及持久化旧非法数据读取不在范围内。

## 非目标与不过度设计说明

- 不在 US、CN 或 HK adapter/workflow 添加分支、fallback、loose parsing 或异常捕获特例。
- 不修改 Host、Engine、Service public protocol、storage schema、publication state machine、action/overwrite/repair 语义。
- 不引入新的 parser class、registry、profile、callback、兼容 wrapper 或旧 enum alias。
- 不执行 UF-PF01/UF-PF12 真实 CLI calibration，不修改冻结 evidence，不刷新 accepted oracle 或 scenario registry。
- 不 push、不创建 PR；按用户授权只在当前分支创建 Gateflow 本地提交。

最小正确方案是让现有 shared static admission 直接消费现有 domain owner，并删除当前重复 market parser；
不需要新的架构层或状态机。

## Blocking open questions

无。精确 owner、修复边界、通用 closed usage code、测试面与排除项均可由用户需求和直接代码证据确定。

## Docs decision

implementation 后按触发规则检查 `dayu/fins/README.md`、`tests/README.md` 与根 `README.md` 的目标读者和
现有约束；Host/Engine 代码与 contract 不变，预期不更新其 README。

## Residual risks / uncovered areas

- 当前尚未运行修改后测试、coverage 与 pyright；分类为 `covered by later approved slice`。
- `upload_material` 仍允许自身可选 fiscal metadata normalization；分类为 `assigned to later work unit`，本 work unit
  不声称改变 material contract。
- `upload_filings_from` 的扫描/脚本 metadata 规则不属于 direct filing admission；分类为
  `assigned to later work unit`。
- UF-PF01/UF-PF12 calibration、冻结 evidence 与 registry 刷新由用户明确排除；分类为
  `assigned to later work unit`。

## User decision

用户已于 2026-08-17 确认以上目标、owner、范围、非目标与成功信号；Gateflow 进入 `plan`。
