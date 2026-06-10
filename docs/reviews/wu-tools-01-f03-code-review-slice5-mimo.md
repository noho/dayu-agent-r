# Code Review

## Scope

- Mode: current changes
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: docs/reviews/wu-tools-01-f03-code-review-slice5-mimo.md
- Included scope: docs/host/issues-implementation-control.md, tests/README.md, docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md
- Excluded scope: unrelated history, core code changes (none in Slice 5)
- Parallel review coverage: 无

## Review Context

Slice 5 是 WU-TOOLS-01-F03 的 closeout slice，目标是补齐文档、验证和 residual reconciliation。本轮不修改核心代码，只更新总控文档、tests README 和 closeout artifact。

## Findings

未发现实质性问题。

## Detailed Analysis

### 1. tests/README.md 更新是否符合职责/更新约束

**检查项**：README 更新边界（tests/README.md:238-242）声明"本文件只描述当前 `tests/` 已存在的事实"。

**发现**：第144行新增内容为：
> 显式 opt-in 的 Web live smoke 位于 `utils/smoke_web_ci.py`，不在默认 pytest 中运行；`tests/tools/web/test_smoke_web_ci.py` 只覆盖 smoke 判定、summary contract 与 diagnostic-only 边界。

该更新描述的是 `utils/` 目录下脚本的位置，严格来说超出了"只描述 `tests/` 已存在的事实"的字面边界。但 plan（wu-tools-01-f03-web-ci-smoke-plan.md:461-489, 548）明确允许此更新，条件是"仅当现有测试手册未覆盖新增 opt-in smoke 边界"，且"只需在不造成职责扩张的前提下补充 opt-in live smoke 位于 `utils/`"。

**裁决**：符合 plan 授权，不构成过度扩写。新增内容是边界说明，不是职责扩张。

### 2. 总控状态 ready-to-open-draft-PR 是否符合当前本地 gate 完成状态

**检查项**：
- 当前 gate：`ready-to-open-draft-PR`（issues-implementation-control.md:143）
- next entry：`WU-TOOLS-01-F03 draft PR gate; do not open PR until authorized`（issues-implementation-control.md:147）
- Slice 1-5 均已完成并有 accepted commit 记录（issues-implementation-control.md:224）

**发现**：Slice 1-5 的 implementation、review、fix、re-review 和 controller validation 均已完成，验证命令通过（36 passed, 0 errors, git diff --check passed）。next entry 明确"Do not open PR until authorized"，不越权开 PR。

**裁决**：状态正确，符合 gate 完成事实。

### 3. WU-TOOLS-01-S5-R2 关闭依据是否充分

**检查项**：
- Residual Risk 表（issues-implementation-control.md:195-203）中无 S5-R2 条目，说明已从 active 表移除
- F03 条目（issues-implementation-control.md:224）记录关闭依据
- implementation artifact（wu-tools-01-f03-implementation-slice5-codex.md:49-60）详细说明关闭理由

**发现**：关闭依据包含：
1. F03 已提供显式 opt-in Web smoke 入口
2. deterministic tests 已覆盖未 opt-in skip、local HTML/PDF case 判定、Docling invocation evidence 缺失时的 blocker、summary 输出、external diagnostic-only 边界
3. local HTML/PDF smoke 与 summary contract 已在 deterministic synthetic coverage 中锁定
4. 外部网站 anti-bot、DNS、timeout、HTTP 403/429/5xx、real browser、provider availability 均由 F03 diagnostic-only 语义处理

**裁决**：关闭依据充分，符合 plan 中的关闭条件（plan:568-585）。外部/browser/provider 不稳定已归口为 diagnostic-only，不需要额外 owner，因为它们不阻塞 local Web smoke。

### 4. F02/F03 条目是否准确

**检查项**：
- F02 条目（issues-implementation-control.md:223）：状态 completed，PR #132 merged 2026-06-10
- F03 条目（issues-implementation-control.md:224）：状态 ready-to-open-draft-PR，记录所有 slice 的 artifact 和验证结果

**发现**：F02 条目正确记录了 PR merge 事实和 R2 关闭归口。F03 条目准确记录了 Slice 1-5 的 implementation artifacts、review artifacts、accepted commits 和 controller validation 结果。未引入新的架构决策或错误事实。

**裁决**：条目准确。

### 5. 验证命令、manual smoke command、summary path、未运行真实 live smoke 的风险说明是否完整

**检查项**：implementation artifact（wu-tools-01-f03-implementation-slice5-codex.md:21-47）

**发现**：
- 验证命令：`pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q`（36 passed）、`python -m pyright dayu/ tests/ utils/`（0 errors）、`git diff --check`（passed）、`bash -n utils/smoke_web_ci.sh`（不适用，无此文件）
- manual smoke command：`DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live`
- summary path：`workspace/output/web_smoke/<run_label>/summary.json` 和 `summary.md`
- 未运行真实 live smoke 的风险说明：明确说明理由（F03 deterministic closeout 已由 focused tests 与 pyright 证明，真实 local PDF smoke 依赖本机 Docling runtime 初始化状态），并声明"该未运行项作为 operator manual smoke，不是 F03 local Web smoke blocker"

**裁决**：完整，符合 plan completion report format（plan:589-608）。

### 6. git status 范围是否符合 Slice 5

**检查项**：`git status --short` 输出：
- `M docs/host/issues-implementation-control.md`（总控更新）
- `M tests/README.md`（README 边界说明）
- `?? docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md`（closeout artifact）

**发现**：无核心代码改动，只有文档和 review artifact，符合 Slice 5 scope（plan:461-489）。

**裁决**：范围正确。

## Open Questions

无。

## Residual Risk

- 未执行真实 `DAYU_RUN_WEB_CI_SMOKE=1`，因此本轮不声明当前机器的 Docling runtime、Chrome/Playwright 或外部网络状态。已在 implementation artifact 中明确记录。
- external URL corpus 仍是显式 diagnostic-only；其失败只进入 summary 证据，不代表 production Web tool regression。已在 implementation artifact 中明确记录。

## Verification Commands Executed

```bash
# pytest
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q
# 结果：36 passed in 0.35s

# pyright
python -m pyright dayu/ tests/ utils/
# 结果：0 errors, 0 warnings, 0 informations

# git diff --check
git diff --check
# 结果：无输出
```

## Conclusion

**pass**

Slice 5 closeout 的文档更新、总控状态推进和 residual reconciliation 均符合 plan 要求。tests/README.md 更新在 plan 授权范围内，总控状态正确反映 gate 完成事实，R2 关闭依据充分，验证命令完整通过。
