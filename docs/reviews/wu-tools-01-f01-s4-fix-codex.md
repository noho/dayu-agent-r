# WU-TOOLS-01-F01 Slice S4 Fix Artifact

## 范围

- Gate: fix gate.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S4 - Download / Preprocess Awaiting Tool Providers`.
- Branch: `host-wu-tools-01-f01`.
- 输入裁决: `docs/reviews/wu-tools-01-f01-s4-code-review-controller-adjudication.md`.

本次只修复 controller adjudication 接受的三条 finding，未进入 re-review、commit、push、PR 或后续 slice。

## 修复内容

### F01-S4-001

- 新增私有模块 `dayu/fins/tools/_ingestion_tool_helpers.py`。
- 将 download/preprocess 共用的 awaiting outcome 构造、failed outcome 构造、必填文本、可选文本数组和可选布尔参数读取逻辑收敛到该私有模块。
- 保留 `download_tools.py` 与 `preprocess_tools.py` 中各自的 tool name、schema、LLM-facing description 和 request construction，不改变工具对外行为。

### F01-S4-002

- 在 `tests/fins/test_fins_ingestion_tools.py` 增加 focused tests：
  - `start_download` 抛出 `OSError` 时返回 `ToolFailedOutcome`，错误码为 `fins_download_start_failed`。
  - `start_download` 抛出非预期异常时返回 `ToolFailedOutcome`，错误码为 `fins_download_start_failed`。
  - `start_preprocess` 抛出 `OSError` 时返回 `ToolFailedOutcome`，错误码为 `fins_preprocess_start_failed`。
  - `start_preprocess` 抛出非预期异常时返回 `ToolFailedOutcome`，错误码为 `fins_preprocess_start_failed`。

### F01-S4-003

- 在 awaiting outcome 测试中，先断言工具立即返回 `ToolAwaitingOutcome` 和 `EXTERNAL_JOB`。
- 断言完成后，通过同一 workspace 派生的 shared ingestion runtime 读取返回的 job id，并等待 job 进入 `succeeded`、`failed` 或 `cancelled` 终态。
- 生产 callable 仍保持非阻塞，只启动 durable job 并返回 awaiting outcome。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/runtime/test_config_loader.py`
  - 结果: 60 passed。
  - 备注: 仅有 `edgar` 依赖 deprecation warnings。
- `source .venv/bin/activate && pyright`
  - 结果: 0 errors, 0 warnings, 0 informations。
  - 备注: pyright 提示存在新版本，不影响本次类型验证。

## README 同步决策

本次只调整 S4 工具适配层私有 helper 组织方式和测试覆盖，不改变用户可见命令、配置入口、provider contract、tool name、tool schema、awaiting outcome 或文档职责范围内的稳定行为。因此未同步修改 README。

## 剩余风险

- 本次未覆盖真实网络 downloader 成功路径；该路径不属于 controller accepted findings，且本次未修改 downloader。
- executor 提交异常测试会在 durable job 创建后触发失败 outcome，用于约束 callable 的非预期异常收口；该场景下遗留 queued record 是当前 runtime start 边界行为，本次未改变生产语义。
