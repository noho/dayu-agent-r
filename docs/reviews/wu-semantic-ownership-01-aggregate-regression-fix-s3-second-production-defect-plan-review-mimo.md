# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二次 Corrected Plan Adversarial Plan Review（AgentMiMo）

## 1. Reviewed target and scope

- **Plan**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
- **Plan SHA-256**: `466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`
- **Correction artifact**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-codex.md`
- **Correction artifact SHA-256**: `15b53e8223883e572653eb4d26aa54390d2081ba84d986f10523722926da86a6`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-controller-adjudication.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-correction-controller-validation.md`
- **Base / HEAD**: `48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe`，branch `phaseflow/host-issues-control`
- **Review date**: 2026-07-19
- **Review type**: 完整 adversarial plan review（不复用第一次 review 结论）

## 2. Assumptions tested

| # | Assumption | Evidence source | Verdict |
|---|---|---|---|
| A1 | virtual-section publication 可在唯一 owner (`sec_form_section_common.py`) 内原子实现 | §4.3 plan text + code lines 426-497, 947-992 | **需具体化** |
| A2 | incomplete marker 与 duplicate/dangling/contradictory 可稳定区分且不吞错 | §4.3 plan text + code lines 842-934 | **需收紧** |
| A3 | base fallback 真正同源——所有 public consumers 消费同一 publication mode | §4.3 plan text + code lines 967-1097 | **需修正** |
| A4 | 零表格场景正确保留 virtual projection | §4.3 counterexample #5 | **成立但需明确边界** |
| A5 | 10-K/10-Q 二次 postprocess 可在 owner 内幂等短路，不需改 subclass | §4.3 plan text + ten_k_processor.py:52, ten_q_processor.py:58 | **成立但需具体 guard** |
| A6 | `list_tables()` 删除 `fallback_ref`/`last_known_ref` 后所有 public consumers 一致 | §4.3 plan text + code lines 974-992 | **需全面化** |
| A7 | 六类 counterexamples 足以防 half state / 猜测归属 | §4.3 matrix | **缺一项关键反例** |
| A8 | production/test/README allowlists 精确且充分 | §3.1-3.4 | **成立** |
| A9 | 219/219 coverage 与全部 §6 门禁可达 | §6 + current code | **成立但有风险** |
| A10 | security、Gemini quota 与 deferred boundaries 保持 | §4.3 unchanged decisions | **成立** |

## 3. Findings

### 01-未修复-高-缺少显式 publication mode 类型定义，atomic publication 不可实施

- **位置**: §4.3 "引入 owner-private publication mode" + §4.3 stop condition "无法在单一 atomic refresh owner 区分 incomplete fallback 与 duplicate/dangling/contradictory fail-closed"
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: plan 说"引入 owner-private publication mode，明确区分 candidate、published virtual 与 published base fallback；public methods 不从空 dict/list 或偶然状态反推模式"，但未定义 mode 的数据结构、存储位置、转换规则或 guard 表达式。
- **反例/失败场景**: 实现 agent 有多种选择：(a) boolean `_is_base_fallback`；(b) enum `_PublicationMode`；(c) 用 `_virtual_sections is None` vs `[]` vs populated 三种状态隐式区分。不同选择导致不同 guard 行为。特别是当前代码用 `if not self._virtual_sections` 作为所有 public methods 的 guard（lines 967, 1007, 1031, 1050, 1096），如果 mode 改变但 guard 不统一更新，会产生混合视图。
- **为什么有问题**: `sec_form_section_common.py` 有 6 个 public methods 使用 `if not self._virtual_sections` guard：`list_tables()`、`list_sections()`、`get_section_title()`、`read_section()`、`search()`。plan 要求"base fallback 时 `_virtual_sections` 可非空"（counterexample #5），但现有 guard 只检查空/非空，不检查 mode。实现 agent 必须同时修改所有 6 个 guard，且必须确保 `_virtual_sections` 在 base fallback 时的状态与 guard 逻辑一致。
- **直接证据**:
  - `list_tables()` line 967: `if not self._virtual_sections: return self._get_base_processor().list_tables()`
  - `list_sections()` line 1007: `if not self._virtual_sections: return self._get_base_processor().list_sections()`
  - `get_section_title()` line 1031: `if not self._virtual_sections: return self._get_base_processor().get_section_title(ref)`
  - `read_section()` line 1050: `if not self._virtual_sections: return self._get_base_processor().read_section(ref)`
  - `search()` line 1096: `if not self._virtual_sections: return self._get_base_processor().search(...)`
  - plan counterexample #5: "zero-table: marker unsupported 不导致合法 virtual sections 被无意义放弃"，即 base fallback 时 `_virtual_sections` 可非空
