# UF-FIX11 S3 Direct Projection Symbol-Boundary Amendment — Directed Re-Review

## Review metadata

- reviewer：MiMo（directed re-review）
- date：2026-08-17
- timestamp：20260817-152609
- reviewed target：`docs/gateflow/uf-fix11-s3-projection-boundary-amendment-20260817.md`（post-fix 版本）
- initial reviews：
  - `docs/reviews/uf-fix11-s3-projection-boundary-review-mimo-20260817.md`（MiMo initial）
  - `docs/reviews/uf-fix11-s3-projection-boundary-review-ds-20260817.md`（DS initial）
- controller adjudication + fix：`docs/gateflow/uf-fix11-s3-projection-boundary-review-fix-20260817.md`
- blocker：`docs/gateflow/uf-fix11-s3-projection-boundary-blocker-20260817.md`
- parent plan：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- code evidence：`dayu/fins/ingestion_runtime.py`、`dayu/fins/direct_events.py`
- scope：只读 re-review。未修改 production/test/README/plan；只新增本 artifact。

## Re-review task

逐项确认 MiMo Finding-001、DS F-01~F-04 已真正关闭；DS F-05 rejected-with-reason 是否保持 fail-closed owner；检查无新 scope/owner/test/gate 问题。

---

## 1. MiMo Finding-001：observation helpers 未在 frozen boundary 中显式列举

### 判定：CLOSED

**fix 内容**：amendment 新增 § "Test and static contract" 末尾段（L81-83）：

> `_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed` 是非 SUCCESS observation 构造点，保持 `FinsResultSummary.warnings=()` 的自然空状态；S3 禁止修改这三个函数。它们不属于 direct typed copy symbol 白名单。

**验证**：

- 三个 observation helpers（L7229、L7284、L7333）被显式列举并冻结。
- "S3 禁止修改这三个函数" 明确排除了 implementation agent 为"一致性"添加显式 `warnings=()` 的可能。
- "它们不属于 direct typed copy symbol 白名单" 与 § "Direct typed copy symbols" 的三个 symbol 白名单一致。
- review-fix artifact（L25-26）确认 `ACCEPT / FIXED`。

**残余**：无。

---

## 2. DS F-01：S3 测试枚举缺两类 contract 红测与两个空值投影用例

### 判定：CLOSED

**fix 内容**：amendment § "Test and static contract" 重写（L69-76）：

1. `test_fins_ingestion_runtime.py` 覆盖 `FinsUploadResultSummary` 的 exact-element、at-most-one 与 `ok`/`skipped` success-only invariant（L69-70）。
2. 非精确元素、超过一个、`failed`/`cancelled`/`deleted` + 非空都拒绝（L70）。
3. uploaded/skipped exact warning copy、uploaded 空值 exact copy、failed/cancelled/deleted 与 generic non-upload 空值（L71-72）。
4. CANCELLED + 非空 direct result fail closed（L72）。

**逐点验证**：

| DS F-01 子项 | fix 覆盖 | 证据 |
|--------------|----------|------|
| 两个 summary 的 constructor 红测 | ✓ | L69-70：exact-element、at-most-one、success-only invariant 红测 |
| deleted 排除出 success 集合 | ✓ | L70：`deleted` + 非空拒绝；L61-62：amendment pin success = `ok`/`skipped` |
| uploaded 空值 exact copy | ✓ | L71："uploaded 空值 exact copy" |
| deleted 空值投影 | ✓ | L72："failed/cancelled/deleted 与 generic non-upload 空值" |

**残余**：无。

---

## 3. DS F-02：AST 结构测试须断言 callsite 全集枚举

### 判定：CLOSED

**fix 内容**：amendment § "Test and static contract"（L73-74）：

> 同一文件的 AST contract 穷举 `ingestion_runtime.py` 中 `_direct_result_event` 的全部 `Call` 节点：数量必须 exact 为两个，warnings 实参集合必须 exact 为 `summary.warnings` 与 `()`；新增任何 callsite 立即红。

**验证**：

- "穷举全部 `Call` 节点" — 明确要求 AST 全集扫描，非逐点断言。
- "数量必须 exact 为两个" — 穷举 + 数量约束 = 全集枚举。
- "warnings 实参集合必须 exact 为 `summary.warnings` 与 `()`" — 实参值也被 pin。
- "新增任何 callsite 立即红" — 红测语义明确。
- review-fix artifact（L18-19）确认 `ACCEPT / FIXED`。

**残余**：无。

---

