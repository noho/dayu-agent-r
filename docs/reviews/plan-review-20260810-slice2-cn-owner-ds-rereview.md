# wu-cli-download-01 Slice 2 Stop-Condition Amendment — DS Re-Review

## 审查元数据

| 项 | 值 |
|---|---|
| 审查类型 | 原 reviewer（DS）re-review — 对照原 artifact `plan-review-20260810-slice2-cn-owner-ds.md` F01-F03 及 MiMo 裁决逐项核验 |
| 审查目标 | 已修订 `docs/gateflow/wu-cli-download-01-slice2-plan-amendment-20260810-030216.md` |
| 原 review | `docs/reviews/plan-review-20260810-slice2-cn-owner-ds.md`（PASS-WITH-RISKS，F01 中 / F02 低 / F03 低） |
| 基线 HEAD | `c6829400a5e37892464a614590062511554f9633` |
| 审查日期 | 2026-08-10 |
| 审查人 | AgentDS（原 reviewer） |
| 产品/测试修改 | 无 |
| 提交 | 无 |

## 修订变更摘要

相对于本 reviewer 初审时的 amendment 版本，修订版主要变更：

- **§3.4**: SEC auxiliary 裁决表新增 "Review-trigger behavior" 列，与 "修订后 owner 与结果" 列形成基线→终态对照
- **§3.2**: PDF catch 部分新增 bold 声明："PDF catch 必须只调用 helper 一次；`FILE_FAILED` 与 `FILING_FAILED` 的 `reason_code` 和 `reason_message` 两个字段都必须逐值复用这同一个返回 pair。不得保留 `FILE_FAILED.reason_code='pdf_download_failed'` 或只共享 message。"
- **§4**: 新增 Review Adjudication Clarification 表，逐条描述 MiMo F01-F03 和 DS F01-F03 的最终裁决与澄清
- **§5.1**: 既有 dirty production files 每项增加状态标签（"current dirty diff 已完成...恢复后验证，必要时只修对应失败"）
- **§5.2**: 从 "New production additions" 改为 "Additional in-scope production owners"，每文件附加显式实现状态标签：`已实现，待验证/必要时仅修失败` / `尚待实施的 owner 修复` / `部分已实现，剩余 owner 迁移`
- **§6.2**: 新增 CN/HK 4xx fail-fast policy 说明段，明确该策略仅适用本 WU、不扩张到 SEC
- **§6.3**: PDF exception boundary 部分新增 bold 声明要求一次 helper 调用、两事件逐值复用
- **§6.5**: 新增 preamble 声明 SEC 侧已在 current dirty diff 实现，恢复后只验证
- **§8.2**: PDF direct owner test 新增 bold 断言要求 `FILE_FAILED` 和 `FILING_FAILED` 的 `reason_code` 和 `reason_message` 精确相等
- **§11**: 新增 stop-condition re-review adjudication 总结段

---

## 逐 Finding 对照裁决

### F-01（原 中）— SEC allowlist 状态模糊 → RESOLVED

**原问题**: amendment §3.4/§6.5 描述的 SEC auxiliary 修复大部分已在 Slice 2 实现，但 §5.2 未区分"验证存在"与"新增实现"，allowlist 状态模糊。

**修订内容**:

1. §3.4 表增加 "Review-trigger behavior" 列——明确区分触发 amendment 的基线问题与修订后终态。表头注释说明"当前 dirty diff 已完成的部分按 §§5/6.5 只验证"。

2. §5.1 每项文件增加状态标签，例如：
   - `sec_downloader.py` — "current dirty diff 已包含 C01 auxiliary propagation 与 safe diagnostics；恢复后按 §8.4 验证，必要时只修对应失败"
   - `sec_pipeline.py` — "current dirty diff 已包含 C01 historical-submissions propagation 与 6-K safe diagnostics；恢复后按 §8.4 验证既有 filing-local state transition"

