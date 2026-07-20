# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 Corrected-Plan Re-Review — AgentDS（第二路）

## Verdict

`PASS / MATERIAL_FINDING=0 / BLOCKER=0 / BACKFLOW=0 / NEW_FINDING=0 / READY_FOR_ACCEPTED_CORRECTED_PLAN_COMMIT / IMPLEMENTATION_NOT_AUTHORIZED`

本 re-review 是 WIN4-RW-RF01 corrected-plan 的第二路完整 plan re-review。严格按用户指定的七个 adversarial lens 从零独立审查 frozen corrected plan，并验证全链 evidence 消费、Controller 裁决优先、初审 INFO/OBS 全部正确消费且无 backflow。

## Review Identity

- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07 WIN4 real-Windows remediation`；不是新 WU
- Gate: corrected-plan 第二路完整 plan re-review（第一路 re-review 由 AgentMiMo 并发执行）
- Review target: `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
- Prior gates consumed: Controller fresh-Windows evidence adjudication → AgentCodex plan correction → Controller plan-correction validation → AgentMiMo/AgentDS 双路初审 → Controller review adjudication → AgentCodex zero-change fix → Controller fix validation

## Immutable Evidence Locks

### Frozen plan

| Measurement | Value | Match |
| --- | --- | --- |
| Path | `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` | — |
| Lines | `1124` | ✓ |
| SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | ✓ |

### Full evidence chain

