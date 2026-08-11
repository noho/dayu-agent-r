# wu-cli-download-01 Slice 2 Stop-Condition Amendment — 独立 Adversarial Plan Review

## 1. 审查元数据

| 项 | 值 |
|---|---|
| 审查类型 | 独立 adversarial plan review（stop-condition amendment 修订版） |
| 审查目标 | `docs/gateflow/wu-cli-download-01-slice2-plan-amendment-20260810-030216.md` |
| 基线 HEAD | `c6829400a5e37892464a614590062511554f9633` |
| Work unit | `wu-cli-download-01` |
| 审查日期 | 2026-08-10 |
| 审查人 | AgentMiMo（独立路径，基于源码直接核验） |
| 输入文档 | amendment artifact、accepted base plan、四份先前 plan review、当前源码 |
| 产品/测试修改 | 无 |

## 2. 审查范围与焦点

用户指定五个焦点：

1. `cn_download_filing_workflow` 是否确为 PDF/Docling document-local failure owner
2. 公开 `project_cn_filing_failure(Exception) -> tuple[str,str]` 是否是最小、直接、唯一 source of truth
3. 子 workflow 两处 catch 与父 workflow leak catch 的复用边界、取消语义和 operation/document blast radius
4. allowlist、测试矩阵、coverage、静态扫描、stop conditions 是否足够
5. 是否遗漏 schema/类型/日志泄漏/terminal uniqueness 风险

## 3. Assumptions Tested

| # | Assumption | 验证方式 |
|---|-----------|---------|
| A1 | `cn_download_filing_workflow.py` 的 PDF/Docling catch 确实使用 `str(exc)` 且可泄漏 | 直接读取源码 line 184/316 |
| A2 | `project_cn_filing_failure` 尚不存在，需新建 | `rg -rn 'project_cn_filing_failure' dayu/ tests/` 返回 NOT FOUND |
| A3 | `_candidate_failure_facts` 已存在于父 workflow 且做相同映射 | 直接读取源码 line 535 |
| A4 | CNINFO/HKEX downloader 的 retry-loop 重构是否真的需要从零开始 | 直接读取 `cninfo_downloader.py:767` 和 `hkexnews_downloader.py:689` |
| A5 | `_is_cancel_requested` 是否仍包装 typed exception | 直接读取 `cn_download_workflow.py:360-376` |
| A6 | SEC `sec_download_filing_workflow.py` 是否已实现 `FinsDownloadProviderError` catch | 直接读取源码 line 286 |
| A7 | runtime `_download_public_failure_from_exception` 是否已有正确的三路映射 | 直接读取源码 line 5016-5069 |

## 4. Findings

### F01-未修复-低-amendment §6.2 对 CNINFO/HKEX retry-loop 重构范围描述不准确

- **位置**: §6.2 "CNINFO/HKEX provider owners"
- **问题类型**: 不可直接实施（过度描述实现范围）
- **当前写法**: "This is an explicit from-zero retry-loop refactor in both synchronous downloaders, not a helper-only patch."
- **反例/失败场景**:
  当前 CNINFO downloader（`cninfo_downloader.py:767-805`）已有 `_cninfo_http_failure` helper，实现与 amendment 描述完全一致的五类 granular mapping（`TimeoutException → TIMEOUT`、`NetworkError → CONNECTION`、`HTTPStatusError → HTTP_STATUS`、`ProtocolError → PROTOCOL`、其它 → `UNKNOWN`），且 `isinstance` 顺序正确（TimeoutException 在 NetworkError 之前）。HKEX downloader（`hkexnews_downloader.py:689-727`）有相同的 `_hkexnews_http_failure` helper。两个 downloader 的 retry loop 已将 HTTP request 与 response parsing 分离：httpx 异常在 retry loop 内捕获并分类，JSON 解析在 retry loop 外捕获为 protocol error。
- **为什么有问题**: amendment 声称需要 "from-zero retry-loop refactor"，但直接代码证据证明重构已经完成。实现 agent 可能错误地重写已正确的代码，引入不必要的 regression 风险。
- **直接证据**:
  - `cninfo_downloader.py:767-805`: `_cninfo_http_failure` 五类映射，TimeoutException 在 NetworkError 之前
  - `cninfo_downloader.py:571-597`: retry loop 结构——HTTP request 在 loop 内，JSON parsing 在 loop 外
  - `cninfo_downloader.py:593-596`: `response.json()` 的 `ValueError` → `_cninfo_protocol_error`
  - `hkexnews_downloader.py:689-727`: `_hkexnews_http_failure` 五类映射
  - `hkexnews_downloader.py:536-560`: retry loop 结构与 CNINFO 一致
