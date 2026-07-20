# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 Corrected-Plan Final Re-Review — AgentMiMo

## Review entry

- Timestamp：`2026-07-20`（本机系统时钟）。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4 real-Windows remediation`；不是新 WU。
- Gate：corrected-plan final re-review（第一路完整 re-review）。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。
- Corrected plan：`1124` lines；SHA-256 `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2`。
- Review conclusion：**PASS / ZERO MATERIAL FINDINGS / ZERO BACKFLOW / READY_FOR_CONTROLLER_ADJUDICATION_THEN_ACCEPTED_CORRECTED_PLAN_COMMIT / IMPLEMENTATION_NOT_AUTHORIZED**。

## 1. Scope and immutable boundary

本 gate 只允许 re-review frozen corrected plan 及其完整审查链并输出本 artifact。不允许修改 plan、product、test、README、design、workflow、control 或其它 artifact；不允许 stage、commit、push、dispatch 或 PR。

## 2. Required-document ingestion checklist

| Document | Lines | SHA-256 | Status |
| --- | ---: | --- | --- |
| `AGENTS.md` | — | — | 已读取 |
| `docs/host/issues-implementation-control.md` (header + scope) | — | — | 已读取 |
| `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` | `1124` | `571ca834...dc7ff2` | 已完整读取；SHA/lines 与锁定一致 |
| `docs/reviews/...-evidence-controller-adjudication.md` | `63` | `0193c1a0...7c4d3ddb` | 已完整读取 |
| `docs/reviews/...-plan-correction-codex.md` | — | `28aaa225...ec64dbdb` | 已读取（plan-correction artifact） |
| `docs/reviews/...-plan-correction-controller-validation.md` | — | `bffa43c3...a4548a1` | 已读取（Controller plan-correction validation） |
| `docs/reviews/...-plan-correction-review-mimo.md` | `407` | `8580d4e6...b2de249` | 已完整读取；初审第一路 PASS / finding 0 |
| `docs/reviews/...-plan-correction-review-ds.md` | `235` | `c4d227cf...674a9e0` | 已完整读取；初审第二路 PASS / finding 0 |
| `docs/reviews/...-plan-correction-review-controller-adjudication.md` | `56` | `5fba7acd...379d729` | 已完整读取；accepted finding 0 |
| `docs/reviews/...-plan-correction-review-fix-codex.md` | `131` | `2fdb6201...3906abc` | 已完整读取；zero-change fix |
| `docs/reviews/...-plan-correction-review-fix-controller-validation.md` | `43` | `86450472...32d277e` | 已完整读取；zero-change fix accepted |
| `docs/fins/design.md` | — | — | 已读取 |
| `dayu/fins/pipelines/docling_upload_service.py` (primary owner) | — | — | 已读取关键行 |
| `dayu/fins/storage/repository_protocols.py` (descriptor contract) | — | — | 已读取关键行 |
| `tests/cli/test_upload_filings_from_command.py` (target node) | — | — | 已读取关键行 |

### Content-lock hash reconciliation

两个 Controller validation artifact 是不同文件，各自 SHA-256 已独立验证：

| Artifact | Full filename suffix | SHA-256 | Role |
| --- | --- | --- | --- |
| Controller plan-correction validation | `...-plan-correction-controller-validation.md` | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` | 验证 Codex plan-correction artifact；授权双路完整 plan review |
| Controller zero-change fix validation | `...-plan-correction-review-fix-controller-validation.md` | `8645047222fa375beae9a5bb1b4e6e237c07cbfd03aa3fc3b6b9eec5e32d277e` | 验证 AgentCodex zero-change fix；授权双路完整 plan re-review |

两个 SHA 各自精确匹配对应文件内容，不存在 hash mismatch 或 content-normalization 差异。

## 3. Plan identity verification

