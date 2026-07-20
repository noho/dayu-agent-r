# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Fresh Windows Plan Correction Review — AgentDS

## Verdict

`PASS / MATERIAL_FINDING=0 / BLOCKER=0 / READY_FOR_IMPLEMENTATION_GATE`

本 review 是 WIN4 plan-correction 的第二路独立完整 review，不参考第一路结论。review 按用户指定的七个 adversarial lens 从零完整审查 corrected plan。

## Review Identity

- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07 WIN4 real-Windows remediation plan correction`；不是新 WU
- Gate: fresh Windows evidence 后的 plan-only correction dual review
- Review target: corrected plan `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
- Controller evidence adjudication: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-evidence-controller-adjudication.md`
- Codex correction artifact: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-plan-correction-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-plan-correction-controller-validation.md`

## Immutable Input Locks

| Item | Value |
| --- | --- |
| Corrected plan SHA-256 | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` |
| Corrected plan lines | `1124` |
| Codex artifact SHA-256 | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` |
| Controller validation SHA-256 | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` |
| Evidence adjudication SHA-256 | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` |
| `docling_upload_service.py` SHA-256 | `aad45665a3a41c39dd228bf323a6ed4bac8ca97488b6917448ba37d2ec656580` |
| `repository_protocols.py` SHA-256 | `428c7a27faed9abf46a79343f0aeb2cd891c86408ba679a12ab998e11cc83b35` |
| `test_upload_filings_from_command.py` SHA-256 | `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` |
| R11 workflow SHA-256 | `4c915a9c79efa5ee0166eb6fae44513ecc077b974217ca1e855e8b7ec4507f43` |
| R12 workflow SHA-256 | `ba99b5a40c6d3116e1d83b05cd97139dcc62699722269b0aa6fc1a8d5ebea7b8` |
| `fins/design.md` SHA-256 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| Controller control SHA-256 | `7ef9bbae017ad8efb59111b0b4d544002e6bf09ace7fe11c7cf68a2773763995`（control doc 在 Codex artifact 记录后由 Controller 正常更新 status，仍由 Controller 自己管理，不是 plan correction scope） |

## Adversarial Lens Results

### Lens 1: primary exact descriptor membership 与 raw source exact basename + public sha256 — owner 分离与充分性

**Direct evidence:**

1. Fins production owner `DoclingUploadService._pick_primary_docling_file()`（`docling_upload_service.py:844-861`）选择首个以 `_docling.json` 结尾的 entry 为 `primary_document`，写入 `SourceDocumentUpsertRequest.primary_document`（line 480）。这是 Fins production/storage owner 的持久化事实。

2. `SourceSnapshotProtocol.primary_filename`（`repository_protocols.py:170-172`）的 public contract 只承诺"返回精确命中文件描述符的主文件名"；不承诺它是 raw source、Docling 产物或任何特定 suffix。

3. `SourceSnapshotFileDescriptor`（`repository_protocols.py:48-65`）公开 exact `name: str` 与可选 `sha256: Optional[str]`。`name` 是 exact 业务文件名，`sha256` 由 `_build_stored_file_entry()` 在落盘时填入（`docling_upload_service.py:1311`：`file_meta.sha256 or asset.sha256`，其中 raw source 的 `asset.sha256` 由写入时的原始 bytes 计算，line 617）。

4. Corrected plan §13.2.1 把两个语义正确分离：
   - Fins-owned primary：`snapshot.primary_filename` 按 exact `name` 在 `snapshot.files` descriptor 集合中恰好命中一次；
   - Raw source publication：exact `source_path.name` 按 `name` 恰好命中一个 descriptor，且其 public `sha256` 精确等于 `hashlib.sha256(fixture).hexdigest()`。

**Adversarial check:**

- 两个断言是否真正独立？是。真实反例已由 R11 `29709987970` / R12 embedded R11 `29709993229` 提供：primary 合法指向 `_docling.json` descriptor，raw source descriptor（原始 HTML）以 exact basename 与 exact fixture SHA-256 独立存在。两者指向不同 descriptor，且各自证明不同的业务事实。
- public contract 足以承载两个断言吗？`SourceSnapshotFileDescriptor` 的 `name` 和 `sha256` 字段是 public contract 的充分接口。raw source 的 `sha256` 在 storage 落盘时由原始 bytes 计算，与 test 侧 fixture bytes SHA-256 同源可比。
- 是否遗漏任何 Fins owner fact？`primary_filename` 的 Fins owner contract（精确命中 descriptor）已被断言；test 不强加 `primary_filename == source_path.name` 的越权约束。

