# UF-FIX03 plan review adjudication

## Gate

- gate: `plan review -> fix`
- work unit: `UF-FIX03 summary-and-bounded-errors`
- reviewed plan: `docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
- review artifacts:
  - `docs/reviews/plan-review-20260813-203415.md`（AgentMiMo）
  - `docs/reviews/plan-review-20260813-203826.md`（AgentDS）
- decision: `fix-required`
- next entry point: `plan fix`

## Scope ruling

用户确认的 work unit、UF-FIX03 和三个 accepted predicates 均以 `upload_filing` 为对象。损坏输入的 filing/company/source 零 publication、typed failure 与 bounded stderr 只约束 filing workflow；不得借共享 upload service 顺手重排 `upload_material` 的 company publication 或重定义 material public failure。material 只允许因为共享 count/result type breaking change而做机械 producer/consumer/test 迁移，不得扩展业务行为。

## Finding adjudication

### M1 — exact-key failure schema migration

- source: AgentMiMo finding 1
- decision: `accepted`（只接受“计划必须明确 breaking 策略”的部分）
- ruling: 项目 schema 规则与用户明确边界要求全新 schema、禁止兼容 shim；五字段 failure schema 是 intentional breaking change，不读取旧四字段，不做 migration、default 或兼容 parser。计划必须写明旧 durable job record 不在本 work unit 的读取契约内，并用 parser rejection test 锁定。
- rejected alternative: 把 `file_label=None` 作为旧四字段 fallback，违反项目 schema/兼容性约束。

### M2 — summary constructor inventory

- source: AgentMiMo finding 2
- decision: `accepted`
- required fix: 计划显式列出当前四个 `FinsUploadResultSummary` 构造点及其 function context，并要求 required、无 default counts 与 static constructor audit。

### M3 — progress payload rename

- source: AgentMiMo finding 3
- decision: `accepted`
- required fix: 本 work unit 不需要改 started/preparing progress 的既有 `file_count`；保留它作为 requested progress unit，避免无需求的 breaking change。只有 terminal summary/durable/direct details增加 `requested_file_count` 与 `stored_file_count`。

### M4 — provenance/fingerprint coupling

- source: AgentMiMo finding 4
- decision: `accepted`
- required fix: 计划说明 closed provenance 的值保持 `original`/`docling` 不变，fingerprint bytes不变，并补等价 fingerprint回归；不得借机改 fingerprint schema。

### M5 — count invariant owner

- source: AgentMiMo finding 5
- decision: `accepted`
- required fix: 明确 `FinsUploadPipelineResult.__post_init__` 与 `FinsUploadResultSummary.__post_init__` 分别校验 pipeline/terminal count contract，所有构造点必须先迁移，禁止只在 downstream renderer校验。

### M6 — real Docling stability

- source: AgentMiMo finding 6
- decision: `accepted`（澄清测试层级）；`xfail/skip` 建议 `rejected-with-reason`
- ruling: deterministic fake converter owner tests负责 closed kind/code/label 映射；已有真实 corrupt sample测试只断言稳定 public contract。不得以平台差异给正确性测试加无条件 xfail/skip；真实跨平台 evidence仍归明确排除的 UF-PF03。

### M7 — per-file conversion control flow

- source: AgentMiMo finding 7
- decision: `accepted`
- required fix: 明确顺序、fail-fast：首个 conversion failure立即包装 typed failure并终止后续转换；之前仅存在内存/临时结果，不产生 publication/stored fact。

### D1 — material company publication contradiction

- source: AgentDS finding F1
- decision: `accepted`
- required fix: 从 success signals、S2 tests和invariants中删除/收窄material zero-publication承诺；filing仍必须在prepare失败时batch begin/company/source/blob publication全部为0。不得重排material company publication。

### D2 — material raw error and missing test scope

- source: AgentDS finding F2
- decision: `rejected-with-reason`（material generic failure行为修复）；`accepted`（共享count机械迁移测试清单不完整）
- ruling: raw material generic failure是另一work unit，不在UF-FIX03 upload_filing范围；不得修改material failure分类、日志或公开reason。若共享 count/result breaking contract要求material producer/consumer迁移，必须加入实际受影响material测试文件，仅断言count schema未破坏既有material行为。

### D3 — file label/public text guard mismatch

- source: AgentDS finding F3
- decision: `accepted`
- required fix: 计划必须指定单一 owner级 public display label contract；failure reason、durable summary、direct result和CLI消费同一个已安全化标签。禁止在details/CLI按label内容加特例或复制fragment/control规则。必须覆盖 `job_id_notes.pdf`、`财报正文.pdf`、Unicode格式控制/换行类名字，保证known typed failure不崩塌为unknown，普通stderr单行有界；无法安全原样展示时只能由owner确定性产生同一个业务可行动标签，raw basename仅进operator log。允许把 `dayu/fins/direct_events.py` 纳入计划，但计划必须论证最小方案并避免通用contract过度扩张。

### D4 — commit failure stored zero

- source: AgentDS finding F4
- decision: `accepted`
- required fix: 增加commit failure精确测试：terminal failed、typed storage/runtime reason保持既有分类、stored为0、published tree不变。

### D5 — no-artifact positive control

- source: AgentDS finding F5
- decision: `accepted`
- required fix: direct boundary test先断言成功terminal和真实Fins publication，再做jobs/Host/runtime artifact负断言；措辞改为regression guard，不声称形式化证明。

## Additional controller requirements

1. `EMPTY_INPUT_FILE` 必须加入closed content-code集合并有kind/code一致性测试。
2. `FinsUploadFailureError` 若意外穿透filing workflow，runtime不得通过异常字符串重新分类；计划必须指定typed defense或确保所有filing边界穷尽catch。
3. delete-with-files保持当前明确ignore行为：requested保留请求数、stored为0；不在本任务改为usage rejection。
4. success invariant只对实际uploaded/ok终态要求stored=requested；skip/delete/cancelled/failed stored为0。
5. 旧 `uploaded_files` 生产/测试字段全部删除，不保留兼容reader/writer。

## Residual risks

- 真实Docling平台差异：`assigned to later UF-PF03 evidence work`。
- material generic raw failure/company-first publication：`assigned to later work unit`，owner为Fins material workflow；本次不得顺手修。
- 旧durable upload summary/failure record：`explicitly excluded by fresh-schema rule`，不兼容读取。

## Completion status

Plan review gate未通过；所有accepted findings必须先由AgentCodex修订plan并产出fix artifact，再交AgentMiMo与AgentDS双路re-review。

## Artifact path

`docs/gateflow/uf-fix03-plan-review-adjudication-20260813.md`
