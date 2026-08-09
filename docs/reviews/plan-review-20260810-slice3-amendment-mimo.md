# Re-Review: WU-CLI-DOWNLOAD-01 Slice 3 Plan Amendment

## Review Target

- **Artifact**: `docs/gateflow/wu-cli-download-01-slice3-plan-amendment-20260810-045002.md`
- **Base plan**: `docs/gateflow/wu-cli-download-01-plan-20260809.md`
- **Baseline HEAD**: `5c09609946d7e5628ce8dbc1ea856439668a82a9`
- **Prior review**: `docs/reviews/plan-review-20260810-045643.md`（PASS，3 low findings）
- **DS review**: `docs/reviews/plan-review-20260810-slice3-amendment-ds.md`（PASS，NB-01, NB-02）
- **Reviewer**: AgentMiMo（原 reviewer re-review）
- **Date**: 2026-08-10

## Re-Review Method

1. 重读 amendment 全文，逐项核对 §8 Review adjudication 中 5 项 finding 的修复声称
2. 实际运行 §3.1 和 §6.3 的 AST 命令，验证可复现性与正确性
3. 核验 DS NB1/NB2 裁决是否正确纳入
4. 检查 scope/owner/allowlist 漂移

## 1. MiMo F1：sync→async 联动 — RESOLVED

**原 finding**: `_PipelineDownloadFakeConverter.__call__` 是同步方法，被 `asyncio.to_thread` 调用；迁移为 async 后 filing workflow 需改为 `await`，amendment 未显式说明。

**修复验证**:

amendment §3.3 现在明确写出 production 从：
```python
await asyncio.to_thread(convert_pdf_to_docling_json, pdf_bytes, pdf_filename)
```
改为：
```python
docling_json_bytes = await docling_conversion_runner.convert_pdf_to_docling_json(
    pdf_bytes, pdf_filename, cancellation_checker=conversion_cancellation_checker,
)
```

§5.2 第 1 点明确"当前 `_PipelineDownloadFakeConverter.__call__` 是由 production `asyncio.to_thread(sync_callable)` 调用的同步方法；把它迁为实现 `CnDoclingConversionRunner` 的 typed deterministic fake runner，删除同步 `__call__`"。

§6.3 增加了 AST gate 验证 filing workflow 中 `await runner.convert_pdf_to_docling_json(...)` 存在且 `asyncio.to_thread(convert_pdf...)` 不存在。

**AST 实际运行验证**:

```
$ python §6.3 filing workflow AST scan (pre-implementation):
runner_awaits=0 to_thread_conversion=1 (line 331)
```

pre-implementation 状态正确：当前无 runner await，有 1 处 to_thread。implementation 后该 gate 应变为 `runner_awaits=1 to_thread_conversion=0`。

**结论**: **RESOLVED**。sync→async 联动已显式说明，AST gate 可执行。

## 2. MiMo F2：行号偏移 — RESOLVED

**原 finding**: amendment §3.2 声称 4 处 old callable 在行 332, 398, 450, 523，实际为 335, 401, 453, 526。

**修复验证**:

amendment §3.2 现在改用函数名定位："CN sync、HK sync、CN stream、non-explicit start 四个 download tests"，§3.3 和 §5.2 同样以函数名为主定位："以测试函数和 constructor keyword 定位，不绑定易漂移行号"。

**AST 实际运行验证**:

§3.1 AST 扫描输出：
```
CONSTRUCTOR tests/fins/test_cn_pipeline.py:332 test_download_runs_cn_workflow_with_injected_discovery_client ['workspace_root', 'cn_discovery_client', 'convert_pdf_to_docling_json']
CONSTRUCTOR tests/fins/test_cn_pipeline.py:398 test_download_runs_hk_workflow_with_injected_discovery_client ['workspace_root', 'hk_discovery_client', 'convert_pdf_to_docling_json']
CONSTRUCTOR tests/fins/test_cn_pipeline.py:450 test_download_stream_runs_cn_workflow_with_injected_discovery_client ['workspace_root', 'cn_discovery_client', 'convert_pdf_to_docling_json']
CONSTRUCTOR tests/fins/test_cn_pipeline.py:523 test_download_non_explicit_nonempty_start_keeps_default_business_limit ['workspace_root', 'cn_discovery_client', 'convert_pdf_to_docling_json']
```

