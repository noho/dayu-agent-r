# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二次 Corrected Plan — Adversarial Plan Review (AgentDS)

## 1. Review identity

- **Reviewer**: AgentDS（独立 adversarial plan review，非 MiMo 复用）
- **Date**: 2026-07-19T17:05:28+08:00
- **Target**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
- **Target SHA-256**: `466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`
- **Gate**: `S3-STOP-F02` second production defect plan correction → dual complete plan review
- **Read evidence**: 完整读取 AGENTS.md、issues-implementation-control.md、phaseflow-umbrella-optimization-control.md、overdesign-controller-discussion.md、五份 design 真源(Host/Engine/Tool/Fins/UI)、plan artifact(完整 879 行)、S3 implementation continuation、S3 second defect Controller adjudication、S3 plan correction Codex、S3 plan correction Controller validation，以及第一次 S3 stop→plan correction→双路 review/fix/re-review→accepted commit→resume 全链。当前代码已核对 `sec_form_section_common.py`(3134行)、`docling_processor.py`(1798行)、`ten_k_processor.py`(91行)、`ten_q_processor.py`(96行)。

## 2. Review scope and posture

本 review 是独立 adversarial plan review，不复用第一次 S3 plan correction 的 MiMo/DS review 结论。重点挑战 plan 指定的：

1. atomic publication 是否可在唯一 owner（`sec_form_section_common.py`）内实现
2. incomplete marker 与 duplicate/dangling/contradictory 分类是否可判定且不吞错
3. base fallback 是否真正同源（复用 base processor 同一套 sections/tables/read contract）
4. 零表格文档语义
5. 10-K/10-Q 二次 postprocess refresh 幂等
6. `list_tables()` 补偿删除后所有 public consumers 一致
7. 六类 counterexamples 是否足以防 half state/猜测归属
8. production/test/README allowlist
9. 219/219 coverage 与全部 §6 门禁
10. security、Gemini quota 与 deferred boundaries

## 3. Assumptions tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | `_refresh_virtual_section_state()` 可在不修改 subclass 的情况下实现幂等 base-fallback no-op | 条件成立，但 plan 未追溯 `_initialize_virtual_sections()` 内首次 refresh（line 408）的调用链 |
| A2 | `_assign_tables_to_virtual_sections()` 可改为仅产生候选 mapping 而不就地污染 public state | 可行，但 plan 未给出该函数的精确改造契约 |
| A3 | `_filter_table_refs_by_availability` 的删除/收紧可在同一 owner 内完成 | 可行，但 plan 欠规格：未说明 replacement 行为 |
| A4 | 10-K/10-Q subclass 的 `expand_*_virtual_sections_content()` 在 `_virtual_sections=[]` 时安全无副作用 | **未验证** — plan 未要求证明这些 expand 函数对空列表输入安全 |
| A5 | Publication mode 的三个状态(candidate/virtual/base-fallback)可仅通过一个 private field 表达 | 可行，但 plan 未定义枚举/状态名 |
| A6 | `list_tables()` 删除 `fallback_ref`/`last_known_ref` 后 base fallback 路径的 table `section_ref` 与 `list_sections()` 的 base ref 一致 | 成立 — 两者都委托 base processor |
| A7 | 219 changed-production 集合在 Slice 2 删除 `direct_stream.py`、新增 `awaiting_resolution.py` 后仍恰好 219 | 成立 — plan 明确预期此变化 |

## 4. Findings

### DS-F01 — 未修复 — 严重程度: 中 — `_initialize_virtual_sections()` 首次 refresh 调用链未在 plan 中显式追溯

- **位置**: plan §4.3 item 1-2,8；当前代码 `sec_form_section_common.py:408`
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: Plan 聚焦于 "10-K/10-Q 父类初始化后的第二次 postprocess/refresh"，但未显式追溯 `_initialize_virtual_sections()` 在第 408 行对 `_refresh_virtual_section_state()` 的**首次调用**。当前 `_initialize_virtual_sections()` 的调用链为：
  ```
  _initialize_virtual_sections()  (line 369)
    → _refresh_virtual_section_state()  (line 408) ← 首次 refresh
    → _postprocess_virtual_sections(full_text)  (line 409) ← mixin default no-op
  ```
  然后 subclass `__init__` 再次调用 `_postprocess_virtual_sections()` → 二次 refresh。
