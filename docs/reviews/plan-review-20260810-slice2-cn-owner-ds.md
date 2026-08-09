# wu-cli-download-01 Slice 2 Stop-Condition Amendment — 独立 Adversarial Plan Review

## 审查元数据

| 项 | 值 |
|---|---|
| 审查类型 | 独立 adversarial plan review（第三路，聚焦五条裁决问题） |
| 审查目标 | `docs/gateflow/wu-cli-download-01-slice2-plan-amendment-20260810-030216.md` |
| 基线 HEAD | `c6829400a5e37892464a614590062511554f9633` |
| Branch | `codex/download-oracle` |
| Work unit | `wu-cli-download-01` |
| 审查日期 | 2026-08-10 |
| 输入材料 | amendment、accepted base plan、4 份 prior plan review、直接源码核验 |
| 产品/测试修改 | 无 |
| 提交 | 无 |

## 审查方法

逐条对 amendment 的五个裁决问题进行第一性原理核验：先读 amendment 的 claim，再直接读 `codex/download-oracle` 分支上的 Slice 2 源码确认当前实际状态，最后判定 amendment 的 owner decision 是否与代码事实一致、是否最小直接、是否存在遗漏风险。

---

## 裁决问题 1：`cn_download_filing_workflow` 是否确为 PDF/Docling document-local failure owner？

### Amendment claim

§3.2 与 §6.3 主张 `cn_download_filing_workflow.py` 是 document-local failure 的真实异常 owner，应定义唯一的 `project_cn_filing_failure` 公开 helper；父 workflow 直接导入复用。

### 直接代码证据

**PDF catch（`cn_download_filing_workflow.py:184-212`）**：
```python
except Exception as exc:
    yield DownloadEvent(FILE_FAILED, ..., reason_message=str(exc))   # line 194
    failed = _build_filing_result(..., reason_code="pdf_download_failed",
                                  reason_message=str(exc))            # line 202
    yield DownloadEvent(FILING_FAILED, ...)
    return
```

**Docling catch（`cn_download_filing_workflow.py:316-332`）**：
```python
except Exception as exc:
    failed = _build_filing_result(..., reason_code="docling_convert_failed",
                                  reason_message=str(exc))            # line 322
    yield DownloadEvent(FILING_FAILED, ...)
    return
```

**父 workflow per-candidate leak catch（`cn_download_workflow.py:286-305`）**：
```python
except Exception as exc:
    reason_code, reason_message = _candidate_failure_facts(exc)      # line 287
    failed_item = _build_candidate_failed_result(...)
    ...
    yield DownloadEvent(FILING_FAILED, ...)
```

### 裁决

**确认成立。** `cn_download_filing_workflow.py` 确实是 PDF/Docling document-local failure 的产生 owner——两处 `except Exception`（line 184 与 line 316）在当前 Slice 2 代码中直接写 `str(exc)` 到 `reason_message`，而父 workflow 的 `_candidate_failure_facts`（line 535-552）反而拥有正确的封闭映射。amendment 将 mapping 归还到 child module 是语义所有权纠正。

**但有一个结构性 nuance**：父 workflow 的 leak catch（line 286）捕获的是**逸出子 workflow generator 的异常**——这些异常理论上不应在正常 document-local failure 路径触发（因为 child 的 PDF/Docling catch 已经 return）。父 leak catch 是防御性边界。amendment 让父直接导入 child 的公开 helper 来处理这个边界，依赖方向是 parent→child，与现有的 `from cn_download_filing_workflow import run_cn_download_single_filing_stream` 一致，不引入反向依赖。

---

## 裁决问题 2：`project_cn_filing_failure(Exception)->tuple[str,str]` 是否最小、直接、唯一 source of truth？

### Amendment claim

§6.3 主张在 `cn_download_filing_workflow.py` 新增一个公开函数 `project_cn_filing_failure(error: Exception) -> tuple[str, str]`，封闭映射为 `FinsDownloadProviderError -> (f"provider_{category}", safe_message)`、`OSError -> ("storage_failed", "下载产物读写失败")`、其它 → `("filing_execution_failed", "财报文档执行失败")`。父 workflow 删除自己的 `_candidate_failure_facts` 并直接导入同一函数。

