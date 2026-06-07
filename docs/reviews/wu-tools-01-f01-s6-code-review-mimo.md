# WU-TOOLS-01-F01 Slice S6 Code Review

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01`
- Slice: `S6 - Config, Docs And Regression Closeout`
- Gate: code review
- Reviewer: mimo
- Artifact: `docs/reviews/wu-tools-01-f01-s6-code-review-mimo.md`

## 结论

**pass-with-findings**

S6 目标全部达成：默认 config 已拆分为三组 disabled provider，workspace overlay 测试证明 read/download/preprocess 可独立启用且不依赖 `include_ingestion_tools`，README 同步符合职责分工，Fins import boundary 新增的 S5 wait adapter 例外足够窄。有一个 medium finding（spec id 与 provider id 命名不一致）和一个 low finding（import boundary 测试用 `Path` 字面比较）。建议关闭 `WU-TOOLS-01-S4-R1`。

## 验证命令结果

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py`
  - 结果：`138 passed, 3 warnings`（warnings 来自 edgar 依赖 deprecation）
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`

## Findings

### F1: spec id `financial-read-tools` 与 provider id `financial-tools` 命名不一致 [MEDIUM]

**文件行号**: `dayu/fins/tools/provider.py:29`

**直接证据**:
- `dayu/config/tool_discovery.json` 中 read provider 的 spec id（map key）为 `"financial-read-tools"`
- `dayu/fins/tools/provider.py:29` 中 `_PROVIDER_ID = "financial-tools"`
- `dayu/fins/tools/download_provider.py:16` 中 `_PROVIDER_ID = "financial-download-tools"`，与 spec id `"financial-download-tools"` 一致
- `dayu/fins/tools/preprocess_provider.py:16` 中 `_PROVIDER_ID = "financial-preprocess-tools"`，与 spec id `"financial-preprocess-tools"` 一致
- `tests/fins/test_fins_ingestion_tools.py:57` 中 `_READ_PROVIDER_ID = "financial-tools"` 与 `_READ_SPEC_ID = "financial-read-tools"` 分开定义

**影响**: `provider_id` 是 `ToolsDiscoveryProviderOutput` 中返回给上层的标识，用于 Service assembly 的 provider 匹配、source ref 构造和 wait adapter 检测。当前 `"financial-tools"` 是旧 mixed provider 时代的遗留命名。虽然功能正确（Service assembly 通过 import path 和 source id 检测 Fins provider），但命名不一致会造成认知负担：后续维护者可能误认为 `"financial-tools"` 仍是 mixed provider，或者在日志/诊断中无法快速区分 read provider 与旧 mixed provider。

**建议**: 将 `_PROVIDER_ID` 改为 `"financial-read-tools"`，同时更新 `_SOURCE_ID` 为 `"dayu.fins.tools.provider"`（当前已是）。需同步更新 `tests/fins/test_fins_ingestion_tools.py:57` 的 `_READ_PROVIDER_ID` 和 `tests/fins/test_fins_storage_provider.py` 中依赖该值的断言。此变更属于 S6 范围内的 cleanup，不影响 Host/Engine contract。若出于兼容性考虑不改，则应在测试或文档中明确说明 `provider_id` vs `spec_id` 的区别。

### F2: import boundary 测试使用 `Path` 字面比较可能因路径规范化而脆弱 [LOW]

**文件行号**: `tests/fins/test_fins_storage_provider.py:630`

**直接证据**:
```python
_FINS_WAIT_ADAPTER_PATH = Path("dayu/fins/ingestion/wait_adapter.py")
# ...
if path == _FINS_WAIT_ADAPTER_PATH:
    return _FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS
```

`Path("dayu/fins/ingestion/wait_adapter.py")` 是相对路径，而 `rglob("*.py")` 返回的 `path` 也是相对路径（从 `"dayu/fins"` 开始 glob）。当前测试在 repo root 运行时两者匹配。但如果将来测试工作目录变化或 glob 行为变化，`Path` 比较可能失败（因为 `Path` 比较是字符串比较，不做 resolve）。

**影响**: 当前测试通过，不影响功能。但这是一个脆弱点。

**建议**: 可以改用 `path.name == "wait_adapter.py" and "ingestion" in path.parts` 做更鲁棒的匹配，或者用 `path.resolve()` 做规范化后比较。优先级低，不阻塞 S6 closeout。

### F3: workspace overlay 测试验证了 `include_ingestion_tools` 不在 provider config 中 [OK - CONFIRMED]

**文件行号**: `tests/fins/test_fins_ingestion_tools.py:211-213`

**直接证据**:
```python
for provider_id in (_READ_SPEC_ID, _DOWNLOAD_SPEC_ID, _PREPROCESS_SPEC_ID):
    provider_config = config.tool_discovery.providers[provider_id]
    assert provider_config.enabled is True
    assert "include_ingestion_tools" not in provider_config.config