## 4. DS F-03：`FinsUploadResultSummary.warnings` 是否带默认值未 pin，成功集合语义未 pin

### 判定：CLOSED

**fix 内容**：amendment § "Public summary empty state"（L60-63）：

> `FinsUploadResultSummary.warnings` 同样使用 `tuple[CompanyMetadataWarning, ...] = ()`，但 service projection 必须显式传 `result.warnings`，不得依赖默认值。它的可携带 warning 状态闭集精确为 `ok`/`skipped`；`failed`/`cancelled`/`deleted` 必须为空。

**逐点验证**：

| DS F-03 子项 | fix 覆盖 | 证据 |
|--------------|----------|------|
| `FinsUploadResultSummary.warnings` 默认值 | ✓ | L60：`= ()` |
| service projection 显式传值 | ✓ | L60-61："service projection 必须显式传 `result.warnings`，不得依赖默认值" |
| success 集合 pin | ✓ | L61-62："闭集精确为 `ok`/`skipped`；`failed`/`cancelled`/`deleted` 必须为空" |
| 与 S1+S2 pipeline invariant 对齐 | ✓ | L61：`ok`/`skipped` 与 S1+S2 冻结的 `FinsUploadPipelineResult` invariant 一致 |

**残余**：无。

---

## 5. DS F-04：direct copy 测试落位与 `test_fins_direct_stream.py` 既有文件职责冲突

### 判定：CLOSED

**fix 内容**：amendment § "Test and static contract"（L67-76）重新按 owner 分工：

- `test_fins_ingestion_runtime.py`（L69-74）：`FinsUploadResultSummary` invariant、upload warning copy、AST contract。
- `test_fins_direct_stream.py`（L75-76）：只覆盖 `FinsResultSummary` public invariant 与 stream contract；禁止 import ingestion runtime private helper。

**验证**：

- runtime helper / AST 测试落位 `test_fins_ingestion_runtime.py` — 与该文件已有先例（L678 `_upload_result_details` owner 测试）一致。
- `test_fins_direct_stream.py` 职责被精确限定为 public invariant + stream contract — 不混合 runtime helper 内部测试。
- "禁止 import ingestion runtime private helper" — 防止职责穿透。
- review-fix artifact（L20-21）确认 `ACCEPT / FIXED`。

**残余**：无。

---

## 6. DS F-05：`_direct_result_event` CANCELLED 归一化分支未同步归零 warnings — REJECTED-WITH-REASON

### 判定：REJECTED-WITH-REASON 有效，fail-closed owner 保持

**controller 裁决**（review-fix L23-24）：

> DS F-05：`REJECTED-WITH-REASON`。CANCELLED + nonempty warning 是非法 typed producer 组合，必须由 public constructor fail closed；helper 静默清空会掩盖 owner violation。计划增加直接拒绝红测，不修改 helper 归一化。

**验证 fail-closed owner 保持**：

1. **amendment L62-63**："_direct_result_event 收到 CANCELLED + 非空 warning 时禁止静默归零，必须让 FinsResultSummary constructor invariant fail closed。" — 明确禁止 helper 层清空，要求 constructor 层拒绝。
2. **amendment L72**："CANCELLED + 非空 direct result fail closed" — 红测覆盖。
3. **fail-closed 语义正确性**：CANCELLED + 非空 warning 是非法 producer 组合（§8.5："cancel 不产生 warning"）。若 helper 静默清空，非法组合不会被发现，owner violation 被掩盖。constructor fail closed 确保非法组合立即暴露。
4. **与既有 CANCELLED 归一化风格的关系**：`_direct_result_event` 的 CANCELLED 归一化（L6465-6482）覆盖 details/error_kind/error_message/download/failure。这些字段的归零是因为 CANCELLED 语义要求它们为空（不是非法组合）。warnings 不同：CANCELLED + 非空 warning 是非法输入，不是"需要归零的合法输入"。因此不归零、让 constructor 拒绝是正确选择。
5. **红测覆盖**：test plan 要求 CANCELLED + 非空 → constructor raise。这比 helper 归零更安全：测试直接验证非法组合被拒绝，而非验证归零后的值。

**残余**：无。F-05 的 rejected-with-reason 逻辑成立，fail-closed owner 由 constructor invariant + 红测双重保证。

---

## 7. 新 scope/owner/test/gate 问题检查

### 7.1 Scope 检查

- production allowed files 全集不变（amendment L30）。
- test allowed files 全集不变（amendment L67）。
- README allowed files 不变（amendment 未触碰 README 决策）。
- Host/Engine/material/oracle/scenario/frozen evidence 不变（amendment L33）。
- **结论**：无 scope leak。