### 直接代码证据

当前 `_candidate_failure_facts`（`cn_download_workflow.py:535-552`）已经实现了精确相同的三段映射：

```python
def _candidate_failure_facts(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, FinsDownloadProviderError):
        return f"provider_{exc.transport_category.value}", exc.safe_message
    if isinstance(exc, OSError):
        return "storage_failed", "下载产物读写失败"
    return "filing_execution_failed", "财报文档执行失败"
```

amendment 的 `project_cn_filing_failure` 在逻辑上与 `_candidate_failure_facts` **完全相同**。区别仅在于：
- **位置**：从父模块移到子模块
- **可见性**：从 `_private` 改为公开
- **调用方**：child 内部 PDF/Docling catch **新增调用**；父 leak catch **改为导入调用**

### 裁决

**确认是最小、直接、唯一 source of truth。**

- **最小**：单一函数，返回 plain `tuple[str, str]`，不引入 dataclass、callback、facade、新 schema。amendment §6.3 明确拒绝 wrapper 和 duplicate mapper。
- **直接**：在 child module 的异常 catch 处直接调用；父 workflow leak catch 通过公开导入直接调用同一函数。
- **唯一**：amendment 要求 rg/AST 证明 `project_cn_filing_failure` 只有一处定义，`_candidate_failure_facts` 被删除。§9 static scan 明确验证这一点。

**一个实现注意点**：`project_cn_filing_failure` 与 `_candidate_failure_facts` 逻辑等价意味着实现 agent 实际上是在做"move + rename + add child call sites"。amendment 正确地将此描述为 ownership 纠正而非新功能，但 implementation agent 需要理解：这不是从零创建新逻辑，而是把已有正确逻辑迁到正确的 owner 位置。

---

## 裁决问题 3：子 workflow 两处 catch 与父 workflow leak catch 的复用边界、取消语义和 operation/document blast radius 是否精确？

### Amendment claim

- Child PDF catch 调用 helper 一次，同时用于 `FILE_FAILED` 和 `FILING_FAILED`。
- Child Docling catch 调用同一 helper 用于 `FILING_FAILED`。
- 父 leak catch 直接导入同一 helper 处理逸出子 generator 的异常。
- `CnDownloadCancelledError` 在三处均显式排除（child line 182/314 显式 re-raise，父 line 282 单独 catch）。
- Operation-terminal 异常（rebuild/company/discovery/cancel-check）全部 propagate 到 runtime，不进入 document row。

### 直接代码证据

**取消语义**：

- `_is_cancel_requested`（`cn_download_workflow.py:360-376`）已在 Slice 2 中简化为直接调用 `cancel_checker()` 并返回 bool——无 wrapping、无字符串包装。任何来自 `cancel_checker()` 的 `FinsDownloadProviderError` 或 `OSError` 原样传播。
- Child 的 `CnDownloadCancelledError` 在 PDF catch（line 182）和 Docling catch（line 314）均显式 `raise`（不进入 catch 块），随后由父的 `except CnDownloadCancelledError`（line 282）单独处理为 cancelled 状态。

**Blast radius**：

- PDF 失败：仅当前 filing → `FILE_FAILED` + `FILING_FAILED` → `return`，后续 candidate 继续。
- Docling 失败：仅当前 filing → `FILING_FAILED` → `return`，后续 candidate 继续。
- 父 leak catch：仅当前 filing → `FILING_FAILED` → `continue`（append to filings），后续 candidate 继续。
- Operation 级异常：propagate 到 `ingestion_runtime.py` 的 `_download_public_failure_from_exception` → typed public failure。

**复用边界**：

- `project_cn_filing_failure` 定义在 child module，child 内部两处 catch 直接调用。
- 父 workflow 通过 `from cn_download_filing_workflow import project_cn_filing_failure` 导入——这与现有的 `from cn_download_filing_workflow import run_cn_download_single_filing_stream`（line 18-20）模式一致。
- 无 forwarding wrapper、无 private cross-module import、无第二份 `isinstance` 映射。

