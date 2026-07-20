# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW Fresh Windows Plan Correction — AgentMiMo Review (第一路)

## Review entry

- Timestamp：`2026-07-20`（本机系统时钟）。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4 real-Windows remediation`；不是新 WU。
- Gate：fresh Windows evidence 后的 plan-only correction review（第一路完整 review）。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。
- Corrected plan：`1124` lines；SHA-256 `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2`。
- Finding status：`WIN4-RW-RF01 = ACCEPTED / PLAN-CORRECTED / IMPLEMENTATION-OPEN`。
- Review conclusion：**PASS / ZERO MATERIAL FINDINGS / READY_FOR_FIX_AND_RE_REVIEW / IMPLEMENTATION_NOT_AUTHORIZED**。

## 1. Scope and immutable boundary

本 gate 只允许 review corrected plan 并输出本 artifact。不允许修改 plan、product、test、README、design、workflow、control 或其它 artifact；不允许 stage、commit、push、dispatch 或 PR。

## 2. Required-document ingestion checklist

| Document | Status |
| --- | --- |
| `AGENTS.md` | 已读取 |
| `docs/host/issues-implementation-control.md` (header + scope) | 已读取 |
| `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` (1124 lines) | 已完整读取 |
| `docs/reviews/...-evidence-controller-adjudication.md` | 已读取 |
| `docs/reviews/...-plan-correction-codex.md` | 已读取 |
| `docs/reviews/...-plan-correction-controller-validation.md` | 已读取 |
| `docs/fins/design.md` | 已读取 |
| `dayu/fins/pipelines/docling_upload_service.py` (primary owner) | 已读取 |
| `dayu/fins/storage/repository_protocols.py` (descriptor/snapshot contract) | 已读取 |
| `dayu/fins/storage/_fs_source_snapshot.py` (descriptor construction) | 已读取 |
| `dayu/fins/storage/_fs_storage_utils.py` (sha256 deserialization) | 已读取 |
| `dayu/fins/storage/local_file_store.py` (sha256 computation) | 已读取 |
| `tests/cli/test_upload_filings_from_command.py` (exact target node) | 已读取 |
| `.github/workflows/r11-upload-script-windows.yml` | 已读取 |
| `.github/workflows/r12-init-windows.yml` | 已读取 |

## 3. Plan identity verification

| Item | Claimed | Verified |
| --- | --- | --- |
| Line count | 1124 | 1124 ✓ |
| SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | 匹配 ✓ |
| Fresh R11 run id | `29709987970` | Controller adjudication 确认 ✓ |
| Fresh R12 run id | `29709993229` | Controller adjudication 确认 ✓ |
| R12 init result | `9/9 passed` | Controller adjudication 确认 ✓ |
| R12 canary | zero match / PASS | Controller adjudication 确认 ✓ |
| R11 result | `3/4 passed` | Controller adjudication 确认 ✓ |
| R12 embedded R11 | `1/2 passed` | Controller adjudication 确认 ✓ |
| Accepted implementation head | `b11eb95c8312e085755b81c630e9c359220d3ff1` | Controller adjudication 确认 ✓ |

## 4. Adversarial review by focus area

### 4.1 Primary exact descriptor membership vs raw source exact basename+public sha256 — owner separation

**Verdict: PASS**

直接代码证据链：

1. `_pick_primary_docling_file()` (`docling_upload_service.py:844-861`) 遍历 `file_entries`，返回第一个 `name.endswith("_docling.json")` 的 entry name。对于 `2024FY_AAPL_Annual_Report.htm`，primary 将是 `2024FY_AAPL_Annual_Report_docling.json`。

2. `SourceSnapshotProtocol.primary_filename` (`repository_protocols.py:169-173`) docstring 承诺"返回精确命中文件描述符的主文件名"。public contract 只要求 primary_filename 在 `files` descriptor 集合中存在，不约束它是原始 source。

3. `SourceSnapshotFileDescriptor` (`repository_protocols.py:47-65`) 公开 `name: str`（必填）和 `sha256: Optional[str]`（可选）。public contract 足以分别证明 primary membership 和 raw-source publication。

4. Current test line 1003 (`assert snapshot.primary_filename == source_path.name`) 错误地把 Fins-owned primary 选择与 raw source basename 合并。`source_path.name` = `"2024FY_AAPL_Annual_Report.htm"` ≠ `"2024FY_AAPL_Annual_Report_docling.json"`。

5. Corrected plan §13.2.1 将其拆分为两个独立断言：
   - `snapshot.primary_filename` 按 exact name 在 descriptors 中恰好命中一次；
   - `source_path.name` 按 exact name 在 descriptors 中恰好命中一个 descriptor，且该 descriptor 的 public `sha256` 等于 `hashlib.sha256(fixture).hexdigest()`。

6. 两者允许指向不同 descriptors——这正是真实 Windows evidence 的实际场景。Plan §13.5.1 的真实反例覆盖了此情况。

**结论：owner 分离成立。Fins 拥有 primary 选择；CLI test 通过 public descriptor contract 独立证明 raw source publication。**

### 4.2 Optional sha256, duplicate descriptor, fixture bytes/hash, with-lifetime counterexamples

**Verdict: PASS（附一个 INFO 级 observation）**

#### sha256 可选性

- `SourceSnapshotFileDescriptor.sha256` 类型为 `Optional[str]`。
- Write path：`_build_stored_file_entry` (`docling_upload_service.py:1311`) 使用 `file_meta.sha256 or asset.sha256`，两者在 `DoclingUploadService` 路径下均非 None：
  - `file_meta.sha256` 来自 `LocalFileStore.put_object`（`local_file_store.py:94`），始终计算；
  - `asset.sha256` 在 `_build_original_assets`（line 617）和 `_build_pending_assets`（line 674）中计算。
- Read path：`_file_object_meta_from_dict` (`_fs_storage_utils.py:429`) 从 persisted JSON 读取 `sha256`。只要 write 时非 None，read 时就是 `str`。
- 实际场景中 `sha256` 不可能为 None。

Plan §13.5.1 已覆盖 sha256 为空/不匹配的 negative case。若 sha256 为 None，`descriptor.sha256 == hashlib.sha256(fixture).hexdigest()` 将 `None != str` → `False` → assertion failure，行为正确。

**Observation (INFO)**：Plan 没有显式讨论 `sha256` 可选性与 type assertion 的交互。这不是 finding——行为正确，negative case 覆盖——但实现时应直接写 `assert descriptor.sha256 is not None and descriptor.sha256 == expected_hash` 或等价的明确 assertion，而非依赖 Python 的 `None != str` 隐式行为。这样 failure message 更清晰。

#### Duplicate descriptor

- `_build_original_assets` 用 `file_path.name` 作为 `name`；`_build_pending_assets` 用 `f"{file_path.stem}{DOCLING_FILE_SUFFIX}"`。
- 对于 `2024FY_AAPL_Annual_Report.htm`：original name = `"2024FY_AAPL_Annual_Report.htm"`，docling name = `"2024FY_AAPL_Annual_Report_docling.json"`。不同。
- Plan §13.2.1 要求"恰好命中一次"（不是"至少一次"），因此 duplicate descriptor 会正确触发 failure。

#### Fixture bytes/hash 一致性

- Test 读取 `_FIXTURE_SOURCE.read_bytes()` → `fixture`。
- `source_path.write_bytes(fixture)` 写入磁盘。
- CLI 读取该文件 → upload service 读取相同 bytes → 计算 SHA-256。
- Test 断言 descriptor sha256 == `hashlib.sha256(fixture).hexdigest()`。
- 全链路使用同一 bytes 对象的 SHA-256。LF/CRLF 差异不影响一致性（plan §2.1 evidence item 7 已证明 CRLF→LF 后逐字节相同，且两者都通过 Docling conversion）。

#### With-lifetime

- Plan §13.2.1 要求在 `with` 块内读取所有 public facts。
- `materialize_files=False` 不创建临时文件副本，snapshot 只持有 meta 句柄。
- 读取 `files`、`primary_filename`、identity 字段均在 `with` 块内，正确。

### 4.3 One exact-node slice, allowlist, sequencing, review/aggregate/rerun gate completeness

**Verdict: PASS**

#### Allowlist 精确性

- §13.3 允许路径：`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 的现有 snapshot assertion block。
- 禁止清单完整覆盖：全部 `dayu/` product code、其它 tests、README、design、workflow、control、helper/schema/oracle 字段、PowerShell/PTY/process isolation、timeout 增加、skip/xfail/mock。
- §13.3 最后一段的 stop condition 明确：若必须越过 allowlist，立即停止回 Controller。