- **影响**: 实现 agent 可能不必要地重写已正确的 retry-loop 代码，浪费时间并引入 regression 风险。amendment 的 Stop Condition 6（retry-loop refactoring）可能被误触发。
- **建议改法和验证点**:
  1. 在 §6.2 中增加："CNINFO/HKEX downloader 已有 `_cninfo_http_failure` / `_hkexnews_http_failure` helper，实现五类 granular mapping 且 `isinstance` 顺序正确。retry loop 已将 HTTP request 与 response parsing 分离。本次 amendment 只需验证现有实现符合闭合分类表，不需从零重构。"
  2. 删除 "from-zero retry-loop refactor" 描述，改为 "verify existing granular mapping"。
  3. §8.1 transport matrix 测试仍需保留，但目的是验证现有实现，而非驱动新实现。
  4. 验证点：现有 `_cninfo_http_failure` / `_hkexnews_http_failure` 的 `isinstance` 顺序与 §6.2 闭合分类表一致。
- **修复风险（低）**: 只需修改 amendment 描述，不需改代码
- **严重程度（低）**: 不影响正确性，但可能导致实现 agent 做不必要的工作

---

### F02-未修复-低-amendment §3.1 对 `_is_cancel_requested` 的 concern 已在当前代码中解决

- **位置**: §3.1、§6.3、§8.2
- **问题类型**: 目标漂移（修复已不存在的问题）
- **当前写法**: "_is_cancel_requested 对 CnDownloadCancelledError 维持 cancelled；对 FinsDownloadProviderError、OSError 与其它异常均不字符串包装。"
- **反例/失败场景**:
  先前 plan review（DS F-02）指出 `cn_download_workflow.py:431-434` 的 `except Exception: raise RuntimeError(...)` 会降解 typed exception。但当前代码（`cn_download_workflow.py:360-376`）的 `_is_cancel_requested` 是一个简单的 pass-through：
  ```python
  def _is_cancel_requested(cancel_checker: Callable[[], bool] | None) -> bool:
      if cancel_checker is None:
          return False
      return cancel_checker()
  ```
  没有 `try/except`，没有 `RuntimeError` wrap。typed exception 原样传播。
- **为什么有问题**: amendment 仍在修复一个已不存在的问题。§8.2 的测试（"Cancellation checker raising FinsDownloadProviderError preserves the exact object"）仍然有价值作为回归保护，但 amendment 的描述暗示当前代码有包装问题。
- **直接证据**:
  - `cn_download_workflow.py:360-376`: `_is_cancel_requested` 是简单 pass-through，无 try/except
  - 先前 plan review DS F-02 描述的问题在当前代码中不存在
- **影响**: 无 correctness 影响。测试仍有回归保护价值。但 amendment 描述可能误导实现 agent。
- **建议改法和验证点**:
  1. 在 §3.1 中增加注释："当前 `_is_cancel_requested` 已是简单 pass-through，无 exception wrapping。§8.2 测试作为回归保护保留。"
  2. 验证点：AST 证明 `_is_cancel_requested` 无 try/except。
- **修复风险（低）**: 只需修改 amendment 描述
- **严重程度（低）**: 无 correctness 影响

---

### F03-未修复-低-amendment §6.5 对 SEC `sec_download_filing_workflow` 的描述与当前实现一致

- **位置**: §5.2、§6.5
- **问题类型**: 目标漂移（描述已实现的行为）
- **当前写法**: "sec_download_filing_workflow.run_download_single_filing_stream catches only the typed provider error around list_filing_files, emits exactly one FAILED filing terminal"
- **反例/失败场景**:
  当前 `sec_download_filing_workflow.py:286-304` 已经实现了这个行为：
  ```python
  except FinsDownloadProviderError as exc:
      filing_result = {
          ...
          "reason_code": f"provider_{exc.transport_category.value}",
          "reason_message": exc.safe_message,
      }
      yield DownloadEvent(
          event_type=DownloadEventType.FILING_FAILED,
          ...
      )
      return
  ```
  amendment 的 §5.2 将此文件列为 "New production additions proved necessary by the call chain"，但代码已经存在。
- **为什么有问题**: amendment 暗示需要新建这个 catch，但代码已经实现。实现 agent 可能不必要地重写已正确的代码。
- **直接证据**:
  - `sec_download_filing_workflow.py:286-304`: 已有 `FinsDownloadProviderError` catch
  - `sec_download_filing_workflow.py:284`: 已有 `SecDownloadCancelledError` catch
- **影响**: 无 correctness 影响。实现 agent 只需验证现有实现符合 amendment 规格。
- **建议改法和验证点**:
  1. 在 §5.2 中将 `sec_download_filing_workflow.py` 从 "New production additions" 改为 "Existing implementation verified to match amendment specification"。
  2. §8.4 测试仍需保留，但目的是验证现有实现，而非驱动新实现。
