# WU-TOOLS-01-F03 Slice 5 Fix Gate Re-Review — AgentDS

## Scope

- Mode: current changes (fix gate re-review)
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main (implicit)
- Output file: docs/reviews/wu-tools-01-f03-code-rereview-slice5-ds.md
- Included scope: uncommitted diff of `docs/host/issues-implementation-control.md`, `tests/README.md`, `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md`
- Excluded scope: 核心代码（本轮无修改）
- Parallel review coverage: 无

## 输入

- Controller adjudication: `docs/reviews/wu-tools-01-f03-code-review-slice5-controller-adjudication.md`
- Codex fix report: `docs/reviews/wu-tools-01-f03-fix-slice5-codex.md`
- 当前 uncommitted diff（`git diff` + `git diff --cached`）

## 验证结果

| 检查项 | 命令 | 结果 |
|---|---|---|
| pytest | `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q` | 36 passed |
| pyright | `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| git diff --check | `git diff --check` | passed（无输出） |

## Required Fixes 逐项核对

### Fix 1: Residual Risk 表新增三条 deferred-with-owner

**状态：通过。**

- `WU-TOOLS-01-S5-R2` 已从 Residual Risk 表移除。
- 新增三条 `deferred-with-owner`：
  - `WU-TOOLS-01-F03-R1` external site instability：owner `Web tools CI owner / future Web hard-gate issue or work unit`
  - `WU-TOOLS-01-F03-R2` real browser capability gap：owner `Web tools CI owner / future real-browser hard-gate issue or work unit`
  - `WU-TOOLS-01-F03-R3` provider/API availability gap：owner `Web tools CI owner / future provider/API hard-gate issue or work unit`
- 每条均明确声明"不是 F03 local Web smoke blocker"，并给出升级为 hard gate 的前置条件（建立稳定环境契约 + 创建独立 owner/issue 或 work unit）。
- Owner/destination 足够明确：命名了 owner 角色（Web tools CI owner）和 destination（future issue or work unit）。

`WU-TOOLS-01-S5-R2` 可关闭，external site / real browser / provider availability 三类风险未丢失，已转入明确 residual tracking。

### Fix 2: manual smoke 证据写入 Slice 5 artifact 和总控

**状态：通过。**

总控 F03 Work Unit row 已记录完整 manual smoke 证据：
- 命令：`source .venv/bin/activate && DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live`
- exit code：`0`
- output：`workspace/output/web_smoke/web-smoke-20260610T030021Z`
- summary status：`passed`
- local_html：`passed`
- local_pdf：`passed`
- external_cases：`0`
- skips：`0`

Implementation artifact（`wu-tools-01-f03-implementation-slice5-codex.md`）包含独立 "Manual Smoke Command" 节，记录相同证据。未发现"未运行真实 DAYU_RUN_WEB_CI_SMOKE=1"旧表述残留。

### Fix 3: F02 non-goal 恢复历史 scope 语义

**状态：通过。**

F02 non-goal 行改动：
- 旧：`不在 F02 定义 Web smoke 的 pass / fail gate；S5-R2 在 F02 后仍保持 open，交由 WU-TOOLS-01-F03 生成 smoke 后关闭。`
- 新：`不在 F02 定义 Web smoke 的 pass / fail gate；F02 完成后该缺口交由 WU-TOOLS-01-F03 生成 smoke 后关闭。`

新文本是 F02 自身 scope 语义：F02 不定义 gate，缺口交给 F03。不再写"已在 F03 Slice 5 closeout 中关闭"的后验事实。

### Fix 4: F02 Work Unit row 只记录 F02 completion 和 F03 前置满足

**状态：通过。**

F02 Work Unit row 改动：
- 旧：`F03 前置条件已满足，WU-TOOLS-01-S5-R2 继续由 F03 关闭或转移。`
- 新：`F02 completion 已完成，F03 前置条件已满足。`

F02 row 不再断言 R2 已由 F03 closeout 关闭。R2 关闭依据仅在 F03 row、Residual Risk 表和 Slice 5 closeout artifact 中记录。

### Fix 5: tests/README.md 更新可接受；无核心代码改动

**状态：通过。**

`tests/README.md` 新增一行：
```
显式 opt-in 的 Web live smoke 位于 `utils/smoke_web_ci.py`，不在默认 pytest 中运行；`tests/tools/web/test_smoke_web_ci.py` 只覆盖 smoke 判定、summary contract 与 diagnostic-only 边界。
```
属于测试 README 职责范围内的默认 pytest 边界说明，不是过度扩写。本轮 diff 仅涉及文档文件，无核心代码改动。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 本轮仅验证文档治理修复与 closeout 证据记录的正确性。external site / real browser / provider/API availability 三类 deferred risk 的后续落地需要独立环境契约和独立 owner，不在本次 re-review 范围内。
- controller manual smoke 证明当前环境下 local HTML/PDF smoke 通过；不声明其他环境或未来环境的通过性。

## 结论

**pass** — 全部 5 项 required fixes 已正确实施，验证检查全部通过，无新增问题。
