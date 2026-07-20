# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S3 Implementation Report

- status: pass
- slice: S3 — Host Adapter Snapshot And Service-Owned Fins Wait Glue
- prerequisite: S2 accepted commit `272575e4`
- implementation owner: AgentCodex
- commit: 未创建；按 gate 流程停在 workspace changes 等待 review / commit

## 实施动机与 owner 结论

本 slice 的问题成立：旧 `dayu.fins.ingestion.wait_adapter` 位于 Fins 包内，却 import Host wait contract 并消费 Host durable wait row 形状。它让 Fins package 拥有了不该拥有的 Host wait-resume integration 语义，并让 adapter 可以从 durable row 字段读取、推断或补偿 Host wait 边界。

正确 owner 分工如下：

- Host 拥有 durable `WaitRecordRow`、claim/backoff、deadline/expiry、cancelled wait abandon、resolve/resume 和 adapter-facing 最小投影。
- Service 拥有 Fins awaiting observation 与 Host wait adapter registry / activation / poll adapter 的组合胶水。
- Fins 只拥有 lightweight observation handle、snapshot、status、runtime 与财报业务结果，不导入 Host。

## 生产代码改动

- `dayu/host/wait_adapter.py`
  - 新增 frozen/slots `WaitAdapterSnapshot(tool_name, resume_token, created_at)` 与 `WaitAdapterSnapshotProjectionError`。
  - `WaitPollAdapter.poll_wait(...)` / `abandon_wait(...)` 改为接收 `WaitAdapterSnapshot`。
  - Host poller 在调用 adapter 前通过 `_adapter_snapshot_from_wait_record(...)` 从 durable row 投影最小 snapshot。
  - snapshot 投影失败在 Host 内 fail closed：poll 路径写 `ADAPTER_ERROR` backoff；abandon 路径写 `ABANDON_ERROR` backoff；adapter 不被调用。
- `dayu/service/fins_wait_adapter.py`
  - 新增 Service-owned Fins wait adapter 模块。
  - adapter 只消费 Host public wait adapter snapshot / outcome / registry contract，不导入 `dayu.host.durable`，不读取 deadline、expiry、claim、state mutator 或 external job ref durable 字段。
  - transient unavailable 只返回 not-ready；终态 deadline/expiry 仍由 Host poll owner 判定。
- `dayu/service/host_assembly.py`
  - Fins wait adapter import 从旧 Fins 模块切到 `dayu.service.fins_wait_adapter`。
- `dayu/fins/ingestion/wait_adapter.py`
  - 删除旧模块；未保留兼容 re-export、wrapper、facade 或 lazy import。
- `utils/smoke_host_public_awaiting_entrypoint.py`
  - smoke fake adapter 签名同步为 `WaitAdapterSnapshot`，删除本地 opaque protocol。

## 测试覆盖

- `tests/host/test_wait_adapter_polling.py`
  - 覆盖 adapter 只收到三字段 snapshot。
  - 覆盖 snapshot 空/超长 token 拒绝。
  - 覆盖 poll / abandon 前 projection failure 均在 Host 侧 backoff 且不调用 adapter。
  - 所有 wait adapter fake 改为 snapshot contract。
- `tests/service/test_fins_wait_adapter.py`
  - 新增 Service-owned adapter 测试，覆盖 registry binding、duplicate fail-fast、activation shared runtime、activation corrupt token、poll status mapping、failed result 缺 message、corrupt/missing handle lost、transient unavailable not-ready、old `created_at` 不制造 lost、abandon cleanup / corrupt / missing / lost / non-transient / transient retry。
- `tests/fins/test_fins_ingestion_tools.py`
  - 删除 Fins 侧 Service adapter tests 与 Host durable imports；保留 Fins observation/tool provider 自身契约测试。
- `tests/fins/test_fins_ingestion_runtime.py`
  - activation submit failure 测试改为直接断言 Fins observation snapshot 终态，不再通过 Service adapter 间接观察。
- `tests/service/test_import_boundary.py`
  - 允许 Service adapter 使用 Fins direct event text public helper。

## README / 文档同步

- `dayu/README.md`: 顶层说明 Fins long-running tools 经 lightweight observation handle 和 Service-owned wait adapter 接入 Host wait-resume。
- `dayu/fins/README.md`: 删除 Fins->Host wait adapter 例外；Fins 只拥有 observation contract，wait adapter binding 属于 Service assembly。
- `dayu/service/README.md`: 新增 `dayu.service.fins_wait_adapter` 稳定入口和 import boundary。
- `dayu/host/README.md`: 记录 Host poller 向 adapter 只投影 `WaitAdapterSnapshot`。
- `tests/README.md`: 将 wait adapter 测试说明从 Fins 迁到 Service。

## 验证结果

```text
pytest tests/service/test_fins_wait_adapter.py tests/service/test_host_assembly.py tests/service/test_import_boundary.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_observation_runner.py tests/host/test_open_host_runtime.py -q
326 passed, 3 warnings
```

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

```text
pytest tests/service/test_fins_wait_adapter.py --cov=dayu.service.fins_wait_adapter --cov-report=term-missing -q
17 passed, 3 warnings
dayu/service/fins_wait_adapter.py coverage: 92%
```

```text
git diff --check
pass
```

```text
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.host' dayu/fins --glob '*.py'
no matches
```

```text
test ! -e dayu/fins/ingestion/wait_adapter.py
pass
```

```text
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.(host|service)' tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py
no matches
```

## 未覆盖风险

- Service adapter 仍通过 `asyncio.run(...)` 在 Host observation thread 内执行 Fins async observation runtime 方法；当前 production poller 调用点是同步 observation thread，非 running event loop。
- 本 slice 不改变 Host wait state machine、Engine awaiting contract、LLM-facing schema 或 tool schema。

## 工具安全未实施

本 S3 未实现任何工具安全项，也未修改 LLM-facing 文本/schema。以下项目仍明确 deferred：

- upload allowlist、user-file authority、explicit file authority 与 symlink-safe upload source policy；
- URL、TLS、redirect、SSRF 与 provenance policy；
- remote download byte-budget policy；
- LLM-facing upload/download security schema、prompt 或 tool schema 变化。

本 slice 只处理 Host/Service/Fins wait adapter 语义所有权与 import boundary，不处理工具安全规划。
