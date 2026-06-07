# WU-TOOLS-01-F01 Slice S6 Fix Re-Review

## Gate

- Work unit: `WU-TOOLS-01-F01`
- Slice: `S6 - Config, Docs And Regression Closeout`
- Gate: fix re-review (定向复审)
- Artifact: `docs/reviews/wu-tools-01-f01-s6-rereview-ds.md`
- Stance: 只验证 accepted findings 是否修复 + fix 是否引入新问题

## Inputs

- `docs/reviews/wu-tools-01-f01-s6-code-review-controller-adjudication.md`
- `docs/reviews/wu-tools-01-f01-s6-code-review-mimo.md`
- `docs/reviews/wu-tools-01-f01-s6-code-review-ds.md`
- `docs/reviews/wu-tools-01-f01-s6-fix-codex.md`

## 结论

**pass**

两个 accepted findings 均已正确修复，无新增 correctness / architecture / test regression。建议关闭 `WU-TOOLS-01-S4-R1`。

## 验证命令结果

```
$ source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py -q
138 passed, 3 warnings in 1.90s
(warnings 均为 edgar 依赖 deprecation warning)

$ source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

## F01-S6-001 修复验证 — PASS

**要求**: read provider `_PROVIDER_ID` 改为 `"financial-read-tools"`，`_SOURCE_ID` 改为 `"dayu.fins.tools.provider"`；不保留旧兼容 alias/wrapper/re-export；测试和 provider report 与 S6 target shape 一致。

**修复证据**:

| 检查点 | 文件:行号 | 当前值 | 状态 |
|---|---|---|---|
| `_PROVIDER_ID` | `dayu/fins/tools/provider.py:29` | `"financial-read-tools"` | ✓ |
| `_SOURCE_ID` | `dayu/fins/tools/provider.py:31` | `"dayu.fins.tools.provider"` | ✓ |
| 测试 `_READ_PROVIDER_ID` | `tests/fins/test_fins_ingestion_tools.py:57` | `"financial-read-tools"` | ✓ |
| 默认 config spec_id | `dayu/config/tool_discovery.json:3` | `"financial-read-tools"` | ✓ |
| 默认 config source_id | `dayu/config/tool_discovery.json:7` | `"dayu.fins.tools.provider"` | ✓ |

**三元组一致性验证** (provider.py -> config -> tests):

- spec_id = `"financial-read-tools"` = provider_id = `_PROVIDER_ID` ✓
- source_id = `"dayu.fins.tools.provider"` = `_SOURCE_ID` ✓
- download: spec_id = `"financial-download-tools"` = provider_id ✓
- preprocess: spec_id = `"financial-preprocess-tools"` = provider_id ✓

三组 provider 的 spec_id/provier_id 全部对称对齐，消除了修前 read provider 与 download/preprocess 不对称的问题。

**source_refs 独立性**:
- `tests/fins/test_fins_ingestion_tools.py:197` — `assert len({report.source_refs[0].source_id for report in result.provider_reports}) == 3` — 证明三组 provider source_id 各不相同 ✓

**旧名残留检查**:
- 代码范围内搜索 `"financial-tools"`（不含 `-read`、`-download`、`-preprocess` 后缀）—— 仅在文档 `docs/reviews/` 的 review artifact 历史描述中出现，生产代码和测试中不存在 ✓
- 无 wrapper、re-export、alias、兼容 facade ✓

## F01-S6-002 修复验证 — PASS

**要求**: Fins import boundary 对 `wait_adapter.py` 的例外匹配更鲁棒，但仍只限这一个文件。

**修复证据**:

| 检查点 | 文件:行号 | 状态 |
|---|---|---|
| 绝对路径构造 | `tests/fins/test_fins_storage_provider.py:70-73` — `_REPO_ROOT = Path(__file__).resolve().parents[2]` + 拼接后 `.resolve(strict=False)` | ✓ |
| 比较时 resolve | `tests/fins/test_fins_storage_provider.py:633` — `path.resolve(strict=False) == _FINS_WAIT_ADAPTER_PATH` | ✓ |
| 例外仅单文件 | `tests/fins/test_fins_storage_provider.py:633` — 精确路径比较，非包级匹配 | ✓ |
| 例外仍禁止 `dayu.engine`/`dayu.service`/`dayu.ui` | `tests/fins/test_fins_storage_provider.py:75` — `_FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.service", "dayu.ui")` | ✓ |
| 未扩大到整个 `dayu.fins.ingestion` | 路径比较精确匹配 `wait_adapter.py` 这一个文件 | ✓ |

**修复前后对比**:

- 修前: `Path("dayu/fins/ingestion/wait_adapter.py")` — 相对路径，对工作目录敏感
- 修后: `(_REPO_ROOT / "dayu/fins/ingestion/wait_adapter.py").resolve(strict=False)` — 绝对路径 + resolve，与 rglob 返回的路径同样 resolve 后比较

`rglob("*.py")` 返回的路径是相对于当前工作目录的，`path.resolve(strict=False)` 会将其转为绝对路径。两端都 resolve 后比较，消除了路径表示差异（symlink、`..`、相对/绝对）带来的脆弱性。

## 合同与架构边界检查 — PASS

| 检查项 | 结论 |
|---|---|
| Host/Engine contracts 未修改 | ✓ fix 未触及 `dayu/host/`、`dayu/engine/` |
| 默认 config 三组 disabled provider 形态未变 | ✓ `tool_discovery.json` 形态与 S6 implementation 一致 |
| workspace overlay 独立启用目标形态未变 | ✓ overlay 仍启用 read/download/preprocess 三组独立 provider，不含 `include_ingestion_tools` |
| README 范围未变 | ✓ fix 未更新任何 README（判断正确） |
| 无兼容旧 mixed provider 路径 | ✓ 无 `"financial-tools"` 旧名 wrapper |
| Fins import boundary 例外范围未扩大 | ✓ 仍只允许 `wait_adapter.py` 导入 `dayu.host` |
| 反向依赖无泄漏 | ✓ `test_runtime_and_engine_do_not_import_fins` 通过 |

## 新增 findings

无。

## WU-TOOLS-01-S4-R1 关闭建议

**建议关闭。**

S1-S5 已实现 shared `DefaultFinsRuntime`、download/preprocess provider、Fins wait adapter 和 Service assembly wiring。S6 implementation 已完成默认 config split、workspace overlay 回归和 README closeout。本次 fix 清除了 read provider 旧 mixed identity 残留，并加固了 import boundary 测试的路径匹配鲁棒性。

全部验证通过（138 passed, 0 pyright errors）。无 residual blocker。真实 SEC/CN/HK network adapter、upload provider、CI/smoke 等已 deferred 到后续 work unit，不阻塞 `WU-TOOLS-01-S4-R1` 关闭。