- **反例/失败场景**: Implementation agent 若只关注 subclass 二次调用的幂等，而忽略首次 refresh（line 408）同样会进入当前的 fail path（`ValueError: 存在无法分配到最终虚拟章节的 table_ref`），可能错误地把首次 refresh 的异常当成 "正确的 fail-closed" 而不做修改。
- **为什么有问题**: Plan 的 root cause 分析正确指出 line 495-497 是抛出点，但未显式说明 line 408 的首次 refresh 是同一个抛出点。Plan 只说 "10-K/10-Q 父类初始化后的第二次 postprocess/refresh"，暗示首次 refresh 在 `_initialize_virtual_sections()` 中已正常完成。但首次 refresh 同样会命中 line 495-497 的 `base_table_refs != section_table_refs` 检查，当前代码在首次 refresh 就会失败。
- **直接证据**:
  - `sec_form_section_common.py:408`: `self._refresh_virtual_section_state()` — 首次调用
  - `sec_form_section_common.py:495-497`: 抛出点
  - Continuation Codex artifact §5.2 记录的 stack trace 显示异常发生在 `_initialize_virtual_sections(min_sections=3)` → `_refresh_virtual_section_state()`
- **影响**: 实施 Agent 可能误解 fix 只需要在 subclass 二次 refresh 处短路，而忽略首次 refresh 同样需要原子 base-fallback 逻辑。
- **建议改法和验证点**:
  1. Plan §4.3 item 2 应显式声明：首次 `_refresh_virtual_section_state()`（`_initialize_virtual_sections:408`）是 publication decision 的第一入口；它的修复逻辑与 subclass 二次 refresh 共享同一幂等路径。
  2. 验证点：S3-STOP-F02 最小复现 case 必须在首次 refresh 完成后 `list_sections()` / `list_tables()` 已可用 base fallback 结果，而不只是 "构造不抛异常"。
- **修复风险**: 低（plan 仅需补一句显式追溯，不需要改设计）
- **严重程度**: 中

### DS-F02 — 未修复 — 严重程度: 中 — `_filter_table_refs_by_availability` 删除/收紧欠规格

- **位置**: plan §4.3 item 6
- **问题类型**: 不可直接实施
- **当前写法**: Plan 写道 "`_filter_table_refs_by_availability()`若会吞掉 marker dangling ref 也必须从该 owner 路径删除或收紧为 fail-closed，不能把矛盾隐藏成完整 mapping"。
- **反例/失败场景**:
  1. 若 implementation agent 选择 "删除"，但 `_filter_table_refs_by_availability` 在 Phase 1 标题匹配中被调用（line 914），删除后 Phase 1 的 `tbl_refs` 将包含 marker 中出现但 base 不存在的 dangling ref。这些 dangling ref 随后被写入 `vs.table_refs`，导致后续 `_refresh_virtual_section_state()` 的 dangling 检查（line 485-486）触发 `ValueError`。这实际上是把 "被静默吞掉的 dangling ref" 变成了 fail-closed，行为正确但 plan 未说明这个因果链。
  2. 若 implementation agent 选择 "收紧为 fail-closed"，需要在 `_filter_table_refs_by_availability` 内部增加检查逻辑，但 plan 未给出 fail-closed 的精确语义：是抛出 `ValueError` 还是返回一个错误标记让上层决定？
- **为什么有问题**: Plan 对关键函数的处置给了 implementation agent 二选一的自由裁量权（"删除或收紧"），但没有给出两种选择的精确 contract。这违背 plan 的 "code-generation-ready" 标准。
- **直接证据**:
  - `sec_form_section_common.py:914-917`: `_filter_table_refs_by_availability()` 被调用并原地过滤 marker 提取的 refs
  - 当前函数签名未知（未读取到函数体），但从调用上下文推断它接受 `set[str]` 并返回过滤后的子集
- **影响**: Implementation agent 可能在两种方案间犹豫，或选择一个方案后发现与 `_refresh_virtual_section_state` 的 dangling check 产生意外交互。
- **建议改法和验证点**:
  1. Plan 应明确选择 "删除"——因为在新的原子 publication 模型中，marker 提取阶段不需要静默过滤；dangling ref 应被后续统一校验（`_refresh_virtual_section_state` line 485-486）捕获为 fail-closed。
  2. 若 Phase 1 直接使用未过滤的 marker refs，必须证明 "marker dangling ref → `_refresh_virtual_section_state` fail-closed" 的路径可达且不被中间的 incomplete-marker check 提前 fallback 吞掉。
  3. 增加一个 explicit counterexample：marker 包含 dangling ref 且 base 部分缺失（incomplete + dangling 同时存在）→ dangling 检测优先于 incomplete fallback。
