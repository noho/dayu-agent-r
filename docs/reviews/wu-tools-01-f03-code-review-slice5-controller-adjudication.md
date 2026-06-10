# WU-TOOLS-01-F03 Slice 5 Code Review Controller Adjudication

## 输入

- Implementation artifact: `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md`
- MiMo review: `docs/reviews/wu-tools-01-f03-code-review-slice5-mimo.md`
- DS review: `docs/reviews/wu-tools-01-f03-code-review-slice5-ds.md`
- Controller validation:
  - `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q` -> 36 passed
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` -> 0 errors
  - `git diff --check` -> passed
- Controller manual smoke:
  - `source .venv/bin/activate && DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live`
  - exit code `0`
  - output: `workspace/output/web_smoke/web-smoke-20260610T030021Z`
  - summary: status `passed`, exit_code `0`, local HTML `passed`, local PDF `passed`, external_cases `0`, skips `0`

## 总体裁决

结论：`pass-with-fixes`。

MiMo 对 README 边界、ready-to-open-draft-PR 状态和 closeout 证据给出 pass。DS 对 residual governance 的挑战成立：F03 可以关闭 `WU-TOOLS-01-S5-R2`，但必须先把 external site / real browser / provider availability 三类非 local smoke 风险转移成明确 residual owner，不能让它们从总控中消失。

另外，DS 对 manual smoke 的 finding 在 controller 侧已关闭：controller 已实际运行 opt-in local smoke，结果为 passed。文档仍需更新，替换原先“未运行真实 smoke”的表述。

## Required Fixes

1. 为 external/browser/provider 三类非 local smoke 风险创建明确 residual tracking entries。
   - 来源：DS F1-S5-DS-001。
   - 要求：在 `docs/host/issues-implementation-control.md` 的 Residual Risk 表中新增条目，状态可为 `deferred-with-owner`，Owner / Destination 必须是明确 owner 角色或后续 work unit / issue destination。
   - 最低条目：
     - external site instability：anti-bot、DNS、timeout、HTTP 403/429/5xx、真实站点波动。
     - real browser capability gap：Playwright browser、Chrome channel、storage-state cookies。
     - provider/API availability gap：provider/API key、quota、auth、环境可用性。
   - 要求说明：这些条目不是 F03 local Web smoke blocker；如果未来要升级为 hard gate，必须先建立稳定环境契约和独立 issue / work unit。

2. 更新 manual smoke closeout 证据。
   - 来源：DS F1-S5-DS-002；controller 已执行手工命令。
   - 要求：更新 `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md` 和总控 F03 条目，记录 controller manual smoke 命令、exit code `0`、summary 目录 `workspace/output/web_smoke/web-smoke-20260610T030021Z`、summary status `passed`、local HTML/PDF both `passed`。
   - 删除或改写“未运行真实 DAYU_RUN_WEB_CI_SMOKE=1”的旧表述。

3. 恢复 F02 非目标段的历史记录语义。
   - 来源：DS F1-S5-DS-003。
   - 要求：不要把 F02 non-goal 改写成后验事实；恢复为 F02 自身 scope 语义，例如“F02 不定义 Web smoke pass/fail gate；F02 完成后该缺口交由 WU-TOOLS-01-F03 生成 smoke 后关闭。”

4. 修正 F02 Work Unit 行的跨 WU forward reference。
   - 来源：DS F1-S5-DS-004。
   - 要求：F02 row 只记录 F02 自身 completion 和 F03 前置满足；不要在 F02 row 中断言 R2 已由 F03 closed。R2 关闭和转移依据只写在 F03 row、Residual Risk 表和 Slice 5 closeout artifact。

## Accepted

- `tests/README.md` 新增 opt-in live smoke 边界说明：accepted。它是测试 README 职责内的默认 pytest 边界说明，不是过度扩写。
- `ready-to-open-draft-PR` gate 和 next entry `do not open PR until authorized`：accepted，前提是上述 fixes 后 residual governance 完整。
- `WU-TOOLS-01-S5-R2` 可关闭：accepted，前提是三类 non-local-smoke risk 已转入 residual table。

## Fix Gate 验证要求

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`