- **影响**: 实现 agent 可能只修改部分 guard，留下混合视图；或选择与 plan 意图不一致的 mode 表达方式，导致 base fallback 时 `list_sections()` 返回 virtual 而 `list_tables()` 返回 base。
- **建议改法和验证点**: 在 plan 中定义具体 `_PublicationMode` enum（`BUILDING` / `VIRTUAL` / `BASE_FALLBACK`）和 `_publication_mode: _PublicationMode` 实例变量。列出所有 6 个 public methods 的 guard 表达式：`if self._publication_mode != _PublicationMode.VIRTUAL: return self._get_base_processor().xxx()`。验证点：counterexample #1（base fallback）时 6 个 methods 全部返回 base processor 结果；counterexample #5（zero-table virtual）时全部返回 virtual 结果。
- **修复风险（低/中/高）**: 低——纯规格补充，不改变实现方向
- **严重程度（高）**: 实现 agent 可能因缺少具体定义而做出不一致选择

### 02-未修复-高-`_filter_table_refs_by_availability()` 可能吞掉 dangling ref，使 incomplete 与 contradictory 不可区分

- **位置**: §4.3 "marker 含非 base dangling ref...必须在 atomic commit 前抛 ValueError" vs §4.3 "marker 不能证明每个 base table 唯一归属时，整体回退 base"
- **问题类型**: 状态机漏洞 / 契约缺失
- **当前写法**: plan 要求"duplicate / dangling / contradictory: commit 前 fail closed，不被 fallback 吞掉"，同时要求"incomplete proof: 不发布半套 virtual state，整体回退 base"。但当前 `_assign_tables_to_virtual_sections()` line 887 调用 `_collect_available_table_refs_from_base()` 和 `_filter_table_refs_by_availability()`，后者会过滤掉不在 base tables 中的 marker refs。
- **反例/失败场景**: marker material 包含 `[[t_0001]]` 和 `[[t_9999]]`，base tables 只有 `t_0001`。`_filter_table_refs_by_availability()` 会静默丢弃 `t_9999`。之后 mapping 看起来完整（所有 base tables 都被映射），但实际上 marker 有 dangling ref。按 plan 的规则，这应该是 contradictory fail-closed，但 filter 吞掉了证据。
- **为什么有问题**: 当前 `_filter_table_refs_by_availability()` (line 887-888, 914-917) 的存在目的就是过滤"仅存在于标记文本、但底层 `list_tables()` 未产出"的表格引用。这与 plan 的"marker dangling ref 必须 fail-closed"要求直接矛盾。如果实现 agent 保留该 filter，dangling ref 被吞掉；如果删除该 filter，`_assign_tables_to_virtual_sections()` 可能将不存在的 table ref 写入 mapping，导致下游 `read_section()` 出现悬挂引用。
- **直接证据**:
  - `_assign_tables_to_virtual_sections()` line 887: `available_table_refs = self._collect_available_table_refs_from_base()`
  - line 914-917: `tbl_refs = _filter_table_refs_by_availability(_extract_table_refs(segment), available_table_refs)`
  - `_collect_available_table_refs_from_base()` docstring line 822: "该集合用于在虚拟章节分配阶段过滤'仅存在于标记文本、但底层 `list_tables()` 未产出'的表格引用"
  - plan §4.3: "marker 含非 base dangling ref...必须在 atomic commit 前抛 ValueError"
- **影响**: 如果保留 filter，plan 的 dangling ref 检测永远不触发，contradictory 被误分类为 complete mapping；如果删除 filter，需要在验证阶段增加显式 dangling 检测，但 plan 未说明如何区分"marker 中的 ref 不在 base tables 中"是 dangling（fail-closed）还是正常的 marker-only ref（安全忽略）。
- **建议改法和验证点**: plan 应明确：(1) 删除 `_filter_table_refs_by_availability()` 从 owner 路径；(2) marker material 中出现的每个 `[[t_XXXX]]` ref 必须在 base tables 中存在，否则为 dangling ref 并 fail-closed；(3) 该规则只在 marker capability 可用时适用——marker unsupported 时无 marker refs 可检查。验证点：counterexample #4 的 dangling case 必须在 filter 删除后才能正确触发 ValueError。
- **修复风险（低/中/高）**: 中——需要同时调整 `_assign_tables_to_virtual_sections()` 的 Phase 1/Phase 2 逻辑
- **严重程度（高）**: 若 filter 保留，contradictory 永远被吞掉，plan 的 fail-closed 承诺失效

