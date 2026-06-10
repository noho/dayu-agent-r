# WU-TOOLS-01-F03 Slice 5 Fix - AgentCodex

## 范围判断

- 本 fix gate 只处理 `docs/reviews/wu-tools-01-f03-code-review-slice5-controller-adjudication.md` 的 Required Fixes。
- Required Fixes 的动机成立：F03 可以关闭 local Web smoke residual，但 external site、real browser、provider/API availability 不能从治理表消失；F02 行也不应记录后续 F03 closeout 的后验事实。
- 本轮不修改核心代码，不 commit，不 push，不进入 re-review。

## 修复内容

- `docs/host/issues-implementation-control.md`
  - Residual Risk 表新增三条 `deferred-with-owner`：
    - `WU-TOOLS-01-F03-R1` external site instability：anti-bot、DNS、timeout、HTTP 403/429/5xx 与真实站点波动。
    - `WU-TOOLS-01-F03-R2` real browser capability gap：Playwright browser、Chrome channel 与 storage-state cookies。
    - `WU-TOOLS-01-F03-R3` provider/API availability gap：provider/API key、quota、auth 与环境可用性。
  - 三条 residual 均明确不是 F03 local Web smoke blocker；未来若升级为 hard gate，必须先建立稳定环境契约，并创建独立 owner / issue 或 work unit。
  - F02 Work Unit row 只记录 F02 completion 与 F03 前置满足，不再写 `WU-TOOLS-01-S5-R2` 已由 F03 closeout 关闭。
  - F02 非目标恢复为历史 scope 语义：F02 不定义 Web smoke pass/fail gate，缺口交由 WU-TOOLS-01-F03 生成 smoke 后关闭。
  - F03 row 与 F03 状态段记录 controller manual smoke：`source .venv/bin/activate && DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live`，exit code `0`，output `workspace/output/web_smoke/web-smoke-20260610T030021Z`，summary status `passed`，local_html `passed`，local_pdf `passed`，external_cases `0`，skips `0`。
- `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md`
  - 删除 / 改写“未运行真实 DAYU_RUN_WEB_CI_SMOKE=1”的旧表述。
  - 记录 controller manual smoke 已运行且 local HTML/PDF passed。
  - 将 external/browser/provider 三类非 local smoke 风险改写为已转入 Residual Risk 表的 deferred-with-owner 条目。

## 验证

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q`
  - 通过：`36 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
  - pyright 输出包含版本提示：`v1.1.409 -> v1.1.410`。
- `git diff --check`
  - 通过：无输出。

## 风险与未覆盖项

- 本 fix 只修文档治理与 closeout 证据记录，不改变 Web smoke 实现。
- external site、real browser、provider/API availability 后续若要成为 hard gate，仍需要独立环境契约和独立 owner / issue。