### 裁决

**确认精确。** 三处 catch 的边界、取消语义和 blast radius 均清晰且无交叉：

- 取消（`CnDownloadCancelledError`）在三处均保持 cancelled 语义，不进入失败行。
- Document-local 失败（PDF/Docling/leak）产生单 filing FAILED row，不阻止其他 candidate。
- Operation-terminal 失败 propagate 到 runtime，不被 document row 消费。
- Helper 复用是直接公开导入，不经过 facade 或 wrapper。

**一个小风险**：父 leak catch（line 286）当前 catch 的 `Exception` 范围很宽。amendment 要求所有非 `CnDownloadCancelledError` 异常进入 helper。但如果 future change 在 child 中新增了不应归为 `filing_execution_failed` 的异常类型，这个宽 catch 会错误分类。amendment 的封闭三段映射（provider/storage/execution）覆盖了当前所有已知异常类型，这是一个可接受的 tradeoff。

---

## 裁决问题 4：Allowlist、测试矩阵、coverage、静态扫描、stop conditions 是否足够？

### Allowlist 验证

amendment §5.2 新增 production allowlist：

| 文件 | 验证 |
|---|---|
| `cninfo_downloader.py` | **必要**：当前仍使用 `RuntimeError(f"...url={url} error={last_exc}")` 模式（`cninfo_downloader.py:588`），需要 from-zero retry-loop 重构 |
| `hkexnews_downloader.py` | **必要**：与 CNINFO 相同模式 |
| `cn_download_filing_workflow.py` | **必要**：当前仍有 `str(exc)` 在 line 194/202/322；需新增 `project_cn_filing_failure` |
| `cn_download_workflow.py` | **必要**：删除 `_candidate_failure_facts`，改为导入 child 的 `project_cn_filing_failure` |
| `cn_download_rebuild.py` | **必要**：emit `missing_periods` |
| `sec_download_filing_workflow.py` | **已在 Slice 2 实现**：line 286-304 已 catch `FinsDownloadProviderError` 并转为单 filing FAILED row |

**allowlist 发现**：`sec_download_filing_workflow.py` 已包含在 §5.2 new additions 中，但该文件的 `FinsDownloadProviderError` catch（line 286-304）**已在 Slice 2 实现**。amendment §3.4 的表格描述"helper 原样传播 → sec_download_filing_workflow → 单 filing FAILED row"是**当前已有行为**，非新增变更。这会导致实现 agent 不确定此文件是否需要修改：如果不需要，为什么列在 allowlist？如果需要，改什么？

### 测试矩阵验证

§8.1（CNINFO/HKEX transport matrix）：覆盖 timeout/connection/HTTP status/malformed JSON/schema/PDF、pre-loop ValueError、hierarchy ordering（Timeout before NetworkError）、retry count。**充分**。

§8.2（CN/HK provenance matrix）：覆盖 discovery/storage/execution propagation 到 runtime、legacy `status="failed"` → `ValueError`、child PDF/Docling direct owner test、parent leak catch same-source test。**充分**。

§8.3（rebuild strictness）：覆盖 producer direct call 和 adapter strict consumption。**充分**。

§8.4（SEC auxiliary failures）：覆盖 browse-ticker/SC13/history propagation、三个 `_try_fetch_*` → filing-local FAILED、6-K preview continuation。但需注意：这些测试描述的行为大部分**已在 Slice 2 实现**。实现 agent 需要确认现有测试已覆盖，而非新增重复测试。

§8.5（count/terminal/public safety）：覆盖 zero-candidate override、defensive `AssertionError`、omitted count、CLI/wait equivalence。**充分**。

### Coverage 与静态扫描

§9 要求对每个修改 production 文件分别 `coverage report --fail-under=80`，包括 `cn_download_filing_workflow.py` 和 `sec_download_filing_workflow.py` 的 direct owner tests。静态扫描覆盖 `url=`/`error={exc}`/`str(exc)`/`_reason_code_from_exception`/`_candidate_failure_facts` 残留、rebuild `missing_periods`、adapter 无 blanket `status="failed"`。**充分**。

### Stop conditions 验证

