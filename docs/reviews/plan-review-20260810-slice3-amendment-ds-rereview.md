# Plan Re-Review: WU-CLI-DOWNLOAD-01 Slice 3 Standalone Amendment

- **Review target**: `docs/gateflow/wu-cli-download-01-slice3-plan-amendment-20260810-045002.md`（修订版，含 review adjudication §8）
- **Original DS review**: `docs/reviews/plan-review-20260810-slice3-amendment-ds.md`（PASS，NB-01 + NB-02）
- **Original MiMo review**: `docs/reviews/plan-review-20260810-045643.md`（PASS，F1 + F2 + F3）
- **Baseline HEAD**: `5c09609946d7e5628ce8dbc1ea856439668a82a9`
- **Branch**: `codex/download-oracle`
- **Review type**: 原 reviewer re-review——逐项闭合 DS NB1/NB2 与 MiMo F1/F2/F3，确认修订无新 finding
- **Reviewer**: AgentDS（原 reviewer）
- **Timestamp**: 2026-08-10 05:10 UTC

---

## 1. Re-Review Method

1. 重读修订后 amendment 全文，定位 §8 review adjudication 中每项 finding 的修复位置。
2. 对每项 finding 独立核验修复是否成立：读对应 amendment 段落 + 运行 AST/`rg` 命令 + 读源码对照。
3. 压测 scope/owner/allowlist 漂移。
4. 判定每项 finding 闭合状态，输出最终 PASS/FAIL。

---

## 2. Finding-by-Finding Closure Verification

### 2.1 DS NB-01：`CONVERSION_COMPLETED` production 精确插入位置未重申

**原 finding**：amendment §5.2(3) 仅描述测试端事件序列变更，未引用 production 端 `CONVERSION_COMPLETED` 在 `cn_download_filing_workflow.py` 中的精确插入位置（conversion 成功后、commit 前）。

**Amendment 修复位置**：§3.4（新增段落）

**修复内容**：
> 交叉引用基础计划 §5.5：production single-filing owner 只有在 child 正常返回、handle close、child output size/digest 验证以及 conversion-completion cancel checkpoint 全部通过后，才可发出 `CONVERSION_COMPLETED`；事件发出后、取得 `PUBLICATION_ELIGIBLE` 前必须再执行 cancel checkpoint。精确顺序为：
> `child output -> close -> size/digest validation -> cancel checkpoint -> CONVERSION_COMPLETED -> cancel checkpoint -> PUBLICATION_ELIGIBLE -> publication batch`。

**直接核验**：

- 源码 `cn_download_filing_workflow.py:331-409`：当前 conversion 成功（line 331-335）→ cancel checkpoint（line 356）→ fingerprint（line 364-367）→ cancel checkpoint（line 368）→ commit batch（line 369-391）→ FILING_COMPLETED（line 404-409）。正确识别了插入窗口：两个 cancel checkpoint 之间（conversion 后验证 checkpoint 与 publication 前 checkpoint）。
- 基础计划 §5.5 定义了完整状态顺序 `PDF_READY -> CONVERSION_STARTED -> CONVERSION_COMPLETED -> PUBLICATION_ELIGIBLE`。
- 修订版明确定义了双 checkpoint 语义：(1) child output 验证通过后的 cancel checkpoint → CONVERSION_COMPLETED；(2) CONVERSION_COMPLETED 后 → cancel checkpoint → publication eligibility。这确保 completed 不能绕过取消直接进入 publication。

**闭合判定**：**已修复。** production 插入位置与双 checkpoint 顺序现在在 amendment 内自足说明，不依赖 implementation agent 自行推导。

---

### 2.2 DS NB-02：`_RecordingPipeline` 子类未具名列入 checklist

**原 finding**：amendment §3.2 提到"1 个子类"但未具名，§5.2 精确变更列表只覆盖 `test_cn_pipeline.py`。

**Amendment 修复位置**：§3.2（表格修订）、§3.3（表格修订）、§5.2（新增末尾段落）

**修复内容**：
- §3.2 表格：`tests/fins/test_cn_download_runtime.py` 的 `_RecordingPipeline.__init__` 与 `_build_runtime_with_cn_hk_adapters`，明确标注"已在原 Slice 3 allowlist，必须迁为 typed deterministic runner"
- §3.3 表格：`_RecordingPipeline.__init__` 单独列出，明确标注"已允许"，处理为"迁为 typed deterministic runner，并纳入 constructor checklist"
- §5.2 末尾段落："原已允许的 `tests/fins/test_cn_download_runtime.py::_RecordingPipeline` 子类也必须纳入 constructor migration/checklist：其 `super().__init__` 删除旧 `convert_pdf_to_docling_json=_RuntimeFakeConverter()`，改为 typed deterministic runner 注入。这是原 Slice 3 allowlist 内的既有工作，不新增 amendment allowlist。"

