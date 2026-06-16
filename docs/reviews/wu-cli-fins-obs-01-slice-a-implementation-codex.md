# WU-CLI-FINS-OBS-01 Slice A Implementation Report

## 实施范围

- 新增 `dayu/fins/direct_events.py`，作为唯一 direct Fins 业务事件 contract：
  - `FinsEventType(PROGRESS/RESULT)`
  - `FinsResultStatus(SUCCESS/FAILURE/CANCELLED)`
  - `FinsOperationKind`
  - `FinsErrorKind`
  - `FinsEventDetail`
  - `FinsProgress`
  - `FinsResultSummary`
  - `FinsEvent`
- `FinsEvent` contract 已固定字段校验：
  - `PROGRESS` 必须有 `progress` 且无 `result`。
  - `RESULT` 必须有 `result` 且无 `progress`。
  - `SUCCESS/FAILURE/CANCELLED` 退出码固定为 `0/1/130`。
  - `message`、`details`、`document_label` 有基础 leakage guard，拒绝 job id、sequence、cursor、absolute path、raw/provider payload、财报正文等文本。
- 重写 `dayu/service/fins_direct.py` 为 direct `AsyncIterator[FinsEvent]` Service boundary：
  - runtime protocol 改为 `download(...)`、`preprocess(...)`、`upload(...) -> AsyncIterator[FinsEvent]`。
  - Service 提供六个 command 边界：`download`、`process`、`process_filing`、`process_material`、`upload_filing`、`upload_material`。
  - Service public direct API 不再导出或依赖 `FinsDirectJobHandle`、`FinsDirectJobEvent`、`FinsDirectTerminalResult`、`stream_job_events_until_terminal(...)`、`wait_for_terminal(...)`、`request_cancel(job_id)`。
  - runtime stream 正常结束但没有 `RESULT` 时，Service 产出明确 `FAILURE` result，不做 terminal job fallback。
- `dayu/fins/ingestion_runtime.py` 只做 Service-facing direct protocol handoff：
  - 新增 `download/preprocess/upload -> AsyncIterator[FinsEvent]` 方法。
  - 方法显式抛出 `FinsDirectStreamNotImplementedError`，不实现真实 runtime stream，不删除或收敛旧 job store。
- 重写 `tests/service/test_fins_direct.py`：
  - fake runtime 返回 `AsyncIterator[FinsEvent]`。
  - 覆盖 progress -> result、failure、异常透传、task cancellation close、no-result failure、重复 result fail fast、不暴露 job handle、contract 校验、基础 leakage guard、六个 Service command request mapping。

## 验证

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py -q`
  - 结果：`19 passed`
  - 备注：第三方 `edgar` 依赖产生 3 条 deprecation warning，非本次修改引入。
- `source .venv/bin/activate && pyright dayu/fins/direct_events.py dayu/service/fins_direct.py dayu/fins/ingestion_runtime.py tests/service/test_fins_direct.py`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

用户指定 pyright target 已由上述 superset 覆盖：

```text
dayu/service/fins_direct.py
dayu/fins/ingestion_runtime.py
tests/service/test_fins_direct.py
```

## README Impact Assessment

- `dayu/service/README.md`
  - 已检查。该 README 当前描述 `dayu.service.fins_direct` 为 durable direct job helper、job event observation、terminal fallback 与 `request_cancel(job_id)`，与 Slice A 新 Service boundary 已不一致。
  - 该文件未见 `Agent更新约束` 章节；按本 WU 要求，本 Slice 只记录 impact，实际 README 编辑留给 Slice E。
- `dayu/fins/README.md`
  - 已检查 `Agent更新约束【必须遵守】`。该 README 面向 `dayu.fins` 当前已实现能力与稳定边界。
  - Slice A 只新增 direct event contract 与 runtime protocol handoff，真实 runtime stream 未实现；若此时更新会把后续 Slice C/D 的未落地能力提前写入稳定说明。因此本 Slice 不编辑，留给 Slice E 结合 C/D 最终代码统一更新。
- `tests/README.md`
  - 已检查。当前 `tests/service/` 与 `tests/cli/` 中 Fins direct 描述仍包含 durable job、sequence、terminal fallback 与 `request_cancel(job_id)`。
  - 本 Slice 已迁移 `tests/service/test_fins_direct.py`，但 CLI 与 runtime 测试仍待后续 Slice；实际 README 编辑留给 Slice E。
- `dayu/README.md`
  - 已检查 `Agent更新约束【必须遵守】`。该 README 总览仍描述 CLI direct 数据命令启动 Fins ingestion job、消费 job event、poll terminal fallback 并用 `request_cancel(job_id)` 取消。
  - 本 Slice 改变 Service direct boundary，但 CLI 与 runtime 尚未完成 replacement；为避免总览文档提前记录未闭环状态，本 Slice 不编辑，留给 Slice E。

## Residual Risk

- `WU-CLI-FINS-OBS-01-R6`：仍触发且保持 open。Slice A 与 Slice C 共享 `dayu/fins/ingestion_runtime.py`，本次只固定 protocol handoff；真实 runtime implementation 明确未做，留给 Slice C。
- `WU-CLI-FINS-OBS-01-R7`：未触发。本 Slice 未设计或实现 lightweight observation handle。
- `WU-CLI-FINS-OBS-01-R8`：未触发。本 Slice 未实现 observation registry、runtime 并发访问或 blocking bridge。

## 未覆盖项

- CLI 仍在后续 Slice B 迁移；本 Slice 未修改 `dayu/cli/commands/fins.py` 或 `dayu/cli/output.py`。
- Fins runtime direct stream 真实执行仍在 Slice C；本 Slice 使用 fake runtime 固定 Service contract，避免越界实现。
- README 实际同步留给 Slice E。