- **修复风险**: 低
- **严重程度**: 中

### DS-F03 — 未修复 — 严重程度: 中 — 10-K/10-Q subclass `expand_*_virtual_sections_content()` 对空 `_virtual_sections` 输入的安全性未验证

- **位置**: plan §4.3 item 8; `ten_k_processor.py:83-86`, `ten_q_processor.py:90-93`
- **问题类型**: 不可直接实施 / open question 未收敛
- **当前写法**: Plan 要求 10-K/10-Q subclass 文件零 diff，同时要求 base fallback 后第二次 postprocess/refresh 幂等。但 subclass 的 `_postprocess_virtual_sections()` 在调用 `_refresh_virtual_section_state()` **之前**先调用了 `expand_ten_k_virtual_sections_content(full_text, virtual_sections=self._virtual_sections)`（10-K line 83-86）或 `expand_ten_q_virtual_sections_content(...)`（10-Q line 90-93）。在 base fallback 状态下，`self._virtual_sections` 已被清空为 `[]`，expand 函数收到空列表。
- **反例/失败场景**: 若 `expand_ten_k_virtual_sections_content` 或 `expand_ten_q_virtual_sections_content` 对空 `virtual_sections` 输入抛异常、执行 O(n) 全量文本扫描、或依赖 `virtual_sections[0]` 等非空假设，则 base fallback 后的 subclass 二次 postprocess 无法幂等——它会在 expand 阶段失败，根本到不了 `_refresh_virtual_section_state()` 的幂等检查。
- **为什么有问题**: Plan 的 "subclass zero diff" 约束是对的（不应为修复 S3-STOP-F02 而修改 subclass），但这要求 expand 函数在收到空输入时安全无副作用。Plan 未要求 implementation agent 先证明这个前提成立。
- **直接证据**:
  - `ten_k_processor.py:83-86`: expand 在 refresh 前调用
  - `ten_q_processor.py:90-93`: expand 在 refresh 前调用
  - expand 函数实现在 `ten_k_form_common.py` / `ten_q_form_common.py`（未读取），其空列表行为未知
- **影响**: Implementation agent 可能在实施后发现 expand 函数对空列表不兼容，被迫修改 subclass 文件（违反 allowlist）或给 expand 函数增加防御代码（扩散 scope）。
- **建议改法和验证点**:
  1. Plan 应增加验证步骤：在 plan-review 或 implementation 入口处，先证明 `expand_ten_k_virtual_sections_content(full_text, [])` 和 `expand_ten_q_virtual_sections_content(full_text, [])` 安全返回（不抛异常，不修改传入的空列表）。
  2. 若 expand 函数确实需要非空输入，plan 需要决定：是让 `_postprocess_virtual_sections` 在 mixin 层检查 base-fallback 并跳过 expand（这仍在 `sec_form_section_common.py` owner 内），还是给 expand 函数的调用方增加 guard。优先方案是 mixin 的 `_postprocess_virtual_sections` 检查 publication mode 并短路——但当前 mixin 的默认实现是空的，短路逻辑需要在 subclass override 之前生效，这需要更复杂的设计。
  3. 实际上最简单的方案是：`_refresh_virtual_section_state()` 在 base-fallback 已发布时立即返回（幂等）。这样即使 expand 函数做了无用功（对空列表做操作），随后的 refresh 也是安全的。但 expand 函数如果对空列表 crash，这个方案就无效。因此必须先验证 expand 函数的空列表行为。
- **修复风险**: 低（只需验证，大概率 expand 对空列表是安全的）
- **严重程度**: 中（若 expand 不安全则需要 plan 修正；若安全则降级为 non-blocking）

### DS-F04 — 未修复 — 严重程度: 低 — Publication mode 枚举未在 plan 中显式定义