| Artifact | Lines | SHA-256 | Consumption |
| --- | ---: | --- | --- |
| Frozen corrected plan | `1124` | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | 完整读取，逐节审查 |
| Controller fresh-Windows evidence adjudication | `63` | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` | 完整读取；root cause 真源 |
| AgentCodex plan correction | — | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` | 完整读取；owner split origin |
| Controller plan-correction validation | — | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` | 完整读取 |
| AgentMiMo 初审 | `407` | `8580d4e6d9e3b4137e0f4b2cea8ea8ed9e4dd4a10c20df8cbffe50572b2de249` | 完整读取；INFO×2 |
| AgentDS 初审 | `235` | `c4d227cf99ff9ac991da030c2ab8fbc386f69d0c6c8e78bbb5e7fa88d674a9e0` | 完整读取；OBS×1 |
| Controller review adjudication | `56` | `5fba7acfd70ab985b568c9457f5160537eb900c47548f22db1100043b379d729` | 完整读取；finding disposition 真源 |
| AgentCodex zero-change fix | `131` | `2fdb62018e499c00d8594310eb4fac532afa17578f96577d90076e6d73906abc` | 完整读取；checkpoint×6 |
| Controller fix validation | `43` | `8645047222fa375beae9a5bb1b4e6e237c07cbfd03aa3fc3b6b9eec5e32d277e` | 完整读取；zero-change accepted |
| `AGENTS.md` | — | — | 已读取；governance rules |
| `docs/host/issues-implementation-control.md` | — | — | 已读取 header+scope |
| `dayu/fins/pipelines/docling_upload_service.py` (primary owner) | — | — | 已读取 L844-861, L610-624, L668-682, L1305-1314 |
| `dayu/fins/storage/repository_protocols.py` (descriptor/snapshot contract) | — | — | 已读取 L47-65, L160-184 |
| `tests/cli/test_upload_filings_from_command.py` (target node) | — | — | 已读取 L980-1029 |

### Current workspace state

- `git diff --check`: PASS（无 whitespace 错误）
- `git diff --cached --name-only`: empty（staged tree 为空）
- `git status --short`: 既有 2 modified + 8 untracked review artifacts；本 gate 新增本文件

---

## Adversarial Re-Review by Specified Focus Areas

### Focus 1: WIN4-RW-RF01 根因是否仍被限定为 test oracle overreach，而非 Fins product defect

**Verdict: PASS — root cause correctly confined to test oracle overreach**

#### Direct production code evidence

1. **Fins primary selection owner**: `DoclingUploadService._pick_primary_docling_file()` (`docling_upload_service.py:844-861`) 遍历 `file_entries`，返回首个 `name.endswith("_docling.json")` 的 entry name（`DOCLING_FILE_SUFFIX = "_docling.json"`, line 58）。这是 Fins production owner 的唯一真源选择。

2. **Primary persistence**: `_pick_primary_docling_file()` 的返回值被写入 `SourceDocumentUpsertRequest.primary_document`（line 480），经 `FsSourceDocumentRepository` 持久化后由 `read_source_snapshot()` 投影。`SourceSnapshotProtocol.primary_filename`（`repository_protocols.py:170-172`）的 public contract 只承诺"返回精确命中文件描述符的主文件名"——不承诺它是 raw source、Docling 产物或任何特定 suffix。

3. **Publication completeness**: Controller evidence adjudication 确认 standalone R11 artifact 的 Fins published tree 包含 company meta、filing manifest、source meta、primary source 与 Docling result。真实上传 exit `0`。失败只阻止随后写出 `cli-grammar-oracle.json`——即失败发生在 test oracle，不在 production upload。

4. **Failing assertion**: 当前 test line 1003 `assert snapshot.primary_filename == source_path.name`。`primary_filename = "2024FY_AAPL_Annual_Report_docling.json"` ≠ `source_path.name = "2024FY_AAPL_Annual_Report.htm"`。该等式要求 Fins primary 必须等于 raw source basename——这是 test 对 Fins owner 选择的越权约束。

5. **No Fins product defect**: Plan §13.1.1 point 2-3 正确证明 company-name、Windows argv quoting、CLI→Service→Fins、Docling conversion、storage transaction/publication 都不是根因。R11 four-node gate 中另三个 nodes 全部通过，进一步排除 generic production defect。

#### Adversarial check

- 是否可能隐藏第二个 Fins product defect？Plan §2.1 "What remains unproved" 承认"现有 generic direct projection 仍不足以诊断任意新的 storage/Docling/third-party failure"。但这不是当前 root cause——当前 failure 的直接证据链（process exit 0 + storage facts 成立 + 唯一失败是 primary==raw source）已完整闭合。Plan §10 diagnostic-first stop gate 为未来未知 failure 提供了正确处置路径。
- 是否可能是 Docling conversion 失败导致 primary 不存在？Controller evidence 确认 Docling result 已存在于 published tree。真实 descriptor 集合包含两个 entries。
- 是否应修改 Fins 让它把 primary 设为 raw source？§2.1 "Minimal remediation decision" 明确拒绝——Fins 拥有 primary 选择权。修改 Fins 来满足 test 是本末倒置。

**结论：根因严格限定为 test oracle overreach。Plan 没有把 Fins product 误判为 defect，也没有在 test 侧补偿 production 缺陷。**

---

### Focus 2: primary exact-name 唯一 descriptor membership 与 raw source exact basename 唯一 descriptor + fixture bytes public SHA-256 — 是否独立、fail-closed、没有强制相等

**Verdict: PASS — 两个断言完全独立、各自 fail-closed、plan 明确禁止强制相等**

#### Independence proof

1. **真实反例已证明独立性**: R11 `29709987970` 与 R12 embedded R11 `29709993229` 的 published tree 中，primary 合法指向 `_docling.json` descriptor，raw source（原始 HTML）以 exact basename 与 correct SHA-256 独立存在于同一 descriptor 集合。两个 descriptor 的 `name` 不同，各自满足自己的 contract。

2. **Plan §13.2.1 的分离设计**:
   - Fins-owned primary: `snapshot.primary_filename` 按 exact `name` 在 `snapshot.files` descriptor 集合中恰好命中一次。不约束该 descriptor 必须是 raw source。
   - Raw source publication: exact `source_path.name` 按 `name` 恰好命中一个 descriptor，且该 descriptor 的 public `sha256` 精确等于 `hashlib.sha256(fixture).hexdigest()`。不约束该 descriptor 必须是 primary。
   - 两者允许指向不同 descriptors——这正是真实 Windows evidence 的实际场景。

3. **Plan §13.5.1 真实反例覆盖**: "当前真实反例必须通过：primary 合法指向非原始 source descriptor，同时原始 source descriptor 以 exact basename 与 exact fixture SHA-256 独立存在"。

#### Fail-closed proof

1. **Primary exact-one**: Plan §13.5.1 明确 primary 零命中或多命中时必须失败。当前实现 `in` operator（line 1004）对多命中不敏感——这正是 OBS-DS-01 指出的问题。Plan §13.2.1 逐字要求"恰好命中一个 descriptor"，§13.5.1 要求 zero/multiple 都失败。Implementation 必须改为 exact cardinality check。

2. **Raw source exact-one**: 同上，raw source basename 零命中或多命中都必须失败。§13.5.1 覆盖。

3. **SHA-256 空值 fail-closed**: `SourceSnapshotFileDescriptor.sha256` 类型为 `Optional[str]`。若为 None，`None == hashlib.sha256(fixture).hexdigest()` → `False` → assertion 失败。当前 write path 始终计算 SHA-256（`docling_upload_service.py:617` raw source, line 674 docling, line 1311 composite），正常路径不可达空值。Plan §13.5.1 已覆盖空值 failure，且 AgentCodex RF01-IMP-CHK-01 要求实现显式 `is not None` check。

4. **SHA-256 不匹配 fail-closed**: Plan §13.5.1 明确覆盖。

#### 禁止强制相等

Plan 全文零处要求 `primary_filename == source_path.name`。§13.2.1 point 5 明确"test 不得规定该 descriptor 必须是原始 source"。§13.6.6 scan 2 对 `primary_filename\s*==\s*source_path[.]name` 要求零输出。§13.5.1 真实反例必须通过"primary 合法指向非原始 source descriptor"。

**结论：两个断言完全独立，fail-closed 语义完整（含 optional sha256 空值），plan 明确禁止强制相等。当前 `in` membership 的 exact-one 不足已由 plan spec 和 negative cases 覆盖，不是 plan gap。**

---

### Focus 3: optional sha、duplicate names、rglob/physical tree、private meta、hardcoded Docling filename 等反例

**Verdict: PASS — 全部反例均有 explicit plan contract 或 forbid clause 覆盖**

| 反例 | Plan 处置 | 验证 |
| --- | --- | --- |
| `sha256: Optional[str]` 空值 | §13.5.1: 空值必须失败；RF01-IMP-CHK-01: 显式 `is not None` | 当前 write path 必然填入；`None != str` fail-closed |
| Duplicate descriptor names | §13.5.1: 零命中/多命中都必须失败 | Plan 要求 exact count `== 1`，替换当前 `in` |
| `rglob` 承担业务语义 | §13.2.1 point 4: `source_artifact_count` 只保留物理 integrity count，不再承担业务 success 语义；§13.5.1: 不得以物理 `rglob` count 替代 raw-source public descriptor name/hash | 既有 `rglob` 行（L1007-1010）在 allowlist 中冻结零 diff；语义降级由 plan 完成 |
| Private meta / raw path 读取 | §13.2.1 point 3: "不读取 raw source meta、meta JSON、private/core path"；§13.6.6 scan 3: 零输出 | Forbidden scan regex 覆盖 |
| 硬编码 Docling expected primary | §13.2.1 point 5: "不得把当前 Docling 产物文件名、suffix 或任何其它 filename 硬编码成 expected primary"；§13.5.1: "不得约束它是某个 Docling filename/suffix" | §13.6.6 scan 2: `_docling[.]json|DOCLING_FILE_SUFFIX` 新增行零输出 |
| Display text 承担 business oracle | §13.2.1 point 1: 删除 `"Fins result"` 断言，不增加任何 stdout/stderr display 断言；§13.5.1: stdout 为空/prefix 变化不得失败 | §13.6.6 scan 1: display 模式新增行零输出 |
| 通过 execution result 反推输入 | §4 WIN4-S1 stop condition: 不得从 execution result 反推输入；§13.2.1 point 5: company-name pre-execution oracle 保留 | company-name oracle 仍逐 token 证明，不依赖 execution success |

**专项反例验证:**

- **Optional sha256 + type assertion 交互**: Plan 未显式讨论 `Optional[str]` 与 assertion 的交互。但这不是遗漏——当前 write path 必然填入 sha256，且 `None != str` 行为正确。AgentCodex RF01-IMP-CHK-01 已将其消费为 implementation 必须显式 `is not None` 的 checkpoint，failure locality 由 implementation review 验证。
- **Duplicate name 在当前实现中不可达但防御性要求成立**: 单次 upload 的 `_build_original_assets` (line 615) 与 `_build_pending_assets` (line 668-674) 各自 name 唯一。但 plan 的 exact-one 要求是防御性的——storage 实现未来变化引入重复时 test 仍 fail closed。
- **`source_artifact_count` 语义降级是否充分**: 是。Plan 保留该字段的写入（oracle JSON field set 零变化），但 test 不再用它推断 primary 或 raw source publication。物理 count 仅作为 workflow integrity gate 的 artifact 数量校验。

**结论：全部反例均被 plan contract、negative case matrix 或 explicit forbid clause 覆盖。零遗漏。**

---

### Focus 4: exact one-test assertion block allowlist、无 helper/import/schema/oracle/README/workflow/Fins/product 扩张

**Verdict: PASS — allowlist 精确到机械可验证，禁止清单全面无遗漏**

#### Allowlist 精确性验证

1. **唯一允许的 diff 位置** (§13.3): `tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 的现有 snapshot assertion block（当前 L992-1009）。