3. §5.2 重命名为 "Additional in-scope production owners proved necessary by the call chain"，并在节首说明"'Additional in-scope' 表示 call chain 证明这些 owner 可在本 review-fix 中修改，不表示每个文件都还有待新增实现。当前状态逐项如下："。每文件标注：
   - `cninfo_downloader.py` — **已实现，待验证/必要时仅修失败**
   - `hkexnews_downloader.py` — **已实现，待验证/必要时仅修失败**
   - `cn_download_filing_workflow.py` — **尚待实施的 owner 修复**
   - `cn_download_workflow.py` — **部分已实现，剩余 owner 迁移**
   - `cn_download_rebuild.py` — **已实现，待验证/必要时仅修失败**
   - `sec_download_filing_workflow.py` — **已实现，待验证/必要时仅修失败**

4. §6.5 preamble: "Current dirty diff 已包含本节...恢复后以 §8.4 direct-owner tests 验证；只有真实失败才在原 allowlist owner 内最小修正，不得把已正确行为当作待新增功能重写。"

5. §11: "DS F01 is resolved by per-owner implementation-state labels"

**核验**: 每个在 scope 内的 production 文件现在都有显式状态标签，精确区分三种状态：
- **已实现，待验证/必要时仅修失败**（6 个文件中的 4 个 SEC 侧 + cninfo/hkex + rebuild）
- **尚待实施的 owner 修复**（`cn_download_filing_workflow.py`）
- **部分已实现，剩余 owner 迁移**（`cn_download_workflow.py`）

实现 agent 不会再误解哪些文件需要新增代码、哪些只需要验证。`sec_download_filing_workflow.py` 明确标注"已实现，待验证/必要时仅修失败"并注明"本 amendment 不要求再次改写该 catch"。

**判定**: **RESOLVED。** per-owner 实现状态标签完全消除了原 F-01 的模糊性。

---

### F-02（原 低）— CN/HK 4xx 行为与 SEC 不对称未说明理由 → RESOLVED

**原问题**: amendment §6.2 分类表要求 CN/HK 4xx 立即停止，但未说明与 SEC 4xx 行为（继续重试循环）的差异理由。

**修订内容**:

§6.2 新增独立说明段（line 255）：
> "CN/HK 对 4xx 的'一次请求后立即停止'是本 WU 明确采用的 fail-fast non-retryable policy，不是从 SEC retry loop 推导出的共享规则。SEC 当前对 4xx 的既有 retry-policy 差异不在这次 CN filing-owner amendment 中扩张或统一；如需改变 SEC policy，必须由另一个明确授权的 plan amendment 处理。"

§4 DS F02 disposition: "§6.2 states that CN/HK 4xx fail-fast is this WU's non-retryable policy. The SEC retry-policy difference is deliberately unchanged and outside this owner amendment."

§11: "DS F02 is resolved by the explicit CN/HK-only 4xx fail-fast policy with no SEC expansion"

**核验**: 不对称被明确记录为刻意设计选择：
- CN/HK 采用 fail-fast non-retryable policy（本 WU 决策）
- SEC 保持既有行为（不在本 amendment scope）
- 如需统一，需要另一个独立授权的 plan amendment

这消除了实现 agent 在参考 SEC 实现时遇到行为不一致而产生的困惑。

**判定**: **RESOLVED。** 4xx 策略差异已显式说明为刻意非对称设计，scope 边界清晰。

---

### F-03（原 低）— `FILE_FAILED` reason_code 与 helper 对齐不明确 → RESOLVED

**原问题**: amendment 要求 `FILE_FAILED` 和 `FILING_FAILED` 都使用同一 helper，但未明确 `FILE_FAILED` 的 `reason_code` 是否也应从 helper 派生（替代硬编码的 `"pdf_download_failed"`）。

**修订内容**:

§3.2 owner decision（line 71，bold 原文）：
> "**PDF catch 必须只调用 helper 一次；`FILE_FAILED` 与 `FILING_FAILED` 的 `reason_code` 和 `reason_message` 两个字段都必须逐值复用这同一个返回 pair。** 不得保留 `FILE_FAILED.reason_code='pdf_download_failed'` 或只共享 message。"