**Verdict: `PASS`** — owner 分离正确且充分。

### Lens 2: optional sha256、duplicate descriptors、fixture bytes/hash、with lifetime 反例

**Direct evidence:**

1. **Optional `sha256`**: `SourceSnapshotFileDescriptor.sha256` 类型为 `Optional[str]`。但如果 raw source descriptor 的 sha256 为 None：`None == hashlib.sha256(fixture).hexdigest()` 为 `False`，assertion 失败。Plan §13.5.1 负向用例明确覆盖"descriptor public sha256为空...时必须失败"。对于当前 storage 实现，`_build_stored_file_entry()` 总是填入 `file_meta.sha256 or asset.sha256`，raw source 的 `asset.sha256` 必填。此实现细节是 Fins owner contract 的保障，不是 test oracle 的隐式假设。

2. **Duplicate descriptors**: §13.5.1 明确覆盖 primary 零命中/多命中与 raw basename 零命中/多命中场景。若同一 name 出现多次（当前实现不应出现），`恰好命中一次` 的断言失败。

3. **Fixture bytes/hash cycle**: test 已有 `fixture = _FIXTURE_SOURCE.read_bytes()`（line 936），随后写入 `source_path`（line 938）。corrected plan 要求 `hashlib.sha256(fixture).hexdigest()` — 直接对写入前的 bytes 计算，摆脱对 storage read-back 或 meta JSON 的依赖。这是从 memory bytes 到 public sha256 的最短验证链。

4. **with lifetime**: corrected plan §13.2.1 明确"只在 `with` 块内读取和确认"，且不得在 `with` 块外访问 snapshot。existing test 已使用 context-manager（line 992-1006）。Plan 还禁止 CLI test 重复增加 Fins close-after-use owner test。

**Adversarial check:**

- Optional sha256 的空值路径是否被测试覆盖？负向用例要求 sha256 为空时失败。但当前实现在正常路径必然填入 sha256 — 负向用例如何构造？这是一个实现问题：需通过 fixture/mock 或特定 storage 状态触发。Plan 未详细说明如何构造空 sha256 descriptor，但"必须失败"的 spec 是完整的。实现阶段可使用 monkeypatched descriptor tuple 覆盖。
- Duplicate 场景是否真实可达？不可达 — 单次 upload 的 pending assets 各 name 唯一。但 negative-case 要求是防御性的，防止 storage 实现未来变化引入重复。

**Verdict: `PASS`** — optional sha256 有 explicit failure contract；duplicate 保护完备；fixture bytes→SHA 链路最短；with lifetime 受保护。

### Lens 3: exact-node allowlist、one-slice sequence、validation/review/aggregate/remote rerun gates 可执行性

**Direct evidence:**

1. **Exact-node allowlist** (§13.3): 唯一允许的 diff 位置是 `test_windows_generated_script_runs_real_cli_into_temp_storage` 的现有 snapshot assertion block（大约 line 998-1006）。同文件 imports/constants/helpers/fixtures/其它 nodes/oracle JSON block 零 diff。§13.3 明确列出全部禁止修改项：所有 `dayu/` product code、其它 tests、全部 README/design、workflow YAML、control/review artifacts。

2. **One-slice sequence** (§13.4): 只有一个 slice `WIN4-RW-RF01`，依赖 `WIN4-RW-S1/S2` accepted aggregate immutable base。经独立 review/fix/re-review 与 accepted implementation commit 后进入 remote rerun。

3. **Validation gates** (§13.6): 分 per-slice focused、aggregate/broader、pyright/Ruff、diff/allowlist、ownership/forbidden-source scans。每条都有 exact 命令。

4. **Remote rerun gates** (§13.8): R11 four nodes → R12 init + embedded R11 → artifact integrity → same-run canary。每个 gate 有 required result、positive evidence 与 failure/stop contract。Controller 独立验证 workflow identity/path/event/ref/head SHA。

