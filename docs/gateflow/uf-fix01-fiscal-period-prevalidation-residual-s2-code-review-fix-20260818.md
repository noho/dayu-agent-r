# UF-FIX01 fiscal-period prevalidation residual — S2 Code Review Fix

## Gate metadata

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- slice：`S2-entry-contracts-docs`
- input adjudication：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-s2-code-review-adjudication-20260818.md`
- status：`fix-complete`
- date：`2026-08-18`

## Accepted finding fixes

1. tool schema 将六值闭集精确限域到 filing：上传 filing 时 `fiscal_period` 必填且只支持
   `FY/H1/Q1/Q2/Q3/Q4`；上传 material 时只声明可选。同步 exact schema contract test 与
   `tests/README.md`，未修改 material admission。
2. static invalid tool runtime 装配 module-level recording `FinsUploadRunner`，删除
   `upload_runner is None` 结构性断言，改为断言 runner 调用记录为空；原有 state、executor、
   observation、job 与 workspace 零副作用断言保持。
3. valid canonical test 改到 runner contract boundary：holding executor 显式激活 observation，
   recording runner 接收 `ValidatedFinsUploadFilingRequest`，测试只断言
   `normalized_fiscal_period`。已删除 `_DirectUploadProducer` import/isinstance、raw 表示与
   canonical 不相等的 pin；断言后通过 `finally` abandon observation，并确认 runtime observation
   记录清空。

## Changed files

- `dayu/fins/tools/upload_tools.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/README.md`
- `docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-s2-code-review-fix-20260818.md`

未修改 material production、ingestion runtime 或其它文件；未提交。

## Verification

- focused：`23 passed, 81 deselected`
- S1+S2 affected suite：`822 passed`
- coverage 同一 affected suite：`822 passed`
  - `dayu/fins/ingestion_runtime.py`：`91%`
  - `dayu/fins/pipelines/docling_upload_service.py`：`89%`
  - `dayu/fins/tools/upload_tools.py`：`93%`
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：通过

测试仅出现 edgartools 既有 deprecation warnings，不影响结果。

## Residual risk

- 本 fix 不改变 material admission；material 财期语义仍由既有 owner 范围处理，不在本次裁决授权内。
- recording runner 只验证 runtime handoff contract，不执行真实 converter 或 storage mutation；这是本次
  accepted finding 要求的边界，相关 production workflow 继续由 affected suite 覆盖。

## Final re-review fix（2026-08-18）

- 输入裁决：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-s2-rereview-adjudication-20260818.md`。
- DS 001：`已修复`。`activate_observation` 与 `executor.run_next()` 已移入既有 `try/finally`，激活、执行及断言异常均会执行 observation abandon；清理断言保持不变。
- DS 002：当前裁决接受部分 `已修复`。CN invalid seeded case id 与 `seed_workspace` 判定均恢复使用既有追踪锚点 `UF-024`。US/HK 新场景注册仍按裁决分配给后续真实 CLI calibration workstream，本轮未修改 registry、oracle 或 evidence。
- 本次只修改 `tests/fins/test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py` 与本 artifact；未新增 production 或 README 修改，未修改 registry、oracle 或 evidence，未提交。
- focused：`48 passed, 3 warnings`。
- S1+S2 affected suite：`822 passed, 3 warnings`。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- warnings 均为既有 edgartools deprecation warnings；无新增未分类 residual risk。