§6.3（line 267，bold 原文）：
> "**PDF exception boundary calls the helper exactly once；both `FILE_FAILED` and `FILING_FAILED` must copy both values of that single `(reason_code, reason_message)` pair without override or recomputation.**"

§8.2 provenance matrix（line 321，bold 原文）：
> "**PDF additionally asserts one helper call and exact equality of both `reason_code` and `reason_message` across `FILE_FAILED` and `FILING_FAILED`—neither field may retain a PDF-specific override.**"

§4 DS F03 disposition: "§3.2 and §§6.3/8.2 now make the existing decision visually explicit: one helper invocation supplies both `reason_code` and `reason_message` to both PDF terminal events."

§11: "DS F03 is resolved as already specified by the single helper-pair requirement for both PDF terminal events"

**核验**: 三处（§3.2、§6.3、§8.2）均以 bold 原文明确要求：
- Helper 只调用一次
- `FILE_FAILED` 和 `FILING_FAILED` 的 `reason_code` 和 `reason_message` 均从同一次 helper 调用返回的 pair 取值
- 明确禁止保留 `FILE_FAILED.reason_code='pdf_download_failed'`
- 明确禁止只共享 message 而不同享 reason_code
- §8.2 测试要求断言跨两事件的精确相等

这比本 reviewer 原建议（"明确 `FILE_FAILED` 的 `reason_code` 也应从 helper 派生"）更严格——不仅要求同源派生，还要求精确的逐值复用和零覆盖。

**判定**: **RESOLVED。** `FILE_FAILED`/`FILING_FAILED` 的 `(reason_code, reason_message)` 对必须从同一次 helper 调用精确逐值复用，三处均有 bold 原文声明和测试断言。

---

## MiMo F01-F03 裁决验证

§4 和 §11 明确记录了 MiMo 三条 finding 的最终裁决，逐条验证未改变 owner/allowlist/schema/stop conditions：

| Finding | 裁决 | Owner 变化？ | Allowlist 变化？ | Schema 变化？ | Stop condition 变化？ |
|---|---|---|---|---|---|
| MiMo F01 | CNINFO/HKEX retry loops 已在 dirty diff，验证非重写 | 无 — downloader 仍为 owner | 无 — 文件仍在 §5.2，状态标签更新为"已实现" | 无 | 无 |
| MiMo F02 | `_is_cancel_requested` 已是 no-catch pass-through，保留回归测试 | 无 — 函数仍在 `cn_download_workflow.py` | 无 — 文件已在 allowlist | 无 | 无 |
| MiMo F03 | `sec_download_filing_workflow` 已有 typed filing-local catch，标注为 implemented-and-pending-verification | 无 — 文件仍为 blast-radius owner | 无 — 文件仍在 §5.2，状态标签更新 | 无 | 无 |

§11 总结行确认："No finding changes owner、allowlist、schema or stop-condition scope"

**判定**: **确认。** MiMo F01-F03 裁决均为纯状态澄清（从 "from-zero rewrite" 降级为 "verification + failure-driven correction" 或标注 "already implemented"），未改变任何 owner、allowlist 成员、schema 定义或 stop condition 语义。

---

## 专项复验

### 1. Per-owner 实现状态标签完备性

**PASS。** 修订版在三个层面覆盖了实现状态：

| 层级 | 位置 | 覆盖内容 |
|---|---|---|
| 既有 dirty production（§5.1） | 5 个文件 | 每项标注 "current dirty diff 已完成...恢复后验证，必要时只修对应失败" |
| Additional in-scope（§5.2） | 6 个文件 | 每项标注 "已实现"/"尚待实施"/"部分已实现" + 具体说明 |
| SEC owner section（§6.5） | 整节 preamble | "Current dirty diff 已包含本节...恢复后以 §8.4 direct-owner tests 验证" |