- **位置**: plan §4.3 item 1
- **问题类型**: 不可直接实施
- **当前写法**: Plan 多处引用 "publication mode" 概念："明确区分 candidate 构建、virtual 已发布与 base fallback 已发布"、"不得用空 dict、时间、日志或偶然 list 顺序反推模式"、"public methods 只消费已发布 mode"。
- **反例/失败场景**: Implementation agent 可能使用 `_virtual_sections` 是否为空 + 一个 `_base_fallback: bool` 标志，而不是明确的枚举。这会导致 "candidate 已构建但尚未 refresh" 与 "base fallback 已发布（`_virtual_sections` 已清空）" 两种状态在外部不可区分——都是 `_virtual_sections == []`。如果 `_initialize_virtual_sections()` 在调用 refresh 之前某处抛异常，"candidate 未发布" 的状态不应被外部方法当作 base fallback。
- **为什么有问题**: Plan 多处强调 "不得用空 dict/list 反推模式"，但未给 implementation agent 提供明确的 enum 定义或状态名，增加了 implementation 的自由裁量空间，可能导致 plan review 与 implementation 之间的语义 gap。
- **直接证据**: plan §4.3 item 1: "引入 owner-private publication mode，明确区分 candidate 构建、virtual 已发布与 base fallback 已发布"
- **影响**: 低 — 大多数 implementation agent 会自然地使用 enum 或 sentinel。但如果 implementation agent 选择了 `_virtual_sections is None` vs `_virtual_sections == []` 等隐式区分，review 时可能引发争议。
- **建议改法和验证点**: Plan 可以建议（非强制）三个状态名：`CANDIDATE` / `VIRTUAL_PUBLISHED` / `BASE_FALLBACK`，并说明初始状态为 `CANDIDATE`、只有 `_refresh_virtual_section_state()` 可以转换到终态。这不是 blocking finding。
- **修复风险**: 低
- **严重程度**: 低

### DS-F05 — 未修复 — 严重程度: 低 — incomplete + dangling 同时存在时的优先级未在 plan 中明确

- **位置**: plan §4.3 item 5
- **问题类型**: open question 未收敛
- **当前写法**: Plan 分别描述 "incomplete proof → base fallback"（item 4）和 "duplicate/dangling/contradictory → ValueError fail-closed"（item 5），但没有明确当两种条件同时满足时的优先级。例如：base 有 `t_0001, t_0002`，marker 有 `t_0001, t_0099`（`t_0002` 缺失 = incomplete，`t_0099` 非 base = dangling）。
- **反例/失败场景**: Implementation agent 可能先检查 incomplete（`t_0002` 缺失）→ 发布 base fallback → 吞掉 dangling（`t_0099`）信号。或者先检查 dangling → fail-closed → 用户看到的是 "dangling ref" 错误而不是 "incomplete proof" 信息。两种行为都可能是合理的，但 plan 应明确选择一种。
- **为什么有问题**: 在 production 真实数据中，marker 同时包含 dangling ref 和缺失 ref 可能是数据损坏信号（如 marker 生成 bug），此时 fail-closed 比静默 fallback 更安全。但 plan 未给出优先级规则。
- **直接证据**: plan §4.3 item 4（incomplete → fallback）与 item 5（dangling → fail-closed）并列，无优先级说明。
- **影响**: 低 — 可以合理默认 "dangling/contradiction 优先于 incomplete"（先检查数据完整性，再检查覆盖完整性），但 plan 应该显式声明。
- **建议改法和验证点**:
  1. Plan §4.3 item 5 应增加优先级声明："dangling/duplicate/contradictory 检查优先于 incomplete 检查；任一 fail-closed 条件命中即抛 `ValueError`，不因同时存在 incomplete 而降级为 base fallback。"
  2. Counterexample matrix 应增加一个混合 case：incomplete + dangling 同时存在 → fail-closed。
- **修复风险**: 低
- **严重程度**: 低

## 5. 重点挑战回答

### 5.1 Atomic publication 是否可在唯一 owner 实现？

**可以。** `_refresh_virtual_section_state()` 是当前唯一的 publication boundary。Plan 的修复方案是：
1. 在 refresh 入口检查 base-fallback 终态 → 幂等返回
2. 在局部变量中完成全部验证（section tree、base table snapshot、marker mapping）
3. 验证通过 → 一次提交三个 projection 字段 + publication mode
4. 验证不通过（incomplete）→ 清空三个字段 + 设置 base-fallback mode
5. 验证失败（contradiction）→ `ValueError`，不修改任何已发布状态

这个方案在单一函数内原子完成，不依赖跨模块协调。唯一需要注意的是首次 refresh（在 `_initialize_virtual_sections:408`）和 subclass 二次 refresh 共享同一入口（见 DS-F01）。

