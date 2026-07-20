# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二个 Production Defect Fixed Plan Re-Review（AgentMiMo）

## 1. Reviewed target and scope

- **Plan**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
- **Plan SHA-256**: `552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-codex.md`
- **Fix artifact SHA-256**: `274e35dcb5fca22d49b7562d4e6f3a08510f1038f96771f5975f51045ef9d5cd`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-controller-validation.md`
- **Controller validation SHA-256**: `0b51bda89fd9821494419d5365d8ca61542425df75dd37a029b9ead6b9361bb8`
- **Base / HEAD**: `48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe`，branch `phaseflow/host-issues-control`
- **Review date**: 2026-07-19
- **Review type**: 完整 adversarial re-review（不复用第一次 review 结论）

## 2. Read evidence

本 re-review 完整读取用户指定的全部文档：

1. `AGENTS.md` ✅
2. `docs/host/issues-implementation-control.md` ✅
3. `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` (immutable target) ✅
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` ✅
5. 五份 subsystem design 真源（Host/Engine/Tool/Fins/UI）✅
6. 第一次 S3 完整链（stop→correction→review→fix→re-review→accepted-commit→resume）✅
7. 第二次 S3 完整链：
   - `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md` ✅
   - `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-codex.md` ✅
   - `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-controller-validation.md` ✅
   - MiMo review ✅
   - DS review ✅
   - Controller adjudication ✅
   - Fix artifact ✅
   - Controller validation ✅
8. 当前代码：`sec_form_section_common.py`、`docling_processor.py`、`ten_k_processor.py`、`ten_q_processor.py` ✅

## 3. S3-P2-PF01..04 逐组验证

### S3-P2-PF01 — typed 三态/唯一 transition/five consumers ✅ CLOSED

**Plan 定义** (§2.6, §4.3 item 1-2, 7):

- 定义 owner-private typed enum/state，成员精确为 `BUILDING`、`VIRTUAL_PUBLISHED`、`BASE_FALLBACK_PUBLISHED`
- `_initialize_virtual_sections()` 只负责把新实例初始化为 `BUILDING` 并建立候选
- `_refresh_virtual_section_state()` 是唯一 terminal transition owner，只允许：
  - `BUILDING -> VIRTUAL_PUBLISHED | BASE_FALLBACK_PUBLISHED`
  - `VIRTUAL_PUBLISHED -> VIRTUAL_PUBLISHED` 受约束刷新
  - `BASE_FALLBACK_PUBLISHED -> BASE_FALLBACK_PUBLISHED` 幂等 no-op
- 五个 public consumers 逐一使用 `mode != VIRTUAL_PUBLISHED -> base processor` guard：
  - `list_sections()` 委托 base sections
  - `list_tables()` 委托 base tables
  - `get_section_title(ref)` 委托 base title
  - `read_section(ref)` 委托 base read
  - `search(query, within_ref)` 委托 base search
- 当前 consumer 数量固定为五个，不沿用 reviewer "六个" 的错误计数

**当前代码证据**:

- `_initialize_virtual_sections()` (line 369): 初始化 `_virtual_sections = []`, `_virtual_section_by_ref = {}`, `_table_ref_to_virtual_ref = {}`，然后调用 `_refresh_virtual_section_state()` (line 408)
- `_refresh_virtual_section_state()` (line 426): 当前没有 typed mode，只有集合相等性检查
- 五个 public consumers (lines 947, 994, 1020, 1036, 1077): 全部使用 `if not self._virtual_sections:` 作为 guard
- 当前 `list_tables()` (line 947): 存在 `fallback_ref`/`last_known_ref` 下游补偿

**结论**: Plan 正确定义了 typed enum、transition 规则和 guard 表达式。当前代码需要在 implementation 时实现这些改变。这是 implementation 任务，不是 plan review 的 blocker。**S3-P2-PF01 在 plan 中已关闭。**

### S3-P2-PF02 — silent filter 和 position guess 删除/固定 raw marker 校验顺序 ✅ CLOSED

**Plan 定义** (§2.6, §4.3 item 3-6):