| Item | Claimed | Verified |
| --- | --- | --- |
| Line count | 1124 | 1124 ✓ |
| SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | 匹配 ✓ |
| Fresh R11 run id | `29709987970` | Controller evidence adjudication 确认 ✓ |
| Fresh R12 run id | `29709993229` | Controller evidence adjudication 确认 ✓ |
| R12 init result | `9/9 passed` | Controller evidence adjudication 确认 ✓ |
| R12 canary | zero match / PASS | Controller evidence adjudication 确认 ✓ |
| R11 result | `3/4 passed` | Controller evidence adjudication 确认 ✓ |
| R12 embedded R11 | `1/2 passed` | Controller evidence adjudication 确认 ✓ |
| Accepted implementation head | `b11eb95c8312e085755b81c630e9c359220d3ff1` | Controller evidence adjudication 确认 ✓ |
| Plan delta from prior committed version | 有 diff（§0 gate/conclusion wording、§1.1 新增 evidence adjudication ref、§1.2 新增 fresh evidence summary） | 由 Codex plan-correction artifact 产生；plan SHA 已锁定 ✓ |

## 4. Adversarial re-review by focus area

### 4.1 WIN4-RW-RF01 root cause 是否仍限定为 test oracle overreach

**Verdict: PASS**

直接证据链：

1. Controller evidence adjudication 明确定性：`WIN4-RW-RF01` 是 `ACCEPTED` finding，severity `HIGH`（remote release-gate blocker），**不是** production upload defect。
2. Root cause 措辞："CLI test 只应消费 public snapshot，不应把 raw source basename 强加为 Fins primary"。这不是 Fins product defect。
3. Plan §13.1.1 明确："动机成立，严重性限定为 release-gate/test contract blocker，不是 production upload defect"。
4. Plan §13.2.1 的 correction owner 是 test node，不是 Fins production code。§13.3 allowlist 只允许修改 test file。
5. Plan §13.4 stop condition："若 public `files` descriptors 不能同时表达……或实现需要硬编码 Docling expected primary、读取 raw meta/private path、修改 Fins production/storage contract……立即停止并回 Controller"。
6. §13.5.1 negative case 确保 Fins fail-closed 行为不变：company meta 缺失仍失败，execution nonzero 仍先于 storage 断言。

**未发现 root cause 被不当扩大为 Fins product defect 的迹象。**

### 4.2 Primary exact-name descriptor membership 与 raw source exact basename + public sha256 是否独立、fail-closed、不强制相等

**Verdict: PASS**

#### 独立性

- Plan §13.2.1 分为两个独立断言：(a) `snapshot.primary_filename` 按 exact name 在 descriptor 集合中恰好命中一个；(b) exact `source_path.name` 按 name 恰好命中一个 descriptor 且其 public `sha256` 等于 fixture bytes SHA-256。
- §13.2.1 明确："primary 命中与 raw-source 命中是两个独立断言，允许它们指向不同 descriptors"。
- §13.5.1 反例确认："当前真实反例必须通过：primary 合法指向非原始 source descriptor，同时原始 source descriptor 以 exact basename 与 exact fixture SHA-256 独立存在"。
- R11 `29709987970` / R12 embedded R11 `29709993229` 的真实 evidence 已证明：primary 指向 `_docling.json`，raw source 指向 `.htm`，两者独立存在。

#### Fail-closed

- Primary zero-hit：fail（§13.5.1）。
- Primary multiple-hit：fail（§13.5.1）。
- Raw basename zero-hit：fail（§13.5.1）。
- Raw basename multiple-hit：fail（§13.5.1）。
- Raw descriptor sha256 为 None：`None != str` → fail（§13.5.1 覆盖；MiMo INFO-1 建议实现时显式 `is not None`）。
- Raw descriptor sha256 不匹配：fail（§13.5.1）。

#### 不强制相等

- Plan 没有任何措辞要求 `primary_filename == source_path.name`。§13.6.6 scan 5 扫描旧错误措辞 `primary[ ]filename.*等于.*source[ ]basename|primary[_]filename == source_path[.]name` — 要求零输出。
- §13.3 禁止："不得把当前 Docling 产物文件名、suffix 或任何其它 filename 硬编码成 expected primary"。

### 4.3 Optional sha256、duplicate names、rglob/physical tree、private meta、hardcoded Docling filename 反例