8 条 stop condition，逐条与代码事实对照：

| # | 条件 | 验证 |
|---|---|---|
| 1 | 修改 excluded file / 需要新 shared module | §5.2/§5.5 边界清晰；`project_cn_filing_failure` 是 child module 内公开函数，非 shared module |
| 2 | stream consumer 要求 `status="failed"` envelope | 当前 adapter 已 strict validate `{ok, cancelled}`（`cn_pipeline.py:1445`）；amendment 不引入 envelope |
| 3 | 需要新 per-document transport field / schema change | 复用现有 `reason_code`/`reason_message`；明确拒绝新 schema |
| 4 | SEC failure 无法归入三层类之一 | §3.4 表已逐项归类；`_try_fetch_*` 在 Slice 2 已实现 filing-local FAILED |
| 5 | 测试保留泛型 `RuntimeError`/raw-message 断言 | §9 要求前置 inventory |
| 6 | retry-loop 重构改变 bounded retry/backoff | §6.2 分类表锁定行为；§8.1 测试覆盖 |
| 7 | count/URL/path/UA 泄露 | §7 binding invariants + §9 static scan |
| 8 | README/CLI/commit 变更 | 明确禁止 |

### 裁决

**基本充分，有一处实现风险**：`sec_download_filing_workflow.py` 的 allowlist 状态模糊——该文件在 Slice 2 中已实现 amendment 描述的行为，但被列入 §5.2"new production additions proved necessary"。如果实现 agent 理解为"需要修改此文件"，可能在已正确代码上做无效改动。建议 amendment 明确标注：`sec_download_filing_workflow.py` 的 `FinsDownloadProviderError` catch 已是 Slice 2 既有实现，本 amendment 只要求**验证其存在**（通过 §8.4 direct owner test），不要求新增 production 改动。

---

## 裁决问题 5：是否遗漏 schema/类型/日志泄漏/terminal uniqueness 风险？

### Schema 风险

amendment 明确拒绝新增 per-row transport 字段（§3.2: "不新增 per-row transport 字段或 public schema"），复用现有 `reason_code`/`reason_message`。category-derived reason（如 `provider_timeout`、`provider_connection`）保留精确来源类别。**无遗漏 schema 风险**。

### 类型风险

`project_cn_filing_failure` 返回 `tuple[str, str]`——弱类型。amendment 明确选择朴素 tuple 以对应两个现有 row 字段。调用方需知道顺序 `(reason_code, reason_message)`，但两字段均写入 dict 再进入 typed `FinsDownloadDocumentResult`，type checker 可在 typed boundary 捕获错误。**低风险，可接受**。

### 日志泄漏风险

**当前泄漏点**：
- `cn_download_filing_workflow.py:194` — `reason_message=str(exc)` 写入 `FILE_FAILED` 事件
- `cn_download_filing_workflow.py:202` — `reason_message=str(exc)` 写入 `FILING_FAILED` 的 `_build_filing_result`
- `cn_download_filing_workflow.py:322` — `reason_message=str(exc)` 写入 `FILING_FAILED` 的 `_build_filing_result`

**修复后**：三处均使用 `project_cn_filing_failure` 返回的固定 safe_message。对于 `FinsDownloadProviderError`，`str(exc)` 已返回 `safe_message`（因为 `super().__init__(self.safe_message)` at `download_contract.py:134`）。对于 `OSError`，固定为 `"下载产物读写失败"`。对于其他，固定为 `"财报文档执行失败"`。**泄漏修复完整**。

**一个注意点**：`FILE_FAILED` 事件（line 185-195）的 payload 包含 `"name": pdf_filename`——这是文件名，不是绝对路径。`pdf_filename = f"{document_id}.pdf"`（line 134），不含路径组件。**安全**。

### Terminal uniqueness 风险

amendment 的封闭映射保证：
- `FinsDownloadProviderError` → runtime `PROVIDER_TRANSPORT`（通过 `_download_public_failure_from_exception`）
- `OSError` → runtime `STORAGE`
- 其他 → runtime `EXECUTION`