2. **当前 assertion block 精确范围**: `with source_repository.read_source_snapshot(...) as snapshot:` 块内 L998-1006。Plan 要修改的是:
   - 删除 L1003 `assert snapshot.primary_filename == source_path.name`
   - 替换 L1004-1006 的 `in` membership 为 exact-one count check
   - 新增 raw source exact basename unique descriptor + public SHA-256 assertion
   - L1007-1010（`source_artifacts` rglob）在 `with` 块外但在同一 test node 内——plan 要求零 diff

3. **同文件禁止修改项** (§13.3): imports、module constants、helpers、fixtures、其它 tests、oracle JSON block——全部零 diff。

#### 禁止清单完整性

| 禁止类别 | Plan 位置 | 覆盖 |
| --- | --- | --- |
| 全部 `dayu/` product code | §13.3 禁止清单 | ✓ |
| 其它 tests | §13.3 | ✓ |
| README/design docs | §13.3 + §13.7 | ✓ |
| Workflow YAML | §13.3 | ✓ |
| Control/review artifacts | §13.3 | ✓ |
| 新 helper/constant/schema field | §13.2.1 point 6 + §13.3 禁止清单 | ✓ |
| Oracle JSON 新字段 | §13.2.1 point 4: "oracle JSON 字段集合必须保持不变" | ✓ |
| `dayu.runtime` secret helper | §13.3 禁止清单 | ✓ |
| PowerShell/PTY/process isolation | §13.3 禁止清单 | ✓ |
| timeout 增加/skip/xfail/mock | §13.3 禁止清单 | ✓ |