AST 输出的行号（332, 398, 450, 523）与 amendment §3.2 表格一致。之前 re-review 发现的 +3 偏移来自 `rg` 匹配位置与 AST `node.lineno` 的差异（rg 匹配的是 `CnPipeline(` 字符串位置，AST 报告的是 Call 节点起始行）。amendment 现在以函数名为主定位，消除了行号漂移风险。

四个函数名全部正确：
- `test_download_runs_cn_workflow_with_injected_discovery_client` ✓
- `test_download_runs_hk_workflow_with_injected_discovery_client` ✓
- `test_download_stream_runs_cn_workflow_with_injected_discovery_client` ✓
- `test_download_non_explicit_nonempty_start_keeps_default_business_limit` ✓

**结论**: **RESOLVED**。函数名定位稳定，AST 命令可复现。

## 3. MiMo F3：AST 命令可复现 — RESOLVED

**原 finding**: §3.1 列出 `rg` 命令但未列出 AST 扫描的具体命令。

**修复验证**:

§3.1 现在包含完整的可执行 Python AST 扫描脚本（约 50 行），可直接 `python - <<'PY' ... PY` 运行。

§6.3 包含两个 implementation-time AST gate：
1. constructor scan（验证 16 处构造、无 legacy injection keyword）
2. filing workflow scan（验证 runner await 存在、to_thread 不存在）

**AST 实际运行验证**:

§3.1 读只读扫描：成功运行，输出所有 CONSTRUCTOR、OLD_INJECTION、EVENT_ASSERT 条目，与 `rg` 结果一致。

§6.3 constructor gate（pre-implementation）：
```
VIOLATIONS:
  dayu/fins/pipelines/cn_download_workflow.py:250: legacy conversion injection keyword
  tests/fins/test_cn_download_runtime.py:1004: legacy conversion injection keyword
  tests/fins/test_cn_download_runtime.py:284: legacy conversion injection keyword
  tests/fins/test_cn_download_workflow.py:731: legacy conversion injection keyword
  tests/fins/test_cn_download_workflow.py:883: legacy conversion injection keyword
  tests/fins/test_cn_download_workflow.py:2121: legacy conversion injection keyword
  tests/fins/test_cn_pipeline.py:332: legacy conversion injection keyword
  tests/fins/test_cn_pipeline.py:398: legacy conversion injection keyword
  tests/fins/test_cn_pipeline.py:450: legacy conversion injection keyword
  tests/fins/test_cn_pipeline.py:523: legacy conversion injection keyword
```

pre-implementation 正确检测到 10 处 legacy injection（7 处 test + 3 处 production workflow pass-through），16 处构造。implementation 后应为 0 violations。

注：AST gate 额外检测到 `cn_download_workflow.py:250` 的 production workflow pass-through（`convert_pdf_to_docling_json=host.convert_pdf_to_docling_json`），这不在 amendment §3.3 的 test injection 表中，但在基础计划 Slice 3 的 `cn_download_workflow.py` production allowlist 内。该 pass-through 随 filing workflow 签名变更自然迁移，AST gate 正确覆盖。

**结论**: **RESOLVED**。AST 命令完整可复现，pre/post-implementation 行为正确。

## 4. DS NB1：CONVERSION_COMPLETED production 精确插入位置 — RESOLVED

**原 finding**: amendment §5.2(3) 仅描述测试端事件序列变更，未引用 production 端插入位置。

**修复验证**:

amendment §3.4 现在交叉引用基础计划 §5.5，明确写出：
> child output -> close -> size/digest validation -> cancel checkpoint -> CONVERSION_COMPLETED -> cancel checkpoint -> PUBLICATION_ELIGIBLE -> publication batch

并说明："completion 既不能表示'child 已启动/已退出但未验证'，也不能直接授予 publication 资格；completed 后到 publication 前的 checkpoint 是取消时无半发布的 owner contract。"

**结论**: **RESOLVED**。production 精确顺序已明确，双 checkpoint 语义清晰。

## 5. DS NB2：_RecordingPipeline 子类 checklist — RESOLVED

**原 finding**: `_RecordingPipeline` 子类未具名列入 amendment checklist。

