# WU-TOOLS-01-F01 Slice S6 Implementation

## Gate

- Work unit: `WU-TOOLS-01-F01`
- Slice: `S6 - Config, Docs And Regression Closeout`
- Gate: implementation only
- Artifact: `docs/reviews/wu-tools-01-f01-s6-implementation-codex.md`
- Commit / push / review gate: not performed by user instruction

## 第一性原理判断

S6 动机成立。S1-S5 已经把 Fins read、download、preprocess runtime/provider/wait adapter 路径落地，但包内默认 `tool_discovery.json` 和部分测试/文档仍保留旧 mixed `financial-tools` 配置形态，且 workspace overlay fixture 仍携带 `include_ingestion_tools`。如果不收口，后续使用者会继续把 ingestion 能力理解成 read provider 的布尔开关，而不是三组独立 provider。

本次不恢复 CLI/UI，不实现真实 SEC/CN/HK 网络 adapter，不改 Host/Engine contract，不更新根 README。

## 改动文件

- `dayu/config/tool_discovery.json`
  - 将默认 Fins 配置从单个 mixed `financial-tools` provider 改为三个 disabled provider：
    - `financial-read-tools` -> `dayu.fins.tools.provider:discover_tools`
    - `financial-download-tools` -> `dayu.fins.tools.download_provider:discover_tools`
    - `financial-preprocess-tools` -> `dayu.fins.tools.preprocess_provider:discover_tools`
  - 删除默认配置中的 `include_ingestion_tools`。
- `tests/runtime/test_config_loader.py`
  - 默认配置断言改为 split provider entries，并断言 read provider config 不包含 `include_ingestion_tools`。
- `tests/tools/test_combined_tools_acceptance.py`
  - combined workspace overlay 改用 `financial-read-tools`，不再携带 `include_ingestion_tools`。
- `tests/fins/test_fins_storage_provider.py`
  - 将 read provider helper 和负测 spec 改为 `financial-read-tools` / `dayu.fins.tools.provider:discover_tools`。
  - 将旧开关测试改为 read provider 只暴露 read tools 的目标行为测试。
  - 更新 Fins import boundary：默认仍禁止 Fins 反向依赖 Host/Service/UI/Engine；仅允许已实现的 `dayu/fins/ingestion/wait_adapter.py` 沿批准边界导入 Host wait/api contract。
- `tests/fins/test_fins_ingestion_tools.py`
  - 新增 workspace overlay 回归，证明 overlay 可独立启用 read/download/preprocess providers，且三组 provider config 都不使用 `include_ingestion_tools`。
- `dayu/config/README.md`
  - 更新默认 Fins providers 说明为三组 disabled entries。
- `dayu/fins/README.md`
  - 同步 read/download/preprocess provider split、默认 disabled 和 wait adapter 边界说明。
- `tests/README.md`
  - 同步 Fins 测试覆盖边界，删除旧开关作为目标行为的描述。

## Config / Provider Split 证据

- 默认配置现在有三组 Fins provider entries，均为 `enabled=false`、`allow_empty=true`、`workspace_root=null`。
- `financial-read-tools` 只保留 read tools 配置项：`include_read_tools` 和 `limits`。
- `financial-download-tools` 与 `financial-preprocess-tools` 分别指向独立 provider import path。
- `tests/fins/test_fins_ingestion_tools.py::test_workspace_overlay_enables_split_fins_providers` 通过真实 `ConfigLoader` 读取 workspace overlay，再交给 `ToolsDiscovery` 发现三组 provider，并验证三组 report / tool names 独立存在。

## include_ingestion_tools 清理结果

- 默认 `dayu/config/tool_discovery.json` 不再出现 `include_ingestion_tools`。
- workspace overlay fixture 不再使用 `include_ingestion_tools`。
- README 不再把 `include_ingestion_tools` 描述为目标配置形态。
- 代码范围内剩余命中仅为测试断言“默认 config / overlay config 不包含该字段”，不是支持目标配置。

## README 同步决策

- 已更新 `dayu/config/README.md`：默认 `tool_discovery.json` provider entries 发生变化，属于该 README 职责。
- 已更新 `dayu/fins/README.md`：S1-S5 已实现 read/download/preprocess runtime/provider split 和 wait adapter 边界，属于 Fins 开发手册职责。
- 已更新 `tests/README.md`：新增/调整 Fins overlay 和 split provider 回归，属于测试手册职责。
- 未更新根 `README.md`：当前仍无 `dayu/cli` package，本轮不宣称 `dayu-cli download/process`。
- 未更新 `dayu/README.md`：本轮未改变稳定分层关系或装配边界。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py`
  - 最终结果：`138 passed, 3 warnings`
  - warnings 均来自 `edgar` 依赖 deprecation warning。
  - 首次运行发现 `tests/fins/test_fins_storage_provider.py::test_fins_import_boundaries_do_not_reverse_depend` 仍未允许 S5 的 Fins wait adapter 边界；已按当前架构改为仅允许 `dayu/fins/ingestion/wait_adapter.py` 导入 Host wait/api contract，其余 Fins 模块仍禁止。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

## WU-TOOLS-01-S4-R1 关闭建议

建议 Controller 关闭 `WU-TOOLS-01-S4-R1`。

证据：

- S1-S5 已建立 shared Fins runtime、download/preprocess provider、Fins wait adapter 和 Service assembly wiring。
- 本轮 S6 已将默认配置和 workspace overlay 回归收口到 read/download/preprocess 三 provider 目标形态。
- 指定验证覆盖 `tests/fins`、`tests/service/test_host_assembly.py`、`tests/runtime/test_config_loader.py` 与 combined tools acceptance，证明 runtime、provider discovery、wait adapter wiring 和 config loader 目标形态均可用。
- `include_ingestion_tools` 不再是默认配置、workspace overlay 或 README 目标形态。

本 artifact 只给关闭建议；是否更新 residual table 由 Controller 裁决。

## Residual / Blocker

- fixed in current slice: 默认 Fins provider config mixed 形态；workspace overlay 使用旧 ingestion 开关；README 旧目标形态说明；Fins import boundary 未识别 S5 wait adapter 例外。
- assigned to later work unit: 真实 SEC/CN/HK 网络 download adapters；upload ingestion provider；SEC/Fins 与 CN/HK CI pipeline/smoke；未来 NEW CLI download/process wrapper。
- blocker: none。
