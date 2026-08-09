# wu-cli-interactive-02 PR review finding fix

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：PR review finding fix
- PR：[#190](https://github.com/noho/dayu-agent-r/pull/190)
- Local HEAD：`a4ff05db`
- Finding：`PR-A01 / accepted-low / duplicate accepted-result required-field owners`
- Adjudication：
  `docs/reviews/gateflow-wu-cli-interactive-02-pr-review-adjudication-20260802.md`
- Fix status：`已修复`，等待 MiMo / DS 独立 re-review
- Artifact path：
  `docs/reviews/gateflow-wu-cli-interactive-02-pr-review-fix-codex-20260802.md`

## First-principles judgment and owner decision

PR-A01 的动机成立，严重性为 low 的判断准确。当前代码没有现时行为差异，
但 proactive `dispatch` 与 reactive `engine_ingest` 各自从同一个
`CompactionOperationResult` optional field 维护相同 required-field 校验与相同
`RuntimeError` 文本。同一 accepted-result presence invariant 因此存在两个 owner，
未来单边修改会使两条 durable projection 路径漂移。

`CompactionOperationResult` 产生并携带 accepted candidate 的成功响应身份与 proposal
manifest reference，是这两个事实的 typed owner。修复应在该类型边界收口；caller 只机械
消费 owner，不应新增共享 helper、兼容 wrapper、re-export 或更泛化抽象。

## Scope and exact changes

本 fix 只修改四个允许文件，并新增本 artifact：

- `dayu/host/compaction_operation.py`
  - 在 `CompactionOperationResult` 增加
    `required_successful_response_identity()`；
  - 增加 `required_proposal_manifest_reference()`；
  - 两个 accessor 都带完整中文 docstring，只读取各自现有字段；字段缺失时沿用原有
    `RuntimeError` 类型和原有错误文本。
- `dayu/host/dispatch.py`
  - proactive accepted caller 机械调用两个 result owner accessor；
  - 删除本地 `_required_successful_response_identity` 与
    `_required_compactor_manifest_reference`。
- `dayu/host/engine_ingest.py`
  - reactive accepted caller 机械调用两个 result owner accessor；
  - 删除本地 `_required_successful_response_identity` 与
    `_required_compactor_manifest_reference`。
- `tests/host/test_compaction_operation.py`
  - existing missing-manifest guard 从 `dispatch` 私有 helper 迁移为直接断言 result
    owner；
  - 新增 missing-successful-identity owner guard test；
  - 删除对 `dayu.host.dispatch` 的测试依赖。

生产/测试 tracked diff 为 `4 files changed, 63 insertions(+), 78 deletions(-)`。
普通 diff stat 与 `git diff -w --stat` 完全一致，没有 formatter-only churn；本轮未运行
formatter。

## Preserved contracts and non-goals

以下均保持不变：

- `CompactionOperationResult` dataclass fields、字段类型与字段顺序；
- operation result construction 与 accepted/rejected control flow；
- wire/schema、durable payload 与 LLM-facing 文本；
- 两条缺失字段错误的异常类型与错误文本；
- terminal CAS、事务边界与 first-committer-wins 语义；
- accepted/rejected behavior、attempt number 与 budget fallback；
- PR body、README、design、oracle、scenario 和所有既有 review artifacts。

本 fix 没有实现 PR-R01、PR-R02、PR-R03 或其它 PR review 建议，也没有新增
compatibility wrapper、re-export、共享 facade 或泛化抽象。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### Tests

| Validation | Result |
|---|---|
| `pytest -q tests/host/test_compaction_operation.py` | `33 passed` |
| `pytest -q tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py`（coverage session） | `283 passed` |
| `pytest -q tests/host`（diagnostic full run） | `2383 passed, 1 skipped, 6 deselected, 6 failed`；六项精确为既有 `test_phase5_local_execution_integration.py` 的 `drain_once().dispatched == 0` baseline |
| `pytest -q tests/host --ignore=tests/host/test_phase5_local_execution_integration.py`（green coverage session） | `2380 passed, 1 skipped, 6 deselected` |

六项 diagnostic full-run failure 与既有 S5 clean-base 裁决、S6 final artifact 记录的六个
节点完全相同；本 fix 未修改该测试文件、queue promotion、drain timing 或 scheduler state。
因此它们不是 PR-A01 regression，本轮也没有越界修复旧 oracle。

### Coverage

green Host coverage session 使用 branch coverage，并只精确排除上述已裁决的单个 baseline
文件；所有 PR-A01 owner/caller tests 均包含在 session 中。

| Production file | Coverage |
|---|---:|
| `dayu/host/compaction_operation.py` | 86% |
| `dayu/host/dispatch.py` | 84% |
| `dayu/host/engine_ingest.py` | 85% |
| Aggregate | 85% |

三个修改生产文件均达到单文件 `>=80%` 目标；未新增 coverage pragma、omit 或 no-cover
规则。

### Type and lint

- Full `python -m pyright dayu/ tests/ utils/`：
  `0 errors, 0 warnings, 0 informations`。
- 原始 affected-file `ruff check`：只报告 5 个 F401，分别是 `dispatch.py` 的四个
  context-budget import 与 `engine_ingest.py` 的一个 run-input import。
- 对 `HEAD` 的两个原文件分别通过 stdin 运行相同 Ruff 检查，精确复现同一组
  `4 + 1` F401，证明不是本 fix 新增或扩散。
- `ruff check --ignore F401` 对四个修改文件：`All checks passed!`。
- 为遵守 exact scope，没有顺手删除这五个与 PR-A01 无关的既有 import。

### Diff, scope and security

- `git diff --check`：通过。
- helper inventory：`dispatch.py` 与 `engine_ingest.py` 中四个旧 local helper 的定义和
  调用均为零；owner 上两个 accessor 各只有一个定义，两类 caller 各机械调用一次。
- tracked code/test diff 精确为四个允许文件；初始三个未跟踪 PR review artifacts 保持
  只读且未改。
- added-line credential / API key / bearer / private-key / long-token pattern scan：零命中。
- HEAD 保持 `a4ff05db`；未执行 stash、checkout、reset、rebase、commit、push 或任何
  GitHub mutation。

## Docs decision

已只读检查 `dayu/host/README.md` 与 `tests/README.md` 的更新边界。本 fix 只收口 Host
内部 typed-result invariant，并迁移既有 owner test；没有改变稳定公共架构说明、测试层级、
测试运行方式、用户命令或工作流。加之本 gate 明确禁止修改 README/design，因此不更新
README 或 design 文档。

## Finding status and residual risks

- `PR-A01`：`已修复`。两个 accepted-result presence invariant 已由
  `CompactionOperationResult` 唯一拥有，四个重复 local helper 已删除。
- 六个 Phase 5 integration baseline failures：`assigned to later work unit`；已有 S5
  clean-base 与 S6 artifacts 跟踪，不由 PR-A01 owner fix 处理。
- 五个 affected-file F401：`assigned to repository hygiene / later work unit`；HEAD 可复现，
  本 fix 没有新增或扩散。
- G01–G07 calibration、formal interactive scenarios 与 renderer target closure：
  `assigned to later work unit`，沿用 PR adjudication 分类。
- GitHub 没有 reported checks：外部 validation gap 保持不变；本轮禁止 GitHub mutation，
  不把 local validation 冒充 CI。
- 没有新的 unclassified residual risk、blocking open question 或 uncovered PR-A01 behavior。

## Completion status and next entry point

Codex PR review fix gate 完成，`PR-A01` 当前状态为 `已修复`。按 adjudication，下一 entry
point 是 MiMo / DS 同时读取本 artifact、PR review adjudication 与 exact fix diff，分别进行
独立 PR re-review。遵照用户指令，本轮在 artifact 生成与本地验证后停止，不 commit、不 push、
不修改 PR body 或 GitHub 状态。