文档级失败行的 `reason_code` 也由同一 `project_cn_filing_failure` 产生（`provider_*`、`storage_failed`、`filing_execution_failed`），与 runtime 公共失败分类形成两层独立但语义一致的投影。文档行的 reason 不会与 operation 级公共失败混淆——后者通过 `FinsPublicFailure` 的 closed classification 字段表达，前者通过 `FinsDownloadDocumentResult.reason_code`。**两层投影清晰分离**。

### 收敛性风险

父 leak catch（line 286）在 child 正常处理所有 document-local failure 时不应被触发。如果被触发，说明 child 有未处理的异常路径——这本身就是需要修复的 bug。amendment 让父使用与 child 相同的 helper 意味着即使发生这种 bug，failure 分类仍然正确。**防御性设计合理**。

### 裁决

**无遗漏的 schema/类型/日志泄漏/terminal uniqueness 风险。** 有一条低严重度观察：`FILE_FAILED` 事件的 `reason_message` 字段（line 194）在修复后使用 helper 的 safe_message——但 `FILE_FAILED` 事件的语义消费者不明确。如果 future consumer 期望从 `reason_message` 获取可操作的诊断信息（例如具体哪个 URL 失败），固定 safe_message 会降低诊断价值。但 amendment 的整体方向是安全优先（不泄漏 URL/contact/path），这是正确的 tradeoff。`FILE_FAILED` 的 consumer（如果有）应通过 `FILING_FAILED` 的 typed `reason_code` 获取分类粒度。

---

## Findings

### F-01-未修复-中-amendment §3.4/§6.5 描述的 SEC auxiliary 修复大部分已在 Slice 2 实现，allowlist 状态模糊

- **位置**: §3.4（SEC auxiliary 裁决表）、§5.2（new production additions）、§6.5（SEC provider/pipeline owners）
- **问题类型**: 不可直接实施 — amendment 描述的行为变更与 Slice 2 已实现代码重叠，实现 agent 可能对已正确代码做无效改动
- **当前写法**: §3.4 的 10 行裁决表描述每个 SEC helper "修订后 owner 与结果"；§5.2 把 `sec_download_filing_workflow.py` 列为"new production additions proved necessary"
- **反例/失败场景**:
  1. `_try_fetch_index_items` / `_try_fetch_index_header_documents` / `_try_fetch_primary_linked_html_files` 在 Slice 2 中已经 raise `FinsDownloadProviderError`（docstring 声明 `Raises: FinsDownloadProviderError`，底层 `_http_get_json`/`_http_get_bytes` 已实现 typed mapping）
  2. `sec_download_filing_workflow.py:286-304` 在 Slice 2 中已经 catch `FinsDownloadProviderError` 并转为单 filing FAILED row
  3. `fetch_sc13_party_roles` 在 Slice 2 中已经通过 `_http_get_bytes` 传播 `FinsDownloadProviderError`
  4. 6-K preview `_precheck_6k_filter` 在 Slice 2 中已经 catch `FinsDownloadProviderError`（line 1724）并使用 safe logging（line 1727）
  5. `_resolve_company_via_browse_edgar_ticker` 的 XML parse 失败在 Slice 2 中已经 re-raise 为 `_sec_protocol_failure()`

  实现 agent 阅读 amendment §3.4 和 §5.2 后可能理解为"需要在 `sec_download_filing_workflow.py` 新增 `FinsDownloadProviderError` catch 逻辑"——但该逻辑已存在。
- **为什么有问题**: amendment 的目标是纠正 code review 发现的 C01/R02/R06，但 §3.4 的"修订后 owner 与结果"列描述的是 Slice 2 **已经实现的终态**，而非"从当前代码到终态需要的变更"。allowlist 把已实现的文件（`sec_download_filing_workflow.py`）与真正需要修改的文件（`cn_download_filing_workflow.py`）混在同一节，不区分"验证存在"与"新增实现"。
- **直接证据**:
  - `sec_downloader.py:2058-2087` — `_try_fetch_index_items` docstring: "Raises: FinsDownloadProviderError"
  - `sec_download_filing_workflow.py:286-304` — 已实现的 `except FinsDownloadProviderError` catch
  - `sec_pipeline.py:1724-1730` — 已实现的 6-K preview `except FinsDownloadProviderError` + safe logging