#### Sequencing

- §13.4 WIN4-RW-RF01 依赖既有 WIN4-RW-S1/S2 accepted aggregate implementation 作为 immutable base。
- 当前只有一个 test-owner slice。
- 经独立 review/fix/re-review 与 accepted implementation commit 后才允许 remote rerun。
- §13.8 closure matrix 要求 fresh R11/R12 双 run 同时通过。

#### Review/aggregate/rerun gate

- §13.0 明确：corrected plan 经 Controller validation、AgentMiMo/AgentDS 双路完整 plan review、finding fix、双路完整 re-review 并形成 accepted corrected-plan commit 前，不得 implementation。
- §13.8 fresh rerun matrix 要求 R11 `4/4 passed`、R12 `9/9 passed`、R12 embedded R11 `2/2 passed`、artifact integrity、canary scan 全部通过。
- §13.8 最后一段明确：任一 run 即使 primary 当前仍选择 Docling JSON，也只作为 Fins owner 事实消费，不能升级为未来 expected primary contract。

#### 完整可执行性

- §13.6 validation commands 全部可直接执行（source .venv/bin/activate 后）。
- §13.6.6 ownership/forbidden-source scans 五条命令全部有明确零输出要求。
- §13.8 closure matrix 每个 gate 都有明确 positive evidence 和 failure semantics。

