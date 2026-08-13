# UF-FIX03 plan review fix

## Gate

- gate: `plan review -> fix`
- work unit: `UF-FIX03 summary-and-bounded-errors`
- fixed plan: `docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
- controller input: `docs/gateflow/uf-fix03-plan-review-adjudication-20260813.md`
- review inputs:
  - `docs/reviews/plan-review-20260813-203415.md`
  - `docs/reviews/plan-review-20260813-203826.md`
- scope: `upload_filing`；material仅共享count contract机械迁移与回归
- completion status: `complete`
- next entry point: `plan re-review`

## Input completeness

已完整读取113行controller adjudication、143行AgentMiMo review、135行AgentDS review、原631行plan与78行binding
goal-confirmation。controller adjudication是本fix gate对review建议的最终裁决：只落实accepted部分，不采纳被裁决排除的material generic
failure修复、material company publication重排、兼容schema或真实测试`xfail/skip`建议。

## Finding status

### M1 — exact-key failure schema migration

- 状态：已修复
- 落实：plan明确five-field object五个key required、`file_label`值可null且字段无default；这是fresh intentional breaking change，
  parser拒绝旧四字段，不迁移、不删除旧record、不提供default/兼容parser/dual writer；旧durable record明确不在读取契约内。

### M2 — summary constructor inventory

- 状态：已修复
- 落实：plan按function context列出四个production `FinsUploadResultSummary(...)` constructor，并补齐六个
  `UploadOperationResult(...)`、pipeline唯一`cls(...)`与failure reason owner constructors；要求required无default及production static audit。

### M3 — progress payload rename

- 状态：已修复
- 落实：撤销progress rename设计；started/preparing/completed继续使用既有`file_count`表示requested progress unit，
  `_PAYLOAD_FILE_COUNT`保持不变。只有terminal summary、durable summary、direct RESULT details使用两个新count。

### M4 — provenance/fingerprint coupling

- 状态：已修复
- 落实：最小实现固定为`Literal["original", "docling"]`加两个exact字符串常量，不引入enum；plan锁定canonical fingerprint
  bytes与现有fixture digest `099dc9636e306c75f1d5d64dd0210123956ba73888e968088c7279baab1d7fdd`，禁止改变fingerprint schema。

### M5 — count invariant owner

- 状态：已修复
- 落实：`FinsUploadPipelineResult.__post_init__()`唯一拥有pipeline count状态矩阵，
  `FinsUploadResultSummary.__post_init__()`唯一拥有terminal count状态矩阵；parser/renderer/progress不得复制校验或重算。

### M6 — real Docling stability

- 状态：已修复
- 落实：deterministic fake converter owner tests锁定kind/code/label映射；已有真实corrupt sample只断言稳定public contract，
  不依赖第三方原始subtype/text，也不得用平台差异添加无条件`xfail`/`skip`；多平台evidence仍归UF-PF03。

### M7 — per-file conversion control flow

- 状态：已修复
- 落实：filing转换明确sequential fail-fast；首个conversion failure立即typed包装并终止，bad后的converter call为0；此前内存/临时
  转换产物不触发batch或stored fact。

### D1 — material company publication contradiction

- 状态：已修复
- 落实：所有zero-publication目标、invariant与测试均收窄到`upload_filing`；plan明确material company-first publication不重排，归后续
  material work unit。

### D2 — material raw error and missing test scope（controller accepted component）

- 状态：已修复
- 落实：加入`tests/fins/test_sec_pipeline_upload_material_stream.py`及CN material现有回归；仅迁移required count并锁定既有raw generic
  message/error与company-first行为。controller排除的material generic failure/log/public reason修复未进入本WU。

### D3 — file label/public text guard mismatch

- 状态：已修复
- 落实：选择`dayu/fins/direct_events.py`内单一canonicalizer/validator的最小方案，复用既有safe-text guard；普通安全basename原样
  保留，`job_id_notes.pdf`、`财报正文.pdf`、Unicode `Cc/Cf`等无法安全原样显示时统一生成`输入文件（文件名已隐藏）`。five-field
  parser只接受canonical值；reason/durable/direct/CLI消费同一值，无下游fragment/control特例、fallback或重复validator；raw basename
  仅以转义形式进operator log。

### D4 — commit failure stored zero

- 状态：已修复
- 落实：新增精确plan assertion：filing commit分别抛`OSError`/`RuntimeError`时terminal failed、stored=0，failure分类保持
  `storage/storage_io`与`runtime/unexpected_runtime`，single rollback与published tree SHA不变。

### D5 — no-artifact positive control

- 状态：已修复
- 落实：direct test先断言success terminal、requested=stored及真实Fins source meta/original blob/derived asset publication，再做
  job/Host/runtime artifact负断言；全篇改称regression guard，不声称形式化证明。

### C1 — `EMPTY_INPUT_FILE` content-code closure

- 状态：已修复
- 落实：plan要求加入`_CONTENT_FAILURE_CODES`，并用kind/code一致性owner test锁定`content/empty_input_file`。

### C2 — typed exception filing boundary

- 状态：已修复
- 落实：SEC/CN/HK filing workflow必须在generic catch前穷尽catch `FinsUploadFailureError`并直接投影`exc.failure`；测试断言runtime
  string classifier未调用。若发现额外filing入口可绕过，stop condition要求改成runtime typed defense，禁止`str(exc)`重分类。

### C3 — delete-with-files behavior

- 状态：已修复
- 落实：保持当前accept/ignore；requested保留validated request文件数，stored=0，不改为usage rejection。

### C4 — success/non-ok invariant scope

- 状态：已修复
- 落实：只有实际uploaded/`ok`要求stored=requested；skip/delete/cancelled/failed为0。pipeline与summary owner分别按自身既有状态闭集
  校验，避免给pipeline虚构cancelled状态。

### C5 — remove `uploaded_files`

- 状态：已修复
- 落实：plan要求production/test零命中，不保留reader、writer、alias、default、fallback或兼容字段。

## Validation

- 完整读取检查：上述五份输入均读到EOF，行数分别为113、143、135、631、78。
- scope检查：plan明确`upload_filing`业务scope，并在non-goals、owner evidence、affected files、S1/S2、matrix与risk中重复锁定material
  仅机械count迁移。
- constructor检查：plan列出四个production summary点、六个operation result点、pipeline唯一constructor与failure reason owner点。
- contract检查：plan包含fresh five-field、progress `file_count`保留、两个`__post_init__` owner、exact provenance/fingerprint、fail-fast、
  单一label owner、commit failure与direct positive control。
- no-touch检查：本gate不修改生产代码、测试、README、冻结JSON或evidence；冻结SHA必须继续匹配plan记录值。
- 代码验证：未运行pytest、coverage或pyright；本gate仅修改Markdown plan artifacts，且用户明确禁止修改/执行实现范围。

## Documentation decision

- 已更新：`docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`。
- 已新增：`docs/gateflow/uf-fix03-plan-review-fix-20260813.md`。
- 未更新README：当前是plan fix gate，无生产/测试行为落地，且本轮明确禁止README修改；plan仅保留未来implementation gate的触发决策。
- 未更新adjudication/review/goal-confirmation：它们是本gate只读证据。

## Residual risks

- 真实Docling跨平台底层差异：`assigned to later UF-PF03 evidence work`；当前deterministic owner tests与稳定真实sample contract覆盖实现正确性。
- material generic raw failure与company-first publication：`assigned to later material work unit`；owner为Fins material workflow，本WU只做
  shared count机械迁移。
- 旧durable upload summary/failure record：`explicitly excluded by fresh-schema rule`；不兼容读取，不在本WU迁移或删除。
- re-review尚未执行：当前fix完成不等于plan review通过；必须由下一gate重新检查所有finding与内部一致性。

## Completion

- 所有controller accepted findings：已修复。
- blocking open question：无。
- next entry point：`plan re-review`。

## Artifact path

`docs/gateflow/uf-fix03-plan-review-fix-20260813.md`
