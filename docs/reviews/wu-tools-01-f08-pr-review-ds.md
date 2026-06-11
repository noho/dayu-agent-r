# WU-TOOLS-01-F08 PR Review Gate

## Metadata

- PR: [#135](https://github.com/noho/dayu-agent-r/pull/135)
- Title: WU-TOOLS-01-F01-02-R3 and F08 tools cleanup
- Head: `phaseflow/wu-tools-r3-f08`
- Base: `main`
- State: OPEN draft
- Reviewer: AgentDS
- Date: 2026-06-11
- Output file: `docs/reviews/wu-tools-01-f08-pr-review-ds.md`
- Scope: PR 135 full diff (`github/main...HEAD`), 111 files, +16179/-5929

## Verdict

pass-with-findings

## Findings

### F1-未修复-中-PR 分支无 CI 检查覆盖

- **入口/函数**: PR 级别 CI gate
- **文件(行号)**: N/A (GitHub checks API)
- **输入场景**: `gh pr checks 135 --repo noho/dayu-agent-r` 返回 `no checks reported on the branch`
- **实际分支**: 无外部 CI pipeline 在此分支上执行过任何自动验证
- **预期行为**: 有 111 文件、16179 行新增的 PR 应有可被 reviewer 独立查阅的 CI 通过记录，或 PR body 明确标注"本 PR 无 CI 覆盖、所有验证为本地手动执行"
- **实际行为**: PR body 列出 `pytest ...`、`python -m pyright ...` 命令但未给出 pass/fail 计数或 CI link；`rg` 命令给出了结果（`no matches`），而 pytest/pyright 命令没有输出
- **直接证据**: `gh pr checks 135` 输出 `no checks reported on the branch`；PR body 中 pytest 与 pyright 行未附带 pass count 或 CI badge
- **影响**: Reviewer 无法从 PR 页面独立确认所列验证命令在当前分支上确实通过；所有验证依赖对 reviewer 本地环境的信任，不可复现审计
- **建议改法和验证点**: 
  1. 在 PR body 中标注"本仓库当前无 CI pipeline，以下为本地验证输出"，并附实际 pass count（如 R3 final closeout 中 `115 passed`、F08 controller 中 `263 passed, 1 skipped`、pyright `0 errors`）
  2. 或配置 GitHub Actions / 等价 CI 使 checks 可被 GitHub 记录
- **修复风险（低）**: 仅涉及 PR body 文本更新或 CI 配置新增，不影响 production code
- **严重程度（中）**: 不阻塞 correctness，但降低了 PR 可审计性；在有 16K 行 diff 的 PR 上缺少 CI 是治理缺口

### F2-未修复-低-PR body 验证命令输出不一致

- **入口/函数**: PR body 的 `## Validation` 节
- **文件(行号)**: PR body（`gh pr view 135 --json body`）
- **输入场景**: Reviewer 仅通过 PR body 评估验证覆盖
- **实际分支**: 8 行验证命令中，4 条 `rg` 命令附带了结果文本（如 `no matches`），2 条 `pytest` 命令和 1 条 `pyright` 命令未附带任何输出
- **预期行为**: 所有验证命令应一致地附带实际输出或明确引用包含验证结果的 review artifact
- **实际行为**: RG 命令有结果而 pytest/pyright 没有，reviewer 不能从 PR body 判断 pyright/pytest 是否通过了当前分支
- **直接证据**: PR body 中 `pytest tests/runtime/test_tool_call_projection.py ...` 行无 pass count，`python -m pyright dayu/ tests/ utils/` 行无输出；而 `rg` 行有 `no matches`
- **影响**: 降低 PR body 作为独立验证文档的可用性
- **建议改法和验证点**: 补齐 pytest 和 pyright 行的 pass/fail count；或统一删除所有命令的输出，改为引用 `docs/reviews/wu-tools-01-f01-02-r3-final-closeout-controller.md` 与 `docs/reviews/wu-tools-01-f08-aggregate-deepreview-controller-adjudication.md` 中的验证记录
- **修复风险（低）**: 仅涉及 PR body 文本
- **严重程度（低）**: 不影响 correctness；review artifact 中已有完整验证记录

## PR Metadata Review

### Title 覆盖

Title "WU-TOOLS-01-F01-02-R3 and F08 tools cleanup" 准确覆盖 R3（legacy adapter retirement + cancellation fix）与 F08（documents processor registry naming cleanup）。不再只描述 R3。

### Head/Base 与 Draft 状态

Head `phaseflow/wu-tools-r3-f08`、base `main` 正确。Draft/open 状态符合当前 gate：R3 的 draft-PR-pass 后，F08 在同一分支上实现，gate 回退到 `ready-to-open-draft-PR`。PR 仍应保持 draft，等待用户 merge decision。控制文档 `docs/host/issues-implementation-control.md` 当前状态表正确反映此状态：
- gate: `ready-to-open-draft-PR`
- implementation status: `WU-TOOLS-01-F08 aggregate deepreview passed; ready to update existing draft PR`
- active work unit: `WU-TOOLS-01-F08`

### PR Body 覆盖范围

PR body 4 条 Summary bullet 分别覆盖：
1. R3：legacy adapter 退役 + 原生工具迁移 + cancellation 修复
2. F04-F07：控制文档清理
3. F08：registry builder 命名 + S1-R2 关闭
4. Notes：deferred risks（Web smoke → #121/#122，physical interrupt → WU-WAIT-03）

覆盖完整，无夸大 CI 状态（未声称 CI passed）。

### Workspace 与 Remote 一致性

- 本地工作区干净：`git status --short` 无输出
- 本地 `github/main..HEAD` 共 18 commits：R3 的 12 commits（`7b465e19` 至 `d7b7c509`）+ F08 的 6 commits（`a0c00567` 至 `3d331a32`）
- Remote `github/phaseflow/wu-tools-r3-f08` 包含所有 18 commits：`git log github/phaseflow/wu-tools-r3-f08..HEAD` 无输出
- 所有 F08 commits 已推送

### PR-level Blocker 检查

- 遗漏文件：无。Diff 覆盖 R3（legacy adapter 删除、工具迁移、cancellation 修复）与 F08（registry 命名、测试、控制文档更新）
- 未推送提交：无。Remote 包含全部本地 commit
- 总控状态错误：无。控制文档 gate/state 与实际情况一致
- F04-F07 残留：`rg "WU-TOOLS-01-F0[4567]" docs/host/issues-implementation-control.md` 无匹配
- Legacy adapter 残留：`rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests` 无匹配
- 旧 registry builder 名残留：`rg "build_engine_processor_registry" dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md` 无匹配
- F08 residual 关闭证据充足：`WU-TOOLS-01-S1-R2` 已在控制文档中关闭，aggregate deepreview 两个 reviewer 均确认
- PR body 与 diff 一致：body 描述的 4 类变更均可在 diff 中找到对应文件：
  - R3 legacy adapter 删除 → `dayu/tools/_legacy_adapter/` 下 6 文件删除
  - 工具迁移 → `dayu/tools/doc_tools.py`、`dayu/tools/web/web_tools.py`、`dayu/fins/tools/fins_tools.py` 大改
  - Cancellation 修复 → `dayu/runtime/tool_call_projection.py` 新增、各 provider 改用 `host_cancelled_outcome`
  - F08 命名 → `dayu/documents/processors/registry.py` 函数重命名 + 4 文件引用更新
  - F04-F07 清理 → `docs/host/issues-implementation-control.md` 177 行改动

### Architecture Boundary Check

- `dayu/runtime/tool_call_projection.py` 仅依赖标准库与 `dayu.contracts`，不 import `dayu.engine/host/service/ui/fins`，符合 `dayu.runtime` 层中立约束
- `dayu/tools/__init__.py` 已移除旧 legacy adapter 描述，不再暴露内部适配器为公共 API
- 无发现跨层反向依赖或实现泄漏

## Open Questions

- 仓库是否计划为此分支配置 CI pipeline？当前 `gh pr checks 135` 无任何 check，16K 行 diff 的 PR 依赖纯手动验证会随仓库规模增长成为持续性治理风险。

## Residual Risk

- 所有 16K 行 diff 的验证依赖本地手动执行；外部 reviewer 或未来维护者无法从 PR 页面独立验证 pytest/pyright 通过状态。
- R3 + F08 作为两个独立 work unit 分别通过了 aggregate deepreview（R3 范围 `main..R3-closeout`，F08 范围 `R3-closeout..HEAD`），但合并后的完整 diff 未作为单一变更集重新 deep review。交互风险低（F08 仅改名），但作为过程风险记录。
- `dayu/fins/tools/read_runtime.py` 中 `_raise_if_fins_cancelled` 已委托给 `read_runtime_helpers.raise_if_fins_cancelled`，但原函数未被删除（仅重构为调用 shared helper）。这属于 `dayu/fins/tools/read_runtime.py` 内部重构，不产生外部契约变化，风险低。

## PR Readiness Summary

PR 135 在技术层面 ready for review。两个 work unit（R3 + F08）均已完成各自的 plan → implementation → code review → deepreview gate，且所有 accepted commits 已推送至远程分支。工作区干净，控制文档状态一致。

当前仅需处理两条低影响 finding：补齐 PR body 中验证命令的输出（或标注无 CI + 引用 review artifact），以及中长期考虑为此仓库配置 CI pipeline。无 blocking finding，不建议因上述 finding 阻止 PR 进入下一步 gate。