#### 机械验证可执行性

§13.6.5 的 diff 验证链可直接执行:
```bash
git diff --unified=0 CORRECTED_PLAN_BASE -- tests/cli/test_upload_filings_from_command.py
git diff --name-only CORRECTED_PLAN_BASE -- dayu tests README.md ':(glob)**/README.md' \
  docs/fins/design.md docs/ui/design.md docs/host/design.md .github/workflows
```
第二条必须只有 target test file。§13.6.6 的五条 forbidden-source scan 全部有精确 regex 和零输出要求。

**结论: allowlist 精确到 reviewer 可逐行机械验证；禁止清单覆盖全部可能扩张方向。零 ambiguity。**

---

### Focus 5: 本地/remote gate、R11/R12 same-run 证据、安全边界与 deferred scope

**Verdict: PASS — remote gate 有 metadata-before-evidence 锁；same-run canary 独立可重算；安全边界无削弱；deferred scope 精确枚举**

#### Remote gate metadata-before-evidence

1. **§13.8 R11/R12 identity gate**: 要求 dispatch response 返回唯一新 run id，且在下载/读取任何 evidence 前验证 workflow identity/name、path、event（`workflow_dispatch`）、branch/ref 与 accepted implementation head SHA。任一 missing/mismatch/ambiguous 立即 fail。不得从"最近 run"、时间戳或 artifact 名反推。

2. **Controller evidence adjudication 已验证此流程**: R11 `29709987970` 与 R12 `29709993229` 的 metadata tuple 均在读取 evidence 前完成验证，且全部精确匹配。

3. **同 run lineage**: §13.8 要求 JUnit、source-hash、全部 downloaded artifacts、完整 workflow logs 与 canary scan 必须属于同一 `run_id`。跨 run 混用即 gate fail。

#### Same-run canary gate

1. **既有 frozen contract 不变**: §13.8 R12 canary gate 沿用 §2.3/§9.3 frozen text——Controller 独立派生，process-internal exact scan，零命中。

2. **Test/Controller 不共享**: §13.8 + §2.3 明确禁止共享派生 helper、constant module 或 needle artifact。

3. **Standalone R11 隔离**: standalone R11 不消费 R12 canary，只按自身 artifact integrity 与无 secret-input contract 验收。

#### Security boundary