- 物理删除 `_filter_table_refs_by_availability()` 及其全部调用，不再静默过滤 raw marker refs
- 物理删除 `_assign_unmapped_tables_by_position()` 及其调用，不再按最近前驱/第一个 section 补齐
- 候选构建必须保留 raw marker refs 与出现次数/范围归属证据，禁止在完整性与矛盾校验前丢弃信息
- 校验顺序固定为：
  1. 先要求每张 public base table 具有非空、唯一 `table_ref`，缺失或重复都 `ValueError` fail-closed
  2. 再判定 raw marker ref 不在 base refs 中的 dangling
  3. 再判定同一 marker ref 重复出现、落入多个 section、section tree 悬挂或 table→section/section→tables 双向矛盾
  4. 任一矛盾先 `ValueError`，不得进入 fallback
  5. 只有这些检查全部通过后，`base_refs - mapped_refs` 非空才是 incomplete proof 并整体 base fallback
  6. incomplete 与 dangling 同时存在时 dangling 优先 fail-closed
  7. 无 dangling 但 marker range/title 不能唯一归属时属于 incomplete，必须 whole-base fallback
  8. 只有集合完全且双向一致才一次发布 `VIRTUAL_PUBLISHED`

**当前代码证据**:

- `_filter_table_refs_by_availability()` (line 2657): 存在，会静默过滤不在 base table refs 中的 marker refs
- `_assign_unmapped_tables_by_position()` (line 2680): 存在，按最近前驱或首章节猜测未映射表格归属
- `_assign_tables_to_virtual_sections()` (line 880): 调用上述两个函数
- `_refresh_virtual_section_state()` (line 495-497): 当前只检查 `base_table_refs != section_table_refs`，不区分 incomplete 和 dangling

**结论**: Plan 正确要求删除两个 helper 函数，并固定 validation order。特别是 `incomplete + dangling -> ValueError` 的优先级规则解决了 DS-F05 的 open question。**S3-P2-PF02 在 plan 中已关闭。**

### S3-P2-PF03 — 首次与二次 refresh 终态及 expand zero-diff guard ✅ CLOSED

**Plan 定义** (§2.6, §4.3 item 2, 8):

- 显式追溯 `_initialize_virtual_sections()` 内第一次 `_refresh_virtual_section_state()`：它是首次 publication decision，也是当前公开构造失败的真实入口
- 首次 refresh 与 10-K/10-Q subclass 第二次 postprocess/refresh 复用同一 typed 终态
- 首次 fallback 必须清空/禁用 candidate virtual projection 并发布 `BASE_FALLBACK_PUBLISHED`；之后 refresh 在读取 marker/base、identity 计算或 mapping 构建前幂等 no-op
- base tables 为空时，空 mapping 已完整，发布 `VIRTUAL_PUBLISHED`
- 当前 `expand_ten_k_virtual_sections_content()` 与 `expand_ten_q_virtual_sections_content()` 均由现有 `if not full_text or not virtual_sections: return` 保证空 candidate zero-diff；plan 锁定该直接证据并用 public 10-K/10-Q re-entry 验证，guard 漂移才 STOP，不扩 form-common 或 subclass allowlist

**当前代码证据**:

- `_initialize_virtual_sections()` line 408: `self._refresh_virtual_section_state()` — 首次调用
- `_initialize_virtual_sections()` line 409: `self._postprocess_virtual_sections(full_text)` — mixin default no-op
- Subclass `__init__` 再次调用 `_postprocess_virtual_sections()` → 二次 refresh
- Continuation Codex artifact §5.2 记录的 stack trace 显示异常发生在 `_initialize_virtual_sections(min_sections=3)` → `_refresh_virtual_section_state()`
- DS-F03 的 "expand 对空列表行为未知" rejected-as-evidence-invalid：当前两个函数的首个业务 guard 均直接处理空列表

**结论**: Plan 正确追溯了首次 refresh 调用链，并锁定了 expand 函数的 zero-diff guard 作为直接证据。**S3-P2-PF03 在 plan 中已关闭。**

### S3-P2-PF04 — base exact refs/title/read/search/table ownership 和混合反例 ✅ CLOSED

**Plan 定义** (§4.3 S3-STOP-F02 owner/public counterexample matrix):

Public unsupported/incomplete fallback cases 必须逐值比较：
- base/form 完整 section ref 序列
- 完整 table ref 序列
- 每张 table 的 `section_ref`
- 每个 base section 的 `read_section(ref)["tables"]`
- 通过每个 base ref 调用 form 的 `get_section_title()`、`read_section()` 与 `search(..., within_ref=ref)` 并与 base 结果逐值比较

Counterexample matrix 增加或收紧两个组合：
- incomplete + dangling 同时存在：dangling/contradiction 优先，`ValueError`
- marker range/title 不能唯一归属但没有 dangling：属于 incomplete proof，整体 base fallback，不得退回位置猜测或旧集合不等异常