- **修复风险（低）**: 只需修改 amendment 描述
- **严重程度（低）**: 无 correctness 影响

---

## 5. 用户焦点逐项裁决

### 5.1 `cn_download_filing_workflow` 是否确为 PDF/Docling document-local failure owner

**裁决：是。直接代码证据确认。**

- `cn_download_filing_workflow.py:184`: PDF catch — `except Exception as exc:` → `reason_code="pdf_download_failed"`, `reason_message=str(exc)`
- `cn_download_filing_workflow.py:316`: Docling catch — `except Exception as exc:` → `reason_code="docling_convert_failed"`, `reason_message=str(exc)`
- 两处都使用 `str(exc)` 直接暴露异常文本，可泄漏 URL、路径、raw payload
- `CnDownloadCancelledError` 在两处 catch 之前都有显式 `except CnDownloadCancelledError: raise`
- 该文件是唯一同时拥有 PDF 下载和 Docling 转换异常边界的模块
- 父 `cn_download_workflow.py` 只能看到子 workflow 已产出的终态事件；对于正常 document-local failure，异常不会到达父模块的 per-candidate catch

**结论：amendment 的 owner 裁决正确，需要在该文件定义 `project_cn_filing_failure` 并替换 `str(exc)`。**

### 5.2 `project_cn_filing_failure(Exception) -> tuple[str,str]` 是否是最小、直接、唯一 source of truth

**裁决：是。设计符合最小、直接、唯一要求。**

- **最小**：3 分支 isinstance 映射，tuple 返回值，无额外依赖
- **直接**：在异常发生点（PDF/Docling catch）调用，不经过 wrapper 或 facade
- **唯一**：amendment 要求 "exactly one definition in cn_download_filing_workflow.py and one direct parent import/use"
- **不是 facade/seam**：它做实际的 mapping 工作（FinsDownloadProviderError → category-derived reason + safe_message; OSError → storage_failed + fixed text; other → filing_execution_failed + fixed text），不是简单转发
- **与现有 `_candidate_failure_facts` 的关系**：父 workflow 的 `_candidate_failure_facts`（`cn_download_workflow.py:535-552`）做完全相同的映射。amendment 正确要求删除 `_candidate_failure_facts` 并用 `project_cn_filing_failure` 替代

**结论：设计正确。`project_cn_filing_failure` 是 document-local failure 的唯一 source of truth。**

### 5.3 子 workflow 两处 catch 与父 workflow leak catch 的复用边界、取消语义和 blast radius

**裁决：边界精确，取消语义正确，blast radius 分离。**

**复用边界**：
- 子 workflow PDF catch（line 184）：document-local，emit FILE_FAILED + FILING_FAILED，return
- 子 workflow Docling catch（line 316）：document-local，emit FILING_FAILED，return
- 父 workflow per-candidate catch（line 286）：operation-level leak catch，handle exceptions that escaped the child generator
- 三处都调用同一个 `project_cn_filing_failure`，保证同源复用

**取消语义**：
- 子 workflow：`CnDownloadCancelledError` 在 PDF catch（line 182-183）和 Docling catch（line 314-315）之前显式 re-raise
- 父 workflow：`CnDownloadCancelledError` 在 per-candidate catch（line 282-285）之前显式捕获
- 取消异常永远不会进入 `project_cn_filing_failure`

**Blast radius**：
- Document-local failure（子 workflow catch）：emit FILING_FAILED row，继续下一个 candidate
- Operation-level leak（父 workflow catch）：emit FILING_FAILED row，继续下一个 candidate（因为 catch 在 per-candidate loop 内）
- Operation-terminal（outer try/except line 306）：propagate to runtime
- 三者不交叉

**结论：amendment 的边界设计正确。**

### 5.4 Allowlist、测试矩阵、coverage、静态扫描、stop conditions

**裁决：足够，但有三个描述性不准确。**

**Allowlist**：
- 完整覆盖所有需要修改的文件
- §5.5 explicitly excluded 列表正确
- `sec_download_filing_workflow.py` 已在 allowlist 中（虽然代码已实现）

**测试矩阵**：
- §8.1 transport matrix：覆盖五类 httpx 异常 + hierarchy ordering + JSONDecodeError + pre-loop ValueError
- §8.2 provenance matrix：覆盖三类异常传播 + legacy status="failed" fail-closed
- §8.3 rebuild strictness：覆盖 producer 和 consumer 双向测试
- §8.4 SEC auxiliary failures：覆盖逐 helper 分类
- §8.5 count/terminal/public safety：覆盖所有终态推导