- **影响**: 实现 agent 可能尝试在已正确代码上做"修复"，导致：(a) 无意义的代码重写；(b) 引入新 bug；(c) 浪费时间在不需要修改的文件上
- **建议改法和验证点**:
  1. 在 §5.2 中区分 `sec_download_filing_workflow.py` 的状态：标注为 "Slice 2 已实现 filing-local FAILED catch；本 amendment 只要求通过 §8.4 direct owner test 验证，无 production 改动"
  2. 在 §3.4 表的 `_try_fetch_*` 行标注 "(Slice 2 已实现)" 以区分已实现与待实现
  3. 在 §6.5 中增加一段 "Slice 2 已有实现确认"，列出已在 Slice 2 正确实现、本 amendment 只验证不该动的 SEC 路径
- **修复风险（低/中/高）**: 低 — 只需 amendment 文本澄清
- **严重程度（低/中/高/严重）**: 中

---

### F-02-未修复-低-CNINFO/HKEX 4xx 立即停止行为与 SEC 不对称，amendment 未显式说明理由

- **位置**: §6.2 闭合分类表
- **问题类型**: 最佳实践偏离 — CN/HK 与 SEC 对同一 `httpx.HTTPStatusError` 的 4xx 行为不同但无文档说明
- **当前写法**: §6.2 分类表要求 CN/HK "`HTTPStatusError` with 4xx → `HTTP_STATUS` non-retryable, Stop without consuming remaining retries"
- **反例/失败场景**:
  1. SEC downloader 的 `_execute_sec_request` 对 4xx 仍走完整重试循环（使用 `_sec_transport_category` 和 `_sec_transport_retryable` 判定，但不提前 break）
  2. CN/HK downloader 的 from-zero 重构要求 4xx 立即停止不消耗剩余重试
  3. 两者行为不对称是刻意设计（4xx 确实不应重试，CN/HK 的 from-zero 重构可以比 SEC 更优），但 amendment 未说明这是有意的改进还是疏忽
- **为什么有问题**: 如果 implementation agent 参考 SEC 实现来写 CN/HK retry loop，会发现行为不一致，可能：(a) 把 CN/HK 也改成 SEC 的行为（继续重试 4xx），(b) 认为 amendment 有误并向 controller 提问，延迟实现
- **直接证据**:
  - §6.2 分类表: "HTTPStatusError with 4xx → Stop without consuming remaining retries"
  - `sec_downloader.py` 的 `_execute_sec_request` 对 4xx 无提前 break
- **影响**: 低 — 实现 agent 大概率遵循 amendment 的明确指令；但缺少理由说明可能引起 review 时的不必要讨论
- **建议改法和验证点**: 在 §6.2 分类表中加注："CN/HK from-zero 重构对 4xx 采用更严格策略（立即停止），与 SEC 既有行为不同但属于改进行为；SEC 不在本 amendment scope"
- **修复风险（低/中/高）**: 低 — 加一行注释
- **严重程度（低/中/高/严重）**: 低

---

### F-03-未修复-低-`FILE_FAILED` 事件 payload 的 `reason_message` 字段语义消费者不明确