所有文件状态形成闭包：真正需要新增 production 代码的只有 `cn_download_filing_workflow.py`（新增 `project_cn_filing_failure` + 替换两处 `str(exc)`）和 `cn_download_workflow.py`（替换 import + 删除 `_candidate_failure_facts`）。

### 2. Stop conditions 与修订自洽性

**PASS。** 8 条 stop condition 未变。修订版的状态标签、policy 说明和 test assertions 均与 stop conditions 一致：

- Stop Condition 1（不修改 excluded file）：§5.2 `sec_download_filing_workflow.py` 标注"已实现，待验证"，明确"本 amendment 不要求再次改写该 catch"
- Stop Condition 4（三层 blast radius 封闭）：§3.4 表 + §6.5 preamble 确认 SEC 侧已在 dirty diff；§8.4 tests 验证而非重写
- Stop Condition 6（retry-loop 不改变 bounded count）：§6.2 分类表锁定行为 + "CN/HK 4xx fail-fast policy" 段明确 scope 边界

### 3. `FILE_FAILED`/`FILING_FAILED` 同源复用证明链

**PASS。** 修订版在三处形成完整证明链：

- **设计规格**（§3.2/§6.3）: bold 声明一次调用、两事件逐值复用、禁止保留 PDF-specific override
- **测试断言**（§8.2）: bold 声明 exact equality assertion across both events + one helper call verification
- **静态扫描**（§9）: `project_cn_filing_failure` exactly one definition；no `reason_message=str(exc)` in PDF/Docling rows

三层证据互相印证，无遗漏。

### 4. 无新增 material finding

对修订版全文做 adversarial scan，**无新增 material finding**。

本 reviewer 初审的三条 finding（F-01/F-02/F-03）已被修订版逐条关闭。MiMo 初审的七条 finding（F01-F07）和三条 OQ 已在前两轮 re-review（MiMo `032712.md`、DS `032848.md`）中全部 resolved。本轮修订未引入新的 owner/allowlist/schema/stop-condition 变更。

---

## Residual Risks（更新后）

| 风险 | 严重度 | 状态 |
|---|---|---|
| 恢复 implementation 后 unknown-`httpx` 测试构造仍需收敛 | 低 | §11 确认为 "fixed in current slice once implementation resumes"，两个失败来自测试构造而非 production 行为 |
| `cn_download_workflow.py` 的 parent import + delete `_candidate_failure_facts` 迁移需要确保 per-candidate leak catch 调用点全部更新 | 低 | §9 static scan 覆盖 `_candidate_failure_facts` 残留检查；§8.2 要求 parent same-source test |
| CN/HK retry loop "已实现"状态需要恢复 implementation 后通过 §8.1 transport matrix 验证 | 低 | §5.2/§6.2 明确"已实现，待验证/必要时仅修失败"；§8.1 测试矩阵覆盖 |

全部为低严重度，均有对应的验证手段。

---

## Final Plan Review Conclusion

**PASS**

原 DS review（`plan-review-20260810-slice2-cn-owner-ds.md`）的三条 finding 全部 RESOLVED：

- **F-01（原 中）**: per-owner 实现状态标签（已实现/尚待实施/部分已实现）消除了 SEC allowlist 模糊性
- **F-02（原 低）**: CN/HK 4xx fail-fast policy 段明确记录为刻意非对称设计，scope 边界清晰
- **F-03（原 低）**: §3.2/§6.3/§8.2 三处 bold 声明要求 `FILE_FAILED`/`FILING_FAILED` 的 `(reason_code, reason_message)` 对从同一次 helper 调用精确逐值复用

MiMo F01-F03 裁决验证通过：均为状态澄清，未改变 owner/allowlist/schema/stop-condition scope。

无新增 material finding。无未闭合 finding。

Amendment 可以进入 implementation。

**Review 结论**: PASS
**输出路径**: `docs/reviews/plan-review-20260810-slice2-cn-owner-ds-rereview.md`