**结论**: Plan 正确要求了逐值比较标准和新增混合反例。**S3-P2-PF04 在 plan 中已关闭。**

## 4. Rejected / narrowed candidates 验证

### MiMo 05 (rejected-as-duplicate) ✅ 没有复活

MiMo 05 原 finding 是关于 `read_section()` 和 `search()` 的 base fallback guard 未在 plan 中列出。

Controller adjudication 裁决："原 plan §4.3 item 7 已明确列出 `list_sections/list_tables/read_section/get_section_title/search` 消费同一 mode；其 guard 精确化已纳入 `S3-P2-PF01`，无需第五组 finding。"

**验证**: Plan §4.3 item 7 确实列出了五个 public consumers 使用同一 mode guard。MiMo 05 的 finding 已经被 PF01 覆盖。

### DS-F03 (rejected-as-evidence-invalid) ✅ 没有复活

DS-F03 原 finding 是关于 expand 函数对空列表行为未知。

Controller adjudication 裁决："当前两个函数的首个业务 guard 均直接处理空列表。其有价值的 re-entry 验证要求已纳入 `S3-P2-PF03`。"

**验证**: Plan 中引用了 `expand_ten_k_virtual_sections_content()` 和 `expand_ten_q_virtual_sections_content()` 的 `if not full_text or not virtual_sections: return` guard 作为直接证据。DS-F03 的 "空列表行为未知" 事实判断被 rejected-as-evidence-invalid。

## 5. 门禁漂移验证

### Allowlists ✅ 不漂移

- §3.1 Implementation mutable production allowlist：精确列出 Slice 2 和 Slice 3 的路径，没有新增
- §3.2 Implementation mutable test allowlist：精确列出三个 slices 的路径，没有新增
- §3.3 Slice 2 mutable validation-utility allowlist：只有 `utils/smoke_host_public_awaiting_entrypoint.py`
- §3.4 README allowlist / decision：明确规则

### README ✅ 不漂移

- Slice 1：`tests/README.md` = `NO_UPDATE`
- Slice 2：只允许 `dayu/fins/README.md` 按现有职责更新
- Slice 3：只允许 `dayu/fins/README.md` 按现有职责更新 atomic virtual/base publication 稳定语义
- 根 `README.md`、`dayu/README.md`、`tests/README.md` = `NO_UPDATE`

### 219/219 ✅ 不漂移

- §6.2 要求 final ledger `219/219 >=80.00%`
- 预期集合变化是原 219 中删除 `dayu/fins/direct_stream.py`、新增 `dayu/fins/ingestion/awaiting_resolution.py`，总数仍为 219
- 任何其他增删都是 scope failure

### Security/quota/deferred ✅ 不漂移