- **位置**: §3.2 PDF catch 修复
- **问题类型**: 契约缺失 — `FILE_FAILED` 事件的 `reason_message` 从 `str(exc)` 改为固定 safe_message 后，下游 consumer 的诊断能力下降
- **当前写法**: amendment 要求 PDF catch 的 `FILE_FAILED` 和 `FILING_FAILED` 都使用同一次 `project_cn_filing_failure` 调用结果
- **反例/失败场景**: `FILE_FAILED` 事件（`cn_download_filing_workflow.py:185-195`）是一个独立事件类型，其 payload 包含 `name`、`stage`、`status`、`reason_code`、`reason_message`。如果存在消费 `FILE_FAILED` 事件的下游逻辑（例如 progress sink 或 event log analyzer），它目前可能依赖 `reason_message` 中的具体异常文本来区分失败模式。改为固定 safe_message 后，`reason_message` 变为 `"下载产物读写失败"` 或 `"财报文档执行失败"`，丢失了细粒度诊断信息。
- **为什么有问题**: amendment 的安全优先方向正确（URL/contact/path 不应出现在 event 中），但 `FILE_FAILED` 的 `reason_code` 字段（`"pdf_download_failed"`）在修复后仍然存在——如果 `reason_code` 保持不变（仍为 `"pdf_download_failed"`），而 `reason_message` 变为固定 safe text，则 `reason_code` 和 `reason_message` 之间存在语义不对称：`reason_code` 来自旧逻辑，`reason_message` 来自新 helper。amendment 未明确 `FILE_FAILED` 的 `reason_code` 是否也应从 helper 派生。
- **直接证据**:
  - `cn_download_filing_workflow.py:189-194` — `FILE_FAILED` 事件 payload 当前写入 `reason_code="pdf_download_failed"` 和 `reason_message=str(exc)`
  - amendment §3.2: "PDF catch 的 `FILE_FAILED` 与 `FILING_FAILED` 必须调用同一次 helper 投影并复用同一对事实"
- **影响**: 低 — `FILE_FAILED` 事件的消费者可能不存在（仅用于 progress tracking），且 `FILING_FAILED` 事件的 `reason_code` 从 helper 派生（如 `provider_timeout`）已经比 `"pdf_download_failed"` 更精确
- **建议改法和验证点**: 明确 `FILE_FAILED` 的 `reason_code` 也应从 helper 返回的第一项（`reason_code`）派生，替换硬编码的 `"pdf_download_failed"`。这样 `FILE_FAILED` 和 `FILING_FAILED` 的 `(reason_code, reason_message)` 对完全一致
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## 专项压测结果

### 1. `_is_cancel_requested` 异常传播

**PASS。** Slice 2 的 `_is_cancel_requested`（`cn_download_workflow.py:360-376`）已简化为直接 `return cancel_checker()`，无 wrapping。`CnDownloadCancelledError`、`FinsDownloadProviderError`、`OSError` 均原样传播。amendment 的 §3.1 描述的是**当前已有行为**，不是待修复项。

### 2. `_candidate_failure_facts` → `project_cn_filing_failure` 迁移

**PASS with note。** 两者逻辑等价（三段映射完全相同）。迁移本质上是 move + rename + public visibility。amendment 正确地将此描述为 ownership 纠正。

### 3. Parent leak catch 的必要性

**PASS。** 父 leak catch（`cn_download_workflow.py:286`）在 child 正常处理所有 document-local failure 时不应被触发，但作为防御性边界保留是合理的。让父使用 child 的公开 helper 保证即使 leak 发生，分类仍然正确。

### 4. `_summary_from_pipeline_result` strict terminal validation

**PASS。** Slice 2 的 adapter（`cn_pipeline.py:1444-1446`）已将 status 严格限定为 `{_CN_TERMINAL_OK, _CN_TERMINAL_CANCELLED}`。不存在 blanket `status="failed"` → provider UNKNOWN 转换。amendment §6.3 的 "CnDownloadAdapter removes the blanket status='failed' -> provider UNKNOWN conversion" 描述的是**当前已有行为**。

### 5. `_terminal_disposition_from_counts` defensive `AssertionError`

**PASS。** Slice 2 已实现（`download_contract.py:509`）：`raise AssertionError("mixed download failure requires discovered_count > 0")`。`discovered_count` 参数已保留。amendment 描述的是**当前已有行为**。

### 6. CNINFO/HKEX downloader 当前状态

**CONFIRMED：需要 from-zero 重构。** 当前 `cninfo_downloader.py:579-588` 使用 `except httpx.HTTPError as exc: ... raise RuntimeError(f"...url={url} error={last_exc}")`。HKEX 相同模式。这是 amendment 中**真正需要新增实现的部分**。

### 7. `cn_download_filing_workflow.py` 当前泄漏状态

**CONFIRMED：str(exc) 仍在使用。** Line 194（FILE_FAILED）、line 202（FILING_FAILED via `_build_filing_result`）、line 322（FILING_FAILED via `_build_filing_result`）均写 `str(exc)`。这是 amendment 中**真正需要修复的部分**。