1. **Trusted-local 不变**: §13.9 Config/Host internal SQLite/EventLog 保持 trusted-local domain。

2. **Non-disclosure 不变**: Tool Trace/audit/public/LLM-facing/operator log 继续禁止 API key/header 明文。

3. **No new secret infra**: §13.9 明确不新增 zeroization、credential broker、unified authorization 或 secret infrastructure。

4. **Redirected stdin 不是 encrypted transport**: §13.9 明确"不把 redirected stdin 伪装成 encrypted transport"。

#### Deferred scope

§13.9 精确枚举: Issue 142、151、175、177、178；Web/WeChat/render；通用 console/PTY/process isolation；setx redesign；统一 authorization/secret management；Fins generic diagnostic schema。Gemini low-budget 保持 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

**结论: remote gate 的 metadata-before-evidence 锁已在 Controller adjudication 中实战验证；same-run canary 独立可重算；安全边界零削弱；deferred scope 精确且无泄漏。**

---

### Focus 6: 初审 INFO/OBS 是否全部被 zero-change fix 正确消费，有无 backflow/new finding

**Verdict: PASS — 全部三个 observation 正确消费为 downstream checkpoint；零 backflow；零 new finding**

#### 消费矩阵

| Observation | 来源 | AgentCodex disposition | Checkpoint | 本 re-review 验证 |
| --- | --- | --- | --- | --- |
| MiMo INFO-1: optional `sha256` 显式性 | 初审 §4.2 | `NO PLAN FIX / CONSUMED` | RF01-IMP-CHK-01 (显式 `is not None`), RF01-REVIEW-CHK-01 (implementation review 验证) | Plan §13.5.1 已覆盖空值 failure；write path 必然填入 sha256；显式 check 改善 failure locality，不改变 contract |
| MiMo INFO-2: added-diff `rglob` scan | 初审 §4.4 | `NO PLAN FIX / CONSUMED` | RF01-IMP-CHK-02 (实现时检查无新增 `rglob`), RF01-REVIEW-CHK-02 (review 确认 publication 断言只消费 `descriptors`) | Plan §13.2.1 禁止 physical tree 推导；allowlist 冻结既有 `rglob` 行零 diff；新增 regex 只重复机械边界 |
| DS OBS-DS-01: `in` membership 不拒绝 duplicates | 初审 §Finding Ledger | `NO PLAN FIX / IMPLEMENTATION REQUIREMENT ALREADY EXPLICIT / CONSUMED` | RF01-IMP-CHK-03 (exact cardinality `== 1`), RF01-REVIEW-CHK-03 (review 验证 zero/multiple-hit failure) | Plan §13.2.1 逐字要求 exact-one；§13.5.1 要求 zero/multiple 都失败；当前 `in` 是待替换对象，不是 plan omission |

#### Backflow 检查

- **是否有 observation 被升级为 material finding？** 否。Controller adjudication 明确三个均为 `NO PLAN FIX`。AgentCodex zero-change fix 未修改 plan。
- **是否有 observation 被遗漏？** 否。三个全部在 AgentCodex artifact §Observation consumption 中逐项处置，每个都有对应的 IMP-CHK 和 REVIEW-CHK。
- **是否有新 observation 从 fix 中产生？** 否。Controller fix validation 确认 plan SHA-256 未变，零新内容。
- **checkpoint 是否引入了超越 allowlist 的要求？** 否。所有 checkpoint 都只约束 implementation/review 在 allowlist 内的行为，不扩大 plan scope。

#### New finding 检查

对全链所有 artifact（Controller evidence adjudication → Codex correction → Controller validation → 初审两路 → Controller adjudication → Codex fix → Controller fix validation）做 diff 扫描：零新增 material finding、blocker、needs-evidence 或 design contradiction。Controller review adjudication final ledger 确认 `accepted plan finding = 0`，该状态未被任何后续 gate 改变。

**结论：三个 observation 全部正确消费为 downstream checkpoint；零 backflow（无 observation→finding 升级、无遗漏、无新增）；零 new finding。**

---

### Focus 7: reviewer next gate 必须是 Controller adjudication 后 exact docs/control/reviews accepted corrected-plan commit；不是直接 implementation、remote 或 closure

**Verdict: PASS — 本 re-review 的 next gate 正确；此前 reviewer next-gate 压缩已被 Controller 纠正**

#### 全链 next-gate 追溯

