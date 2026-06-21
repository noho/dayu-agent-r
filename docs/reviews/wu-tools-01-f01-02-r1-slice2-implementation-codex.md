# WU-TOOLS-01-F01-02-R1 Slice 2 Implementation

## 改动摘要

- Fins download / preprocess / upload awaiting callable 已从 immediate submit 改为 prepare-only：工具只调用 `prepare_observed_*`，返回既有 `ToolAwaitingOutcome(EXTERNAL_JOB)` shape，不提交 executor。
- `FinsIngestionRuntime` 新增 `prepare_observed_download` / `prepare_observed_preprocess` / `prepare_observed_upload` / `activate_observation(handle)`：
  - prepare 注册 process-local observation，保存 direct stream `producer` / `context` / cancellation state，初始状态复用 `PENDING`。
  - activation 在同一个 observation lock 内查找 handle、drain 已有队列、检查 cancellation / terminal / submitted，并原子标记 `submitted=True`；executor submit 在锁外执行。
  - repeated activation 幂等，不 double-submit。
  - prepared observation 在 activation 前取消会 terminal 为 `CANCELLED`，后续 activation 不 submit。
  - submit 或 activation 异常会把已存在 observation terminal 为 `FAILED`，可由现有 wait adapter 观察，不会永久停留在 `PENDING`。
- 保留 direct `start_observed_*` 启动语义：其实现为 prepare 后立即 activate；未改变 durable `start_download` / `start_preprocess` / `start_upload` job API 行为。
- `dayu.fins.ingestion.wait_adapter` 新增 `FinsIngestionWaitActivationAdapter` 与 `build_fins_wait_activation_registry(...)`，复用 `FINS_INGESTION_WAIT_ADAPTER_KEY`，解析现有 opaque resume token 后调用 runtime activation。
- `FinsObservationRuntime` protocol 增补 prepare / activate 方法。
- 测试覆盖三类 awaiting tool prepare-only、三类 operation activation 提交、activation 幂等、pre-activation cancel、deterministic cancel/activate lock ordering、submit failure wait-adapter 可观察、unexpected activation exception terminal 化，以及 resume token opaque 禁止片段。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
  - 结果：`51 passed`
  - 备注：存在 3 条 upstream `edgar` deprecation warnings。
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - 结果：`68 passed`
  - 备注：存在 3 条 upstream `edgar` deprecation warnings。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
  - 备注：pyright 提示有新版本 `v1.1.410`，当前环境为 `v1.1.409`。

## README 判断

- 已更新 `dayu/fins/README.md`：本次修改触及 `dayu/fins/`，且该 README 已记录 awaiting observation runtime / wait adapter 入口与状态流；旧文本会误导为工具调用直接 `start_observed_*` 并启动 executor，因此按其更新约束做最小事实同步。
- 未更新 `tests/README.md`：本次只在既有 `tests/fins/` 文件中补充同层级 focused coverage，没有新增测试目录、运行方式或维护约定。
- 未更新根 README / `dayu/README.md` / Host README：未修改用户可见 CLI/Web/安装工作流、分层关系或 Host 文件；production Service wiring 属 Slice 3。

## 剩余风险与未覆盖项

- Slice 2 只提供 Fins activation adapter 与 builder，未把 activation registry 接入 Service / production Host assembly；该 wiring 属计划中的 Slice 3。
- `build_fins_wait_adapter_registry(...)` 与 `build_fins_wait_activation_registry(...)` 当前各自按 workspace root 构造 runtime；production 中要确保 awaiting tool runtime、poll adapter runtime 与 activation adapter runtime 的 process-local observation registry 装配一致，避免找不到 prepared observation。此项同属 Slice 3 assembly 风险。
- 本 Slice 未引入 durable prepared job 状态；prepared-but-unaccepted observation 仍按计划保持 process-local，runtime teardown 后自然丢弃。