### 4.4 是否仍隐含硬编码 Docling primary、raw meta/private path、display/rglob business oracle

**Verdict: PASS**

#### Hardcoded Docling primary

- §13.2.1 明确禁止："test 不得规定该 descriptor 必须是原始 source，也不得把当前 Docling 产物文件名、suffix 或任何其它 filename 硬编码成 expected primary"。
- §13.4 stop condition："不得用 Docling filename 替代"。
- §13.6.6 scan 2：`rg '^\+.*(_docling[.]json|DOCLING_FILE_SUFFIX|primary_filename\s*==\s*source_path[.]name)'` — 零输出。
- Plan 文本中 `_docling.json` 出现在 §13.1.1 的 evidence 描述中（说明 Fins 选择了它），但不在 implementation requirement 中。

#### Raw meta/private path

- §13.2.1 明确禁止："不读取 raw source meta、meta JSON、private/core path，不 materialize 或打开 source file，也不从物理 storage tree 反推 publication 业务事实"。
- §13.6.6 scan 3：`rg '^\+.*(source_meta|meta[.]json|private|_core|materialize_files\s*=\s*True|get_source\()'` — 零输出。

#### Display/rglob business oracle

- §13.2.1 point 1 删除 `"Fins result"` 断言，不增加 `Fins summary` 或任何 stdout display 文本断言。
- §13.2.1 point 4：`source_artifact_count` 只保留为物理 integrity count，不再承担业务成功语义。
- §13.6.6 scan 1：`rg '^\+.*(Fins (result|summary|progress|succeeded|failure|cancelled)|execution\.(stdout|stderr))'` — 零输出。
- §13.6.6 scan 4：`rg '^\+(async )?def |^\+class |^\+.*"[A-Za-z_]+"\s*:'` — 零输出（不新增 helper/constant/schema）。