### 5.2 Incomplete marker 与 duplicate/dangling/contradictory 分类是否可判定且不吞错？

**可判定。** 分类逻辑清晰：
- **Duplicate**: base `table_ref` 集合本身有重复 → fail-closed（数据完整性错误）
- **Dangling**: marker 中有 ref 但 base 中不存在 → fail-closed（数据一致性错误）
- **Contradictory**: table→section 与 section→tables 双向不一致或 section tree 悬挂 → fail-closed（数据一致性错误）
- **Incomplete**: base 中有 table 但 marker 中无对应 proof → base fallback（能力不足，不是错误）

每个条件都可在一个确定的集合操作中判定。不吞错的关键是：dangling/duplicate/contradictory 检查必须在 incomplete fallback 决策**之前**执行（见 DS-F05 优先级建议）。

### 5.3 Base fallback 是否真正同源？

**是。** Base fallback 复用 `self._get_base_processor()` —— 即 MRO 中 `_VirtualSectionProcessorMixin` 的下一跳（对 TenKFormProcessor 而言是 `SecProcessor`）。所有 public methods（`list_sections`、`list_tables`、`read_section`、`get_section_title`、`search`）在 base fallback 下都直接委托 base processor 的同名方法。这确保了：
- section ref 命名空间一致（base processor 的 `s_XXXX`）
- table `section_ref` 指向 base section refs 且与 `list_sections()` 返回的 refs 一致
- 没有混合虚拟/基础视图

### 5.4 零表格文档语义

**正确。** Plan 的 counterexample #5 覆盖了零表格文档。关键区分：
- 零表格 + marker unsupported: 空 table mapping 是完整的 proof → 发布合法 virtual sections ✓
- 零表格 + marker supported: 同上，空 mapping 也是完整的 ✓
- 非零表格 + marker unsupported: 有 base tables 但无 marker proof → base fallback ✓

### 5.5 10-K/10-Q 二次 postprocess refresh 幂等

**基本可行，但有一个未验证前提（见 DS-F03）。** Plan 要求 base fallback 后：
1. Subclass `_postprocess_virtual_sections()` 仍会被调用
2. 其中的 expand 函数对空 `_virtual_sections` 安全（无副作用）
3. `_refresh_virtual_section_state()` 检测 base-fallback 已发布 → 立即返回

步骤 2 是未验证的前提。

### 5.6 `list_tables()` 补偿删除后所有 public consumers 一致

**一致。** Plan 要求删除 `list_tables()` 的 `fallback_ref`/`last_known_ref` 和 `_assign_unmapped_tables_by_position()`。删除后：
- Virtual mode: `list_tables()` 只使用 `_table_ref_to_virtual_ref` exact mapping（line 979-983）
- Base fallback mode: `list_tables()` 委托 base processor（line 968）
- `list_sections()`、`read_section()`、`get_section_title()`、`search()` 全部检查同一 publication mode 并委托同一 base processor

所有 public consumers 共享同一真源。不存在 "sections 已 fallback 但 tables 还在用虚拟映射" 的混合状态。

### 5.7 六类 counterexamples 是否足以防 half state/猜测归属？

**基本足够，建议增加一个混合 case（见 DS-F05）。** 当前六类覆盖：
1. ✅ 正常 fallback（unsupported marker + tables）
2. ✅ 正常 virtual（complete marker + tables）
3. ✅ Incomplete fallback（partial marker）
4. ✅ Contradiction fail-closed（duplicate/dangling/contradiction）
5. ✅ Zero-table
6. ✅ 10-K/10-Q 幂等

建议增加：
7. ⚠️ Incomplete + dangling 同时存在 → 确认 fail-closed 优先于 fallback

### 5.8 Production/test/README allowlist

**清晰且精确。** Production allowlist 只有两个路径（Docling protected + sec_form_section_common new）。Test allowlist 六个路径，README allowlist 只有 `dayu/fins/README.md`。所有 protected zero-diff paths 明确列出。

### 5.9 219/219 coverage 与全部 §6 门禁

**门禁完整。** Plan §6 覆盖：canonical non-coverage suite、exact single-node exclusion coverage with collect-only preflight、full pyright (0 errors)、Ruff immutable baseline、diff-check、build (wheel+sdist)、six canonical scans、Slice 2/3 owner scans、security/deferred/no-code ledger、per-slice real smoke。门禁密度充分。

