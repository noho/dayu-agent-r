# WU-TOOLS-01-F01 Slice S6 Fix

## Gate

- Work unit: `WU-TOOLS-01-F01`
- Slice: `S6 - Config, Docs And Regression Closeout`
- Gate: fix
- Artifact: `docs/reviews/wu-tools-01-f01-s6-fix-codex.md`
- Fix inputs:
  - `docs/reviews/wu-tools-01-f01-s6-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-s6-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s6-code-review-ds.md`
  - `docs/reviews/wu-tools-01-f01-s6-implementation-codex.md`
- Commit / push: not performed by user instruction

## Accepted Findings 修复

### F01-S6-001: read provider 仍保留旧 mixed identity

状态：已修复。

修复：

- `dayu/fins/tools/provider.py`
  - `_PROVIDER_ID` 从 `financial-tools` 改为 `financial-read-tools`。
  - `_SOURCE_ID` 从 `dayu.fins.tools` 改为 `dayu.fins.tools.provider`。
  - 未新增旧名 wrapper、re-export、alias 或兼容 facade。
- `tests/fins/test_fins_ingestion_tools.py`
  - `_READ_PROVIDER_ID` 同步为 `financial-read-tools`。
  - 现有 split provider discovery 与 workspace overlay 回归继续断言 read/download/preprocess 三组 provider report id、spec id、source id 和工具名独立一致。

结果：read/download/preprocess 三组 provider 的 config spec id、provider report id 与 source id 均对齐 S6 target shape。

### F01-S6-002: wait_adapter import boundary 例外路径匹配脆弱

状态：已修复。

修复：

- `tests/fins/test_fins_storage_provider.py`
  - 用 `Path(__file__).resolve().parents[2]` 定位仓库根目录，构造并缓存 `dayu/fins/ingestion/wait_adapter.py` 的规范化绝对路径。
  - `_fins_forbidden_import_roots(path)` 改为比较 `path.resolve(strict=False)` 与该规范化绝对路径。
  - 例外仍只允许这一个文件导入 Host wait/api contract；其它 `dayu.fins` 模块仍禁止导入 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。
  - 例外没有扩大到整个 `dayu.fins.ingestion` 包。

## 改动文件

- `dayu/fins/tools/provider.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_storage_provider.py`
- `docs/reviews/wu-tools-01-f01-s6-fix-codex.md`

本 fix 没有修改 Host/Engine contracts，没有恢复 CLI/UI，没有实现真实网络 adapter，没有扩大 README cleanup。

## README 同步决策

- `dayu/config/README.md`：不更新。S6 implementation 已记录默认 split provider entries；本 fix 只修 read provider 自报 identity，与 README 当前配置说明一致。
- `dayu/fins/README.md`：不更新。README 已描述 read/download/preprocess provider split；没有旧 `financial-tools` 目标形态需要清理。
- `tests/README.md`：不更新。测试分层说明不依赖 provider report id 具体值。
- 根 `README.md`：不更新。当前仍无 `dayu/cli` package，本 fix 不宣称 CLI download/process。
- `dayu/README.md`：不更新。本 fix 未改变稳定分层关系或装配边界。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py`
  - 结果：`138 passed, 3 warnings`
  - warnings 均为 `edgar` 依赖 deprecation warning。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

## WU-TOOLS-01-S4-R1 关闭建议

仍建议 Controller 关闭 `WU-TOOLS-01-S4-R1`。

证据：

- S1-S5 已实现 shared Fins runtime、download/preprocess providers、Fins wait adapter 和 Service assembly wiring。
- S6 implementation 已完成默认 config、workspace overlay、README 和 regression closeout。
- 本 fix 已清除旧 read provider mixed identity 残留，并让 import boundary 例外更鲁棒且保持单文件范围。
- 指定 pytest、pyright 和 `git diff --check` 均通过。

是否更新 residual table 仍由 Controller 裁决。

## Residual / Blocker

- fixed in current fix gate:
  - `F01-S6-001`: read provider identity/source id 与 split provider target shape 对齐。
  - `F01-S6-002`: Fins wait adapter import boundary 例外路径匹配更鲁棒且仍限单文件。
- assigned to later work unit:
  - 真实 SEC/CN/HK 网络 download adapters。
  - upload ingestion provider。
  - SEC/Fins 与 CN/HK CI pipeline/smoke。
  - 未来 NEW CLI download/process wrapper。
- blocker: none。
