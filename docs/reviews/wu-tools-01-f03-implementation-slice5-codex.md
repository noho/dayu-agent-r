# WU-TOOLS-01-F03 Slice 5 Implementation Closeout - AgentCodex

## 范围判断

- Slice 5 的动机成立：Slice 1-4 已接受，剩余工作是文档职责判断、最终验证、`WU-TOOLS-01-S5-R2` residual reconciliation 和总控状态推进。
- 本轮不需要修改核心代码。F03 已在 `utils/smoke_web_ci.py` 与 deterministic tests 中提供 local HTML/PDF smoke、summary contract、external diagnostic-only 语义和 Playwright 非 gate 边界。

## 改动文件

- `tests/README.md`
  - 已先阅读 README 更新边界。该文件职责是描述当前 `tests/` 已存在事实、测试运行方式与维护规则。
  - 因 `tests/tools/web/test_smoke_web_ci.py` 已存在，且现有 README 只说明 Web provider tests 必须 deterministic，未说明 live smoke 位于 `utils/` 且不进入默认 pytest；本轮补充一句 opt-in Web live smoke 边界，属于 README 职责范围。
- `docs/host/issues-implementation-control.md`
  - 将 WU-TOOLS-01-F03 推进到 `ready-to-open-draft-PR`。
  - 记录 Slice 5 closeout artifact、最终验证、manual smoke command 与 residual reconciliation。
  - 关闭 `WU-TOOLS-01-S5-R2`；external site instability、real browser capability gap、provider/API availability gap 转入带 owner 的 deferred residual tracking entries。
- `docs/reviews/wu-tools-01-f03-implementation-slice5-codex.md`
  - 记录本轮 closeout 证据。

## 验证

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q`
  - 通过：`36 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
  - pyright 输出包含版本提示：`v1.1.409 -> v1.1.410`。
- `git diff --check`
  - 通过：无输出。
- `bash -n utils/smoke_web_ci.sh`
  - 不适用：当前仓库没有 `utils/smoke_web_ci.sh`。

## Manual Smoke Command

默认 deterministic pytest 不运行真实 live smoke。Controller 已运行手工 opt-in smoke：

```bash
source .venv/bin/activate && DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live
```

运行结果：

- exit code：`0`
- output：`workspace/output/web_smoke/web-smoke-20260610T030021Z`
- summary status：`passed`
- local_html：`passed`
- local_pdf：`passed`
- external_cases：`0`
- skips：`0`

该 smoke 证明当前 controller 环境下 local HTML/PDF smoke 与 summary contract 已通过。external cases 为 0，表示本次 manual smoke 没有把外部 URL corpus 纳入 hard gate。

## R2 Residual Reconciliation

`WU-TOOLS-01-S5-R2` 结论：closed。

关闭依据：

- F03 已提供显式 opt-in Web smoke 入口：`utils/smoke_web_ci.py`。
- deterministic tests 已覆盖未 opt-in skip、local HTML/PDF case 判定、Docling invocation evidence 缺失时的 blocker、summary JSON/Markdown 输出、external diagnostic-only 不覆盖 local gate、external artifact gap 和 child process error 不改变 local pass、`--include-playwright` 仅影响 external diagnostic-only。
- local HTML/PDF smoke 与 summary contract 已在 deterministic synthetic coverage 中锁定，并由 controller manual smoke 证明当前环境下通过：summary status `passed`，local_html `passed`，local_pdf `passed`。
- 外部网站 anti-bot、DNS、timeout、HTTP 403/429/5xx、real browser / Chrome channel / storage-state cookies、provider/API key、quota、auth 与环境可用性均不是 F03 local Web smoke blocker。

没有新的无 owner residual。以下非 local smoke 风险已转入 `docs/host/issues-implementation-control.md` 的 Residual Risk 表，状态均为 `deferred-with-owner`：

- `WU-TOOLS-01-F03-R1` external site instability：anti-bot、DNS、timeout、HTTP 403/429/5xx 与真实站点波动。
- `WU-TOOLS-01-F03-R2` real browser capability gap：Playwright browser、Chrome channel 与 storage-state cookies。
- `WU-TOOLS-01-F03-R3` provider/API availability gap：provider/API key、quota、auth 与环境可用性。

这些条目不是 F03 local Web smoke blocker。后续若需要把 external corpus、real Playwright browser 或 provider/API availability 升级为 hard gate，必须先建立稳定环境契约，并创建独立 owner / issue 或 work unit；这不属于 `WU-TOOLS-01-S5-R2` 的 local Web smoke 关闭条件。

## 风险与未覆盖项

- 本次 controller manual smoke 已证明当前环境下 local HTML/PDF smoke 通过；不声明 Chrome/Playwright、provider/API 或外部站点 hard gate 可用性。
- external URL corpus 仍是显式 diagnostic-only；其失败只进入 summary 证据，不代表 production Web tool regression。