5. **Diagnostic-first stop** (§10): 若 S1 后仍失败，停止 root-cause 修复，先判断 failure 位于哪个 existing owner boundary；无 owner fact 则回 plan correction。

**Adversarial check:**

- allowlist 是否精确到 reviewer 可机械验证？是。`git diff --unified=0 CORRECTED_PLAN_BASE -- tests/cli/test_upload_filings_from_command.py` 只应显示 target node snapshot assertion block 变化。多条 scan（§13.6.6）机械验证不引入 forbidden patterns。
- one-slice 是否有足够验证覆盖？§13.6.1 要求：target file、POSIX real smoke、三个 public repository owner nodes 与 Windows exact node 分别报告结果。
- remote rerun 是否避免 run-id 猜测？§13.8 明确"本次 dispatch response 返回唯一新 run id"，且 identity verification 在读取 evidence 前完成。这延续了 Controller evidence adjudication 的已验证流程。

**Verdict: `PASS`** — 所有 gate 可独立执行与机械验证。

### Lens 4: 是否残留硬编码 Docling primary、raw meta/private path、display 或 rglob 业务 oracle

**Source scan evidence:**

1. **Old error phrasing scan**（`primary[ ]filename.*等于.*source[ ]basename|primary[_]filename == source_path[.]name`）: `0` hits.
2. **Hardcoded Docling expected primary scan**: corrected plan 中出现 `_docling.json` 或 `DOCLING_FILE_SUFFIX` 的句子均出现在禁止语境中：
   - §13.1.1 line 734: "`_pick_primary_docling_file()` 选择 Docling JSON" — 这是 Fins owner evidence 描述，不是 test 侧要求。
   - §13.5.1 line 906: "不得约束它是某个 Docling filename/suffix" — 禁止性约束。
   - §13.4 line 872-873 / §13.5.1 / §13.6.6 line 1033-1034: 扫描命令禁止实现引入硬编码。
   - §13.8 line 1104: "不得把 raw source改成 expected primary、把 Docling filename硬编码为 expected primary" — diagnostic-first 禁止项。
   - 零处要求 test 把 Docling filename 固化为 expected primary。
3. **Raw meta/private path scan**: 全部命中都是禁止性措辞（"不读取 raw meta/private path"、"禁止 raw meta/private-path 读取"等）。
4. **Display oracle scan**: §13.5.1 明确"stdout 为空、prefix变化...不得失败"（line 915-916）；"stdout含任意看似成功词但 exit非零...不得通过"（line 916-917）。
5. **rglob scan**: existing `source_artifacts = tuple(path for path in (storage / "portfolio").rglob("*") if path.is_file())`（line 1007-1010）在 corrected plan §13.2.1 中被保留但语义降级为"只保留为 uploaded evidence package 的物理 integrity count，不再承担业务 success 语义"（line 793-795）。oracle JSON 继续写入 `source_artifact_count`，但不被 test 用来推断 primary 或 raw source publication。
6. **Implementation scan commands** (§13.6.6): 五条 scan 全部零输出的要求确保实现不引入上述 forbidden patterns。

**Verdict: `PASS`** — 零残留硬编码 Docling primary、raw meta/private path、display 或 rglob 业务 oracle。

### Lens 5: negative cases、scan、README、安全、deferred/no-code、trusted-local、canary 传播

**Direct evidence:**

1. **Negative cases** (§13.5.1): 覆盖 exit nonzero 先于 storage（line 903）、company meta 缺失/非法（line 904）、primary 零/多命中（line 905-906）、raw basename 零/多命中（line 908-909）、sha256 空/不匹配（line 908-909）、真实反例必须通过（line 910-911）、display 不成为 oracle（line 915-917）、company-name oracle 不变（line 918-919）、oracle JSON 字段集合不变（line 920-921）。

2. **Security**: §13.9 保持 trusted-local Config/Host durable state 边界；Tool Trace/audit/public/LLM/operator non-disclosure 不变。R12 canary contract 按既有 frozen text 不变。No new secret infrastructure。