```

此断言证明 workspace overlay 中三组 provider 的 config 都不包含 `include_ingestion_tools`。默认 `dayu/config/tool_discovery.json` 也不再包含该字段。README 不再描述该字段为目标配置。旧 fail-closed 测试已被替换为独立 provider discovery 测试。

**结论**: `include_ingestion_tools` 清理完整，无残留。

### F4: Fins import boundary wait adapter 例外足够窄 [OK - CONFIRMED]

**文件行号**: `tests/fins/test_fins_storage_provider.py:70-72`

**直接证据**:
```python
_FINS_WAIT_ADAPTER_PATH = Path("dayu/fins/ingestion/wait_adapter.py")
_FINS_DEFAULT_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.host", "dayu.service", "dayu.ui")
_FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.service", "dayu.ui")
```

`wait_adapter.py` 是唯一被允许导入 `dayu.host` 的 Fins 模块。其余所有 Fins 模块仍禁止导入 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。`wait_adapter.py` 实际导入了 `dayu.host.api` 和 `dayu.host.wait_adapter`，这些是 Host 公共契约，符合 S5 设计意图。

`wait_adapter.py` 同时仍禁止导入 `dayu.engine`、`dayu.service`、`dayu.ui`，且 `dayu.runtime` 和 `dayu.engine` 也被验证不导入 `dayu.fins`（`test_runtime_and_engine_do_not_import_fins`）。

**结论**: 例外范围精确，不掩盖 Fins 反向依赖风险。

### F5: README 同步符合职责 [OK - CONFIRMED]

**审查点**:
- `dayu/config/README.md`: 更新了三组 disabled Fins provider entries 说明，符合 config README 职责。不写未来 CLI。
- `dayu/fins/README.md`: 更新了 read/download/preprocess provider split、默认 disabled 和 wait adapter 边界说明，符合 Fins 开发手册职责。
- `tests/README.md`: 更新了 Fins 测试覆盖边界，删除了旧开关作为目标行为的描述，符合测试手册职责。
- 根 `README.md` 未更新：正确，当前无 `dayu/cli` package。
- `dayu/README.md` 未更新：正确，未改变稳定分层关系。

### F6: 遗漏测试检查 [OK - CONFIRMED]

**审查点**:
- config loader 默认 config: `test_config_loader.py` 覆盖了默认 tool_discovery.json 的三组 provider entries
- combined tools acceptance: `test_combined_tools_acceptance.py` 覆盖了 Doc/Fins/Web 聚合、Service assembly 传入 Host、ToolRuntime 执行
- Fins full tests: `test_fins_storage_provider.py` 覆盖 read provider discovery/execution/boundary、`test_fins_ingestion_tools.py` 覆盖 split provider discovery/awaiting/wait adapter、`test_fins_ingestion_runtime.py` 覆盖 runtime pipeline
- Service host assembly: `tests/service/test_host_assembly.py` 覆盖 Fins await assembly wiring

## WU-TOOLS-01-S4-R1 关闭建议

**建议关闭**。

证据链：
1. S1-S5 已建立 shared `DefaultFinsRuntime`、download/preprocess provider、Fins wait adapter 和 Service assembly wiring。
2. S6 已将默认配置和 workspace overlay 回归收口到 read/download/preprocess 三 provider 目标形态。
3. 验证覆盖 config loader、combined tools acceptance、Fins full tests、Service host assembly，全部通过。
4. `include_ingestion_tools` 不再是默认配置、workspace overlay 或 README 目标形态。
5. `WU-TOOLS-01-S4-R1` 的原始定义是"迁移共享 Fins ingestion service/runtime，并分别提供 download / preprocess tool providers 的 awaiting adapter"——这些均已实现。

F1（provider id 命名不一致）不阻塞 S4-R1 关闭，因为它是命名 cleanup 而非功能缺失。可在后续 cleanup work unit 或当前 branch 的 fix pass 中处理。

## 残余风险

- **fixed in current slice**: 默认 Fins provider config mixed 形态；workspace overlay 使用旧 ingestion 开关；README 旧目标形态说明；Fins import boundary 未识别 S5 wait adapter 例外。
- **assigned to later work unit**: 真实 SEC/CN/HK 网络 download adapters；upload ingestion provider；SEC/Fins 与 CN/HK CI pipeline/smoke；未来 NEW CLI download/process wrapper。
- **non-blocking residual**: read provider `_PROVIDER_ID` 命名不一致（F1）。
- **blocker**: none。