**Coverage**：
- §9 要求每个 production 文件单独 `--fail-under=80`
- 不用 aggregate 百分比掩盖单文件不足

**静态扫描**：
- §9 覆盖 url=、error=、str(exc)、contact canary、raw payload、traceback、absolute path
- rg/AST 验证 `_candidate_failure_facts` 删除、`project_cn_filing_failure` 唯一定义

**Stop conditions**：
- 8 条 stop conditions 覆盖所有已知风险
- Stop Condition 6（retry-loop refactoring）在当前代码中不适用（retry-loop 已正确实现），但仍作为安全网保留

**三个描述性不准确**：
1. §6.2 "from-zero retry-loop refactor" — 已实现，不需从零重构
2. §3.1 `_is_cancel_requested` wrapping concern — 已解决，当前代码是 pass-through
3. §5.2 `sec_download_filing_workflow.py` 列为 "New production additions" — 代码已存在

**结论：allowlist、测试矩阵、coverage、静态扫描、stop conditions 足够。三个描述性不准确不影响 correctness，但应修正以避免误导实现 agent。**

### 5.5 是否遗漏 schema/类型/日志泄漏/terminal uniqueness 风险

**裁决：无遗漏。**

**Schema 泄漏**：
- amendment 明确 "不新增 per-row transport 字段或 public row schema"
- category-derived use of existing `reason_category` is allowed
- §7 binding invariant 3: "no new per-document transport field or public row schema change"

**类型泄漏**：
- `project_cn_filing_failure` 返回 `tuple[str, str]`，对应现有 `reason_code` 和 `reason_message` 字段
- 不暴露 `FinsDownloadProviderError` 的内部字段（transport_category 只通过 category-derived reason 暴露）

**日志泄漏**：
- §9 静态扫描覆盖 url=、error=、str(exc)、contact canary、raw payload、traceback、absolute path
- PDF/Docling catch 的 `reason_message` 改为 helper 输出（safe_message 或 fixed text）
- `_cninfo_http_failure` / `_hkexnews_http_failure` 的日志只含 operation/attempt/category

**Terminal uniqueness**：
- amendment 要求 "exactly one filing terminal" for document-local failures
- PDF catch emit FILE_FAILED + FILING_FAILED（两个 event，一个 filing terminal）
- Docling catch emit FILING_FAILED（一个 event，一个 filing terminal）
- 父 workflow leak catch emit FILING_FAILED（一个 event，一个 filing terminal）
- 每个 filing 只有一个 terminal（FILING_COMPLETED 或 FILING_FAILED）

**结论：无遗漏。amendment 的 binding invariants 和静态扫描覆盖所有已知风险。**

## 6. Open Questions

无。所有先前 plan review 的 open questions 已在 amendment 中解决。

## 7. Residual Risks

| 风险 | 严重度 | 说明 | 跟踪位置 |
|---|---|---|---|
| amendment 描述与当前代码状态不一致 | 低 | §6.2 retry-loop 重构、§3.1 _is_cancel_requested、§5.2 sec_download_filing_workflow | 实现 agent 验证 |
| `_candidate_failure_facts` 删除后父 workflow 的 per-candidate catch 需验证 | 低 | 替换为 `project_cn_filing_failure` 后行为应完全一致 | §8.2 测试 |
| CnDownloadFilingError（RuntimeError 子类）进入 helper 时的映射 | 低 | 映射为 "filing_execution_failed"，语义正确 | §8.2 测试 |

## 8. Final Plan Review Conclusion

**PASS**

amendment 的核心设计正确且可直接实施：

1. **cn_download_filing_workflow 确为 PDF/Docling document-local failure owner** — 直接代码证据确认（line 184/316 的 `str(exc)` 泄漏）
2. **`project_cn_filing_failure` 是最小、直接、唯一 source of truth** — 3 分支 tuple 返回，无 facade/seam
3. **子/父 workflow catch 边界精确** — 取消语义正确（CnDownloadCancelledError 不进入 helper），blast radius 分离（document-local vs operation-level）
4. **allowlist、测试矩阵、coverage、静态扫描、stop conditions 足够** — 三个描述性不准确不影响 correctness
5. **无 schema/类型/日志泄漏/terminal uniqueness 遗漏**

三个低严重度 findings（F01-F03）均为描述性不准确，不影响 correctness 或 implementation 方向。实现 agent 应在开始前验证当前代码状态，避免不必要地重写已正确的代码。

amendment 可以进入 implementation。

**Review 结论**: PASS
**输出路径**: `docs/reviews/plan-review-20260810-slice2-cn-owner-mimo.md`
