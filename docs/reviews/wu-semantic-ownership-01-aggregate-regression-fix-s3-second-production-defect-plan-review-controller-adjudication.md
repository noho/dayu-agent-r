# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二个 Production Defect Plan Review Controller Adjudication

## Verdict

`PLAN_FIX_REQUIRED / ACCEPTED_GROUPS=4 / BLOCKER=0 / DESIGN_CONTRADICTION=0`。

AgentMiMo 与 AgentDS 均完整 review immutable plan
`466fd5fd717c1ea35a4da0807ef425300ea7b4c855c400361805438681bcea6b`，并一致接受
atomic virtual/base publication 的 owner 与方向。两路 finding 高度重叠；Controller 合并为四组
plan-only fixes。没有用户产品决策、外部授权或新 WU 需要。

Review artifacts：

- MiMo：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-mimo.md`，
  SHA-256 `6e747659183c0c59efed30e22129e3c5510802ae154be307d2d122f3449854dc`。
- DS：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-ds.md`，
  SHA-256 `6c7556f20c78901b188f01649184b2df7cd479ab3d2facd3bf9a1c3af56ed822`。

## Accepted plan-fix groups

### S3-P2-PF01 — typed publication state and exact consumers

接受 MiMo 01、DS-F04，并吸收 MiMo 05 的有效部分。

Plan 必须固定 owner-private typed enum/state，至少区分 `BUILDING`、`VIRTUAL_PUBLISHED`、
`BASE_FALLBACK_PUBLISHED`；初始状态与唯一 transition owner 是
`_initialize_virtual_sections()` / `_refresh_virtual_section_state()` 的同一 owner boundary。
不得以 `_virtual_sections`、空 dict/list、异常或偶然顺序反推状态。

当前直接 public consumers 是五个，不是 reviewer 文本中的六个：`list_sections()`、
`list_tables()`、`get_section_title()`、`read_section()`、`search()`。Plan 必须逐一要求它们只按
typed mode 选择完整 virtual 或完整 base contract；virtual 之外一律直接委托 base processor。

### S3-P2-PF02 — raw marker proof, validation order and helper disposition

接受 MiMo 02/06、DS-F02/DS-F05。

Plan 必须作唯一选择，而不是“删除或收紧”：从 owner mapping path 删除
`_filter_table_refs_by_availability()` 的静默过滤语义，并删除
`_assign_unmapped_tables_by_position()` 及其最近/首章节猜测。候选构建必须保存 raw marker refs，
在任何 incomplete fallback decision 前按以下顺序校验：

1. base table refs 非空、唯一；重复 fail-closed；
2. raw marker ref 不在 base refs 中是 dangling，fail-closed；
3. 同一 marker ref 重复出现、落入多个 section 或 section/tree/bidirectional contradiction，
   fail-closed；
4. 上述矛盾均不存在后，`base_refs - mapped_refs` 非空才是 incomplete proof，整体 base fallback；
5. 两集合完全且双向一致才可一次发布 virtual state。

因此 incomplete + dangling 混合 case 必须先 fail-closed，不能被 fallback 吞掉。

### S3-P2-PF03 — first refresh and terminal fallback lifecycle

接受 DS-F01、MiMo 03；DS-F03 只接受“把已经存在的直接证据与验证要求写清楚”，不接受其
“空列表行为未知”的事实判断。

Plan 必须显式追溯 `_initialize_virtual_sections()` 内的第一次
`_refresh_virtual_section_state()`：它是首次 publication decision，也是当前公开构造失败的真实
入口。首次 refresh 与 10-K/10-Q subclass 的第二次 postprocess/refresh 复用同一个 owner mode，
不能把修复误写成只处理第二次调用。

首次 fallback 必须清空/禁用 candidate virtual projection 并发布 typed base-fallback terminal；
之后 refresh 幂等 no-op。base tables 为空时空 mapping 已完整，仍发布合法 virtual state，不进入
fallback。

当前代码已直接证明两个 expand functions 对空 candidate 安全：
`expand_ten_k_virtual_sections_content()` 与 `expand_ten_q_virtual_sections_content()` 均以
`if not full_text or not virtual_sections: return` 开头。Plan 应把该 zero-diff guard 作为当前证据
锁定，并用 public 10-K/10-Q re-entry cases 验证；若该 guard 或行为漂移才 STOP，不扩
`ten_k_processor.py`、`ten_q_processor.py` 或 form-common allowlist。

### S3-P2-PF04 — exact base identity and mixed counterexamples

接受 MiMo 04，并把两路 ref/混合-case建议收敛为一个测试规格。

Public unsupported/incomplete fallback cases 必须逐值比较 base processor 与 form processor 的
section refs、table refs、table `section_ref`、`read_section(...)["tables"]`，并通过 base refs 调用
`get_section_title()` / `read_section()` / `search()`，证明 ref 命名空间、内容和 table ownership
全部同源，不能只比较长度/非空/内容摘要。

Counterexample matrix 增加或收紧两个组合：

- incomplete + dangling 同时存在：dangling/contradiction 优先，`ValueError`；
- marker range/title 不能唯一归属但没有 dangling：属于 incomplete proof，整体 base fallback，
  不得退回位置猜测或旧集合不等异常。

## Rejected / narrowed reviewer candidates

- MiMo 05 作为独立 finding rejected-as-duplicate：原 plan §4.3 item 7 已明确列出
  `read_section()`、`get_section_title()` 与 `search()` 使用同一 mode；其 guard 精确化已纳入
  `S3-P2-PF01`，无需第五组 finding。
- DS-F03 的“expand 对空列表行为未知” rejected-as-evidence-invalid：当前两个函数的首个业务
  guard 均直接处理空列表。其有价值的 re-entry 验证要求已纳入 `S3-P2-PF03`。
- DS-F04 的具体状态名建议 accepted into `S3-P2-PF01`，但不新增 public schema；该 enum 仅是
  owner-private typed state。
- reviewer 对“六个 public methods”的计数不采用；当前代码是上述五个 public consumers。

## Scope and next gate

唯一授权是 AgentCodex plan-only fix：

- 修改 `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`；
- 新建 `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-plan-review-fix-codex.md`。

不得修改 production、tests、README、control、既有 artifacts；不得运行实现、stage/commit、进入
code review/aggregate。修复后必须由 Controller 验证，并由 AgentMiMo / AgentDS 对完整新 plan
做并发完整 re-review；只看 fix diff 不算 re-review。