| Gate | Actor | 原始 next-gate 声明 | 是否正确 | Controller 处置 |
| --- | --- | --- | --- | --- |
| 初审 | AgentMiMo | "AgentDS 第二路 review" | 当时正确（DS 尚未执行） | — |
| 初审 | AgentDS | `READY_FOR_IMPLEMENTATION_GATE` | **错误** — 跳过了 fix/re-review 流程 | Controller adjudication: "不具授权效力...固定完整流程仍包括 AgentCodex plan-finding fix record 和双路完整 re-review" |
| Review adjudication | Controller | "AgentCodex zero-change fix → Controller validation → 双路完整 plan re-review" | 正确 | — |
| Zero-change fix | AgentCodex | "Controller validation 后只能进入双路完整 plan re-review" | 正确 | — |
| Fix validation | Controller | "只授权 AgentMiMo 与 AgentDS 并发执行双路完整 corrected-plan re-review" | 正确 | — |
| **本 re-review** | **AgentDS** | **Controller adjudication → accepted corrected-plan commit → implementation** | **正确** | — |

#### 本 re-review 的 next gate 验证

Controller review adjudication 明确:
> "只授权 AgentCodex 形成 zero-change plan-review fix artifact...Controller validation 后再执行 AgentMiMo/AgentDS 双路完整 plan re-review。Implementation 尚未授权。"

Controller fix validation 明确:
> "只授权 AgentMiMo 与 AgentDS 并发执行双路完整 corrected-plan re-review...accepted corrected-plan commit、one-test implementation、remote dispatch、PR review 与 final closeout 仍未授权。"

因此本 re-review 完成后:
1. 两路 re-review 结果由 Controller 裁决。
2. 若双路均 PASS 且 zero material finding，形成 accepted corrected-plan commit。
3. Implementation、remote dispatch、PR review、closure 均仍未授权。

**本 re-review 的 next gate 是: Controller adjudication of dual re-review results → accepted corrected-plan commit。不是 implementation、不是 remote dispatch、不是 closure。**

---

## Finding Ledger

| # | Severity | Status | Description |
| --- | --- | --- | --- |
| — | — | — | 本轮无 material finding、blocker、needs-evidence、backflow 或 design contradiction |

### Observation summary（全部为 NO PLAN FIX / ALREADY CONSUMED）

| # | Source | Subject | Status |
| --- | --- | --- | --- |
| MiMo INFO-1 | 初审 | optional `sha256` 显式性 | CONSUMED → RF01-IMP-CHK-01 / RF01-REVIEW-CHK-01 |
| MiMo INFO-2 | 初审 | added-diff `rglob` scan | CONSUMED → RF01-IMP-CHK-02 / RF01-REVIEW-CHK-02 |
| DS OBS-DS-01 | 初审 | `in` membership 不拒绝 duplicates | CONSUMED → RF01-IMP-CHK-03 / RF01-REVIEW-CHK-03 |

**无新增 observation。三个既有 observation 均被正确消费，无 backflow。**

---

## Open Questions

`0`。Primary owner、raw-source publication 证明、exact-node allowlist、validation matrix、remote closure gate、security/deferred boundary、observation consumption 与 next gate 均已收敛。Implementation agent 无需重新设计。

---

## Per-Focus Adversarial Results Summary

| Focus | Subject | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 | Root cause: test oracle overreach vs Fins product defect | PASS | Fins `_pick_primary_docling_file` 是 primary 唯一 owner；process exit 0 + storage facts 成立；唯一失败是 test L1003 `==` |
| 2 | Primary exact-one membership vs raw source exact basename + SHA-256 独立/fail-closed/非强制相等 | PASS | 两个断言独立（真实反例证明）；各自 exact-one fail-closed；plan 零处要求相等；当前 `in` 不足已由 spec 覆盖 |
| 3 | Optional sha/duplicate/rglob/private meta/hardcoded Docling 反例 | PASS | 全部有 explicit contract/forbid/negative case；零遗漏 |
| 4 | Exact-node allowlist，无 helper/import/schema/oracle/README/workflow/Fins/product 扩张 | PASS | 只允许现有 snapshot assertion block；禁止清单完整；§13.6.5/§13.6.6 机械可验证 |
| 5 | 本地/remote gate、R11/R12 same-run、安全边界、deferred scope | PASS | Metadata-before-evidence；same-run canary 独立；security 不变；deferred 精确 |
| 6 | INFO/OBS 全部正确消费，无 backflow/new finding | PASS | 3/3 consumed → 6 checkpoints；零 backflow；零 new finding |
| 7 | Next gate: Controller adjudication → accepted corrected-plan commit，非 implementation/remote/closure | PASS | Controller 已纠正初审 next-gate 压缩；本 re-review next gate 正确 |

