# WU-CLI-FINS-OBS-01 Aggregate Fix (AgentCodex)

## 范围

- **Gate**：aggregate deepreview fix
- **Finding**：AgentMiMo `BF-1`
- **Finding artifact**：`docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260616.md`
- **修复目标**：让 Service import boundary 测试表达新的 Fins direct public contract，关闭 `dayu.fins.direct_events` 被误判为 forbidden Fins import 的问题。

## 根因判断

`dayu.service.fins_direct` 导入 `dayu.fins.direct_events` 是成立且必要的边界选择。该模块承载 direct path 的 typed public event contract，Service direct API 需要用它表达 `AsyncIterator[FinsEvent]`、progress/result 语义和 exit status，不应回退为 durable job handle 或把事件形态复制到 Service 层。

失败根因不是实现越界，而是 `tests/service/test_import_boundary.py` 的 `SERVICE_ALLOWED_IMPORTS` 未随 Slice A/B 的公共 direct event contract 同步更新。现有 allowlist 已允许 `dayu.fins.ingestion_runtime`、`dayu.fins.service_runtime` 和 `dayu.fins.domain.enums` 作为 Service/Fins assembly 与 typed request 边界；`dayu.fins.direct_events` 属于同一类显式 public boundary。

## 修改

- `tests/service/test_import_boundary.py`
  - 在 `SERVICE_ALLOWED_IMPORTS` 中加入 `dayu.fins.direct_events`。
- `tests/README.md`
  - 同步说明 Service import boundary 允许 `dayu.service.fins_direct` 导入 Fins direct event public boundary。

## 非目标

- 不移动 `dayu.fins.direct_events` 到其它包；当前 work unit 只修正已确认的公共契约边界。
- 不放宽整个 `dayu.fins` 前缀；Service 仍只能导入显式白名单 public boundary。
- 不改变 CLI / Service / runtime direct stream 行为。

## 验证计划

- `pytest tests/service/test_import_boundary.py -q`
- WU targeted pytest matrix
- `pyright dayu/ tests/ utils/`
- `git diff --check`
