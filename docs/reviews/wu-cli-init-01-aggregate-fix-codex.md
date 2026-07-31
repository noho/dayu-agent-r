# WU-CLI-INIT-01 Aggregate Deepreview Fix — Codex

## Gate

- Work unit：`WU-CLI-INIT-01`
- Gate：`aggregate deepreview fix`
- 输入：
  - `docs/reviews/wu-cli-init-01-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-cli-init-01-aggregate-deepreview-ds.md`
  - `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- Scope：只处理 Controller 接受的 DS F2；不修改生产代码、测试或历史 gate 记录。

## 第一性原理与语义所有权

问题成立，但根因不是 CLI parser 或运行时行为错误。当前 parser、负向测试和 Goal Confirmation 已一致规定公开参数为
`--model/-m`，且旧参数不存在；不一致来自实施总控文档只有历史 gate 快照，没有显眼的当前契约提示。

该提示的 owner 是 `docs/host/ui-implementation-control.md` 的当前实施契约区域。正确修复是在该区域声明当前公开参数，
并保留下文历史 gate 的原始记录；改写历史记录会破坏 gate 审计事实。

## Controller 裁决与直接证据

| Finding | 裁决 | 直接证据 | 处理 |
|---|---|---|---|
| DS F1：`docs/cli_ci.md` 方法论变更 scope boundary 模糊 | reject | Goal Confirmation 的 Preflight 明确记录 handbook 与 init oracle 已在本 Gateflow 前由用户要求提交；`git show 933908a8` 进一步确认该独立提交为 `docs: record CLI calibration workflow and init oracle`，只修改 `docs/cli_ci.md` 与 `docs/cli_ci_oracles.json`。 | 不修改。该 handbook 独立任务不是本 work unit 的 scope creep。 |
| DS F2：控制文档仍出现 `--model-name` | accept | `dayu/cli/arg_parsing.py` 只注册 `--model/-m`；`tests/cli/test_arg_parsing.py` 明确验证 help 不出现并且 parser 拒绝 `--model-name`；控制文档的 3 处命中均位于既有 WU-CLI-01 历史 implementation/review gate。 | 在控制文档“真源层级”后的显眼位置新增当前 CLI 契约提示，不重写历史 gate。 |
| DS F3：CLI 常量与 ConfigLoader 文件名重复 | reject | `dayu/cli/commands/init.py` 的 `_EXECUTION_PROFILES_FILE_NAME` 只定位单个 workspace 文件以执行 no-follow shape guard；publication 路径 `dayu/cli/init_workspace.py` 仍调用 `dayu.runtime.config_loader.config_file_names()` 枚举完整配置目录。 | 不修改。上游单文件 shape guard 没有接管 publication catalog ownership。 |
| DS F4：`authority_basis` 指向旧仓库路径 | reject | `docs/cli_ci_oracles.json` 将该项明确标为 `reference-observation`，并说明旧版 overwrite/reset 行为仅作为目录迁移后的语义参考；因此指向用户指定的 OLD repo reference 符合字段语义。 | 不修改。 |

MiMo review 的 3 项 informational finding 均判定无需修改，其中 Goal Confirmation 的修复前描述明确属于历史快照；
本 gate 同样不回写这些历史记录。

## 变更

- `docs/host/ui-implementation-control.md`
  - 在“真源层级”后的当前契约位置补充说明：公开模型覆盖参数已冻结为 `--model/-m`，旧参数
    `--model-name` 不存在，历史 gate 命中不代表当前公开参数。
  - 保留 3 处历史 gate 记录原文。
- `docs/reviews/wu-cli-init-01-aggregate-fix-codex.md`
  - 记录四项 Controller 裁决、直接证据、变更边界与验证结果。

未修改生产代码、测试、README、oracle 或既有 review artifact。

## 验证

- `rg` 检查 current-contract 提示：通过；新增提示同时包含 `--model/-m`、`--model-name`、历史 gate 与当前公开参数语义。
- `rg -n -C 2 --fixed-strings -- '--model-name' docs/host/ui-implementation-control.md`：通过；除新增提示外，原有 3 处历史 gate 命中仍保留。
- `git diff --check`：通过。

本 gate 未改代码，因此不运行 pytest 或 pyright；验证范围与文档-only 变更风险相称。

## 残余风险与停止条件

四项 finding 均已完成裁决：F2 由当前契约提示关闭，F1/F3/F4 按 Controller 理由 reject。无未分类残余风险。

停止于文档修改与指定验证；不 commit、不进入 re-review、不修改生产或测试。
