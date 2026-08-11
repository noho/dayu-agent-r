# wu-cli-download-01 Slice 2 Stop-Condition Amendment — MiMo 原 Reviewer Re-Review

## 1. 审查元数据

| 项 | 值 |
|---|---|
| 审查类型 | 原 reviewer re-review（对照 `plan-review-20260810-slice2-cn-owner-mimo.md` F01-F03 逐项核验） |
| 审查目标 | 修订后 `docs/gateflow/wu-cli-download-01-slice2-plan-amendment-20260810-030216.md` |
| 原 review | `docs/reviews/plan-review-20260810-slice2-cn-owner-mimo.md` |
| DS review | `docs/reviews/plan-review-20260810-slice2-cn-owner-ds.md` |
| 基线 HEAD | `c6829400a5e37892464a614590062511554f9633` |
| Work unit | `wu-cli-download-01` |
| 审查日期 | 2026-08-10 |
| 审查人 | AgentMiMo |
| 产品/测试修改 | 无 |
| 提交 | 无 |

## 2. 修订核验总览

| 原 finding | 修订 disposition | 核验结果 |
|---|---|---|
| MiMo F01 retry-loop 重构范围描述 | Resolved | **resolved** |
| MiMo F02 `_is_cancel_requested` concern | Resolved | **resolved** |
| MiMo F03 `sec_download_filing_workflow` 已实现 | Resolved | **resolved** |
| DS F01 SEC allowlist 模糊 | Resolved | **resolved** |
| DS F02 4xx 行为不对称 | Resolved | **resolved** |
| DS F03 `FILE_FAILED` reason_code 对齐 | Resolved | **resolved** |

## 3. 逐项核验

### MiMo F01 — retry-loop 重构范围描述 → RESOLVED

**原问题**: amendment §6.2 声称 "from-zero retry-loop refactor"，但当前代码已有 `_cninfo_http_failure` / `_hkexnews_http_failure` granular mapping。

**修订内容**: §6.2 新增："**the current dirty diff already contains that refactor**. 恢复 implementation 后以本节分类表验证...只有测试、类型检查或静态扫描证明偏离时才做最小修正，不得重新改写已满足下列边界的 loop。"

§5.2 对 `cninfo_downloader.py` 和 `hkexnews_downloader.py` 标注："**已实现，待验证/必要时仅修失败**：current dirty diff 已有 CNINFO/HKEX closed mapping、retry/parser separation 与 safe logging；保留 unknown-httpx 测试收敛，不得无效重写 retry loop。"

§4 裁决表："MiMo F01 | Resolved | CNINFO/HKEX closed retry loops are already present in the current dirty diff. §§3.1/5.2/6.2 now require verification and failure-driven correction only, not a from-zero rewrite."

**核验**: 修订后的 §6.2 明确区分 "review trigger 时的状态"（需要 from-zero 重构）与 "当前 dirty diff 的状态"（重构已完成，只验证）。§5.2 的 "已实现，待验证/必要时仅修失败" 标签防止实现 agent 重写已正确的代码。§8.1 transport matrix 测试保留为验证工具，而非驱动新实现。

**判定**: **RESOLVED。** 描述性不准确已修正，实现 agent 不会做不必要的重写。

---

### MiMo F02 — `_is_cancel_requested` concern → RESOLVED

**原问题**: amendment §3.1 描述 `_is_cancel_requested` 不包装 typed exception，但当前代码已是简单 pass-through，amendment 暗示当前有包装问题。

**修订内容**: §4 裁决表："MiMo F02 | Resolved | `_is_cancel_requested` is already a no-catch pass-through in the current dirty diff. §§3.1/5.2/6.3 retain its tests solely as regression protection."

§6.3 保持："_is_cancel_requested does not wrap exception text."

§3.1 保持描述但 §4 明确这是当前已有行为。

**核验**: 修订后的 amendment 不再暗示当前代码有包装问题。§8.2 的测试保留为回归保护，这是正确的——即使当前代码已正确，测试仍能防止未来 regression。

**判定**: **RESOLVED。** 描述性 concern 已通过 §4 裁决表澄清。

---

### MiMo F03 — `sec_download_filing_workflow` 已实现 → RESOLVED

**原问题**: amendment §5.2 将 `sec_download_filing_workflow.py` 列为 "New production additions"，但代码已实现 `FinsDownloadProviderError` catch。