### 03-未修复-中-base fallback 时 `_virtual_sections` 非空与现有 `_initialize_virtual_sections()` 流程冲突

- **位置**: §4.3 counterexample #5 + code lines 369-409
- **问题类型**: 过度耦合 / 实现路径不清
- **当前写法**: plan 说"zero-table: marker unsupported 不导致合法 virtual sections 被无意义放弃"，即 base fallback 时 `_virtual_sections` 可非空。但 `_initialize_virtual_sections()` line 403-404 在 marker 不足时调用 `_build_virtual_sections_from_base()`，该方法从 base processor 的 sections 构建 virtual sections。
- **反例/失败场景**: 一个 10-K 文档，marker capability 不可用，base 有 sections 但无 tables。按 plan，这属于 counterexample #5（zero-table + marker unsupported），应该保留 virtual sections。但 `_initialize_virtual_sections()` 调用 `_build_virtual_sections_from_base()` 构建了 virtual sections，然后 `_refresh_virtual_section_state()` 进入。此时 base_table_refs 为空，section_table_refs 也为空（因为 marker 不可用，`_assign_tables_to_virtual_sections()` 未执行），所以 `base_table_refs == section_table_refs` 成立，不会抛 ValueError。这种情况下现有的"marker 不足 → 回退 base sections"路径**恰好**产生了正确结果，但这不是因为 plan 的 atomic publication 生效，而是因为碰巧两个空集合相等。
- **为什么有问题**: 如果文档有 tables（counterexample #1），marker 不可用时 `_build_virtual_sections_from_base()` 构建了 virtual sections，`_assign_tables_to_virtual_sections()` 因空 marker 返回，然后 `base_table_refs != section_table_refs` 抛 ValueError。plan 要求此场景整体 base fallback，但 `_virtual_sections` 已被 `_build_virtual_sections_from_base()` 填充。实现 agent 需要在 `_refresh_virtual_section_state()` 中检测到此情况后清空 `_virtual_sections` 并设置 base fallback mode。这与 counterexample #5（保留 `_virtual_sections`）形成张力。
- **直接证据**:
  - `_initialize_virtual_sections()` line 403-404: `if len(built_sections) < min_sections: built_sections = self._build_virtual_sections_from_base()`
  - counterexample #1: "public TenK + unsupported marker + base table: 构造成功，逐值回退同源 base contract"
  - counterexample #5: "zero-table: marker unsupported 不导致合法 virtual sections 被无意义放弃"
- **影响**: 实现 agent 可能在 `_refresh_virtual_section_state()` 中统一清空 `_virtual_sections`（破坏 counterexample #5），或统一不清空（破坏 counterexample #1 的 base fallback 承诺）。
- **建议改法和验证点**: plan 应明确 `_initialize_virtual_sections()` 的流程：marker 不足时先调用 `_build_virtual_sections_from_base()` 构建候选，然后 `_refresh_virtual_section_state()` 按以下规则决定 mode：base tables 非空且 marker 无法证明完整 ownership → base fallback（清空 `_virtual_sections`）；base tables 为空 → virtual mode（保留 `_virtual_sections`，空 mapping）。验证点：counterexample #1 和 #5 的行为必须不同且都正确。
- **修复风险（低/中/高）**: 低——纯规格澄清
- **严重程度（中）**: 实现 agent 可能因不清楚流程而做出错误选择

### 04-未修复-中-六类 counterexamples 缺少"marker available + base tables 非空 + mapping 完整但 `_build_virtual_sections_from_base()` 也被调用"的混合场景