**未覆盖项（INFO，非 finding）**：§13.6.6 没有显式扫描新增 diff 中的 `rglob` 使用。但 §13.2.1 已明确禁止以物理 `rglob` count 替代 raw-source public descriptor；且新增断言只使用 `descriptors`（public snapshot contract），不使用 `rglob`。现有 `rglob`（line 1007-1008）在 target node 之外，allowlist 冻结其零 diff。风险可忽略。

### 4.5 Negative cases, source scans, README/security/deferred/no-code/trusted-local/canary propagation

**Verdict: PASS**

#### Negative cases (§13.5.1)

覆盖完整：

| Scenario | Expected | Covered |
| --- | --- | --- |
| execution nonzero | fail before storage assertions | ✓ |
| exit 0 but company meta missing/invalid | fail | ✓ |
| filing document id zero or multiple | fail | ✓ |
| primary filename zero hit in descriptors | fail | ✓ |
| primary filename multiple hit | fail | ✓ |
| raw basename zero hit | fail | ✓ |
| raw basename multiple hit | fail | ✓ |
| descriptor sha256 is None | fail | ✓ (implicit) |
| descriptor sha256 mismatch | fail | ✓ |
| primary ≠ raw source (real counterexample) | PASS | ✓ |
| stdout empty/prefix change/summary order change | not fail | ✓ |
| stdout success word but exit nonzero | not pass | ✓ |
| company-name oracle still enforced | exact one `Apple Inc.` | ✓ |
| oracle JSON field set unchanged | no new fields | ✓ |

#### Source scans (§13.6.6)

五条 scan 全部有明确零输出要求。Regex 正确覆盖目标模式。

#### README/security/deferred/no-code

- §13.7：README 零 diff，不更新。
- §13.9：Config/Host trusted-local 裁决不变；Tool Trace/audit 禁止明文不变。
- Deferred：Issue 142/151/175/177/178、Web/WeChat/render、Gemini quota 均不实施。
- §13.3 禁止清单覆盖 unified authorization、secret infrastructure、process isolation。

#### Canary propagation

- §13.8 R12 canary gate 要求 Controller 按 §2.3/§9.3 frozen text 独立派生，进程内 exact scan 同一 R12 run 全部 artifact files 与 workflow log files，零命中。
- 不读取/回显/落盘 canary。
- Standalone R11 不进入 canary scan。
- §13.9 明确 standalone R11 只按 artifact integrity 与无 secret-input contract 验收。

### 4.6 Over-design, over-coupling, or missing real Windows artifact integrity

**Verdict: PASS**

#### Over-design

- 只修改一个 test node 的 snapshot assertion block。
- 不新增 helper、constant、schema、fixture 字段、import 或 public contract。
- 不修改 Fins production code。
- Oracle JSON 字段集合零变化。

#### Over-coupling

- Primary membership 与 raw-source publication 两个断言彼此独立。
- 未来 Fins 更换合法 primary 时不会迫使 CLI test 同步改名。
- 不硬编码 Docling expected primary。
- 不依赖 display text、物理 tree 或偶然 filename 选择。

#### Real Windows artifact integrity

- §13.8 R11 artifact integrity 要求：generated script SHA-256 与 oracle 一致；physical artifact count 一致且 >0；required recorder/script/oracle/JUnit/stdout/stderr 存在。
- §13.8 R12 artifact integrity 要求：同一 R12 run 的 JUnit、source hashes、全部 downloaded artifacts 与完整 workflow logs 齐全并重新计算 hash。
- `source_artifact_count` 保留为物理 integrity count，不承担业务成功语义。

### 4.7 All old WIN4-RW accepted behaviors correctly preserved

**Verdict: PASS**

#### WIN4-RW-S1（已接受，当前零 diff）

- §13.4 明确：WIN4-RW-S2 及其 aggregate gates 已接受，当前 correction 不得重新实施或修改。
- `_assert_single_windows_upload_company_name` 继续保留（§13.2.1 point 5）。
- `company_name_supplied=true` 继续写入 oracle（§13.2.1 point 4）。
- `--company-name "Apple Inc."` 继续与 POSIX real workflow 对齐。