**修订内容**: §5.2 将 `sec_download_filing_workflow.py` 标注为："**已实现，待验证/必要时仅修失败**：current dirty diff 已把 `list_filing_files` typed provider failure 投影为恰好一个 FAILED filing row；本 amendment 不要求再次改写该 catch。"

§4 裁决表："MiMo F03 | Resolved | `sec_download_filing_workflow` already contains the approved typed filing-local catch. §§5.2/6.5 mark it implemented-and-pending-verification rather than a new production change."

§6.5 新增："Current dirty diff 已包含本节的 SEC auxiliary typed propagation、sec_download_filing_workflow filing-local catch、historical-submissions propagation、6-K safe diagnostic 与 HEAD optional behavior。恢复后以 §8.4 direct-owner tests 验证；只有真实失败才在原 allowlist owner 内最小修正，不得把已正确行为当作待新增功能重写。"

**核验**: 修订后的 §5.2 和 §6.5 明确区分 "已实现需验证" 与 "待实现需新增"。实现 agent 不会在已正确的 SEC 代码上做无效改动。

**判定**: **RESOLVED。** allowlist 状态模糊已消除。

---

## 4. Controller 对 DS F01-F03 裁决的核验

### DS F01 — SEC allowlist 模糊 → RESOLVED

**DS 原问题**: amendment §3.4/§5.2/§6.5 描述的 SEC auxiliary 修复大部分已在 Slice 2 实现，allowlist 未区分 "已实现需验证" 与 "待实现需新增"。

**Controller 裁决** (§4): "DS F01 | Resolved | §5 now distinguishes additional in-scope owners from new work and records the state of every such owner; already-correct SEC/CN dirty code must not be rewritten without a failing check."

**核验**: §5.2 对每个文件标注实现状态：
- `cninfo_downloader.py` / `hkexnews_downloader.py`: "已实现，待验证/必要时仅修失败"
- `cn_download_filing_workflow.py`: "尚待实施的 owner 修复"
- `cn_download_workflow.py`: "部分已实现，剩余 owner 迁移"
- `cn_download_rebuild.py`: "已实现，待验证/必要时仅修失败"
- `sec_download_filing_workflow.py`: "已实现，待验证/必要时仅修失败"

§6.5 新增："恢复后以 §8.4 direct-owner tests 验证；只有真实失败才在原 allowlist owner 内最小修正，不得把已正确行为当作待新增功能重写。"

**判定**: **RESOLVED。** allowlist 现在明确区分每个文件的实现状态。owner/allowlist/schema/stop conditions 实质范围未改变。

---

### DS F02 — CN/HK 4xx 行为与 SEC 不对称 → RESOLVED

**DS 原问题**: CN/HK 对 4xx 立即停止，SEC 对 4xx 仍走完整重试循环，amendment 未说明理由。

**Controller 裁决** (§4): "DS F02 | Resolved by policy clarification | §6.2 states that CN/HK 4xx fail-fast is this WU's non-retryable policy. The SEC retry-policy difference is deliberately unchanged and outside this owner amendment."

**核验**: §6.2 新增明确声明："CN/HK 对 4xx 的"一次请求后立即停止"是本 WU 明确采用的 fail-fast non-retryable policy，不是从 SEC retry loop 推导出的共享规则。SEC 当前对 4xx 的既有 retry-policy 差异不在这次 CN filing-owner amendment 中扩张或统一；如需改变 SEC policy，必须由另一个明确授权的 plan amendment 处理。"

**判定**: **RESOLVED。** 策略差异已显式记录。owner/allowlist/schema/stop conditions 实质范围未改变。Stop Condition 6 仍作为安全网保留，但现在有明确的 policy 声明防止误触发。

---

### DS F03 — `FILE_FAILED` reason_code 对齐 → RESOLVED

**DS 原问题**: PDF catch 的 `FILE_FAILED` 事件 `reason_code` 硬编码为 `"pdf_download_failed"`，应从 helper 派生。

**Controller 裁决** (§4): "DS F03 | Resolved as already specified | §3.2 and §§6.3/8.2 now make the existing decision visually explicit: one helper invocation supplies both `reason_code` and `reason_message` to both PDF terminal events. No owner, schema, or scope change is introduced."

