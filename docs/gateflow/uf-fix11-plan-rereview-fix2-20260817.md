# UF-FIX11 plan re-review fix2 artifact

## 1. Gate 元数据

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：`plan re-review -> fix -> re-review`
- Fix 状态：`fix-complete-awaiting-re-review`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 修订目标：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- Review artifacts：
  - `docs/reviews/plan-rereview-ds-20260817.md`
  - `docs/reviews/plan-rereview-mimo-20260817.md`
- Controller decision：接受 DS 新 finding 1、2（由本轮用户指令给出）
- 当前 gate：`re-review`
- 下一入口：`re-review`
- Artifact path：`docs/gateflow/uf-fix11-plan-rereview-fix2-20260817.md`
- Blocker：无

本 gate 只修订 plan 并写本 artifact，不进入 implementation，不修改生产代码或测试，不运行真实 CLI evidence，不创建 PR。

## 2. Scope 与 changed files

### 2.1 Changed files

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-plan-rereview-fix2-20260817.md`（新增）

### 2.2 明确未修改

- 生产代码：无
- 测试代码：无
- README：无
- Host/Engine/material/oracle/scenario/frozen evidence：无
- 既有 review/adjudication/fix artifacts：无
- commit/push/PR：无

## 3. Re-review 结论与 controller 裁决

- MiMo re-review：`pass`，确认 A1-A10 全部按上一轮裁决关闭，没有新 finding。
- DS re-review：`pass-with-risks`，确认上一轮 DS 1-6 全部关闭，并提出两个新的 evidence-based 规格缺口。
- Controller：接受 DS 新 finding 1、2；本 fix2 只落实这两个 accepted findings，不重开 A1-A10 或 goal。

两个新 finding 均成立：其一是 strict filing parser 形成后，遗漏真实 failure producer 会丢失 typed failure；其二是 SKIP 新 commit path 若不转交 batch capability，会在 durable commit 后被 outer finally 二次 rollback 并反演为失败。这两者都是 owner/state-machine 规格缺口，不是展示层补丁。

## 4. 直接证据

### 4.1 DS-RR1：failure terminal producer

1. `dayu/fins/pipelines/sec_upload_workflow.py::_build_sec_filing_failure_event` 独立调用 `host._build_result(...)` 构造 `status="failed"` result；当前没有 `warnings` 参数。
2. `dayu/fins/pipelines/cn_pipeline.py::_build_cn_filing_failure_event` 独立调用 `pipeline._build_upload_result(...)` 构造同类 failed result；当前也没有 `warnings` 参数。
3. SEC/CN 各有 fresh-validation failure 与 try-block 内 typed/storage/generic failure 调用点，均汇聚到各自 builder；所以修改 builder 是正确且唯一 producer boundary，不应在每个 yield 点重复拼字段。
4. `dayu/fins/service_runtime.py` 的 filing 结果统一进入 `FinsUploadPipelineResult.from_pipeline_json(...)`。Plan 已规定 `SourceKind.FILING` 缺失 warnings fail-closed；若 builder 漏改，真实 typed `FinsUploadFailureReason` 会被 parser `ValueError` 覆盖，随后走 generic exception failure。
5. 因此 producer 与 strict parser 必须在同一 Slice 2 原子收敛，并用真实 workflow event roundtrip 验证；handcrafted dict 或 mock parser 不能证明生产 builder 正确。

### 4.2 DS-RR2：batch capability 转交

1. `dayu/fins/pipelines/filing_upload_publication.py::execute_prepared_filing_publication` 初始化 `batch_terminal_started = False`。
2. outer `finally` 在 flag 仍为 `False` 时调用 `rollback_prepared_upload_batch(...)`。
3. 现有 PUBLISH、cancel、conflict 和原 SKIP terminal branches 都在进入 terminal owner 前把 flag 设为 `True`；PUBLISH 明确在调用 commit helper 前转交 capability。
4. `BatchingRepositoryProtocol.commit_batch` 的契约明确：方法消费 batch capability，commit 成功或抛错后 caller 都不得再次 rollback。
5. `rollback_prepared_upload_batch` 在没有主异常时会原样抛 rollback error；因此新 SKIP metadata commit 若漏设 flag，会在 commit 成功后对已消费 token 二次 rollback，使 durable success 被上报为异常。
6. 正确顺序只能是 `stage -> batch_terminal_started=True -> commit_batch`；flag 设置晚于 commit、commit 后复位或 finally 二次 rollback 都违反 capability owner contract。

### 4.3 重复条目

- normalization 规则已在 plan §6.2 唯一列出；Slice 1 再次写出 NFKC/whitespace/casefold 步骤属于重复规格，可能产生文本漂移。
- README 精确 allowed files 已在 Slice 3 列出；§9.3 再列同一组文件会重复，尤其 `dayu/fins/README.md` 同时成为两个 allowed-file bullet。

## 5. Accepted finding fixes

### 5.1 DS-RR1 — SEC/CN failure event builders 未落名

- Decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan changes：
  1. Slice 2 Exact changes 点名 `_build_sec_filing_failure_event(...)` 与 `_build_cn_filing_failure_event(...)`，要求每个 failed result 通过各自 result builder 显式写 `warnings=[]`。
  2. 明确所有 filing terminal producers：normal success/skip 取 shared warnings；early cancelled/delete 显式空数组；failed builders 显式空数组。
  3. 禁止 failure builder 省略字段或从 exception/message 推断 warning。
  4. 将 `FinsUploadPipelineResult.from_pipeline_json(..., source_kind: SourceKind)` 与 `service_runtime` 显式 callsite 从 Slice 3 的 schema 决策提前到 Slice 2，使 producer/consumer 在同一 slice 可运行、可 review；Slice 3 只继续 summary/durable/direct/UI 投影。
  5. Slice 2 allowed files 增加 `dayu/fins/ingestion_runtime.py`、`dayu/fins/service_runtime.py` 及对应测试文件，且明确只允许 parser/callsite 范围。
- Required tests：
  - SEC/CN 各执行真实 filing workflow，分别触发实际 failure builder，不手工构造 result dict、不 mock parser。
  - 从 terminal event 读取 raw result，断言 `warnings == []`。
  - 用 `SourceKind.FILING` 通过真实 parser roundtrip，断言 parsed warnings 为 `()`，原 failure code/kind/message exact 保留。
  - 每端至少覆盖 fresh-validation failure 与 try-block 内 failure 的 producer contract。
- Stop condition：任一 filing failure producer 省略 warnings，或 roundtrip 退化为 generic exception failure，即停止 Slice 2。
- Residual classification：`fixed in current slice`。

### 5.2 DS-RR2 — SKIP metadata commit 未写死 capability 转交

- Decision：`accepted`
- Fix/re-review 状态：`已修复`
- Plan changes：
  1. §8 state machine 与 §8.3 exact sequence 固定为：

     `stage_upload_company_meta_decision -> batch_terminal_started=True -> batching_repository.commit_batch -> build skip result -> replace outcome`

  2. flag 必须在 storage commit 调用前设置，表示 capability 已转交；commit 成功或抛错后 outer finally/exception handler 均不得 rollback。
  3. 继续禁止 SKIP 调用 filing publish helper 或 stage filing/source asset。
  4. Slice 2 stop condition 明确拦截 flag 顺序错误、commit 后复位和任何二次 rollback。
- Required tests：
  - 成功：terminal-aware batching spy 断言 `commit_count == 1`、caller `rollback_count == 0`、result 为 skipped、alias/company outcome durable；若 rollback 已消费 token则测试直接失败。
  - commit failure：storage 消费 capability 后抛原 storage/typed error，断言 `commit_count == 1`、caller `rollback_count == 0`、原 failure 保留、无 warning。
  - commit 前 stage failure 对照：capability 尚未转交，outer caller 恰好 rollback 1 次。
- Residual classification：`fixed in current slice`。

## 6. Cleanup

### 6.1 Company-name normalization 重复项

- §6.2 保留唯一完整规则：NFKC、Unicode whitespace collapse、`casefold()`。
- Slice 1 改为引用 §6.2 的 frozen equivalence helper，不再重复列举步骤。
- 结果：`casefold()` 作为规范化列表条目只出现一次。

### 6.2 Fins README 重复项

- Slice 3 `Allowed files -> 文档` 保留唯一精确 README 文件清单。
- §9.3 改为引用该唯一清单，不再重复列出 `dayu/fins/README.md` 等 bullet。
- §11.2 仍保留 Fins README 的更新理由与内容边界；它是 docs decision，不是重复 allowed-file 条目。

## 7. Validation

本 fix2 gate 只修改 Markdown，因此未运行 pytest、coverage 或 pyright，也未运行真实 CLI evidence。Implementation 需要执行的 producer roundtrip、capability tests、coverage、pyright 与 static checks 已写入 plan。

静态验证项目：

1. 两份 re-review 已完整读取；DS finding 1/2 与 MiMo pass 结论均记录。
2. Plan current gate 与 next entry 均为 `re-review`。
3. Slice 2 同时包含两个 failure builders、真实 producer/parser roundtrip、显式 `warnings=[]`、parser/source-kind callsites。
4. SKIP metadata sequence 中 `batch_terminal_started=True` 严格早于 `commit_batch`；success/failure caller rollback 为 0，commit 前 stage failure rollback 为 1。
5. `casefold()` 规范化列表条目只有一个；`dayu/fins/README.md` 只有一个 allowed-file bullet。
6. Plan/fix2 artifact 无 trailing whitespace。
7. 只修改本 plan 与新增 fix2 artifact；生产/测试/README/既有 artifacts 无改动。

实际静态结果：

| 检查 | 结果 |
| --- | --- |
| Plan `casefold()` 精确计数 | `1`，只保留 §6.2 规范化条目 |
| Plan Fins README allowed-file bullet 计数 | `1`，只保留 Slice 3 清单；§11.2 为职责说明而非重复 entry |
| DS-RR1/DS-RR2 与 gate 扫描 | 通过；两项均为 `accepted`/`已修复`，current gate/next entry 均为 `re-review` |
| trailing whitespace | 通过；plan 与 fix2 artifact 均无匹配 |
| `git diff --name-only` | 为空；无 tracked 生产/测试/README 修改 |
| 操作范围核对 | 本 gate 只调用 patch 修改 plan，并创建本 fix2 artifact；既有 untracked UF-FIX11 review/artifacts 未写入 |

## 8. Residual risks 与 uncovered areas

| Residual | Classification | Owner/destination | 本轮处理 |
| --- | --- | --- | --- |
| DS-RR1 failure producer/schema 漂移 | `fixed in current slice` | UF-FIX11 Slice 2 implementation/review | 真实 SEC/CN producer -> parser roundtrip tests |
| DS-RR2 capability 二次 rollback | `fixed in current slice` | UF-FIX11 Slice 2 implementation/review | exact flag 顺序 + terminal-aware rollback-count tests |
| name-only metadata batch writer lock/physical swap 成本 | `assigned to later work unit` | 后续性能/存储 work unit | final-truth correctness 优先 |
| degraded unrelated source fail closed | `fixed in current slice` | UF-FIX11 Slice 2 | 维持 whole-tree owner tests，不 bypass |
| material company-name warning | `assigned to later work unit` | 独立 material work unit | 本轮不改 material flow/schema |
| 真实 CLI evidence、oracle/scenario/frozen evidence | `assigned to later work unit` | evidence work unit | 用户明确排除 |
| durable 后 guard-release/cleanup 报错时不发 warning | `assigned to later work unit` | storage operations work unit | 沿用既有 failure contract |

没有未分类 residual risk，没有 `requiring new issue or explicit user decision` 项。

## 9. Docs decision

本 gate 的文档职责只包括修订 plan 与新增本 fix2 artifact。README 只记录已实现稳定行为，当前未进入 implementation，因此不修改 README；实施后的 README 触发仍由 plan Slice 3 执行。

## 10. Completion status

- DS-RR1：`accepted` / `已修复`，等待 re-review。
- DS-RR2：`accepted` / `已修复`，等待 re-review。
- A1-A10：不重开；沿用已完成裁决与 re-review 关闭状态。
- Blocking open question：无。
- Unclassified residual risk：无。
- 当前 gate：`re-review`。
- 下一入口：`re-review`。
- Implementation：未进入。
- PR：未创建。