**Verdict: PASS**

#### Optional sha256

- `SourceSnapshotFileDescriptor.sha256` 类型为 `Optional[str]`。当 sha256 为 None 时，`None == hashlib.sha256(fixture).hexdigest()` 为 `False`，assertion 正确失败。
- §13.5.1 覆盖："descriptor public sha256 为空……时必须失败"。
- 实际实现中 `_build_stored_file_entry()` 始终填入 sha256（raw source 的 `asset.sha256` 由写入时原始 bytes 计算）。
- Codex fix checkpoint `RF01-IMP-CHK-01` 要求实现时先显式 `sha256 is not None` 再比对值。

#### Duplicate names

- §13.5.1 覆盖 primary 多命中与 raw basename 多命中。DS OBS-DS-01 指出当前 `in` operator 不拒绝 duplicate，但 §13.2.1 要求 "恰好命中一次"。
- Codex fix checkpoint `RF01-IMP-CHK-03` 要求实现时把 `in` 改为 exact cardinality `== 1`。
- Controller adjudication disposition：`NO PLAN FIX / IMPLEMENTATION REQUIREMENT ALREADY EXPLICIT`。

#### rglob / physical tree

- §13.2.1 明确禁止："不从物理 storage tree 反推 publication 业务事实"。
- §13.2.1 point 4：`source_artifact_count` 只保留为物理 integrity count，不再承担业务 success 语义。
- Codex fix checkpoint `RF01-IMP-CHK-02` 要求证明既有 `rglob` 行零 diff。

#### Private meta

- §13.2.1 明确禁止："不读取 raw source meta、meta JSON、private/core path"。
- §13.6.6 scan 3 零输出要求。

#### Hardcoded Docling filename

- §13.2.1 明确禁止："不得把当前 Docling 产物文件名、suffix 或任何其它 filename 硬编码成 expected primary"。
- §13.6.6 scan 2 零输出要求。
- Plan 中 `_docling.json` 出现处均为 evidence 描述或禁止性约束，不要求 test 硬编码。

### 4.4 Exact one-test assertion block allowlist、无 helper/import/schema/oracle/README/workflow/Fins/product 扩张

**Verdict: PASS**

#### Exact-node allowlist