**核验**: §3.2 新增明确声明："**PDF catch 必须只调用 helper 一次；`FILE_FAILED` 与 `FILING_FAILED` 的 `reason_code` 和 `reason_message` 两个字段都必须逐值复用这同一个返回 pair。** 不得保留 `FILE_FAILED.reason_code="pdf_download_failed"` 或只共享 message。"

§8.2 新增："**PDF additionally asserts one helper call and exact equality of both `reason_code` and `reason_message` across `FILE_FAILED` and `FILING_FAILED`—neither field may retain a PDF-specific override.**"

**判定**: **RESOLVED。** `FILE_FAILED` 和 `FILING_FAILED` 的 `(reason_code, reason_message)` 对现在显式要求完全一致，均从 helper 派生。owner/allowlist/schema/stop conditions 实质范围未改变。

---

## 5. Owner/Allowlist/Schema/Stop Conditions 实质范围核验

| 维度 | 修订前 | 修订后 | 范围变化 |
|---|---|---|---|
| **Owner scope** | 6 个 production files + 4 个 test files | 同上 | **无变化** |
| **Allowlist** | §5.2 列出 6 个 additional in-scope production owners | 同上，但每个文件标注实现状态 | **无实质变化**（仅增加状态标签） |
| **Schema** | 不新增 per-row transport 字段或 public schema | 同上 | **无变化** |
| **Stop conditions** | 8 条 | 同上 | **无变化**（Stop Condition 6 增加 policy 声明但条件本身不变） |
| **Binding invariants** | 10 条 | 同上 | **无变化** |
| **Test matrix** | §8.1-8.5 | 同上，§8.2 增加 PDF helper pair equality assertion | **无实质变化**（增加一个验证点） |

**结论：controller 的裁决未改变 owner/allowlist/schema/stop conditions 的实质范围。** 所有修订都是描述性澄清或实现状态标注，不引入新的 owner、文件、schema 字段或 stop condition。

---

## 6. 新增发现

无新增 finding。

修订后的 amendment 在以下方面增强了规格：
- §5.2 的逐文件实现状态标签消除了 allowlist 模糊。
- §6.2 的 "current dirty diff already contains that refactor" 防止不必要的 retry-loop 重写。
- §6.2 的 CN/HK 4xx policy 声明消除了与 SEC 的不对称疑问。
- §3.2 和 §8.2 的 PDF helper pair equality 要求确保 `FILE_FAILED` 和 `FILING_FAILED` 完全一致。

---

## 7. Residual Risks

| 风险 | 严重度 | 状态 |
|---|---|---|
| `_candidate_failure_facts` 删除后父 workflow 的 per-candidate catch 需验证 | 低 | §8.2 已有 same-source reuse 测试 |
| CnDownloadFilingError（RuntimeError 子类）进入 helper 时的映射 | 低 | 映射为 "filing_execution_failed"，语义正确 |
| DS review 的 CNINFO/HKEX "需要 from-zero 重构" 基于 review-trigger baseline | 低 | 修订后 amendment 正确区分 review trigger 与 current dirty diff 状态 |

所有 residual risk 均为低严重度且有对应的验证手段。

---

## 8. 结论

**PASS。**

原 review F01-F03 全部 resolved。DS F01-F03 全部 resolved。controller 裁决未改变 owner/allowlist/schema/stop conditions 实质范围。无新增 finding。

修订后的 amendment 在以下关键方面达到了可直接实施的规格：
1. §6.2 retry-loop 重构描述已修正为 "verify existing" 而非 "from-zero rewrite"（F01 resolved）。
2. §3.1 `_is_cancel_requested` 的 concern 已通过 §4 裁决表澄清为当前已有行为（F02 resolved）。
3. §5.2 `sec_download_filing_workflow.py` 已标注为 "已实现，待验证/必要时仅修失败"（F03 resolved）。
4. §5.2 所有 SEC/CN 文件均有明确的实现状态标签（DS F01 resolved）。
5. §6.2 CN/HK 4xx policy 已显式声明（DS F02 resolved）。
6. §3.2/§8.2 PDF helper pair equality 已显式要求（DS F03 resolved）。

amendment 可以进入 implementation。

**Review 结论**: PASS
**输出路径**: `docs/reviews/plan-review-20260810-slice2-cn-owner-mimo-rereview.md`