### 7.2 Owner 检查

- warning semantic owner 仍为 `company_meta_contract.py`（domain fact）→ `company_metadata_warning.py`（public projection）。
- direct typed copy owner 为 `ingestion_runtime.py::_direct_upload_terminal_events`（upload path）和 `ingestion_runtime.py::_direct_result_event`（projection point）。
- `FinsResultSummary` public invariant owner 为 `direct_events.py`。
- `FinsUploadResultSummary` summary invariant owner 为 `ingestion_runtime.py`。
- test owner 按文件分工明确（L67-76）。
- **结论**：无 semantic owner drift。

### 7.3 Test 检查

- invariant 红测：`FinsResultSummary` 和 `FinsUploadResultSummary` 的 exact-element、at-most-one、success-only + 非空拒绝（L69-70）。
- projection 正例：uploaded/skipped exact copy、uploaded 空值 copy、deleted/cancelled/failed/generic 空值（L71-72）。
- CANCELLED + 非空 fail closed（L72）。
- AST 穷举 callsite 全集（L73-74）。
- public invariant + stream contract（L75-76）。
- **结论**：测试规格完整，无缺口。

### 7.4 Gate 检查

- gate order：initial review → controller adjudication + fix → re-review → acceptance → plan-gate commit → S3 implementation。
- plan-gate commit boundary：只允许 docs（amendment L90-98）。
- stop condition：不修改 Host/Engine、不从 raw fields 推断、不扩大文件范围（amendment L78-79）。
- **结论**：gate order 完整，commit boundary 清晰。

---

## 8. Amendment 内部一致性复核

| 维度 | 一致性 |
|------|--------|
| Motivation ↔ frozen boundaries | ✓：symbol 漏列问题，只扩大白名单 |
| Symbol list ↔ parameter strategy | ✓：三个 symbol，upload exact / generic explicit `()` |
| `FinsResultSummary.warnings=()` ↔ `FinsUploadResultSummary.warnings=()` | ✓：两者都带默认，producer/helper 层仍必填 |
| Success set pin ↔ S1+S2 pipeline invariant | ✓：`ok`/`skipped` 一致 |
| Test owner 分工 ↔ allowed files | ✓：两个 test 文件都在 allowed list |
| CANCELLED fail-closed ↔ rejected F-05 | ✓：constructor invariant + 红测，不清空 |
| observation helpers 冻结 ↔ symbol 白名单 | ✓：L81-83 显式冻结，不在白名单内 |
| Stop condition ↔ frozen boundaries | ✓：不修改白名单外 producer |
| Residual classification ↔ review findings | ✓：无未分类 residual |

---

## 9. Residual risks

| 风险 | 分类 | 说明 |
|------|------|------|
| CANCELLED + 非空 warning 的 constructor invariant 实现 | `covered by resumed S3` | `FinsResultSummary.__post_init__` 需新增校验；红测覆盖 |
| `FinsUploadResultSummary.__post_init__` success-only invariant 实现 | `covered by resumed S3` | 需新增 `ok`/`skipped` only 校验；红测覆盖 |
| AST 穷举测试的 robustness（Call 节点匹配精度） | `covered by resumed S3` | 实现时需确保 AST visitor 正确识别 `_direct_result_event` 调用 |
| observation helpers 不被误改 | `covered by resumed S3` | L81-83 显式冻结 + stop condition 隐含禁止 |

所有 residual 均属于 S3 implementation 范畴，amendment 层面无需额外处理。

---

## 10. Conclusion

**PASS**

逐项确认结果：

| Finding | 判定 | 说明 |
|---------|------|------|
| MiMo Finding-001 | CLOSED | observation helpers 在 L81-83 显式冻结 |
| DS F-01 | CLOSED | constructor 红测、deleted/empty 投影用例已补齐 |
| DS F-02 | CLOSED | AST 穷举 callsite 全集，exact 两个，新增即红 |
| DS F-03 | CLOSED | `FinsUploadResultSummary.warnings=()` pinned，success=`ok`/`skipped` pinned |
| DS F-04 | CLOSED | runtime helper/AST 测试落位 `test_fins_ingestion_runtime.py` |
| DS F-05 | REJECTED-WITH-REASON 有效 | CANCELLED + 非空 → constructor fail closed，不清空；红测覆盖 |

无新 scope/owner/test/gate 问题。amendment 内部一致，所有 initial review findings 已按 controller 裁决收口。S3 implementation 可在 plan-gate commit 后恢复。