3. **README**: §13.7 明确 WIN4-RW-RF01 零 README diff。既有 WIN4-RW-S2 的 README 更新已是 accepted immutable base。

4. **Deferred/no-code** (§13.9): Issue 142/151/175/177/178、Web/WeChat/render、unified authorization/secret management、Gemini low-budget 均保持 deferred/non-blocking，不在本次 scope。

5. **Canary propagation**: §13.8 R12 same-run canary gate 沿用既有 §2.3/§9.3 frozen contract。Test/Controller 禁止共享 helper。Standalone R11 按自身无 secret-input contract 验收，不进入 canary scan。

**Adversarial check:**

- negative cases 是否构成可测试的闭合集合？是。每项都有明确 pass/fail condition，可直接映射到 assertion。
- 安全边界是否有任何削弱？没有。trusted-local 裁决、canary contract、Tool Trace/audit non-disclosure 均未改写。
- README zero diff 是否合理？合理。这是一个 internal test oracle 修正，不改变用户可见行为、配置、命令行参数或最终用户工作流。

**Verdict: `PASS`** — negative cases 闭合，安全/deferred/README/canary 边界保持。

### Lens 6: overdesign/overcoupling 与 artifact integrity

**Direct evidence:**

1. **Scope minimality**: 唯一 slice，唯一 exact test node，唯一现有 snapshot assertion block。不新增 helper、constant、schema field、public contract field、oracle JSON field、import、fixture、wrapper 或 compatibility seam。

2. **Owner coupling**: primary membership 与 raw source publication 彼此独立断言。Fins 未来更换 primary 选择（如切换到 Markdown 或 native PDF）时，raw source publication 断言不变；raw source descriptor name/hash 断言不变。没有将 test oracle 耦合到当前 primary 的具体实现选择。

3. **Artifact integrity**: §13.3 frozen immutable base 保证 `WIN4-RW-S1/S2` aggregate implementation、product、tests、README、design、workflow 全部 zero diff。§13.6.5 diff check 机械验证。

4. **No infrastructure**: 不引入通用 descriptor helper、publication verifier、storage abstraction layer、test framework 或 shared fixture。现有 `hashlib`、`fixture` bytes、`source_path`、`descriptors` 已足够。

**Adversarial check:**

- 是否任何实现细节可被进一步删减？检查后无。现有 assertions 已是最小集合：process exit + company/source identity + primary membership + raw source descriptor name/hash。
- primary 与 raw source 断言是否真正去耦？是。如果 Fins 改为不生成 Docling JSON（primary 变为原始 HTML），raw source assertion 不变（它只检查 source_path.name 是否存在且有正确 sha256）；如果 Fins 新增 third descriptor（如 Markdown），两个断言都不受影响（primary 仍命中一个，raw source 仍命中一个）。

**Verdict: `PASS`** — 无 overdesign/overcoupling；artifact integrity 受 frozen base 锁与 diff 机械验证保护。

### Lens 7: 既有 accepted 行为是否被错误重开或削弱

**Direct evidence:**

1. **WIN4-RW-S1** (secret-input boundary): §13.4 明确 "本 slice及其aggregate gates已接受。当前 correction不得重新实施或修改"。

2. **WIN4-RW-S2** (setx stdio/timeout): 同上，immutable base。

3. **WIN4-F01** (company-name): §2.1 root cause 已建立，§3.2 明确禁止"给缺失 company name 增加...fallback"。corrected plan 不重开此 root cause。

4. **WIN4-F02** (setx): 已有 R12 `9/9` positive evidence；§2.2 production contract 不变。不重开。

5. **WIN4-F03** (safe test failure projection): §2.3 contract 不变。canary contract 沿用 frozen text。不重开。

6. **原有 accepted aggregate commit** (`8aeb67be`): §13.0 明确 WIN4-RW-S1/S2 是 immutable implementation base，不是未来 diff allowlist。

7. **Topic 1-7 closed findings**: corrected plan 不涉及 Topic 1-7 的 production code、schema、public contract 或 design truth。

**Adversarial check:**