- **位置**: §4.3 "Six owner/public counterexamples"
- **问题类型**: 测试缺口
- **当前写法**: 六类反例覆盖：(1) unsupported marker + base table；(2) complete mapping；(3) incomplete proof；(4) duplicate/dangling/contradictory；(5) zero-table；(6) 10-K/10-Q second postprocess。但缺少一个关键场景：marker capability 不可用时，`_initialize_virtual_sections()` 调用 `_build_virtual_sections_from_base()` 构建 virtual sections，这些 sections 来自 base processor 而非 marker。此时如果 base tables 非空，plan 要求 base fallback。
- **反例/失败场景**: `_build_virtual_sections_from_base()` 构建的 virtual sections 与 marker-based sections 有不同的 ref 命名空间。如果实现 agent 在 `_refresh_virtual_section_state()` 中检测 marker 不可用后进入 base fallback，但 `_virtual_sections` 中仍有 `_build_virtual_sections_from_base()` 的残留，`list_sections()` 可能返回 base-derived virtual refs 而非 base processor 的原始 refs。
- **为什么有问题**: counterexample #1 使用真实 `TenKFormProcessor`，其 `_initialize_virtual_sections()` 会走 `_build_virtual_sections_from_base()` 路径（因为 SecProcessor marker 返回空字符串）。但 counterexample #1 只断言"构造成功，逐值回退同源 base contract"，没有验证 `list_sections()` 返回的 ref 命名空间是 base processor 的原始 ref 还是 `_build_virtual_sections_from_base()` 生成的虚拟 ref。
- **直接证据**:
  - `_initialize_virtual_sections()` line 403-404: `_build_virtual_sections_from_base()` 在 marker 不足时被调用
  - counterexample #1: 只断言"构造成功，逐值回退同源 base contract"，未验证 ref 命名空间
- **影响**: 实现 agent 可能在 base fallback 时不清空 `_virtual_sections`，导致 `list_sections()` 返回 base-derived virtual refs，与 base processor 的原始 refs 不一致。
- **建议改法和验证点**: counterexample #1 应增加断言：`list_sections()` 返回的每个 `ref` 必须等于 base processor `list_sections()` 返回的对应 `ref`；`list_tables()` 返回的每个 `section_ref` 必须是 base processor `list_tables()` 返回的对应 `section_ref`。这确保 base fallback 时 ref 命名空间完全来自 base processor。
- **修复风险（低/中/高）**: 低——增加一条断言
- **严重程度（中）**: 若不验证 ref 命名空间，base fallback 的"同源"承诺可能仅在内容层面成立而 ref 层面不成立

### 05-未修复-低-`read_section()` 和 `search()` 的 base fallback guard 未在 plan 中列出

- **位置**: §4.3 "`list_sections/list_tables/read_section` 只消费已发布同一状态；`get_section_title/search` 不形成混合视图"
- **问题类型**: 契约缺失
- **当前写法**: plan 要求所有 public methods 消费同一 publication mode，但只详细描述了 `list_tables()` 的 `fallback_ref`/`last_known_ref` 删除，以及 `list_sections()` 的 base fallback。`read_section()` 和 `search()` 的 guard 逻辑未明确。
- **反例/失败场景**: 实现 agent 修改了 `list_tables()` 和 `list_sections()` 的 guard，但忘记修改 `read_section()` 和 `search()`。base fallback 时 `list_sections()` 返回 base sections，但 `read_section()` 仍尝试从 `_virtual_section_by_ref` 查找，导致 KeyError。
- **为什么有问题**: 当前 `read_section()` line 1050 用 `if not self._virtual_sections` guard，`search()` line 1096 同样。如果实现 agent 只修改 `list_tables()` 和 `list_sections()` 的 guard 而遗漏其他，会产生混合视图。
- **直接证据**:
  - `read_section()` line 1050-1054: `if not self._virtual_sections: return self._get_base_processor().read_section(ref)` / `section = self._virtual_section_by_ref.get(ref)` / `if section is None: raise KeyError(...)`
  - `search()` line 1096-1097: `if not self._virtual_sections: return self._get_base_processor().search(...)`
  - plan 只说"list_sections/list_tables/read_section 只消费已发布同一状态；get_section_title/search 不形成混合视图"
- **影响**: 若 `read_section()` guard 遗漏，base fallback 时调用 `read_section("some_base_ref")` 会抛 KeyError。
- **建议改法和验证点**: plan 应明确列出所有 6 个 public methods 的 guard 表达式，或明确说"所有 public methods 统一使用 `self._publication_mode != _PublicationMode.VIRTUAL` 作为 base fallback guard"。验证点：counterexample #1 必须同时断言 `read_section()` 和 `search()` 在 base fallback 时返回 base processor 结果。
- **修复风险（低/中/高）**: 低——纯规格补充
- **严重程度（低）**: 实现 agent 有较大概率自行发现并修复，但 plan 应明确

### 06-未修复-低-`_assign_unmapped_tables_by_position()` 删除后的 Phase 2 行为未明确