**直接核验**：

- AST 扫描确认：`CONSTRUCTOR tests/fins/test_cn_download_runtime.py:284 __init__ ['workspace_root', 'cn_discovery_client', 'convert_pdf_to_docling_json']` + `OLD_INJECTION tests/fins/test_cn_download_runtime.py:284 __init__`
- `rg` 确认唯一子类：`tests/fins/test_cn_download_runtime.py:268:class _RecordingPipeline(CnPipeline):`
- 修订版正确区分了"amendment 新增 allowlist"（`test_cn_pipeline.py`）与"原 allowlist 内既需 migration"（`_RecordingPipeline`），不造成 scope 混淆。

**闭合判定**：**已修复。** `_RecordingPipeline` 已具名，migration 路径明确，ownership 边界清晰（原 allowlist 内工作，不扩大 amendment scope）。

---

### 2.3 MiMo F1：同步 fake 到 async runner 的 production 联动未显式说明

**原 finding**：test fake 从同步 `__call__` 改为 async method 后，production 端如何联动消费未显式说明。

**Amendment 修复位置**：§3.3（新增代码示例）、§5.2(1)（fake 迁移说明）、§6.3（AST gate）

**修复内容**：

§3.3 明示 production 改动：
```python
# 当前（将被替换）
await asyncio.to_thread(convert_pdf_to_docling_json, pdf_bytes, pdf_filename)

# 改为
docling_json_bytes = await docling_conversion_runner.convert_pdf_to_docling_json(
    pdf_bytes,
    pdf_filename,
    cancellation_checker=conversion_cancellation_checker,
)
```

§5.2(1) 明示 test fake 改动：删除同步 `__call__`，改为 `async convert_pdf_to_docling_json(pdf_bytes, stream_name, *, cancellation_checker)`。两个签名（production runner method 与 test fake method）完全一致。

§6.3 AST gate 验证：
- runner_awaits == 1（production 有且仅有一处 typed runner await）
- to_thread_conversions == 0（production 无残留同步线程调用）

**直接核验**：

- 实际运行 §6.3 AST gate（预实现状态）：`runner_awaits=0 to_thread_conversions=1`——正确检测到当前旧状态
- 修复后，该 gate 要求 `runner_awaits=1 to_thread_conversions=0`——正确验证 production 联动
- test fake 签名 `async convert_pdf_to_docling_json(pdf_bytes, stream_name, *, cancellation_checker)` 与 production Protocol method 完全一致——不依赖隐式类型转换

**闭合判定**：**已修复。** sync→async 的 production-test 联动现在双向显式说明，且有 AST gate 可自动验证。

---

### 2.4 MiMo F2：四处 `test_cn_pipeline.py` 行号偏移且易漂移

**原 finding**：原 amendment 以行号（`:332-335` 等）定位 constructor injection，代码变更后行号必然漂移。

**Amendment 修复位置**：§3.2、§3.3、§5.2（全部改用函数名 + constructor keyword 定位）

**修复内容**：
- §3.2 表格：`test_cn_pipeline.py` 的 "CN sync、HK sync、CN stream、non-explicit start 四个 download tests"
- §3.3 表格：四个完整测试函数名（`test_download_runs_cn_workflow_with_injected_discovery_client` 等）
- §5.2(2)：四个测试函数名，并注明"以测试函数和 constructor keyword 定位，不绑定易漂移行号"
- §6.3：AST scan 自动按 keyword 重定位，不依赖行号

**直接核验**：

AST 扫描确认四个测试函数及其旧 injection：
```
OLD_INJECTION tests/fins/test_cn_pipeline.py:332 test_download_runs_cn_workflow_with_injected_discovery_client
OLD_INJECTION tests/fins/test_cn_pipeline.py:398 test_download_runs_hk_workflow_with_injected_discovery_client
OLD_INJECTION tests/fins/test_cn_pipeline.py:450 test_download_stream_runs_cn_workflow_with_injected_discovery_client
OLD_INJECTION tests/fins/test_cn_pipeline.py:523 test_download_non_explicit_nonempty_start_keeps_default_business_limit
```

四个函数名与 keyword 精确匹配，行号仅作参考。

**闭合判定**：**已修复。** 定位方式从脆弱行号改为函数名 + constructor keyword + AST 重定位。

---

### 2.5 MiMo F3：已执行 AST 扫描缺少可复现命令

**原 finding**：原 amendment 声称已执行 AST 扫描但未提供可复现命令。

**Amendment 修复位置**：§3.1（完整可执行 AST 命令）、§6.3（implementation-time AST gate）

