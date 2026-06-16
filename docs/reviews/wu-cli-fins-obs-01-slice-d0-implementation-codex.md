# WU-CLI-FINS-OBS-01 Slice D0 Implementation

## 范围

- Slice：D0 lightweight observation handle contract-only checkpoint
- Plan 真源：`docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- 允许范围：Fins observation contract、contract-level tests、README impact assessment

## 第一性原理判断

D0 的动机成立：tool awaiting 需要一个可 poll / cancel / abandon 的 observation ref，但这不等于 Fins core runtime 必须维护 durable job system。当前 slice 只固定轻量 handle 的 contract 和 recovery 语义，防止 Slice C/D 在删除或降级旧 job store 前重新依赖 job id、sidecar cursor 或 durable resume。

## 修改

- 新增 `dayu/fins/ingestion/observation_handle.py`
  - 定义 `FinsObservationHandle`、`FinsObservationStatus`、`FinsObservationPollErrorKind`、`FinsObservationSnapshot`、`FinsObservationRuntime` protocol。
  - 定义 `FinsObservationResolutionKind`，用层中立分类固定 observation status / poll error 到 Host wait resolution 的映射，不导入 Host。
  - 定义 `observation_handle_id_to_resume_token(...)` 与 `parse_observation_handle_id_token(...)`，当前 resume token 只承载 opaque `finsobs_...` hex-only handle id。
  - 校验 handle / message 不包含 job、sequence、cursor、resume token、tool call、storage path 或路径片段。
- 更新 `dayu/fins/ingestion/__init__.py`
  - 导出 D0 observation contract 符号。
- 更新 `tests/fins/test_fins_ingestion_tools.py`
  - 覆盖 resume token 解析成功。
  - 覆盖 non-hex / corrupt token 与 missing process-local observation source 分类为 LOST。
  - 覆盖 observation status 到 resolution kind 映射。
  - 覆盖 terminal snapshot result、pending retry-after 以及非法字段组合。
  - 覆盖 contract 禁止 job / sequence / cursor / storage path 文本。
- 更新 `tests/README.md`
  - 记录新增 lightweight observation handle contract 测试事实。

## 明确未做

- 未实现 process-local observation registry。
- 未修改 `dayu/fins/ingestion/wait_adapter.py`。
- 未修改 Fins tool helper 的 `resume_token=start.job_id` 路径。
- 未删除或降级 `FinsIngestionRuntime` 旧 job store / sidecar API。
- 未修改 Host wait record schema、Host API、Engine contract 或 `ToolAwaitingOutcome` union。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
  - 47 passed，3 条第三方 `edgar` deprecation warning。
- `source .venv/bin/activate && pyright dayu/fins/ingestion/observation_handle.py dayu/fins/ingestion/__init__.py tests/fins/test_fins_ingestion_tools.py`
  - 0 errors，0 warnings。

## README Impact

- `dayu/fins/README.md`
  - 已检查。当前 README 仍整体描述旧 durable Fins job / wait adapter / sidecar 语义；replacement plan 已把实际 README 统一清理放到 Slice E。D0 只新增未接入 runtime/wait adapter 的 contract checkpoint，不单独修改 Fins README，避免局部文档与仍未迁移的 runtime / wait adapter 代码事实冲突。
- `tests/README.md`
  - 已更新。新增 observation handle contract 测试事实属于测试维护者需要知道的当前测试范围。
