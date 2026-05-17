# P9.5 S3 Host Public Error Taxonomy And Command Handle Encapsulation Implementation

## 范围

- Gate：P9.5 S3 Host Public Error Taxonomy And Command Handle Encapsulation implementation。
- 分支：`p9.5-pre-p10-hardening`。
- 计划来源：`docs/host/p9-5-pre-p10-hardening-plan.md` 的 S3。

## 动机判断

S3 动机成立。直接证据是 public command/read facade 已依赖 `HostCommandHandle` 持有的 durable store 与 admission service，但部分路径会让 durable error 穿透 public 边界；同时 `retry_run`、`replay_run`、`purge_session` 在 handle 关闭后会先返回 `UNSUPPORTED_OPERATION`，没有先执行 handle lifecycle 校验。

## 变更文件

- `dayu/host/command.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_package_exports.py`
- `docs/reviews/p9-5-s3-host-public-error-command-handle-implementation-20260517.md`

## 实现内容

- 在 `dayu/host/command.py` 增加私有 durable/internal error 到 `HostApiError` 的转换 helper。
- 将 durable config、foreign key、unique/id conflict、idempotency conflict、transaction busy/retry exhausted 和 generic durable failure 映射到既有 public error code，不新增 public error code。
- 让 `HostCommandHandle._transaction_runner()`、`_run_read()`、`_run_write()` 和 command facade 在 public 边界转换 durable error。
- 让 `retry_run`、`replay_run`、`purge_session` 先检查 closed handle；closed handle 统一返回 `HostApiErrorCode.INVALID_STATE`。
- 增加 public behavior 测试，覆盖 session/read/admission/deferred facade 在 closed handle 下先返回 `INVALID_STATE`，并覆盖 retryable transaction busy 转换。
- 增加包根负向导出测试，确认 `dayu.host` 不导出 durable store、admission service、active registry、ToolRuntime factory/handle/build request 和 dispatch scheduler。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_package_exports.py tests/host/test_public_contracts.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py`
  - 结果：69 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过，无输出。

## 文档决策

已检查 `dayu/host/README.md`。现有文档已说明 closed handle 下 public facade 返回 `HostApiError(code=INVALID_STATE, retryable=False)`，并说明 durable、admission、ToolRuntime 与 scheduler 内部边界不从 `dayu.host` 包根导出；本次不需要修改 README。

## 残余风险

- 本次没有新增 public error code；transaction busy/retry exhausted 复用 `INTERNAL_ERROR` 且 `retryable=True`。
- durable generic failure 统一映射为 `INTERNAL_ERROR`；若后续 durable 层新增更细分类，需要在同一私有转换 helper 中补充映射。
- 未触及 Host 状态机、schema、Service/UI 导入路径、P10+ 语义、兼容 re-export 或内部 service property。

## 停止状态

S3 implementation 完成。未 commit、未 push、未创建 PR，未进入 review gate。