**修复内容**：
- §3.1：已执行的 discovery AST scan 提供完整 `python - <<'PY' ... PY` 可执行命令
- §6.3：implementation-time 提供两组 AST gate：
  1. Constructor scan：验证 16 个 constructor 且零 `convert_pdf_to_docling_json` keyword
  2. Typed runner await scan：验证 1 个 `await runner.convert_pdf_to_docling_json(...)` 且零 `asyncio.to_thread(convert_pdf...)`

**直接核验**：

两个 AST 命令均已实际运行：
- §3.1 discovery scan → 输出与预期一致（16 constructors, 10 old injections, 正确区分 download/upload events）
- §6.3 constructor gate → 预实现状态正确检测到 10 violations + 16 constructors
- §6.3 runner await gate → 预实现状态正确检测到 `runner_awaits=0 to_thread_conversions=1`

**闭合判定**：**已修复。** AST 扫描现可完整复现，implementation agent 可独立运行验证。

---

## 3. Scope / Owner / Allowlist Drift Check

| 检查项 | 原 amendment | 修订版 | 漂移？ |
|---|---|---|---|
| 新增 test allowlist | `tests/fins/test_cn_pipeline.py` | 不变 | 无 |
| 新增 production files | 无 | 不变 | 无 |
| 新增 runtime helper 修改 | 禁止 | 不变 | 无 |
| semantic owner 定义 | §4.1 六个 owner | 不变 | 无 |
| conversion dependency owner | `cn_download_protocols.py` | 不变 | 无 |
| event sequence owner | `cn_download_filing_workflow.py` + `download_events.py` | 不变 | 无 |
| facade contract owner | `cn_pipeline.py` | 不变 | 无 |
| upload contract 误改风险 | §5.2(4) 明确禁止 | §3.4 增加交叉验证（upload events 用独立 enum） | 无 |
| SEC download 误改风险 | §3.4 已区分 | 不变 | 无 |
| `_RecordingPipeline` scope | 未具名 | 已具名，明确为原 allowlist 内迁移，不扩大 amendment | 无 |

**结论：零漂移。** 修订版仅在原 scope 内增加澄清与可执行命令，未扩大 production scope、test allowlist 或 owner boundary。

---

## 4. AST Gate Executability Verification

两组 AST gate 均已在当前 HEAD (`5c096099`) 上实际运行验证：

### Gate 1: Constructor scan (§6.3)

```
预实现输出：10 legacy injection violations + 16 constructors
实现后期望：0 violations + 16 constructors
```

10 个 violations 精确覆盖：
- Production：`cn_download_workflow.py:250`（1 处）
- Test（原 allowlist）：`test_cn_download_runtime.py:284,1004`（2 处）+ `test_cn_download_workflow.py:731,883,2121`（3 处）= 5 处
- Test（amendment 新增）：`test_cn_pipeline.py:332,398,450,523`（4 处）= 4 处

总计 10 处，与 amendment claims 一致。

### Gate 2: Typed runner await scan (§6.3)

```
预实现输出：runner_awaits=0 to_thread_conversions=1
实现后期望：runner_awaits=1 to_thread_conversions=0
```

to_thread_conversion 定位在 `cn_download_filing_workflow.py:331-335`（当前唯一 `asyncio.to_thread(convert_pdf_to_docling_json, ...)` 调用），为基础计划 Slice 3 production 修改目标。

**结论：两组 AST gate 均可执行、可复现、有明确的 pass/fail 标准。**

---

## 5. Final Re-Review Conclusion: **PASS**

逐项闭合状态：

| Finding | 原状态 | 修复位置 | 核验方式 | 闭合 |
|---|---|---|---|---|
| DS NB-01 | low, non-blocking | §3.4 交叉引用 + 双 checkpoint 顺序 | 源码对照 + amendment 文本 | ✓ 已闭合 |
| DS NB-02 | low, non-blocking | §3.2, §3.3, §5.2 具名 + migration 说明 | AST + rg + amendment 文本 | ✓ 已闭合 |
| MiMo F1 | low, accepted | §3.3 代码示例 + §5.2(1) + §6.3 AST gate | AST gate 实际运行 | ✓ 已闭合 |
| MiMo F2 | low, accepted | §3.2, §3.3, §5.2 改用函数名 + keyword | AST scan 实际运行 | ✓ 已闭合 |
| MiMo F3 | low, accepted | §3.1 可执行命令 + §6.3 AST gate | 两组命令实际运行 | ✓ 已闭合 |

**五项 finding 全部闭合。无新 finding。**

修订版 amendment 在以下方面比原版更强：
1. production-test sync→async 联动现可 AST 自动验证
2. 函数级定位消除行号漂移风险
3. CONVERSION_COMPLETED 双 checkpoint 顺序精确到 production 插入点
4. `_RecordingPipeline` 具名纳入 checklist 且不扩大 scope
5. 全部 AST 命令可复现、可独立运行

**下一合法动作**：等待 MiMo 原 reviewer re-review 也确认 PASS，然后进入 Slice 3 implementation。