---

## Open Questions

### OQ-1: `sec_download_filing_workflow.py` 在 allowlist 中的实际变更范围

该文件已在 Slice 2 中实现 `FinsDownloadProviderError` catch。如果 amendment 的 allowlist 意图是"验证存在 + direct owner test"而非"新增 production 改动"，当前 allowlist 的分类方式（§5.2 new production additions）会产生误导。建议澄清。

### OQ-2: CN/HK downloader 重构是否会触及 `_http_head_meta`

`cninfo_downloader.py` 的 `_http_head_meta`（line 636-657）catch `httpx.HTTPError` 返回 `CnReportHeadMeta(content_length=None, ...)`——这是 metadata-only optional 降级，与 amendment 的 HEAD optional 分类一致。retry-loop 重构是否需要同步更新此方法的异常处理？当前 amendment 未提及。

---

## Residual Risks

| 风险 | 严重度 | 说明 | 跟踪位置 |
|---|---|---|---|
| SEC allowlist 模糊导致无效改动 | 中 | F-01：`sec_download_filing_workflow.py` 等文件已在 Slice 2 实现 amendment 描述的行为，allowlist 未区分"验证"与"新增实现" | Slice 2 implementation 启动前澄清 |
| CN/HK retry loop 重构范围 | 中 | 两个 downloader 的 `_http_get_json`、`_http_post_form`、`_http_download_bytes` 均需重构；`_http_head_meta` 边界待确认 | Slice 2 implementation |
| CN/HK 4xx 行为与 SEC 不对称 | 低 | F-02：刻意设计但未说明理由 | Slice 2 code review |
| `FILE_FAILED` reason_code 与 helper 对齐 | 低 | F-03：`FILE_FAILED` 的 `reason_code` 当前硬编码 `"pdf_download_failed"`，应从 helper 派生 | Slice 2 implementation |
| `_build_filing_result` receiver 签名 | 低 | 函数接受 `reason_code` 和 `reason_message` 参数（line 841-842），已与 helper 返回值匹配，无需修改签名 | 实现时确认 |

---

## Final Plan Review Conclusion

**PASS-WITH-RISKS**

amendment 对五条裁决问题的 core design 均正确：

1. `cn_download_filing_workflow.py` **是** PDF/Docling document-local failure 的正确 owner——该文件当前写 `str(exc)` 到 event/row，amendment 将封闭 helper 迁入此文件正确。
2. `project_cn_filing_failure(Exception)->tuple[str,str]` **是**最小、直接、唯一的 source of truth——三段封闭映射无 facade/seam，与现有 `_candidate_failure_facts` 逻辑等价，区别仅在于位置和可见性。
3. 子 workflow 两处 catch 与父 leak catch 的复用边界、取消语义和 blast radius **精确**——`CnDownloadCancelledError` 三处均正确排除，document-local failure 不影响其他 filing，operation-terminal 异常 propagate 到 runtime。
4. Allowlist、测试矩阵、coverage、静态扫描、stop conditions **基本充分**——唯一需要澄清的是 SEC 侧 allowlist 中几个文件的状态（已在 Slice 2 实现 vs 需要新增实现）。
5. 无遗漏的 schema/类型/日志泄漏/terminal uniqueness 风险——`str(exc)` 的三个泄漏点均被 helper 替代覆盖。

**存在 1 个中等严重度 finding（F-01）**：amendment 描述的 SEC auxiliary 修复大部分已在 Slice 2 实现，但 allowlist 未区分"已实现需验证"与"待实现需新增"，可能导致 implementation agent 在已正确代码上做无效改动。

**存在 2 个低严重度 finding（F-02/F-03）**：CN/HK 4xx 行为与 SEC 不对称未说明理由；`FILE_FAILED` 的 `reason_code` 是否从 helper 派生未明确。

**无 blocking finding。** 所有 finding 均可通过 amendment 文本澄清或在实现阶段按 stop condition 机制处理。

审查 artifact: `docs/reviews/plan-review-20260810-slice2-cn-owner-ds.md`