- 是否任何既有 positive evidence 被降级为 "pending"？没有。WIN4-RW-F02 保持 POSITIVE REMOTE EVIDENCE；WIN2-F01/F02/F03 与 WIN3-F01 已在第四轮 Windows evidence 中关闭。
- 是否任何既有 failure contract 被放宽？没有。§13.8 remote closure matrix 保持或强化了原有 failure/stop 语义。

**Verdict: `PASS`** — 零 accepted 行为被重开或削弱。

## Findings Ledger

| # | Severity | Status | Description |
| --- | --- | --- | --- |
| — | — | — | 本轮无 material finding、blocker、needs-evidence 或 design contradiction |

### Observation OBS-DS-01 (LOW / non-blocking)

**Subject**: 现有 `snapshot.primary_filename in tuple(descriptor.name for descriptor in descriptors)` 只检查 membership，不检查 exact count = 1。

**Evidence**: `test_upload_filings_from_command.py:1004-1006` 使用 `in` operator。Corrected plan §13.2.1 bullet 5 要求 "exact name 恰好命中一个 descriptor"，§13.5.1 负向用例要求多命中时失败。当前 `in` 对多命中（同一 name 出现两次）仍然通过。

**Practical assessment**: 在正常 storage 实现中，单次 upload 的 pending assets 各自 name 唯一，duplicate name 不会出现。此 observation 是防御性而非可达缺陷。实现时改为 `len([d for d in descriptors if d.name == target]) == 1` 即可完全对齐 plan spec，不改变 target node 之外的任何代码。

**Disposition**: 由 Controller 裁决是否要求在 corrected plan 中显式化此 count 约束。当前 plan 的 spec 已通过 negative case 明确了 exact-one 语义，implementation agent 应能从 negative case 推导出需要 count check。若 Controller 认为此 spec→implementation 映射足够明确，无需 plan 修改。

## Open Questions

`0`。primary owner、raw-source publication 证明、exact-node allowlist、validation matrix、remote closure gate 与 security/deferred boundary 均已收敛。

## Residual Risk and Owner/Destination

1. **非 Windows 无法证明 real smoke**: 既有风险。本地 `skip` 只记录平台事实；最终 closure evidence 唯一 destination 是 §13.8 的 fresh R11/R12 rerun。
2. **Optional `sha256` 空值路径不可达于正常 storage**: 当前 `_build_stored_file_entry()` 必然填入 sha256。如果 storage 实现未来变化使 sha256 变为 None/NULL，该 test 会在 raw source publication assertion 处 fail closed — 这是正确行为。不需要 pre-emptive mock。
3. **`snapshot.primary_filename` 恰好命中一个 descriptor 的 Fins contract 保障**: `SourceSnapshotProtocol.primary_filename` 的 contract 承诺"精确命中文件描述符"。如果 Fins storage 实现违反此 contract，test 会 fail — 这是 contract 消费者的正确行为。

## Plan SHA / Artifact SHA / Lines

| Item | SHA-256 | Lines |
| --- | --- | --- |
| Corrected plan | `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` | `1124` |
| Codex artifact | `28aaa225122c17dc9083d6229556191a66734045e5bf865b71e38ddaec64dbdb` | `134` |
| Controller validation | `bffa43c3fd3a984ac9ea57c7de805fc387759fd9c865c2c1a190e921da4548a1` | — |
| Evidence adjudication | `0193c1a03dd8f9c5bd7d78465c9d6d4e4aae4d661a373c7eccdc6c8f7c4d3ddb` | — |

## Fixed Next Gate

AgentMiMo 与 AgentDS 双路 plan review 均完成后，由 Controller 裁决。若双路均 PASS 且无 material finding，可进入 plan correction acceptance（accepted corrected-plan commit），随后授权 one-test implementation gate。

## Validation

- Corrected plan SHA-256: `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2` = spec target ✓
- Corrected plan lines: `1124` = spec target ✓
- Old-error wording scan: `0` hits ✓
- Hardcoded Docling expected primary scan: `0` prescriptive hits ✓
- Raw meta/private path scan: `0` prescriptive hits ✓
- Product/test/workflow/design hashes: match Codex lock ✓
- Control doc hash delta: Controller normal status update, not in plan correction scope ✓
- Controller evidence/validation artifacts: not overwritten ✓
- Staged tree: empty ✓
- `git diff --check`: pass ✓
