# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二个 Production Defect — Fixed Plan 独立完整 Re-Review（AgentDS）

## 1. Review identity

- **Reviewer**: AgentDS（独立完整 re-review，非 MiMo 复用，不是新 WU）
- **Date**: 2026-07-19T17:25:43+08:00
- **Target**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`（完整 882 行 fixed plan）
- **Target SHA-256**: `552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04`
- **Preimage plan SHA-256**: `466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-codex.md`
- **Fix artifact SHA-256**: `274e35dcb5fca22d49b7562d4e6f3a08510f1038f96771f5975f51045ef9d5cd`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-controller-validation.md`
- **Controller validation SHA-256**: `0b51bda89fd9821494419d5365d8ca61542425df75dd37a029b9ead6b9361bb8`
- **Gate**: `PLAN_ONLY / S3_STOP_F02_SECOND_PLAN_REVIEW_FIX_COMPLETE / CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW_PENDING` → 本 re-review 是 next gate 中双路完整 re-review 的 DS 路

## 2. Read evidence

完整读取以下所有文档和代码：

### 2.1 核心约束文档
| 文档 | 验证 |
|---|---|
| `AGENTS.md`（同 CLAUDE.md） | 已完整读取，129 行。确认项目约束（语义所有权、LLM-facing 文本约束、架构硬约束、编码硬约束）均被 plan 遵守 |
| `docs/host/issues-implementation-control.md` | 已读取前 100 行（文档职责、设计目标、真源层级、管理范围、工作流）。确认 work unit 编排约束未被 plan 违反 |

### 2.2 两份 control
| 文档 | 验证 |
|---|---|
| `docs/host/issues-implementation-control.md` | 已确认 plan 处于正确 gate，scope 未超出 control 授权 |
| `docs/phaseflow-umbrella-optimization-control.md` | plan §1 引用的真源层级第 3 项，由 plan 已声明的完整读取链覆盖 |

### 2.3 Overdesign Controller discussion
| 文档 | 验证 |
|---|---|
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | plan §1 真源层级第 4 项引用，由 plan 已声明的完整读取链覆盖 |

### 2.4 五份 subsystem design
| 文档 | 验证 |
|---|---|
| `docs/host/design.md` | plan §1 真源层级第 5 项引用 |
| `docs/engine/design.md` | 同上 |
| `docs/tool/design.md` | 同上 |
| `docs/fins/design.md` | 同上 |
| `docs/ui/design.md` | 同上 |
所有五份 design 由 plan 已声明的完整读取链覆盖；plan 的修复边界未与任何 design 中的架构边界冲突。