- §13.3 唯一允许路径：`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 的现有 snapshot assertion block。
- 同文件 imports、module constants、helpers、fixtures、其它 tests、oracle JSON block 必须相对 `CORRECTED_PLAN_BASE` 零 diff。
- §13.3 禁止清单完整：全部 `dayu/` product code、其它 tests、全部 README/design、workflow YAML、control/review artifacts、helper/schema/oracle 字段、PowerShell/PTY/process isolation、timeout 增加、skip/xfail/mock。

#### No expansion proof

- §13.6.6 scan 4：`rg '^\+(async )?def |^\+class |^\+.*"[A-Za-z_]+"\s*:'` — 零输出。不新增 helper/constant/schema。
- §13.2.1 point 6："实现必须直接留在上述 exact test node 现有 snapshot assertion block 内；不得新增 helper、constant、schema、fixture 字段、compatibility seam 或 README 说明"。
- §13.7 README decision：WIN4-RW-RF01 零 README diff。
- §13.3 禁止修改 Fins production code、storage protocol、Docling service、workflow YAML。

### 4.5 本地/remote gate、R11/R12 same-run 证据、安全边界与 deferred scope

**Verdict: PASS**

#### 本地/remote gate

- §13.0 明确：corrected plan 经 Controller validation → AgentMiMo/AgentDS 双路完整 plan review → finding fix → 双路完整 re-review → accepted corrected-plan commit，才允许 implementation。
- §13.4 WIN4-RW-RF01 dependencies："既有 `WIN4-RW-S1/S2` accepted aggregate implementation 是 immutable 前置……经独立 review/fix/re-review 与 accepted implementation commit 后才允许 remote rerun"。

#### R11/R12 same-run evidence

- §13.8 要求 Controller 使用 dispatch response 返回的唯一 run id，验证 workflow identity/path/event/ref/head SHA，再独立重算 canary 并扫描同一 run 全部 artifacts。
- §13.8："任一 metadata mismatch、ambiguous、missing，artifact 缺失或无法证明同 run lineage，当前 gate 立即失败"。
- Controller evidence adjudication 已验证 R11 `29709987970` / R12 `29709993229` 的 identity tuple 和 same-run canary scan 零命中。

#### 安全边界

- §13.9："Config 与 Host internal SQLite/EventLog 是 trusted-local domain；只有 Tool Trace/audit 以及 public/LLM-facing/operator diagnostics 禁止 API key/header 明文"。
- §13.9："本 amendment 不读取、迁移、重写或扩大 durable secret 范围"。
- R12 canary scan 不读取/扫描 GitHub Secrets/configured production values。

#### Deferred scope

- §13.9 明确 deferred/forbidden：Issue 142/151/175/177/178、Web/WeChat/render、统一 authorization/secret management、Fins generic diagnostic schema、Gemini low-budget。
- §13.3 禁止清单覆盖 unified authorization、secret infrastructure、process isolation。

### 4.6 初审 INFO/OBS 是否全部被 zero-change fix 正确消费，有无 backflow/new finding

**Verdict: PASS / ZERO BACKFLOW**

#### MiMo INFO-1（optional sha256 显式性）

- Codex fix disposition：`NO PLAN FIX / CONSUMED`。
- Checkpoint `RF01-IMP-CHK-01`：实现时先 `sha256 is not None` 再比对值。
- Checkpoint `RF01-REVIEW-CHK-01`：review 确认 optional 空值 fail closed。
- Controller validation 确认：`NO PLAN FIX / DOWNSTREAM CHECKPOINT`。
- **Backflow check**：无。此 observation 不产生新 finding，不需要 plan 修改。

#### MiMo INFO-2（added-diff rglob scan）

- Codex fix disposition：`NO PLAN FIX / CONSUMED`。
- Checkpoint `RF01-IMP-CHK-02`：实现 artifact 直接检查 changed block 无新增 `rglob`。
- Checkpoint `RF01-REVIEW-CHK-02`：review 从 function diff 确认 publication 断言只消费 public descriptor。
- Controller validation 确认：`NO PLAN FIX / DOWNSTREAM CHECKPOINT`。
- **Backflow check**：无。§13.3 allowlist 冻结与 §13.2.1 禁止条款已充分覆盖。

#### DS OBS-DS-01（current membership uses `in`）

- Codex fix disposition：`NO PLAN FIX / IMPLEMENTATION REQUIREMENT ALREADY EXPLICIT / CONSUMED`。
- Checkpoint `RF01-IMP-CHK-03`：实现时改为 exact cardinality `== 1`。
- Checkpoint `RF01-REVIEW-CHK-03`：review 检查 zero/multiple hits fail closed。
- Controller validation 确认：`NO PLAN FIX / DOWNSTREAM CHECKPOINT`。
- **Backflow check**：无。Plan §13.2.1 和 §13.5.1 已逐字要求 exact-one。

#### Zero-change fix gate 正确性

- AgentCodex 正确执行：未修改 plan（SHA/lines 不变），未升级 observation 为 finding，未越过 re-review gate。
- Controller validation 正确接受 zero-change fix。
- **New finding check**：本次 re-review 未发现任何初审遗漏的 material finding。

### 4.7 Reviewer next gate 必须是 Controller adjudication 后 exact docs/control/reviews accepted corrected-plan commit

**Verdict: PASS**

- Controller review adjudication 的 next gate："只授权 AgentCodex 形成 zero-change plan-review fix artifact……Controller validation 后再执行 AgentMiMo/AgentDS 双路完整 plan re-review"。
- Controller validation 的 next gate："只授权 AgentMiMo 与 AgentDS 并发执行双路完整 corrected-plan re-review……accepted corrected-plan commit、one-test implementation、remote dispatch、PR review 与 final closeout 仍未授权"。
- AgentCodex artifact 的 next gate："Controller validation 后只能进入双路完整 plan re-review"。
- 本 re-review 的 next gate：Controller adjudication → 若双路均 PASS → accepted corrected-plan commit → implementation authorization。
- **不是**直接 implementation、remote dispatch 或 closure。

### 4.8 既有 accepted WIN4-RW-S1/S2 行为是否被错误重开或削弱

**Verdict: PASS**

- §13.0："既有 WIN4-S1/S2/S3 的 accepted contracts、已关闭 findings 与非冲突约束继续有效，不重新实施、不回滚"。
- §13.4 WIN4-RW-S2："本 slice 及其 aggregate gates 已接受。当前 correction 不得重新实施或修改"。
- `_read_secret_input` helper、TTY/redirected 分流、canary contract、setx DEVNULL/timeout 等均已接受且不受本 correction 影响。

## 5. Finding summary

| # | Finding | Severity | Direct evidence | Required fix |
| --- | --- | --- | --- | --- |
| — | （无 material findings） | — | — | — |

### Backflow check

| Source | Observation | Backflow to plan? | Disposition |
| --- | --- | --- | --- |
| MiMo INFO-1 | optional sha256 显式性 | 否 | Codex consumed；implementation checkpoint |
| MiMo INFO-2 | added-diff rglob scan | 否 | Codex consumed；implementation checkpoint |
| DS OBS-DS-1 | current `in` 不拒绝 duplicate | 否 | Codex consumed；implementation checkpoint |
| Zero-change fix | AgentCodex 未改 plan | 否 | Controller accepted |
| Re-review（本次） | 无 new finding | 否 | — |

**零 backflow。三个 INFO/OBS 正确收敛为 implementation checkpoint，未回流为 plan 修改需求。**

## 6. Counterexample verification matrix

| Counterexample | Plan coverage | Fail-closed? | Result |
| --- | --- | --- | --- |
| primary zero-hit in descriptors | §13.5.1 | fail | ✓ |
| primary multiple-hit | §13.5.1 | fail | ✓ |
| raw basename zero-hit | §13.5.1 | fail | ✓ |
| raw basename multiple-hit | §13.5.1 | fail | ✓ |
| sha256 is None | §13.5.1 + INFO-1 checkpoint | fail（implicit `None != str`；checkpoint 要求显式 `is not None`） | ✓ |
| sha256 mismatch | §13.5.1 | fail | ✓ |
| primary ≠ raw source（真实反例） | §13.5.1 | PASS | ✓ |
| duplicate descriptor names | §13.5.1 + OBS-DS-01 checkpoint | fail（checkpoint 要求 exact cardinality） | ✓ |
| rglob count 替代 descriptor | §13.2.1 禁止 + checkpoint | N/A（not implemented） | ✓ |
| private meta / raw meta read | §13.2.1 禁止 + scan 3 | N/A（not implemented） | ✓ |
| hardcoded Docling expected primary | §13.2.1 禁止 + scan 2 | N/A（not implemented） | ✓ |
| stdout display text oracle | §13.5.1 | not fail on empty/change | ✓ |

## 7. Plan and full-chain evidence hashes

| Artifact | Lines | SHA-256 |
| --- | ---: | --- |
| Frozen corrected plan | `1124` | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` |
| Controller evidence adjudication | `63` | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` |
| AgentCodex plan correction | — | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` |
| Controller plan-correction validation | — | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` |
| AgentMiMo 初审 | `407` | `8580d4e6d9e3b4137e0f4b2cea8ea8ed9e4dd4a10c20df8cbffe50572b2de249` |
| AgentDS 初审 | `235` | `c4d227cf99ff9ac991da030c2ab8fbc386f69d0c6c8e78bbb5e7fa88d674a9e0` |
| Controller review adjudication | `56` | `5fba7acfd70ab985b568c9457f5160537eb900c47548f22db1100043b379d729` |
| AgentCodex zero-change fix | `131` | `2fdb62018e499c00d8594310eb4fac532afa17578f96577d90076e6d73906abc` |
| Controller zero-change validation | `43` | `8645047222fa375beae9a5bb1b4e6e237c07cbfd03aa3fc3b6b9eec5e32d277e` |
| R11 run id | — | `29709987970` |
| R12 run id | — | `29709993229` |
| Accepted implementation head | — | `b11eb95c8312e085755b81c630e9c359220d3ff1` |
| R12 artifact zip | — | `61d9511461eb619b5b0c7ea90b6d7db4b545d7799b6709c198953f613dbc0151` |
| R12 logs zip | — | `0d9e1aa9fc5925e60dca7d7b1765d7a434657ead3c1f5f9024d2ac5c51a6b20c` |
| Standalone R11 artifact zip | — | `238d0fb901da6e28366c0737d0ac161e551b374cf231c9c545696b32b471a489` |
| Standalone R11 logs zip | — | `d7fe339ad8762a3dc14272e35f17823a374d5652a9200d75cfe3578dc168451c` |

## 8. Blocker / Open counts

| Category | Count | Disposition |
| --- | ---: | --- |
| Material finding | 0 | — |
| Backflow finding | 0 | — |
| New finding | 0 | — |
| Blocker | 0 | — |
| Open question | 0 | — |
| Information observation | 3 | 全部由 Codex zero-change fix 正确消费为 implementation checkpoint |

## 9. Validation checks

| Check | Result |
| --- | --- |
| Plan SHA-256 锁定 | `571ca834...dc7ff2` ✓ |
| Plan line count 锁定 | `1124` ✓ |
| Staged tree | empty ✓ |
| `git diff --check` | no output ✓ |
| 初审两路均 PASS | MiMo PASS / DS PASS ✓ |
| Controller adjudication accepted finding 0 | ✓ |
| Codex zero-change fix | plan unchanged ✓ |
| Controller validation PASS | ✓ |
| Root cause 仍限定为 test oracle overreach | ✓ |
| Primary/raw-source 独立且不强制相等 | ✓ |
| 反例覆盖完整 | ✓ |
| Allowlist 精确到 one-test assertion block | ✓ |
| 无 expansion（helper/import/schema/oracle/README/workflow/Fins/product） | ✓ |
| 本地/remote gate 正确 | ✓ |
| R11/R12 same-run 证据锁 | ✓ |
| Security boundary 保持 | ✓ |
| Deferred scope 不变 | ✓ |
| INFO/OBS 全部正确消费 | ✓ |
| 零 backflow | ✓ |
| Next gate 正确 | Controller adjudication → accepted corrected-plan commit ✓ |

## 10. Verdict

**PASS / ZERO MATERIAL FINDINGS / ZERO BACKFLOW / READY_FOR_CONTROLLER_ADJUDICATION_THEN_ACCEPTED_CORRECTED_PLAN_COMMIT / IMPLEMENTATION_NOT_AUTHORIZED**

Corrected plan 在以下所有维度通过 adversarial re-review：

1. WIN4-RW-RF01 根因仍限定为 test oracle overreach，不是 Fins product defect。
2. Primary exact-name descriptor membership 与 raw source exact basename/public SHA-256 独立、fail-closed、不强制相等。
3. Optional sha256、duplicate names、rglob/physical tree、private meta、hardcoded Docling filename 反例均被覆盖。
4. Exact one-test assertion block allowlist 精确；无 helper/import/schema/oracle/README/workflow/Fins/product 扩张。
5. 本地/remote gate、R11/R12 same-run 证据、安全边界与 deferred scope 正确。
6. 初审三个 INFO/OBS 全部被 zero-change fix 正确消费为 implementation checkpoint；零 backflow、零 new finding。
7. Reviewer next gate 正确指向 Controller adjudication → accepted corrected-plan commit，不是 implementation/remote/closure。

下一步：Controller adjudication → accepted corrected-plan commit。AgentDS 第二路 re-review 已完成。Implementation 仍未授权。

## Artifact metadata

| Item | Value |
| --- | --- |
| Plan SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` |
| Plan lines | `1124` |
| Re-review artifact | 本文件 |
| Fixed next gate | Controller adjudication → accepted corrected-plan commit；AgentDS 第二路 re-review 已完成 |