#### WIN4-RW-S2（已接受，当前零 diff）

- §13.4 WIN4-RW-S2 slice 明确标记为"已接受、当前零 diff"。
- `_read_secret_input` helper 的 TTY/redirected 分流、EOF/interrupt 语义、line ending 处理、non-disclosure 均不被修改。
- `tests/cli/test_init_command.py` 和 `tests/cli/test_prompt_command.py` 的 TTY fake 不被修改。

#### WIN4-S1/S2/S3（更早 accepted）

- §13.0 明确：既有 WIN4-S1/S2/S3 的 accepted contracts、已关闭 findings 与非冲突约束继续有效，不重新实施、不回滚。
- setx DEVNULL/timeout/names-only result 不被修改。
- `_run_init` Popen lifecycle/anonymous handles/safe failure renderer 不被修改。

#### Display text change

- §13.1.1 明确：`"Fins result"` → `"Fins summary"` 的展示词漂移不会推翻已完成的业务运行。删除 display text 断言，不增加新的 display 断言。

## 5. Finding summary

| # | Finding | Severity | Direct evidence | Required fix |
| --- | --- | --- | --- | --- |
| — | （无 material findings） | — | — | — |

### INFO-level observations（不阻塞）

| # | Observation | Impact |
| --- | --- | --- |
| INFO-1 | Plan 没有显式讨论 `sha256: Optional[str]` 与 assertion 的交互；实现时建议写 `assert descriptor.sha256 is not None and descriptor.sha256 == expected_hash` 以获得更清晰 failure message | 不影响正确性，Python `None != str` 隐式行为已覆盖 |
| INFO-2 | §13.6.6 没有显式扫描新增 diff 中的 `rglob` 使用；但 §13.2.1 禁止条款与 allowlist 冻结已覆盖 | 不影响安全性，新增断言只使用 `descriptors` |

## 6. Assumptions tested

| Assumption | Direct check | Result |
| --- | --- | --- |
| primary 必须等于 raw source 才能证明上传成功 | Fins `_pick_primary_docling_file` 选择 Docling JSON；public descriptor contract 不要求 primary == raw source | REJECTED |
| sha256 可能为 None 导致 assertion crash | `DoclingUploadService` write path 始终计算 sha256；`None != str` → assertion failure 行为正确 | REJECTED (作为 blocker) |
| 需要修改 Fins production/storage contract | 当前 production exit 0 且 public facts 合法，缺陷只在 test oracle | REJECTED |
| 需要新增 helper/schema/oracle 字段 | target node 已有 fixture bytes、hashlib、source path 与 descriptors | REJECTED |
| one-test correction 足够 | 两个 run 唯一共同失败同源于同一 assertion | ACCEPTED |
| display text 变化影响业务成功证明 | process exit 0 + public storage facts 已充分 | REJECTED |
| 需要硬编码 Docling expected primary | Fins owner 选择可能变化；public descriptor contract 足以证明 | REJECTED |

## 7. Code-level evidence verification

### 7.1 Primary owner trace

```
DoclingUploadService._build_pending_assets (line 631-685)
  → builds original + docling assets
  → _store_upload_assets (line 439-463)
    → stores all assets
    → _pick_primary_docling_file (line 844-861)
      → selects first entry ending with "_docling.json"
    → writes primary_document to source meta
```

### 7.2 Descriptor construction trace

```
FsSourceDocumentRepository.read_source_snapshot (line 510-542)
  → _FsRepositorySet.core.read_source_snapshot
    → _read_source_snapshot (line 493-619)
      → _parse_snapshot_files (line 910-990)
        → _file_object_meta_from_dict (line 410-430 of _fs_storage_utils.py)
          → sha256 = str(payload.get("sha256")) if payload.get("sha256") is not None else None
        → SourceSnapshotFileDescriptor(sha256=file_meta.sha256)
```

### 7.3 SHA-256 write path

