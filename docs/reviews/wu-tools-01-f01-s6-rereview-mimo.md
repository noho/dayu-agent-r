# WU-TOOLS-01-F01 Slice S6 Fix Re-Review

## Gate Metadata

- Work unit: `WU-TOOLS-01-F01`
- Slice: `S6 - Config, Docs And Regression Closeout`
- Gate: fix re-review
- Reviewer: mimo
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s6-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-s6-fix-codex.md`
  - `docs/reviews/wu-tools-01-f01-s6-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-s6-code-review-ds.md`
  - `dayu/fins/tools/provider.py`
  - `tests/fins/test_fins_ingestion_tools.py`
  - `tests/fins/test_fins_storage_provider.py`

## 结论

**pass**

两个 accepted findings 均已正确修复，fix 未引入新的 correctness / architecture / test regression。

## 验证命令结果

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py`
  - 结果：`138 passed, 3 warnings`（warnings 来自 edgar 依赖 deprecation）
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

## Accepted Findings 修复状态

### F01-S6-001: read provider 旧 mixed identity → 已修复

**修复内容验证**:

| 检查项 | 预期 | 实际 | 状态 |
|---|---|---|---|
| `provider.py:29` `_PROVIDER_ID` | `"financial-read-tools"` | `"financial-read-tools"` | ✓ |
| `provider.py:31` `_SOURCE_ID` | `"dayu.fins.tools.provider"` | `"dayu.fins.tools.provider"` | ✓ |
| `test_fins_ingestion_tools.py:57` `_READ_PROVIDER_ID` | `"financial-read-tools"` | `"financial-read-tools"` | ✓ |
| `test_fins_storage_provider.py:528` spec_id | `"financial-read-tools"` | `"financial-read-tools"` | ✓ |
| `test_fins_storage_provider.py:530` import_path | `"dayu.fins.tools.provider:discover_tools"` | `"dayu.fins.tools.provider:discover_tools"` | ✓ |
| workspace overlay fixture source_id | `"dayu.fins.tools.provider"` | `"dayu.fins.tools.provider"` | ✓ |

**三组 provider identity 对齐验证**:

| Provider | `_PROVIDER_ID` | `_SOURCE_ID` | spec_id (config key) |
|---|---|---|---|
| read | `financial-read-tools` | `dayu.fins.tools.provider` | `financial-read-tools` |
| download | `financial-download-tools` | `dayu.fins.tools.download_provider` | `financial-download-tools` |
| preprocess | `financial-preprocess-tools` | `dayu.fins.tools.preprocess_provider` | `financial-preprocess-tools` |

三组 provider 的 `provider_id` / `spec_id` / `source_id` 命名约定完全一致，无残留旧 mixed provider identity。

**无旧兼容路径**: diff 中未新增 wrapper、re-export、alias 或兼容 facade。旧 `include_ingestion_tools` 配置字段已从 `_spec()` helper 和 workspace overlay fixture 中移除。

### F01-S6-002: wait_adapter import boundary 路径匹配鲁棒性 → 已修复

**修复内容验证**:

`test_fins_storage_provider.py:70-73` 使用规范化绝对路径比较：

```python
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FINS_WAIT_ADAPTER_PATH = (
    _REPO_ROOT / "dayu" / "fins" / "ingestion" / "wait_adapter.py"
).resolve(strict=False)
```

`_fins_forbidden_import_roots()` (行 633) 使用 `path.resolve(strict=False)` 做规范化后比较：

```python
if path.resolve(strict=False) == _FINS_WAIT_ADAPTER_PATH:
    return _FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS
```

**鲁棒性提升**: 旧实现使用相对 `Path` 字面比较（`Path("dayu/fins/ingestion/wait_adapter.py")`），新实现通过 `Path(__file__).resolve().parents[2]` 定位仓库根目录并构造绝对规范化路径，消除了因工作目录或路径表示差异导致匹配失败的风险。

**例外范围未扩大**: 例外仍只允许 `dayu/fins/ingestion/wait_adapter.py` 导入 `dayu.host`；其余所有 `dayu.fins` 模块仍禁止导入 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。`_FINS_DEFAULT_FORBIDDEN_IMPORT_ROOTS` 与 `_FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS` 的差异仅在于是否包含 `dayu.host`，符合预期。

## 新增 Finding 检查

**未发现新增 findings。**

逐项检查：
- Host/Engine contracts: diff 未修改 `dayu/host/`、`dayu/engine/` 任何文件。
- default config split: `dayu/config/tool_discovery.json` 未变更，三组 disabled provider entries 形态不变。
- workspace overlay 目标形态: 测试 fixture 使用独立三组 provider config，不含 `include_ingestion_tools`。
- README 范围: fix-codex 已说明不更新任何 README，决策合理（变更仅涉及 provider 自报 identity 和测试鲁棒性，不改变配置说明或分层关系）。
- 兼容旧 mixed provider 路径: 无。`include_ingestion_tools` 从 `_spec()` 和 workspace overlay 中移除，`test_read_provider_ignores_legacy_ingestion_switch` 已重写为 `test_read_provider_only_exposes_read_tools`，不再传递旧开关。

## WU-TOOLS-01-S4-R1 关闭建议

**建议关闭。**

证据链完整：
1. S1-S5 已实现 shared `DefaultFinsRuntime`、download/preprocess provider、Fins wait adapter 和 Service assembly wiring。
2. S6 已将默认配置和 workspace overlay 回归收口到 read/download/preprocess 三 provider 目标形态。
3. 本 fix 已清除旧 read provider mixed identity 残留（F01-S6-001），并让 import boundary 例外路径匹配更鲁棒且保持单文件范围（F01-S6-002）。
4. 指定 pytest（138 passed）、pyright（0 errors）和 `git diff --check` 均通过。
5. `include_ingestion_tools` 不再是默认配置、workspace overlay 或 README 目标形态。
6. 三组 provider 的 `provider_id` / `spec_id` / `source_id` 命名约定完全一致。

## 残余风险

- **fixed in current fix gate**: read provider identity/source id 与 split provider target shape 对齐（F01-S6-001）；Fins wait adapter import boundary 例外路径匹配更鲁棒且仍限单文件（F01-S6-002）。
- **assigned to later work unit**: 真实 SEC/CN/HK 网络 download adapters；upload ingestion provider；SEC/Fins 与 CN/HK CI pipeline/smoke；未来 NEW CLI download/process wrapper。
- **non-blocking residual**: none。
- **blocker**: none。
