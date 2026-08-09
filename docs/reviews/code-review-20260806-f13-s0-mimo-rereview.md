# Code Review — S0 Re-review

## Scope

- Mode: re-review of M1-M4 findings
- Base: `2d914beefb7bdee3e762df06f5f1ef0d115da143`
- Controller adjudication: `docs/gateflow/pr-190-f13-s0-review-adjudication-20260806.md`
- Original review: `docs/reviews/code-review-20260806-145045.md`
- Reviewed files:
  - `docs/host/design.md` (修复后)
  - `docs/gateflow/pr-190-f13-s0-design-implementation-20260806.md` (修复后)

## Findings Re-review

### M1: `CompactAcceptedTruthV4`字段列表未完整展开

- **原severity**: 中
- **Controller裁决**: ACCEPT / FIXED
- **复审结果**: **FIXED**
- **证据**:
  - `docs/host/design.md:3447-3456`新增完整typed shape：
    ```text
    CompactAcceptedTruthV4
      proposal: CompactCandidateV4
      replacement: CompactAcceptedReplacementV4
      source_boundary: tuple[CompactSourceBoundaryEntryV4, ...]
      represented_coverage: CompactRepresentedCoverageV4
      omitted_coverage: CompactOmittedCoverageV4
      policy_usage_audit: CompactPolicyUsageAuditV4
      current_input_ref: str
      _permit: _CompactAcceptancePermit
    ```
  - 同一位置明确说明"frozen/slots dataclass且无业务默认值"
  - 同一位置说明"truth校验child types、current input与coverage partition shape"
- **验证**: 字段列表完整，类型明确，与`CompactAcceptedEvidenceFactV4`和`CompactAcceptedReplacementV4`的定义风格一致。实现者可直接从此处构造typed dataclass。

### M2: reactive multi-pass聚合规则描述过于简略

- **原severity**: 中
- **Controller裁决**: ACCEPT / FIXED
- **复审结果**: **FIXED**
- **证据**:
  - `docs/host/design.md:3918-3932`新增详细multi-pass聚合规则：
    1. 每个pass必须针对自己的immutable boundary完成一次完整v4 accept
    2. pass-local caps只是提前拒绝明显非法结果，不能替代root final caps
    3. Host按pass queue顺序机械聚合audit proposal（summary text换行连接、labels unique union、new facts按pass queue拼接）
    4. Host同时从各pass accepted replacement聚合final replacement（retained atoms在前、new atoms在后，atom不可拆分）
    5. atom属于retained还是new只能由source kind确定
    6. 最终root governance validator必须重新执行exact binding、combined caps、coverage、逐fact refs等式、accepted aggregate union与request-boundary ordered-subset校验
  - `docs/gateflow/pr-190-f13-s0-design-implementation-20260806.md`的"Changed design truth"章节也记录了这些规则
- **验证**: 聚合规则现在精确且可执行，覆盖了：(1)多个pass的replacement如何合并；(2)retained/new顺序；(3)caps检查时机（pass-local预检 + root final验证）。实现者可据此实现确定性聚合。

### M3: implementation artifact缺goal逐项映射

- **原severity**: 低
- **Controller裁决**: ACCEPT / FIXED
- **复审结果**: **FIXED**
- **证据**:
  - `docs/gateflow/pr-190-f13-s0-design-implementation-20260806.md:64-76`新增"Goal Confirmation逐项映射"表
  - 8项目标逐项映射：
    | Confirmed goal | Design owner / section | S0固定结果 |
    |---|---|---|
    | 1. accepted EvidenceFact是含非空per-fact refs的原子事实 | §24.3 accepted types / accept chain | `CompactAcceptedEvidenceFactV4`同形保存claim、selection、context与非空refs |
    | 2. rolling旧fact只可keep/omit且claim+refs同源 | §24.2、§24.3 source boundary、§24.4 rolling | required retain selector只选previous label |
    | 3. new fact只选当前真实evidence且逐fact解析 | §24.3 proposal / strict binding | `support_labels`只允许`evidence_material` |
    | 4. durable前完整barrier、repair与fallback | §24.3 accept chain、§24.6 repair、§25状态机 | boundary构造先fail closed |
    | 5. 无工具证据的用户/assistant修正不得升级 | §24.2、§24.3 source-kind规则、§24.5 Memory | non-evidence source只可进入相应非evidence section |
    | 6. rejected/failed/stale/late无污染和单terminal | §24.3 repair末段、§24.6、§25 | invalid / transient result无accepted读取入口 |
    | 7. artifact/EventLog/Memory/reconnect/Trace同源 | §24.4 persistence / consumers | schema-5保存proposal+replacement |
    | 8. owner tests、真实provider与Oracle边界 | §24.7 | 冻结mandatory owner / integration矩阵 |
- **验证**: 映射表完整覆盖goal confirmation的8项目标，每项目标都有明确的design section和S0固定结果。Controller和reviewer可直接用此表验证S0完整性。

### M4: `CompactSourceBoundaryEntryV4`的约束描述分散

- **原severity**: 低
- **Controller裁决**: REJECT WITH REASON
- **Controller reason**: "字段shape与紧随其后的同一§24.3约束已经形成一个连续contract，且完整覆盖source refs、evidence refs、kind与empty规则。复制约束到伪类型内部会形成第二份易漂移规范；这只是排版偏好，不构成语义缺口。"
- **复审结果**: **REJECT成立**
- **审查**:
  1. 字段定义在`docs/host/design.md:3337-3345`，约束在`docs/host/design.md:3361-3363`，两者都在§24.3内
  2. 约束确实完整覆盖了所有关键点：
     - `source_refs`必须是非空、唯一的immutable source refs
     - `previous_evidence_fact`与`evidence_material`的`canonical_evidence_refs`必须非空且唯一
     - 其它source kind必须为空
     - material-pack entry到durable boundary entry必须逐项复制并校验等式
     - 任一evidence entry refs为空时typed fail closed
  3. 这些约束与字段定义在同一个section（§24.3）内，形成连续的contract
  4. 复制约束到类型定义内部确实会形成第二份易漂移规范，违反single source of truth原则
  5. 实现者在§24.3内可以找到所有必要信息，不需要跨section查找
- **结论**: Controller的reject reason成立。这是排版偏好而非语义缺口，不构成阻塞问题。

## Open Questions

- 无

## Residual Risk

- 本re-review只验证了M1-M4的修复状态；S0未修改生产代码或测试，因此无法验证runtime行为。
- schema-4 compact payload / Session replay的不兼容性已在design.md中明确，但迁移策略不在F13范围。
- Oracle formal replacement scenarios保持`assigned to later Oracle adjudication`，当前未接受。
- reactive multi-pass聚合规则已在design.md中精确定义，但实际实现可能需要额外的edge case测试。

## Gate Status

所有accepted findings（M1、M2、M3）已在owner文档或evidence artifact修复；M4以避免重复真源为由拒绝，reject reason成立。S0 review gate通过。