---

## Residual Risk and Owner/Destination

| # | Risk | Owner | Destination |
| --- | --- | --- | --- |
| 1 | 非 Windows 本地无法证明 real smoke | Test platform | §13.8 fresh R11/R12 remote rerun |
| 2 | Optional `sha256` 空值路径在正常 storage 不可达 | `SourceSnapshotFileDescriptor` protocol | 当前 write path 必然填入；future storage 变化时 test fail-closed |
| 3 | `snapshot.primary_filename` 的 exact-one contract 由 Fins storage 实现保障 | `FsSourceDocumentRepository` | 若 Fins 违反此 contract，test fail——正确行为 |
| 4 | Duplicate descriptor names 在当前实现不可达 | `DoclingUploadService` | Plan 防御性 exact-one 要求覆盖 future 变化 |
| 5 | 初审 AgentDS next-gate 措辞 `READY_FOR_IMPLEMENTATION_GATE` | AgentDS 初审 artifact | 已被 Controller 纠正；本 re-review 正确声明 next gate；历史 artifact 不修改 |

---

## Plan SHA / Artifact SHA / Lines

| Item | SHA-256 | Lines |
| --- | --- | --- |
| Frozen corrected plan | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | `1124` |
| Controller evidence adjudication | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` | `63` |
| AgentCodex plan correction | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` | — |
| Controller plan-correction validation | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` | — |
| AgentMiMo 初审 | `8580d4e6d9e3b4137e0f4b2cea8ea8ed9e4dd4a10c20df8cbffe50572b2de249` | `407` |
| AgentDS 初审 | `c4d227cf99ff9ac991da030c2ab8fbc386f69d0c6c8e78bbb5e7fa88d674a9e0` | `235` |
| Controller review adjudication | `5fba7acfd70ab985b568c9457f5160537eb900c47548f22db1100043b379d729` | `56` |
| AgentCodex zero-change fix | `2fdb62018e499c00d8594310eb4fac532afa17578f96577d90076e6d73906abc` | `131` |
| Controller fix validation | `8645047222fa375beae9a5bb1b4e6e237c07cbfd03aa3fc3b6b9eec5e32d277e` | `43` |
| **本 re-review** | **见文件尾** | **本文件** |

---

## Validation

| Check | Result |
| --- | --- |
| Frozen plan SHA-256 = `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | ✓ |
| Frozen plan lines = `1124` | ✓ |
| Controller evidence adjudication SHA verified | ✓ |
| AgentMiMo 初审 SHA verified | ✓ |
| AgentDS 初审 SHA verified | ✓ |
| Controller review adjudication SHA verified | ✓ |
| AgentCodex zero-change fix SHA verified | ✓ |
| Controller fix validation SHA verified | ✓ |
| Plan 零修改（SHA 与 lines 与入场一致） | ✓ |
| Product code 零修改（`dayu/` unchanged） | ✓ |
| Test code 零修改 | ✓ |
| Staged tree empty | ✓ |
| `git diff --check` pass | ✓ |
| 只新增本 re-review artifact | ✓ |
| 未 stage/commit/push/dispatch/PR | ✓ |

---

## Fixed Next Gate

Controller 对 AgentMiMo 与 AgentDS 双路 re-review 结果进行裁决。若双路均 PASS 且 zero material finding，形成 accepted corrected-plan commit。**Implementation、remote dispatch、PR review 与 final closeout 仍未授权。**

---

## Artifact Metadata

| Item | Value |
| --- | --- |
| Review type | 第二路完整 corrected-plan re-review |
| Umbrella | `WU-SEMANTIC-OWNERSHIP-01` |
| Continuation | `AR-F07 WIN4-RW-RF01` |
| Gate | corrected-plan re-review |
| Frozen plan SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` |
| Frozen plan lines | `1124` |
| Verdict | `PASS / MATERIAL_FINDING=0 / BLOCKER=0 / BACKFLOW=0 / NEW_FINDING=0` |
| Next gate | Controller adjudication → accepted corrected-plan commit |
| Implementation authorized | No |