```
DoclingUploadService._build_original_assets (line 617):
  raw_sha256 = hashlib.sha256(raw_data).hexdigest()

DoclingUploadService._build_pending_assets (line 674):
  docling_sha256 = hashlib.sha256(docling_data).hexdigest()

LocalFileStore.put_object (line 94):
  sha256=sha256.hexdigest()  # always computed

_build_stored_file_entry (line 1311):
  "sha256": file_meta.sha256 or asset.sha256  # always non-None
```

### 7.4 Current failing assertion

```python
# tests/cli/test_upload_filings_from_command.py line 1003
assert snapshot.primary_filename == source_path.name
# primary_filename = "2024FY_AAPL_Annual_Report_docling.json"
# source_path.name = "2024FY_AAPL_Annual_Report.htm"
# → AssertionError
```

### 7.5 Corrected assertion design (§13.2.1)

```python
# Assertion 1: primary membership (Fins-owned)
assert snapshot.primary_filename in tuple(d.name for d in descriptors)
# "2024FY_AAPL_Annual_Report_docling.json" in descriptors ✓

# Assertion 2: raw source publication (independent)
source_descriptor_matches = tuple(
    d for d in descriptors if d.name == source_path.name
)
assert len(source_descriptor_matches) == 1
source_descriptor = source_descriptor_matches[0]
assert source_descriptor.sha256 == hashlib.sha256(fixture).hexdigest()
```

两个断言独立：primary 可以指向 Docling JSON descriptor，raw source 指向 HTML descriptor。两者共存于同一 `files` 集合。

## 8. Open questions

`0`。Primary owner、raw-source publication 证明、exact-node allowlist、README 零 diff、remote closure 与 security boundary 均已收敛。

## 9. Residual owner/destination

| Item | Owner | Destination |
| --- | --- | --- |
| WIN4-RW-RF01 implementation | `tests/cli/test_upload_filings_from_command.py` target node | Controller-authorized one-test fix |
| Fins primary 选择 | `dayu/fins/pipelines/docling_upload_service.py` | 不修改；Fins owner truth |
| Raw source publication | `dayu.fins.storage` public descriptor contract | 不修改；public contract 足够 |
| Fresh R11/R12 closure | Controller §13.8 | 双 run + canary scan |
| sha256 可选性 | `SourceSnapshotFileDescriptor` protocol | INFO-1：实现时显式 `is not None` |

## 10. Accepted/Rejected recommendations

### Accepted

- Corrected plan §13.2.1 的两个独立断言设计。
- §13.3 exact-node allowlist 与禁止清单。
- §13.5.1 negative case matrix。
- §13.6.6 forbidden-source scans。
- §13.8 fresh remote rerun closure matrix。
- §13.9 security/deferred/residual boundary。

### Rejected

- 把 raw source 改成 expected primary（制造新的语义所有权错误）。
- 硬编码 Docling filename 为 expected primary（Fins owner 选择可能变化）。
- 读取 raw meta/private path（违反 public contract 消费边界）。
- 修改 Fins production/storage contract（当前无 production defect）。
- 新增 helper/schema/oracle 字段（target node 已有全部所需输入）。

## 11. Verdict

**PASS / ZERO MATERIAL FINDINGS / READY_FOR_FIX_AND_RE_REVIEW / IMPLEMENTATION_NOT_AUTHORIZED**

Corrected plan 在 primary/raw-source owner 分离、allowlist 精确性、negative case 覆盖、scan 完整性、closure matrix 可执行性、security boundary 保持与旧 accepted behavior 保留方面均通过 adversarial review。两个 INFO-level observations 不阻塞。

下一步：AgentDS 第二路完整 plan review → finding fix（如有）→ 双路 re-review → accepted corrected-plan commit → implementation。

## Artifact metadata

| Item | Value |
| --- | --- |
| Plan SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` |
| Plan lines | 1124 |
| Review artifact lines | 本文件 |
| Controller adjudication SHA | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` |
| Controller validation SHA | 见 `docs/reviews/...-plan-correction-controller-validation.md` |
| Codex correction SHA | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` |
| Fixed next gate | AgentDS 第二路 review → fix → re-review → accepted commit |