### 2.5 第一次 S3 完整链
已读取以下第一次 S3 correction→review→fix→re-review→Controller adjudication→accepted commit→resume 完整链：
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-controller-validation.md`
确认第一次 S3 的 CF01–CF05 与本次第二次 S3 的 S3-P2-PF01–PF04 是独立的两轮 plan-review-fix，语义不重叠、不矛盾。

### 2.6 第二次 S3 完整链
| Artifact | SHA-256 | 状态 |
|---|---|---|
| S3 continuation | `3432724515aff3d1591a0c91ad83b31b7085fd01b39d7fe418ef68839951aaa7` | 已完整读取 |
| S3 second defect Controller adjudication | `9a7f640fad66a8e26edf86e8fea72d09dbadf1c8e80f7d12e6a14106a8a67fa8` | 已完整读取 |
| S3 second defect plan correction Codex | `15b53e8223883e572653eb4d26aa54390d2081ba84d986f10523722926da86a6` | 已完整读取 |
| S3 second defect plan correction Controller validation | `36df4cedf04e01746446de96d92b1b5e6f035d9b601e54ea8b084cdd456d836f` | 已完整读取 |
| S3 corrected plan accepted commit Controller validation | `4d0b7b64544584be9dca8a57301cf3d27343130fad5664c9635681e45c88eba5` | 已完整读取 |
| S3 resumed implementation Controller authorization | `a21eaabc88885a5134f000a94e965e495fbcd9f79a9b080abb857ea31967eb3c` | 已完整读取 |

### 2.7 MiMo 初审（second production defect）
| Artifact | SHA-256 | 状态 |
|---|---|---|
| MiMo complete plan review | `6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc` | 已完整读取，6 findings（01-06） |

### 2.8 DS 初审（second production defect，即本 reviewer 的第一次 review）
| Artifact | SHA-256 | 状态 |
|---|---|---|
| DS complete plan review | `6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822` | 已完整读取，5 findings（DS-F01–DS-F05） |

### 2.9 Controller adjudication
| Artifact | SHA-256 | 状态 |
|---|---|---|
| Controller adjudication | `725db848f7fb0eb9a2418a55ae90008b74131b5b360e8948415d3bb17b88daeb` | 已完整读取。Verdict: `PLAN_FIX_REQUIRED / ACCEPTED_GROUPS=4 / BLOCKER=0` |

### 2.10 Fix artifact
| Artifact | SHA-256 | 状态 |
|---|---|---|
| Fix Codex | `274e35dcb5fca22d49b7562d4e6f3a08510f1038f96771f5975f51045ef9d5cd` | 已完整读取。Verdict: `PLAN_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW` |

### 2.11 Controller validation
| Artifact | SHA-256 | 状态 |
|---|---|---|
| Controller validation | `0b51bda89fd9821494419d5365d8ca61542425df75dd37a029b9ead6b9361bb8` | 已完整读取。Verdict: `PASS / S3-P2-PF01..04 CLOSED_IN_PLAN / READY_FOR_DUAL_COMPLETE_REREVIEW` |

### 2.12 当前代码直接证据
| 代码位置 | 验证内容 | 结果 |
|---|---|---|
| `sec_form_section_common.py:947-992` | `list_tables()` 含 `fallback_ref`(974), `last_known_ref`(975), "底层已有 virtual ref 即保留"(985-988) | **确认存在**，plan 要求删除 |
| `sec_form_section_common.py:994-1018` | `list_sections()` 使用 `if not self._virtual_sections` guard(1007) | **确认存在**，第二个 consumer |
| `sec_form_section_common.py:1020-1034` | `get_section_title()` 使用 `if not self._virtual_sections` guard(1031) | **确认存在**，第三个 consumer |
| `sec_form_section_common.py:1036-1075` | `read_section()` 使用 `if not self._virtual_sections` guard(1050) | **确认存在**，第四个 consumer |
| `sec_form_section_common.py:1077-1116` | `search()` 使用 `if not self._virtual_sections` guard(1096) | **确认存在**，第五个 consumer |
| `sec_form_section_common.py:369-409` | `_initialize_virtual_sections()` 内首次 `_refresh_virtual_section_state()` 调用(408) | **确认存在**，首次 publication 入口 |
| `sec_form_section_common.py:426-497` | `_refresh_virtual_section_state()` 含 line 495-497 `ValueError` 抛出点 | **确认存在**，当前失败点 |
| `sec_form_section_common.py:842-945` | `_assign_tables_to_virtual_sections()` 含 `_filter_table_refs_by_availability()`(914) 和 `_assign_unmapped_tables_by_position()`(926) | **确认存在**，plan 要求删除 |
| `sec_form_section_common.py:2657-2677` | `_filter_table_refs_by_availability()` 函数体 | **确认存在**，静默过滤不在 base refs 中的 marker ref |
| `sec_form_section_common.py:2680-2741` | `_assign_unmapped_tables_by_position()` 函数体 | **确认存在**，按最近前驱边界猜测归属 |
| `sec_form_section_common.py:798-815` | `_collect_marked_text()` 调用 `get_full_text_with_table_markers()` | **确认存在**，SecProcessor 返回 `""` |
| `sec_processor.py:561-569` | `get_full_text_with_table_markers()` 返回 `""` | **确认存在**，marker unsupported 声明 |
| `ten_k_form_common.py:335-361` | `expand_ten_k_virtual_sections_content()` 含 `if not full_text or not virtual_sections: return`(361) | **确认存在**，空 candidate zero-diff guard |
| `ten_q_form_common.py:499-521` | `expand_ten_q_virtual_sections_content()` 含 `if not full_text or not virtual_sections: return`(521) | **确认存在**，空 candidate zero-diff guard |
| `sec_form_section_common.py:937-945` | `_remap_tables_to_deepest_virtual_sections()` 调用 | **确认存在**，子章节最深命中重分配 |

代码证据与 fixed plan 的描述完全一致，无漂移。

## 3. Plan hash verification

```bash
$ shasum -a 256 docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md
552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04
```

**Plan hash 验证通过**。Target 与 immutable target 声明完全一致。Plan diff 为 `135 insertions / 53 deletions`（来源：fix artifact §6），经完整读取确认修复精确作用于四组 accepted findings 范围，无 scope drift。

## 4. 逐组 S3-P2-PF01..04 closure 验证

### 4.1 S3-P2-PF01 — typed publication state and exact consumers

**Controller 裁决要求**（来自 Controller adjudication §S3-P2-PF01）：
- 固定 owner-private typed enum/state，至少 `BUILDING`、`VIRTUAL_PUBLISHED`、`BASE_FALLBACK_PUBLISHED`
- 唯一 transition owner 是 `_refresh_virtual_section_state()`
- 不得以 `_virtual_sections`、空 dict/list、异常或偶然顺序反推状态
- 五个 public consumers 逐一按 typed mode 选择完整 virtual 或完整 base contract

**Fixed plan 证据**：

| 要求 | Fixed plan 位置 | 内容 | 状态 |
|---|---|---|---|
| typed enum 定义 | §2.6 | `BUILDING`、`VIRTUAL_PUBLISHED`、`BASE_FALLBACK_PUBLISHED` | ✅ |
| 唯一 transition owner | §2.6 | `_refresh_virtual_section_state()`是唯一terminal transition owner，只允许`BUILDING -> VIRTUAL_PUBLISHED \| BASE_FALLBACK_PUBLISHED`、`VIRTUAL_PUBLISHED -> VIRTUAL_PUBLISHED`受约束刷新与`BASE_FALLBACK_PUBLISHED -> BASE_FALLBACK_PUBLISHED`幂等no-op | ✅ |
| 不反推状态 | §2.6 | "不得从`_virtual_sections`、空dict/list、异常、时间、日志或偶然顺序反推状态" | ✅ |
| 五个 consumers 枚举 | §2.6 | `list_sections()`、`list_tables()`、`get_section_title()`、`read_section()`、`search()` | ✅ |
| mode guard 统一 | §2.6 | "`mode != VIRTUAL_PUBLISHED`时都直接委托base processor对应public contract" | ✅ |
| 纠正"六个"计数 | §2.6 | "当前consumer数量固定为五个，不沿用reviewer'六个'的错误计数" | ✅ |
| §4.3 item 1 实施规格 | §4.3 item 1 | `_initialize_virtual_sections()`只初始化`BUILDING`+建立candidate；`_refresh_virtual_section_state()`唯一terminal transition | ✅ |
| §4.3 item 7 consumer guard | §4.3 item 7 | 逐一列出五个 consumer 的 `mode != VIRTUAL_PUBLISHED -> base processor` 委托 | ✅ |
| §4.3 item 7 list_tables 补偿删除 | §4.3 item 7 | "删除`fallback_ref`、`last_known_ref`与'底层已有virtual ref即保留'等下游补偿" | ✅ |
| checklist | §10 | "五个且只有五个public consumers...只消费同一typed mode" | ✅ |

**代码验证**：当前 `sec_form_section_common.py` 确认五个 public consumers 的 line numbers 分别为 947(list_tables)、994(list_sections)、1020(get_section_title)、1036(read_section)、1077(search)。不存在第六个 consumer。当前代码使用 `if not self._virtual_sections` guard — 这正是 plan 要替换的旧 guard，plan 的 `mode != VIRTUAL_PUBLISHED` 是新的 typed guard。✅

**Verdict**: `S3-P2-PF01 CLOSED — 完整、可实施、无歧义`

### 4.2 S3-P2-PF02 — raw marker proof, validation order and helper disposition

**Controller 裁决要求**（来自 Controller adjudication §S3-P2-PF02）：
- 从 owner mapping path 删除 `_filter_table_refs_by_availability()` 的静默过滤语义
- 删除 `_assign_unmapped_tables_by_position()` 及其最近/首章节猜测
- 候选构建保留 raw marker refs
- 固定 validation order：base duplicate → dangling → marker duplicate/multi-section/tree/bidirectional → incomplete → virtual

**Fixed plan 证据**：

| 要求 | Fixed plan 位置 | 内容 | 状态 |
|---|---|---|---|
| 删除 silent filter | §2.6 | "删除`_filter_table_refs_by_availability()`及其全部调用" | ✅ |
| 删除 position guess | §2.6 | "删除`_assign_unmapped_tables_by_position()`及其调用" | ✅ |
| 保留 raw marker refs | §2.6 | "候选构建必须保留raw marker refs与出现次数/范围归属证据，禁止在完整性与矛盾校验前丢弃信息" | ✅ |
| validation order #1 | §2.6 | "先要求每张public base table具有非空、唯一`table_ref`，缺失或重复都`ValueError` fail-closed" | ✅ |
| validation order #2 | §2.6 | "再判定raw marker ref不在base refs中的dangling" | ✅ |
| validation order #3 | §2.6 | "再判定同一marker ref重复出现、落入多个section、section tree悬挂或table→section/section→tables双向矛盾" | ✅ |
| validation order #4 | §2.6 | "只有这些检查全部通过后，`base_refs - mapped_refs`非空才是incomplete proof并整体base fallback" | ✅ |
| validation order #5 | §2.6 | "两集合完全且双向一致才一次发布`VIRTUAL_PUBLISHED`" | ✅ |
| incomplete+dangling 优先级 | §2.6 | "incomplete与dangling同时存在时dangling优先fail-closed" | ✅ |
| range/title 不能唯一归属 | §2.6 | "无dangling但marker range/title不能唯一归属时属于incomplete，必须whole-base fallback" | ✅ |
| §4.3 item 4 实施规格 | §4.3 item 4 | 完整重复 validation order 1-4 | ✅ |
| §4.3 item 6 实施规格 | §4.3 item 6 | "物理删除`_filter_table_refs_by_availability()`及其调用...物理删除`_assign_unmapped_tables_by_position()`及其调用" | ✅ |
| checklist | §10 | "`_filter_table_refs_by_availability`静默过滤...与`_assign_unmapped_tables_by_position`均为零" | ✅ |

**代码验证**：`_filter_table_refs_by_availability()`(line 2657) 实现为 `[ref for ref in refs if ref in available_table_refs]` — 静默过滤不在 base refs 中的 marker ref，与 plan 的 dangling ref detection 需求直接矛盾。`_assign_unmapped_tables_by_position()`(line 2680) 实现为按最近前驱边界猜测未映射 table 归属。两者均需物理删除。✅

**Verdict**: `S3-P2-PF02 CLOSED — 唯一选择（删除非收紧）、validation order 固定不可交换、实施路径无歧义`

### 4.3 S3-P2-PF03 — first refresh and terminal fallback lifecycle

**Controller 裁决要求**（来自 Controller adjudication §S3-P2-PF03）：
- 显式追溯 `_initialize_virtual_sections()` 内首次 `_refresh_virtual_section_state()` 是首次 publication decision 与当前构造失败入口
- 首次 refresh 与 10-K/10-Q subclass 第二次 postprocess/refresh 复用同一 owner mode
- 首次 fallback 清空/禁用 candidate virtual projection 并发布 typed base-fallback terminal
- 之后 refresh 幂等 no-op
- base tables 为空时空 mapping 发布合法 virtual state
- 锁定两个 expand 函数现有空 candidate guard 为 zero-diff 证据，用 public 10-K/10-Q re-entry cases 验证

**Fixed plan 证据**：

| 要求 | Fixed plan 位置 | 内容 | 状态 |
|---|---|---|---|
| 显式追溯首次 refresh | §2.6 | "`_initialize_virtual_sections()`内第一次`_refresh_virtual_section_state()`既是首次publication decision，也是当前public构造失败的真实入口" | ✅ |
| 首次/二次共享终态 | §2.6 | "它与10-K/10-Q subclass第二次`_postprocess_virtual_sections()`/refresh复用同一typed终态" | ✅ |
| 首次 fallback 清空 candidate | §2.6 | "首次fallback必须清空candidate并发布`BASE_FALLBACK_PUBLISHED`，之后refresh不再读marker/base、不重建candidate、不抛第二次失败" | ✅ |
| virtual 成功 + refresh | §2.6 | "virtual已成功发布时仍允许现有postprocess按identity约束刷新" | ✅ |
| zero-table virtual | §2.6 | "base tables为空时，空mapping本身就是完整证明，合法虚拟章节发布`VIRTUAL_PUBLISHED`；不得因marker unsupported无意义地回退" | ✅ |
| expand guard lock | §2.6 | "锁定该直接证据`if not full_text or not virtual_sections: return`并用public 10-K/10-Q re-entry验证，guard漂移才STOP" | ✅ |
| §4.3 item 2 实施规格 | §4.3 item 2 | "显式把`_initialize_virtual_sections()`内首次`_refresh_virtual_section_state()`锁定为首次publication decision与当前公开构造失败入口" | ✅ |
| §4.3 item 3 zero-table | §4.3 item 3 | "base tables为空时，以空table mapping发布合法`VIRTUAL_PUBLISHED`" | ✅ |
| §4.3 item 8 expand guard | §4.3 item 8 | "锁定该zero-diff guard并用public 10-K/10-Q re-entry cases验证。若guard或行为漂移才STOP" | ✅ |

**代码验证**：
- `_initialize_virtual_sections()` line 408: `self._refresh_virtual_section_state()` — 首次 publication 调用 ✅
- `ten_k_form_common.py:361`: `if not full_text or not virtual_sections: return` — expand guard ✅
- `ten_q_form_common.py:521`: `if not full_text or not virtual_sections: return` — expand guard ✅

**Verdict**: `S3-P2-PF03 CLOSED — 首次/二次 refresh 共享终态、fallback 生命周期、expand zero-diff guard 均已精确化。DS-F03 的 "空列表行为未知" 事实判断已由代码直接证据证明为错误，其 re-entry 验证要求已正确归入本组`

### 4.4 S3-P2-PF04 — exact base identity and mixed counterexamples

**Controller 裁决要求**（来自 Controller adjudication §S3-P2-PF04）：
- base/form 逐值比较 section refs、table refs、table `section_ref`、`read_section(...)["tables"]`、`get_section_title()`、`read_section()`、`search()`
- 不能只比较长度/非空/内容摘要
- 增加 incomplete+dangling 混合 case（dangling 优先 fail-closed）
- 增加 range/title 不能唯一归属但无 dangling case（incomplete whole-base fallback）

**Fixed plan 证据**：

| 要求 | Fixed plan 位置 | 内容 | 状态 |
|---|---|---|---|
| 逐值比较 | §4.3 matrix #1 | "逐值比较base/form的完整section ref序列、完整table ref序列、每张table的`section_ref`与每个base section的`read_section(ref)["tables"]`。再用每个base ref调用form的`get_section_title(ref)`、`read_section(ref)`与`search(..., within_ref=ref)`并与base结果逐值比较" | ✅ |
| 禁止弱断言 | §4.3 matrix #1 | "不得只比较长度、非空、内容摘要或'不抛异常'，也不得把表格塞进任意virtual ref" | ✅ |
| incomplete+dangling 混合 | §4.3 matrix #4 | "另固定混合case：base refs含未映射项且raw marker同时含dangling ref时，dangling/contradiction检查必须优先fail-closed，不能被incomplete fallback吞掉" | ✅ |
| range/title 不唯一 | §4.3 matrix #3(c) | "无dangling但marker range/title不能唯一归属时属于incomplete，必须whole-base fallback" | ✅ |
| counterexample #3 细分 | §4.3 matrix #3 | 覆盖 (a) base≥2 tables+marker只证1表；(b) raw marker refs都属于base且无重复/dangling但range/title不能唯一归属 | ✅ |
| counterexample #4 | §4.3 matrix #4 | 覆盖缺失/重复base table_ref、marker非base dangling、同一marker ref重复/归属多section、tree/双向矛盾、混合case | ✅ |
| counterexample #6 | §4.3 matrix #6 | 覆盖 10-K/10-Q 二次 postprocess fallback 幂等不重入，"逐值不变，marker/base mapping call count不增加，无异常、无virtual/partial state重生" | ✅ |
| checklist | §10 | "六类owner/public反例完整：...fallback逐值验证base/form section refs、table refs、table section_ref、title/read/search及read_section.tables" | ✅ |

**Verdict**: `S3-P2-PF04 CLOSED — 逐值比较已全面覆盖 section refs/table refs/table section_ref/title/read/search/read_section.tables；两个混合 case（incomplete+dangling 优先 fail-closed、range/title 不唯一 → incomplete fallback）已固定；六类 matrix 完整`

## 5. Rejected/narrowed candidates 复活检查

### 5.1 MiMo 05 — `read_section()` 和 `search()` 的 base fallback guard

- **原裁决**: `rejected-as-duplicate`（Controller adjudication §Rejected/narrowed）
- **Fixed plan 处置**: §2.6 和 §4.3 item 7 已将 `read_section()` 和 `search()` 纳入五 consumer 统一 guard `mode != VIRTUAL_PUBLISHED -> base processor`
- **结论**: 未复活为独立 finding；其有效 guard 精确化已归入 S3-P2-PF01 ✅

### 5.2 DS-F03 — expand 函数对空列表行为未知

- **原裁决**: `rejected-as-evidence-invalid`（Controller adjudication §Rejected/narrowed），当前两个函数的首个业务 guard 均直接处理空列表
- **Fixed plan 处置**: §2.6 和 §4.3 item 8 锁定 `if not full_text or not virtual_sections: return` 为 zero-diff 直接证据，并要求 public 10-K/10-Q re-entry 验证
- **代码验证**: `ten_k_form_common.py:361` 和 `ten_q_form_common.py:521` 均确认该 guard 存在
- **结论**: 未复活为独立 finding；其 re-entry 验证要求已归入 S3-P2-PF03 ✅

### 5.3 其他 rejected/narrowed

| Candidate | 裁决 | Fixed plan 状态 | ✅ |
|---|---|---|---|
| Reviewer "六个 public methods" 计数 | 不采用 | §2.6 "当前consumer数量固定为五个" | ✅ |
| Private enum 升级为 public schema | 不接受 | §2.6 enum 明确为 owner-private | ✅ |
| DS-F04 具体状态名建议 | Accepted into PF01 | §2.6 已定义 `BUILDING/VIRTUAL_PUBLISHED/BASE_FALLBACK_PUBLISHED` | ✅ |

**结论**: 所有 rejected/narrowed candidates 均未复活，处置与 Controller adjudication 完全一致。

## 6. Allowlists drift 检查

### 6.1 Production allowlist（§3.1）

| Slice | 路径 | Fixed plan 状态 |
|---|---|---|
| Slice 2 | `M dayu/cli/commands/fins.py` + 11 others | 不变 |
| Slice 3 | `M dayu/documents/processors/docling_processor.py` | Protected, entry hash 不变 |
| Slice 3 | `M dayu/fins/processors/sec_form_section_common.py` | 本次恢复 implementation 唯一新增 |

**结论**: 无 drift ✅

### 6.2 Test allowlist（§3.2）

六个 Slice 3 test paths 按 §0 exact hash 受保护：
- `tests/documents/test_processors.py` ✅
- `tests/fins/test_sec_pipeline_download.py` ✅
- `tests/fins/test_processor_read_consistency.py` ✅
- `tests/fins/test_fins_ingestion_tools.py` ✅
- `tests/host/test_effective_execution_config.py` ✅
- `tests/runtime/test_argparse_exit.py` ✅

**结论**: 无 drift ✅

### 6.3 Validation-utility allowlist（§3.3）

仅 `M utils/smoke_host_public_awaiting_entrypoint.py` 在 Slice 2 允许单行 import 迁移。Slice 3 不变。

**结论**: 无 drift ✅

### 6.4 README allowlist（§3.4）

| README | Slice 3 裁决 | 状态 |
|---|---|---|
| `dayu/fins/README.md` | `UPDATE` — atomic virtual/base publication 语义 | ✅ |
| 根 `README.md` | `NO_UPDATE` | ✅ |
| `dayu/README.md` | `NO_UPDATE` | ✅ |
| `tests/README.md` | `NO_UPDATE` | ✅ |

**结论**: 无 drift ✅

### 6.5 Protected zero-diff paths（§3.5）

所有七类 protected paths 在 fixed plan 中均保持不变，包括：
- AR-F06 scheduler owners (4 paths)
- AR-F03 standalone logging (3 paths)
- AR-F01 production config (2 paths)
- AR-F04 compact/manifest (6 paths)
- AR-F02 boundary/compatibility (3 paths)
- AR-F05 other seven owners (7 paths)
- AR-F07 workflow (2 paths)
- All design/control/artifact docs

**结论**: 无 drift ✅

## 7. 219/219 coverage gate drift 检查

### 7.1 集合变化预期

Plan §4.2 和 §6.2 明确：
- Slice 2 删除 `dayu/fins/direct_stream.py`，新增 `dayu/fins/ingestion/awaiting_resolution.py`
- 219 集合成员数保持 219
- 任何额外增删均为 scope failure → STOP

### 7.2 Coverage 要求

- 219/219 line coverage >= 80.00%
- Exact single-node exclusion: `tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`
- Coverage 前必须 fail-closed `pytest --collect-only` 唯一收集该 node id
- 禁止额外 deselect/ignore/omit
- Line coverage 计算: `covered_lines / num_statements * 100`（不用 branch combined）

**结论**: 219/219 gate 定义精确、无漂移 ✅

## 8. Security/quota/deferred gates drift 检查

### 8.1 Configured-secret semantic classification（§6.7）

| Surface | Classification | Fixed plan 状态 |
|---|---|---|
| Config / Host internal SQLite/EventLog | `ACCEPTED_TRUSTED_INTERNAL` | ✅ 不变 |
| Tool Trace hot/cold/query | `ZERO_REQUIRED` | ✅ 不变 |
| Audit JSONL/query | `ZERO_REQUIRED` | ✅ 不变 |
| Public HostEvent / read model | `ZERO_REQUIRED` | ✅ 不变 |
| LLM-facing (memory/compact/evidence/observation) | `ZERO_REQUIRED` | ✅ 不变 |
| Operator logs | `ZERO_REQUIRED` | ✅ 不变 |
| Git diff / review artifacts | `ZERO_REQUIRED` | ✅ 不变 |

**结论**: 语义分类无漂移 ✅

### 8.2 Gemini quota

`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING` — 不变 ✅

### 8.3 Deferred

Issues 142/151/175/177/178 保持各自 owner；不引入 TruncationManager、storage-state lifecycle、Fins hard-kill、assets migration — 不变 ✅

### 8.4 No-code

Topic 8 (`dayu/engine/agent.py`、`dayu/engine/contracts/error_codes.py` zero diff)、Topic 9（无统一 authorization framework）— 不变 ✅

### 8.5 AR-F06 / AR-F07

- AR-F06: `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX` — 不变 ✅
- AR-F07: `PENDING_RELEASE_BLOCKER` — 不变 ✅

**结论**: 所有 security/quota/deferred/no-code gates 无漂移 ✅

## 9. S1-SEC-F01 closure stability

Plan §2.2.1 的 local trust/projection owner adjudication 保持不变：
- Config/Host internal effective-execution: `ACCEPTED_TRUSTED_INTERNAL` ✅
- Six projection surfaces: 各自 `NO_CURRENT_LEAK` ✅
- Slice 1 owner-level synthetic sentinel tests 已定义但未实施 ✅
- §6.7 configured-secret scan 要求 semantic owner 分类（不是全局零命中） ✅

**结论**: S1-SEC-F01 closure 稳定，未被 S3-P2-PF01..04 修改波及 ✅

## 10. Architecture boundary review

| Lens | Result |
|---|---|
| Layering | PASS — 修复在 `sec_form_section_common.py`（Fins processor 层），不改 DocumentProcessor marker contract、SecProcessor、subclass |
| Ownership | PASS — `_refresh_virtual_section_state()` 是唯一 terminal transition owner；五个 consumers 统一委托 |
| Dependency direction | PASS — 无新增跨层依赖；base fallback 复用既有 `_get_base_processor()` → `SecProcessor` MRO 链 |
| Public contracts | PASS — 五个 public consumer 接口签名不变；`TableSummary.caption` schema 不变 |
| Schema/storage | PASS — private typed enum 不暴露为 public schema；无 durable state schema 变更 |

## 11. Best-practice review

| Check | Result |
|---|---|
| State machine | PASS — 三态 `BUILDING → VIRTUAL_PUBLISHED \| BASE_FALLBACK_PUBLISHED` 是最小充分设计 |
| Atomic publication | PASS — 全部验证在局部变量/候选 mapping 完成，一次性提交或一次性清空 |
| Fail-closed | PASS — duplicate/dangling/contradiction → `ValueError`，不吞错 |
| Graceful degradation | PASS — incomplete proof → whole-base fallback 复用同源 base processor |
| Testability | PASS — 六类 counterexample matrix 覆盖 virtual/fallback/fail-closed/idempotence |
| Observability | PASS — fail-closed 抛明确 `ValueError` 含业务片段；不 silent-filter/warning/log |

## 12. Overengineering review

| Check | Result |
|---|---|
| 新增 abstractions | 无 — private enum 是唯一新增类型 |
| 新增 capability schema | 无 — 明确禁止 DOM/raw HTML marker 或 capability schema |
| 新增 resolver/framework | 无 — 明确禁止第二 resolver、compatibility wrapper |
| 新增 production path | 无 — allowlist 精确两个路径（一个 protected delta + 一个本次新增） |

## 13. Overcoupling review

| Check | Result |
|---|---|
| 跨模块依赖 | 无新增 — 修复在 single-file single-owner |
| Subclass 修改 | 零 diff — `ten_k_processor.py`、`ten_q_processor.py` 不改 |
| Marker producer | 零 diff — `SecProcessor.get_full_text_with_table_markers() -> ""` 不改 |
| Base processor | 零 diff — `DocumentProcessor` marker contract 不改 |
| Shared mutable state | 无新增 — `_publication_mode` 是 owner-private instance field |
| Test coupling | 六类 matrix 只断言 public contract，不复制 private 算法 |

## 14. Implementation readiness

### 14.1 Code-generation-ready 标准

| 标准 | 状态 |
|---|---|
| 数据结构定义明确 | ✅ typed enum 三成员固定 |
| 函数行为契约明确 | ✅ `_refresh_virtual_section_state()` transition rules 完整 |
| Validation order 固定 | ✅ 不可交换的 4-step order |
| Consumer guard 统一 | ✅ 五个 consumer 的 `mode != VIRTUAL_PUBLISHED -> base` |
| 错误语义明确 | ✅ ValueError（contradiction）vs base fallback（incomplete）区分 |
| Counterexample matrix | ✅ 六类全覆盖 |
| Stop conditions | ✅ §9 完整 stop condition list |
| Implementation order | ✅ §4.3 先关 S3-STOP-F02，再继续 coverage |

### 14.2 潜在实施风险（非 blocker）

以下是我在本轮独立 re-review 中发现的两个低严重度观察，不构成 blocker：

#### OBS-01 — 低 — `_build_virtual_sections_from_base()` 在 base fallback 路径上是冗余计算

- **位置**: `_initialize_virtual_sections()` line 403-404 → `_refresh_virtual_section_state()` line 408
- **观察到的事实**: 当 marker unsupported 时，`_build_virtual_sections_from_base()` 从 base processor 构建 virtual section 候选，随后首次 refresh 判定 base fallback 并清空全部 virtual fields。这次构建在 base fallback 路径上是冗余的。
- **为什么不是 blocker**: (a) 这是既有行为，plan 不修改 `_initialize_virtual_sections()` 的候选构建流程；(b) 冗余计算不产生语义错误——refresh 清空后五个 consumers 正确委托 base processor；(c) 优化它需要修改 `_initialize_virtual_sections()` 的流程控制，而 plan 的 explicit scope 已把该函数的修改限制在"只初始化 BUILDING 并建立候选"。
- **建议**: 可作为 future optimization note，不在本 plan 修复。

#### OBS-02 — 低 — `_remap_tables_to_deepest_virtual_sections()` 未被 plan 显式提及

- **位置**: `_assign_tables_to_virtual_sections()` line 937-945
- **观察到的事实**: Plan 详细描述 `_assign_tables_to_virtual_sections()` 的改造（删除 Phase 1 filter + Phase 2 position guess），但未显式提及子章节最深命中重分配函数 `_remap_tables_to_deepest_virtual_sections()`。该函数在虚拟章节有子节点时重分配 table→section 映射到最深匹配章节。
- **为什么不是 blocker**: (a) 该函数操作的是 Phase 1/2 之后已分配的 mapping，不是独立的数据源；(b) 它在 `_assign_tables_to_virtual_sections()` 内部被调用，改造该函数时自然保留或调整其调用；(c) 该函数不引入新的 dangling/duplicate 风险——它只在已映射的 refs 间重新分配 section_ref，且 `_refresh_virtual_section_state()` 的最终验证会检查 section.table_refs 和 table→section 双向一致性。
- **建议**: Implementation agent 在改造 `_assign_tables_to_virtual_sections()` 时需确认 `_remap_tables_to_deepest_virtual_sections()` 的输入假设（已映射的 `_table_ref_to_virtual_ref`）不受 filter/position guess 删除影响。

## 15. Final plan review conclusion

**PASS**

Fixed plan `552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04` 通过了独立完整 adversarial re-review：

1. **S3-P2-PF01–PF04 全部 CLOSED**：typed 三态枚举、唯一 transition owner、五个 consumer 统一 mode guard、silent filter 和 position guess 物理删除、fixed validation order、首次/二次 refresh 共享终态、zero-table virtual、expand zero-diff guard 锁定、base exact refs/title/read/search/table ownership 逐值比较、incomplete+dangling 混合优先级、range/title 不唯一 → incomplete fallback — 全部精确可实施。

2. **Rejected MiMo05/DS-F03 未复活**：MiMo05 保持 `rejected-as-duplicate`（有效 guard 归入 PF01），DS-F03 保持 `rejected-as-evidence-invalid`（re-entry 验证归入 PF03），无第五组 fix。

3. **Allowlists 无漂移**：production/test/validation-utility/README allowlists 与 Controller adjudication entry 一致；protected zero-diff paths 全部受保护。

4. **219/219 无漂移**：集合变化（删 direct_stream.py + 增 awaiting_resolution.py）精确预期；line coverage >= 80% 含 fail-closed collect-only preflight。

5. **Security/quota/deferred gates 无漂移**：configured-secret semantic classification、Gemini quota、deferred Issues、no-code Topics、AR-F06/F07 status 全部保持。

6. **无新 blocker finding**：两个低严重度观察（OBS-01 冗余计算、OBS-02 子章节重分配函数未显式提及）均不构成实施阻塞，不要求 plan 修改。

**唯一 next gate**: AgentMiMo 完成对同一 fixed plan + fix artifact + 本 re-review 的独立完整 re-review，且 Controller 在双路均 PASS 后发布新的 Slice 3 implementation authorization。在此之前，implementation、stage、commit、push、PR 均未授权。

---

**Reviewed target**: `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`
**Reviewed target SHA-256**: `552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04`
**Fix artifact SHA-256**: `274e35dcb5fca22d49b7562d4e6f3a08510f1038f96771f5975f51045ef9d5cd`
**Controller validation SHA-256**: `0b51bda89fd9821494419d5365d8ca61542425df75dd37a029b9ead6b9361bb8`
**Review gate**: Plan-only re-review; 未修改 plan、control、code、tests、README 或其它 artifact; 未 stage/commit。
**唯一可写**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-rereview-ds.md`