**修复验证**:

- §3.2 表格：具名 `tests/fins/test_cn_download_runtime.py` 的 `_RecordingPipeline.__init__` 与 `_build_runtime_with_cn_hk_adapters`
- §3.3 表格：具名同一文件，标注"已允许，迁为 typed deterministic runner，并纳入 constructor checklist"
- §5.2 末段：显式说明"原已允许的 `tests/fins/test_cn_download_runtime.py::_RecordingPipeline` 子类也必须纳入 constructor migration/checklist"

**AST 实际运行验证**:

```
CONSTRUCTOR tests/fins/test_cn_download_runtime.py:284 __init__ ['workspace_root', 'cn_discovery_client', 'convert_pdf_to_docling_json']
OLD_INJECTION tests/fins/test_cn_download_runtime.py:284 __init__
```

`_RecordingPipeline.__init__` 的 `super().__init__` 正确被 AST 检测为构造调用，且 `convert_pdf_to_docling_json` keyword 被标记为 OLD_INJECTION。

**结论**: **RESOLVED**。_RecordingPipeline 已具名纳入三处 checklist。

## 6. Scope / Owner / Allowlist 漂移检查

| 检查项 | 结果 |
|---|---|
| Production allowlist 新增 | 无。§5.3 明确"基础计划列出的全部 production allowlist 原样保持" |
| Test allowlist 新增 | 仅 `tests/fins/test_cn_pipeline.py`。§5.1 |
| Semantic owner 变更 | 无。§4.1 与基础计划一致 |
| Runtime helper 修改 | 无。§5.3 明确禁止 |
| Upload 测试修改 | 无。§5.2(4) 明确禁止 |
| Base plan 修改 | 无。§5.3 明确禁止 |
| Goal drift | 无。amendment 唯一目标是扩大 test allowlist |

**结论**: **无漂移**。scope、owner、allowlist 全部稳定。

## 7. §6.3 Implementation-Time AST Gate 完整性

§6.3 列出 10 项静态证据要求。逐项可执行性检查：

| # | 要求 | 可执行命令 | 验证 |
|---|---|---|---|
| 1 | CnPipeline 构造穷举 + 无 legacy keyword | §6.3 Python AST gate | ✅ 已运行，16 构造 / 10 violations (pre-impl) |
| 2 | `convert_pdf_to_docling_json` 只允许 Protocol/runner/workflow | `rg` | ✅ 命令明确 |
| 3 | production 无 `asyncio.to_thread(convert_pdf...)` | §6.3 filing workflow AST gate | ✅ 已运行，pre-impl 检测到 1 处 |
| 4 | `ProcessCnDoclingConversionRunner` 调用 `start()` | AST | ✅ 命令明确 |
| 5 | runtime helper 未修改 | `git diff --exit-code` | ✅ 命令明确 |
| 6 | 事件顺序双断言 | 测试运行 | ✅ 命令明确 |
| 7 | completed-after-cancel owner test | 测试运行 | ✅ 命令明确 |
| 8 | upload event tests 未误改 | §3.1 AST EVENT_ASSERT 输出 | ✅ 已验证 upload 使用独立 enum |
| 9 | 无 compat shim / hasattr / sleep | `rg` | ✅ 命令明确 |
| 10 | 无 contact/absolute path leak | `rg` | ✅ 命令明确 |

**结论**: 10 项 AST/static gate 全部可执行。

## Findings

无新 finding。

## Final Conclusion: **PASS**

逐项确认：

| 项目 | 状态 |
|---|---|
| MiMo F1 (sync→async) | ✅ RESOLVED |
| MiMo F2 (行号偏移) | ✅ RESOLVED |
| MiMo F3 (AST 命令) | ✅ RESOLVED |
| DS NB1 (CONVERSION_COMPLETED 位置) | ✅ RESOLVED |
| DS NB2 (_RecordingPipeline checklist) | ✅ RESOLVED |
| Scope/owner/allowlist 漂移 | ✅ 无漂移 |
| AST gate 可执行性 | ✅ 10/10 可执行 |
| 新 finding | 无 |

amendment 已正确修复全部 5 项 low finding，无未闭合项。下一合法动作是等待 DS re-review 确认，两路均 accepted 后进入 Slice 3 implementation。