- **位置**: §4.3 "删除 `_assign_unmapped_tables_by_position()` 及其调用"
- **问题类型**: 契约缺失
- **当前写法**: plan 要求删除 `_assign_unmapped_tables_by_position()`，这是 `_assign_tables_to_virtual_sections()` Phase 2 的位置回退逻辑。但未说明 Phase 1 标题匹配未覆盖的表格应如何处理。
- **反例/失败场景**: marker material 中 `[[t_0001]]` 出现在一个 marker 标题无法匹配到任何 virtual section 的区域。Phase 1 跳过该区域。Phase 2 被删除后，`t_0001` 不被分配到任何 section。按 plan 的规则，这属于"incomplete proof"（base table 有 ref 但 marker 无法证明归属），应该整体 base fallback。但如果没有 Phase 2，这个 table ref 会成为"未映射的 base ref"，在验证阶段被 `base_table_refs != section_table_refs` 检测到并抛 ValueError，而非触发 base fallback。
- **为什么有问题**: plan 区分"incomplete proof → base fallback"和"contradictory → fail-closed ValueError"。删除 Phase 2 后，标题未匹配的 table ref 会触发 ValueError 而非 base fallback，因为验证阶段只检查集合相等性，不区分"marker 未覆盖"和"marker 矛盾"。
- **直接证据**:
  - `_assign_tables_to_virtual_sections()` line 924-934: Phase 2 调用 `_assign_unmapped_tables_by_position()`
  - `_refresh_virtual_section_state()` line 495-497: `if base_table_refs != section_table_refs: raise ValueError(...)`
  - plan: "marker 不能证明每个 base table 唯一归属时，整体回退 base"
- **影响**: 若 Phase 2 删除后不调整验证逻辑，部分标题未匹配的场景会从 plan 预期的 base fallback 变成 ValueError fail-closed。
- **建议改法和验证点**: plan 应明确：删除 Phase 2 后，`_refresh_virtual_section_state()` 的验证逻辑需要区分两种 `base_table_refs != section_table_refs` 情况：(a) marker 中存在非 base dangling ref（contradictory → ValueError）；(b) base tables 中存在 marker 未覆盖的 ref（incomplete → base fallback）。区分方式：先检查 `section_table_refs - base_table_refs`（dangling），再检查 `base_table_refs - section_table_refs`（unmapped）。前者为空而后者非空时，属于 incomplete proof，触发 base fallback。
- **修复风险（低/中/高）**: 低——验证逻辑的小调整
- **严重程度（低）**: 实现 agent 大概率能自行发现，但 plan 应明确以避免混淆

## 4. Open questions

无。所有假设已通过直接代码/设计证据验证或转化为 findings。

## 5. Residual risks and suggested tracking destination

| Risk | Severity | Destination |
|---|---|---|
| `_filter_table_refs_by_availability()` 是否应在 owner 路径完全删除 | 中 | 本 plan §4.3 或 Controller 裁决 |
| `_build_virtual_sections_from_base()` 在 base fallback 时是否应被调用 | 低 | 本 plan §4.3 |
| `sec_form_section_common.py` 从 36.61% 到 80% 需要大量 test cases | 中 | implementation phase |
| AR-F06 scheduler node 在 coverage 模式下是否能稳定通过 | 低 | 已有 baseline residual |
| 219 集合在 Slice 2 迁移后是否精确维持 | 低 | Slice 2 exit gate |

## 6. Final plan review conclusion

**PASS-WITH-RISKS**。

Plan 的方向正确：atomic virtual/base publication 是唯一语义正确的修复路径，六类 counterexamples 覆盖了主要 failure modes，allowlists 精确，security/deferred/quota 边界保持。但存在一个高严重度 finding（#01：缺少显式 publication mode 类型定义）和一个高严重度 finding（#02：`_filter_table_refs_by_availability()` 可能吞掉 dangling ref），这两个 finding 若不在 plan-fix 阶段解决，实现 agent 有很大概率产出不一致的 guard 逻辑或错误地将 contradictory 误分类为 incomplete。

建议 Controller 裁决 finding #01 和 #02 为 accepted，finding #03-#06 为 question 或 non-blocking observation。AgentCodex 在 plan-fix 阶段补充 `_PublicationMode` enum 定义、明确 `_filter_table_refs_by_availability()` 的删除决策、以及列出所有 6 个 public methods 的 guard 表达式后，本 plan 可进入 implementation。