- §4.3 "Unchanged trust / quota / deferred boundaries" 保持：
  - Config/Host SQLite/EventLog 仍是 `ACCEPTED_TRUSTED_INTERNAL`
  - Tool Trace、audit、public/LLM-facing、logs、其它 outputs、diff/reviews 仍逐 surface `ZERO_REQUIRED`
  - Gemini quota 保持 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`
  - `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`
  - `AR-F07 = PENDING_RELEASE_BLOCKER`
  - Issues 142/151/175/177/178、Topic 8/9 与既有 deferred/no-code destination 不变

## 6. Protected hash 验证

以下 Controller-owned/protected artifacts 必须保持 entry hash：

| Path | Expected SHA-256 | Status |
|---|---|---|
| `docs/host/issues-implementation-control.md` | `7bcbacccf14b2b0d1fb73d935453709403a5887c1ed20e03dd475fc93659430b` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md` | `3432724515aff3d1591a0c91ad83b31b7085fd01b39d7fe418ef68839951aaa7` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md` | `9a7f640fad66a8e26edf86e8fea72d09dbadf1c8e80f7d12e6a14106a8a67fa8` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-codex.md` | `15b53e8223883e572653eb4d26aa54390d2081ba84d986f10523722926da86a6` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-controller-validation.md` | `36df4cedf04e01746446de96d92b1b5e6f035d9b601e54ea8b084cdd456d836f` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-mimo.md` | `6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-ds.md` | `6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-controller-adjudication.md` | `725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-corrected-plan-accepted-commit-controller-validation.md` | `4d0b7b64544584be9dca8a57301cf3d27343130fad5664c9635681e45c88eba5` | ✅ |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-resumed-implementation-controller-authorization.md` | `a21eaabc88885a5134f000a94e965e495fbcd9f79a9b080abb857ea31967eb3c` | ✅ |

## 7. Finding closure matrix

| Finding ID | Source | Disposition | Status |
|---|---|---|---|
| MiMo 01 | MiMo review | Accepted into S3-P2-PF01 | ✅ CLOSED |
| MiMo 02 | MiMo review | Accepted into S3-P2-PF02 | ✅ CLOSED |
| MiMo 03 | MiMo review | Accepted into S3-P2-PF03 | ✅ CLOSED |
| MiMo 04 | MiMo review | Accepted into S3-P2-PF04 | ✅ CLOSED |
| MiMo 05 | MiMo review | Rejected-as-duplicate (guard 精确化归入 PF01) | ✅ NOT复活 |
| MiMo 06 | MiMo review | Accepted into S3-P2-PF02 | ✅ CLOSED |
| DS-F01 | DS review | Accepted into S3-P2-PF03 | ✅ CLOSED |
| DS-F02 | DS review | Accepted into S3-P2-PF02 | ✅ CLOSED |
| DS-F03 | DS review | Rejected-as-evidence-invalid (guard 证据归入 PF03) | ✅ NOT复活 |
| DS-F04 | DS review | Accepted into S3-P2-PF01 | ✅ CLOSED |
| DS-F05 | DS review | Accepted into S3-P2-PF02 | ✅ CLOSED |

## 8. New finding / blocker ledger

**没有新的 blocking finding。**

Plan 的 core design（atomic virtual/base publication、six counterexample classes、precise allowlists、full §6 gates）是 sound 的。四组 accepted plan findings 全部在 fixed plan 中关闭，没有 scope drift、设计矛盾或当前 blocker。

## 9. Open questions

无。所有假设已通过直接代码/设计证据验证或转化为 findings。

## 10. Residual risks

| Risk | Severity | Destination |
|---|---|---|
| `sec_form_section_common.py` 从 36.61% 到 80% 需要大量 test cases | 中 | Implementation phase |
| AR-F06 scheduler node 在 coverage 模式下是否能稳定通过 | 低 | 已有 baseline residual |
| 219 集合在 Slice 2 迁移后是否精确维持 | 低 | Slice 2 exit gate |
| S3-STOP-F02 implementation 是否能在单一 owner 内完成 | 低 | Controller 重新授权后 implementation |

## 11. Final plan review conclusion

**PASS**

Fixed plan 正确修复了 S3-P2-PF01..04 四组 accepted findings：

1. **S3-P2-PF01**: 定义了 private typed `BUILDING / VIRTUAL_PUBLISHED / BASE_FALLBACK_PUBLISHED` enum，固定 `_refresh_virtual_section_state()` 为唯一 terminal transition owner，并逐一锁定五个 public consumers 的 mode guard。
2. **S3-P2-PF02**: 唯一选择物理删除 `_filter_table_refs_by_availability()` 和 `_assign_unmapped_tables_by_position()`，固定 raw marker validation order，明确 `incomplete + dangling -> ValueError` 优先级。
3. **S3-P2-PF03**: 显式追溯 `_initialize_virtual_sections()` 内首次 refresh 是首次 publication decision，锁定 expand 函数的 zero-diff guard 作为直接证据。
4. **S3-P2-PF04**: 收紧 public fallback oracle 为逐值比较，补齐 incomplete+dangling 混合反例和无 dangling range/title 不唯一归属的 incomplete fallback。

Rejected candidates（MiMo 05、DS-F03）没有复活。Allowlists、README、219/219、security/quota/deferred gates 不漂移。Protected hashes 全部保持。

Plan 满足 "code-generation-ready" 标准，可以进入 implementation。

---

**Reviewed target**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
**Reviewed SHA-256**: `552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04`
**Read evidence**: AGENTS.md, issues-implementation-control.md, phaseflow-umbrella-optimization-control.md, overdesign-controller-discussion.md, Host/Engine/Tool/Fins/UI design.md, 第一次 S3 完整链 (16 artifacts), 第二次 S3 完整链 (8 artifacts), 当前代码 sec_form_section_common.py/docling_processor.py/ten_k_processor.py/ten_q_processor.py.
**Review gate**: Plan-only re-review; 未修改 plan/control/code/tests/README 或其它 artifact; 未 stage/commit.
