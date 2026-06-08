# WU-TOOLS-01-F01 Slice S6 Code Review

## Gate

- Work unit: `WU-TOOLS-01-F01`
- Slice: `S6 - Config, Docs And Regression Closeout`
- Gate: deep review
- Artifact: `docs/reviews/wu-tools-01-f01-s6-code-review-ds.md`
- Stance: correctness / architecture / maintainability / missing tests
- 结论: **PASS-WITH-FINDINGS**

## 验证命令结果

```
$ source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py -q
138 passed, 3 warnings in 1.85s
(warnings 均为 edgar 依赖 deprecation warning)

$ source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

## Findings（按严重程度排序）

### F2 — read provider `_PROVIDER_ID` 仍为旧 mixed provider 名 `"financial-tools"`

- **文件**: `dayu/fins/tools/provider.py` 行 29
- **直接证据**:

  ```python
  # provider.py:29
  _PROVIDER_ID: Final[str] = "financial-tools"
  ```

  对比 download/preprocess provider：

  ```python
  # download_provider.py:16
  _PROVIDER_ID: Final[str] = "financial-download-tools"
  # preprocess_provider.py:16
  _PROVIDER_ID: Final[str] = "financial-preprocess-tools"
  ```

  默认 `tool_discovery.json` 中 spec_id（config map key）为 `"financial-read-tools"`，但 read provider 自报 `provider_id = "financial-tools"`。download/preprocess 的 provider_id 与各自的 spec_id 一致，只有 read provider 不一致。

- **影响**:
  1. `"financial-tools"` 是 S4 前旧 mixed provider（集合 read/download/preprocess）的名称。read provider 在 S4 已聚焦为只输出 read tools，但 `provider_id` 仍保留旧名。
  2. `ToolsDiscoveryProviderReport.provider_id` 与 `spec_id` 在 read provider 上不一致（`"financial-tools"` vs `"financial-read-tools"`），而 download/preprocess 是一致的。这种不对称在 provider report 消费方（如 Service assembly、诊断）中增加了理解成本。
  3. 计划 S4 明确要求 "Do not keep a mixed provider facade for compatibility"——`"financial-tools"` 命名本身是 mixed provider 概念的残留。

- **不构成功能性 bug 的原因**: 当前 Service assembly 用 `provider_config.provider_id`（即 config map key = spec_id）检测 Fins awaiting providers，不依赖 provider 自报的 `provider_id`。工具发现、Host/Engine 执行路径也不依赖 provider_id 做路由决策。所有测试通过。

- **建议**: 将 `provider.py` 中 `_PROVIDER_ID` 改为 `"financial-read-tools"`，同步更新 `test_fins_ingestion_tools.py` 中 `_READ_PROVIDER_ID = "financial-read-tools"`。这会消除 spec_id/provider_id 的不对称，使三组 provider 的命名约定一致。

- **如果暂时不改**: 至少应在 `provider.py` docstring 或 Fins README 中显式说明 provider_id 与 spec_id 的差异及其历史原因，防止后续维护者产生混淆。

### F3 — 无其他 findings

其余 7 个审查重点均通过，具体如下：

## 审查重点逐项结论

### 1. 默认配置形态 ✓ PASS

`dayu/config/tool_discovery.json` 中 Fins 相关为三个独立 disabled provider entries：
- `financial-read-tools` → `dayu.fins.tools.provider:discover_tools`
- `financial-download-tools` → `dayu.fins.tools.download_provider:discover_tools`
- `financial-preprocess-tools` → `dayu.fins.tools.preprocess_provider:discover_tools`

无 `include_ingestion_tools` 字段。默认 `enabled=false`、`allow_empty=true`、`workspace_root=null`。

### 2. Workspace overlay 独立启用 ✓ PASS

`tests/fins/test_fins_ingestion_tools.py::test_workspace_overlay_enables_split_fins_providers`（行 200-228）通过真实 `ConfigLoader` + `ToolsDiscovery` 证明：
- overlay 可独立启用 read/download/preprocess 三组 provider
- 各组 config 均不含 `include_ingestion_tools`
- 三组 provider report 的 spec_id 和 tool_names 各不重叠

`tests/runtime/test_config_loader.py::test_default_runtime_config_files_load_as_typed_views`（行 381-398）断言默认 read provider config 不包含 `include_ingestion_tools`。

### 3. 旧 `include_ingestion_tools` 残余范围 ✓ PASS

代码范围内 `include_ingestion_tools` 仅出现在：
- `tests/runtime/test_config_loader.py` 行 388: `assert "include_ingestion_tools" not in read_provider.config`（负断言）
- `tests/fins/test_fins_ingestion_tools.py` 行 212: `assert "include_ingestion_tools" not in provider_config.config`（负断言）

两处均为"字段不存在"的防御性断言。`dayu/config/tool_discovery.json`、workspace overlay fixture、README 均不再将其作为目标配置形态。`provider.py` 已删除 `_CONFIG_INCLUDE_INGESTION_TOOLS_FIELD` 及相关解析逻辑。

### 4. provider_id vs spec_id — 见 F2

### 5. Fins import boundary S5 wait adapter 例外 ✓ PASS

`tests/fins/test_fins_storage_provider.py` 行 71-72：
```python
_FINS_DEFAULT_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.host", "dayu.service", "dayu.ui")
_FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.service", "dayu.ui")
```

`_fins_forbidden_import_roots()`（行 617-632）按文件路径选择禁用根：
- `dayu/fins/ingestion/wait_adapter.py` → 允许 `dayu.host`，禁止 `dayu.engine`/`dayu.service`/`dayu.ui`
- 其余所有 Fins 模块 → 禁止 `dayu.host`/`dayu.engine`/`dayu.service`/`dayu.ui`

例外范围足够窄（单文件，且 wait_adapter 的职责就是桥接 Fins job 到 Host wait-resume contract）。Host → Fins 方向无 import，不存在反向依赖风险。`test_runtime_and_engine_do_not_import_fins`（行 375-385）确证 Engine/runtime 不导入 Fins。

### 6. README 同步 ✓ PASS

| README | 更新 | 判断 |
|---|---|---|
| `dayu/config/README.md` | 行 175-183：默认 Fins providers 三组 disabled entries 表格 | 属于该 README 职责（配置项变化），内容准确 |
| `dayu/fins/README.md` | 全文同步 read/download/preprocess provider split、默认 disabled、wait adapter | 属于 Fins 开发手册职责 |
| `tests/README.md` | 行 147-155：同步 Fins ingestion/awaiting split provider 回归覆盖 | 属于测试手册职责 |
| 根 `README.md` | 未更新 | 正确——当前无 `dayu/cli`，不宣称 CLI download/process |
| `dayu/README.md` | 未更新 | 正确——S6 未改变稳定分层/装配边界 |

无"写未来 CLI"、无"过度更新根 README"、无"config README 越界写 Engine/Service 内部机制"。

### 7. WU-TOOLS-01-S4-R1 关闭判断 ✓ 建议关闭

S4-R1 定义在 `docs/host/issues-implementation-control.md` 行 198：
> 迁移共享 Fins ingestion service/runtime，并分别提供 download / preprocess tool providers 的 awaiting adapter。

计划 `wu-tools-01-f01-plan.md` 行 700：
> WU-TOOLS-01-S4-R1: covered by S1-S6 if shared runtime, split providers and wait adapter integration complete.

S1-S6 完成状态：
- S1: `DefaultFinsRuntime` + `FinsIngestionRuntime` + job store ✓
- S2: preprocess source→processed pipeline ✓
- S3: download adapter protocol + fake adapter + storage write + unsupported-source failure ✓
- S4: 三组独立 provider（read/download/preprocess）+ `ToolAwaitingOutcome` ✓
- S5: `FinsIngestionWaitPollAdapter` + Service assembly wiring ✓
- S6: config/docs/test 收口 ✓

全部验证命令通过（138 passed, 0 pyright errors）。无直接阻塞证据。

**唯一附条件**: F2（provider_id 命名）建议修复但不阻塞关闭——功能性正确性、测试覆盖和文档准确性均不依赖 `provider_id` 取值。

### 8. 测试覆盖 ✓ PASS

| 覆盖维度 | 覆盖文件/测试 | 状态 |
|---|---|---|
| Config loader 默认 config | `test_default_runtime_config_files_load_as_typed_views` 断言三组 Fins provider + `include_ingestion_tools` 不存在 | ✓ |
| Combined tools acceptance | `test_combined_tools_acceptance.py` 覆盖 Doc/Fins/Web 聚合、ToolRuntime accept、ScenePrepare tag 选择 | ✓ |
| Fins full tests | `tests/fins/` 覆盖 storage provider、ingestion runtime、ingestion tools（download/preprocess provider discovery + awaiting + wait adapter） | ✓ |
| Service host assembly | `tests/service/test_host_assembly.py` 覆盖 Fins awaiting assembly wiring | ✓ |

无遗漏的 S6 计划指定测试类别。

## 补充说明

- `dayu/fins/ingestion/wait_adapter.py` 额外导入了 `dayu.fins.tools.download_tools.DOWNLOAD_TOOL_NAME` 和 `dayu.fins.tools.preprocess_tools.PREPROCESS_TOOL_NAME`（行 28-29），但这两个目标模块不导入 `dayu.host`，无传递性反向依赖风险。
- `test_combined_tools_acceptance.py` workspace overlay 只启用 `financial-read-tools`（不含 download/preprocess），这符合其"Doc/Fins/Web combined acceptance"定位——下载/预处理验收由 `test_fins_ingestion_tools.py` 独立覆盖。

## WU-TOOLS-01-S4-R1 关闭建议

**建议关闭。** S1-S5 已实现 shared runtime、split providers 和 wait adapter wiring；S6 已将默认配置和 workspace overlay 回归收口到三 provider 目标形态；所有指定验证通过。F2（provider_id 命名）是 cosmetic consistency issue，不构成功能阻塞。建议关闭后在 issues-implementation-control.md 中将 F2 作为轻量 follow-up 或直接在本 branch 修复。
