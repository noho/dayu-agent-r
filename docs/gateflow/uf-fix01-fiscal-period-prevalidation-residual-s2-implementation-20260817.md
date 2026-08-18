# UF-FIX01 财期预校验残余 S2 Implementation

## Gate

- Work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- Slice：`S2-entry-contracts-docs`
- Gate：implementation
- 基线：S1 accepted commit `f6b2d04c`
- 状态：implementation complete，等待 code review
- Artifact：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-s2-implementation-20260817.md`

## Scope 与语义 owner 决策

- fiscal period 的闭集校验与 canonical 值继续由 domain fiscal-period owner 产生；CLI 与 tool 不复制市场分支或业务校验。
- CLI 只验证 owner 产出的 validated Service handoff 与既有 usage failure 投影。
- tool adapter 只保留既有通用文本 trim；大小写规范化与 `FY/H1/Q1/Q2/Q3/Q4` 闭集判定仍由 runtime 复用的 filing validator 完成。
- tool schema 只承担 LLM-facing 自足说明，未新增 adapter 校验、兼容 alias 或 runtime enum 反向拼装。
- `tests/fins/test_fins_service_runtime.py` 无需修改：现有 tool/runtime observation seam 已足以证明 canonical handoff 与 start-before-validation 不变量。

## Changed files

- `dayu/fins/tools/upload_tools.py`
  - `fiscal_period` schema description 自足列出 `FY、H1、Q1、Q2、Q3、Q4`，保持 filing 必填、material 可选语义。
- `tests/cli/test_fins_commands.py`
  - 增加 US `AAPL/BANANA`、CN `600519/9M`、HK `0700.HK/BANANA` 非法财期入口矩阵。
  - 断言 exit `2`、精确单行 reason、stdout 空、无 traceback、Service factory/upload stream 零调用，以及 fresh/seeded workspace 快照不变。
  - 增加 US/CN/HK 小写与首尾空白输入到 canonical validated Service request 的契约。
- `tests/fins/test_fins_ingestion_tools.py`
  - 增加三市场 raw tool 非法财期的具体 `invalid_argument` usage envelope。
  - 通过现有 forbidden state/executor、observation registry、job store、无 runner seam 与 workspace snapshot，证明 storage/executor/observation/job/runner 及其后 converter 均不可达且零副作用。
  - 增加三市场 raw lower/whitespace period 经 runtime validator 绑定为 canonical observation producer request 的契约。
  - 增加 tool schema description 精确断言。
- `README.md`
  - 在最终用户 direct filing 上传说明中记录六值闭集、trim/uppercase、三市场同规则，以及 CLI 非法值 exit `2`、启动与 workspace mutation 前拒绝。
- `dayu/fins/README.md`
  - 在 filing typed validator/static admission owner 段记录财期同源、market-neutral 与 downstream-before-start 契约。
- `tests/README.md`
  - 在 UF-FIX01 owner coverage 段记录 CLI/tool 三市场入口、canonical、failure envelope、zero-side-effect 与 schema 覆盖职责。
- 本 implementation artifact。

## Validation

- S2 affected tests：`269 passed`。
- S1 + S2 affected regression：`822 passed`。
- 精确 production coverage：
  - `dayu/fins/ingestion_runtime.py`：`91%`
  - `dayu/fins/pipelines/docling_upload_service.py`：`89%`
  - `dayu/fins/tools/upload_tools.py`：`93%`
  - 三文件合计：`91%`，满足 `>=80%`。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 测试仅使用进程内 CLI 调用与 deterministic fake/runtime seam；未运行真实 CLI、网络或 Docling calibration。

## Docs decision

- 根 README 命中用户可见 CLI 参数、退出码、输出与工作区行为触发条件，因此做最小用户手册更新。
- `dayu/fins/README.md` 命中 Fins domain owner 与 static admission 稳定边界，因此只更新对应开发者契约段。
- `tests/README.md` 命中测试职责变化，因此只更新现有 UF-FIX01 coverage 段，不写用例流水账。
- 未触及分层关系或装配边界，不修改 `dayu/README.md`。

## Exclusions 与 residual risks

- 按 accepted plan 排除：不修改 adapter、renderer、catcher、US/CN/HK workflow；不修改 frozen evidence、oracle、scenario；不处理 `upload_filings_from` 或 material metadata；不运行真实 CLI、网络或 Docling calibration；不提交 commit。
- 未修改 `tests/fins/test_fins_service_runtime.py`，因为现有最窄 tool/runtime seam 已覆盖本 slice 所需 observation-before-start 与 canonical producer contract。
- 当前 slice 无未分类 residual risk；上述排除项均为 accepted non-goals，不是本 slice deferred finding。

## Completion

S2 implementation 已完成，允许文件与验证要求均满足。下一入口为 S2 code review；当前按用户要求停止，不提交，等待 review。