### 5.10 Security、Gemini quota 与 deferred boundaries

**全部保留。** Plan §4.3 "Unchanged trust / quota / deferred boundaries" 明确保持：Config/Host SQLite trusted internal、Tool Trace/audit/public/LLM/log zero-required、Gemini quota non-blocking no-code、AR-F06 retained/unfixed、AR-F07 pending release blocker、Issues 142/151/175/177/178 与 Topic 8/9 不实施。

## 6. Best-practice / overengineering / overcoupling review

### 6.1 Best-practice

Plan 选择 atomic publication state machine 是正确的工程选择。三态模型（candidate/virtual/base-fallback）是这类问题的最小充分设计。Plan 拒绝 "首章节/最近章节猜测" 正确遵循了 semantic ownership 约束。

### 6.2 Overengineering

无。Plan 明确拒绝：新增 capability schema、DOM/raw HTML marker、第二 resolver、compatibility wrapper、secret infrastructure、tool authorization framework。修复范围严格限定在 single-owner single-file。

### 6.3 Overcoupling

无。Plan 的修复不引入新的跨层/跨模块依赖。Subclass 文件保持零 diff。Marker producer contract 不变。Public consumer 接口不变。

## 7. Lenses summary

| Lens | Result |
|------|--------|
| Architecture boundary | PASS — 修复在唯一 owner boundary 内 |
| Best-practice | PASS with notes — atomic state machine 正确 |
| Optimal-solution | PASS — 最小修复，不扩展 scope |
| Overengineering | PASS — 无过度设计 |
| Overcoupling | PASS — 无新增耦合 |

## 8. Open questions

| # | Question | Suggested owner |
|---|----------|----------------|
| Q1 | `expand_ten_k_virtual_sections_content(full_text, [])` 是否安全无副作用？(DS-F03) | Implementation agent 在实施前验证 |
| Q2 | `_filter_table_refs_by_availability` 的精确处置：删除 vs 收紧？(DS-F02) | Controller 在 plan-fix gate 裁决 |
| Q3 | Incomplete + dangling 同时存在时优先级？(DS-F05) | Controller 裁决，建议 dangling 优先 |

## 9. Residual risks

| Risk | Severity | Destination |
|------|----------|-------------|
| expand 函数对空列表输入不安全导致 subclass 需要修改 | 中 | Implementation 入口验证，若属实则 STOP |
| Publication mode 枚举选择引发 implementation/review 争议 | 低 | Plan 可建议状态名（非强制） |
| 首次 refresh 调用链被 implementation agent 忽略 | 中 | DS-F01 fix 后消除 |

## 10. Final plan review conclusion

**PASS-WITH-FINDINGS**

Plan 的 core design（atomic virtual/base publication, six counterexample classes, precise allowlists, full §6 gates）是 sound 的。三个 medium findings（DS-F01/F02/F03）和两个 low findings（DS-F04/F05）均不构成结构性 blocker：DS-F01 需要 plan 补充首次 refresh 调用链追溯，DS-F02 需要明确 `_filter_table_refs_by_availability` 的处置方案，DS-F03 需要验证 expand 函数的空列表安全性。这些都可以在 plan-fix gate 内解决，不需要重新设计。

Plan 满足 "code-generation-ready" 标准的前置条件是 DS-F01/F02/F03 被 accepted 并修正。修正后可以进入 dual complete plan re-review。

### Zero-finding ledger（若最终 PASS）

本 review 产出 5 个 findings（3 medium, 2 low），无 critical/严重。即使所有 findings 被 Controller reject-with-reason，plan 的核心语义模型和门禁体系没有结构性缺陷。

---

**Reviewed target**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
**Reviewed SHA-256**: `466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`
**Read evidence**: AGENTS.md, issues-implementation-control.md (完整), phaseflow-umbrella-optimization-control.md, overdesign-controller-discussion.md, Host/Engine/Tool/Fins/UI design.md (完整), S3 continuation/Controller adjudication/plan correction Codex/plan correction Controller validation (完整), 第一次 S3 stop→correction→review→fix→re-review→accepted commit→resume 完整链 (16 artifacts), 当前代码 sec_form_section_common.py/docling_processor.py/ten_k_processor.py/ten_q_processor.py.
**Review gate**: Plan-only; 未修改 plan/control/code/tests/README 或其它 artifact; 未 stage/commit.
