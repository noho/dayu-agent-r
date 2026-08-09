# PR190 F15/F16 Post-Scan Final Adversarial Re-Review（DeepSeek 独立）

## Gate / scope

- Gate: post-scan final adversarial re-review gate。Controller 裁决 review-fix 已完成 MiMo 001-P2/002-P3 修复后，commit/PR 前最后一道独立审查。
- Branch / base: `codex/interactive-oracle` / `580b1427`（merge-base `113ea34d4`）。
- 本复读只审查、写 artifact，禁止编辑、commit、push 或 PR 操作。
- 上一份 DS final re-review（`pr-190-f15-f16-final-rereview-ds-20260807.md`，PASS）在 scan 时序上证据失效：当时未覆盖 `write_final_publication_scan_report` 的 final completion/index descriptor coverage、secret-scan 唯一自排除、stale report 拒绝、scan-to-open race 等关键路径；本轮从零独立出发，不依赖该份过期 PASS。

## Binding artifacts（全部完整读取）

- `AGENTS.md`
- `docs/gateflow/pr-190-f15-f16-plan-acceptance-20260807.md`（plan）
- `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`（implementation）
- `docs/gateflow/pr-190-f15-f16-implementation-review-adjudication-20260807.md`（Controller adjudication）
- `docs/gateflow/pr-190-f15-f16-review-fixes-20260807.md`（review-fix，含 MiMo 001-P2/002-P3 修复与 Controller 补充）
- `docs/reviews/pr-190-f15-f16-implementation-review-ds-20260807.md`（初始 DS review，背景参考）
- `docs/reviews/pr-190-f15-f16-implementation-review-mimo-20260807.md`（初始 MiMo review，背景参考）
- `docs/reviews/pr-190-f15-f16-final-rereview-mimo-20260807.md`（MiMo final re-review，含 001-P2/002-P3 finding）

## 审查范围

- Tracked diff: 11 files（`dayu/host/compact_material.py` 为首）+ `utils/cli_ci_run_observation.py`（new）+ `tests/cli/test_cli_ci_run_observation.py`（new）。
- 两个 ignored temporary harness（完整阅读 3077 + 1447 行）：
  - `workspace/tmp/prompt_observe_calibration.py`
  - `workspace/tmp/f14_real_cli_observation.py`
- Focused tests: 7 文件 454 passed。
- 禁改面审计：`dayu/host/durable/run_transition.py`、`dayu/host/compaction.py`（validator）、F14 `compacted_source_refs` 实现、oracle/scenario files、prompts、Engine。

## Pre-review baseline verification

| 检查项 | 结果 |
|---|---|
| `git diff --check` | PASS |
| `run_transition.py` diff | **0 lines** |
| `compaction.py` validator diff | **0 lines** |
| F14 `compacted_source_refs` 实现 diff | **0 lines** |
| oracle/scenario files diff | **0 lines** |
| prompts diff | **0 lines** |
| Engine diff | **0 lines** |
| `CancelMode` enum diff | **0 lines** |
| Tracked helper SHA-256 | `239bfd1f762fa44fd4e0e2131fe577f64cc2c7f240bcd2d00f2b46da2cc06872` ✅（与 review-fix artifact 一致） |
| Prompt harness SHA-256 | `15c6e2dbcc081b20c63197aba03544d00042ecf1718ab0e44214b09a5dea5e60` ✅ |
| F14 harness SHA-256 | `dfc3d61853e0c2bf5b7b6421ae57bd1440ad09d33446c72e5c1e28941bb1535e` ✅ |

## 测试与类型检查

| Suite | Result |
|---|---|
| 全量 affected tests（7 文件） | **454 passed** in 4.46s |
| pyright `dayu/ tests/ utils/` | **0 errors, 0 warnings** |
| pyright ignored harness（2 文件） | **0 errors, 0 warnings** |
| `py_compile` ignored harness（2 文件） | PASS（review-fix gate 已验证） |
| `git diff --check` | PASS |

---

## 专题一：Final Publication Helper 逐行反例验证

本专题是本次 re-review 的核心增量——上一份 DS PASS 未覆盖 `write_final_publication_scan_report` 完整 contract。

### 1.1 入口边界——report name、traversal、root symlink、resolution

**入口**: `write_final_publication_scan_report()` (`cli_ci_run_observation.py:843-855`)

**逐行验证**:

| 行号 | 检查 | 反例 | 结果 |
|---|---|---|---|
| 847-848 | `report_path.name != "secret-scan.json"` | `Path("public/other.json")` → `ValueError` | ✅ fail closed |
| 849-850 | `".." in report_path.parts` | `Path("public/../secret-scan.json")` → `ValueError("path traversal")` | ✅ lexical traversal 拒绝 |
| 851-852 | `evidence_root.is_symlink()` | symlink root → `RunObservationError` | ✅ root 不得为 symlink |
| 853 | `evidence_root.resolve(strict=True)` | 不存在或 broken → `FileNotFoundError`/`OSError` | ✅ strict resolution |
| 854-855 | `not root.is_dir()` | regular file root → `ValueError` | ✅ 必须为目录 |

### 1.2 双层 resolved containment

**入口**: `write_final_publication_scan_report()` (`cli_ci_run_observation.py:856-867`)

**证据链**:

1. **第一层（line 856-860）**: `absolute_report.relative_to(root)` — 对 absolute path 做 lexical containment。若 report 在 root 外（如 `/tmp/outside/secret-scan.json` 相对 `/tmp/evidence`），`relative_to` 抛出 `ValueError` → 转换为 `ValueError("report_path must be inside evidence_root")`。
2. **第二层（line 861-867）**: `resolved_report = report_path.resolve(strict=False)` 后再 `resolved_report.relative_to(root)` — 处理 symlink 绕过。若 report_path 是 `evidence/public/link/../secret-scan.json` 且 `link` 指向 root 外，resolve 后路径逃逸 → `ValueError`。
3. 测试 `test_final_publication_scan_rejects_traversal_and_outside_report` 覆盖 outside target 与 `..` traversal（`:858-901`）。

**裁决**: **PASS** — 双层 containment：lexical + resolved，不可绕过。

### 1.3 report ancestor symlink 逐组件检查

**入口**: `write_final_publication_scan_report()` (`cli_ci_run_observation.py:868-873`)

**证据链**:

1. 从 root 出发，沿 `relative_report.parts[:-1]`（report 的所有中间目录组件）逐级构造 `path_cursor`。
2. 每级调用 `path_cursor.is_symlink()` — 对 broken symlink 同样返回 `True`。
3. 任一 ancestor 为 symlink → `RunObservationError("report_path ancestor symlink is forbidden")`。
4. 测试 `test_final_publication_scan_rejects_traversal_and_outside_report` 构造 `linked-report-directory → actual-report-directory` symlink ancestor，report path 为 `linked-report-directory/secret-scan.json` → `RunObservationError(match="ancestor symlink")`（`:895-900`）。

**裁决**: **PASS** — 逐组件 ancestor symlink 检查，broken symlink 同样拒绝。

### 1.4 report parent 存在性 + 第一次存在性检查

**入口**: `write_final_publication_scan_report()` (`cli_ci_run_observation.py:874-879`)

**证据链**:

1. Line 874-875: `report_parent.is_dir()` — 若 parent 不存在或不是目录 → `RunObservationError`。
2. Line 876-879: `absolute_report.exists() or absolute_report.is_symlink()` — **第一次**存在性检查。既存 regular file、directory、broken symlink、valid symlink 全部拒绝 → `RunObservationError("must not already exist")`。
3. 测试 `test_final_publication_scan_rejects_existing_stale_report` 构造 stale `secret-scan.json` → 被拒绝且 stale 内容原样保留（`:828-856`）。

**裁决**: **PASS** — stale report（regular/dir/broken/valid symlink）全部 fail closed，不覆盖。

### 1.5 candidate 枚举——special/non-dir 候选不遗漏

**入口**: `write_final_publication_scan_report()` (`cli_ci_run_observation.py:881-885`)

**证据链**:

1. `root.rglob("*")` — 递归枚举，sorted deterministic。
2. Filter: `candidate.is_symlink() or not candidate.is_dir()`：
   - Regular file: `not is_dir()` = True → **included**
   - Symlink to file: `is_symlink()` = True → **included**
   - Symlink to dir: `is_symlink()` = True → **included**（后续 path hygiene 拒绝）
   - Broken symlink: `is_symlink()` = True → **included**（后续 path hygiene 拒绝）
   - Directory: `not is_dir()` = False, `is_symlink()` = False → excluded
   - FIFO/socket/device: `not is_dir()` = True → included → `scan_public_evidence_files` 中 `is_file()` = False → `regular_file_missing` validation error
3. `secret-scan.json` 报告在此时**尚不存在**（line 876-879 已确认），因此不在 candidate 中——这是**唯一合法的自排除**。
4. `run-completion.json`、`execution-index-f15-f16.json` 等 final metadata **已落盘**，必然进入 candidates 并被 scan 覆盖。
5. 测试 `test_final_publication_scan_covers_final_metadata_and_only_excludes_report` 断言 descriptors 包含 `execution-index-f15-f16.json`、`run-completion.json`、`scenario-001/stdout.txt`，**不含** `public/secret-scan.json`（`:819-825`）。
6. 测试 `test_final_publication_scan_enumerates_secret_database_and_symlink_candidates` 断言 actual secret、raw DB file、raw DB text path、symlink 全部进入 scan（`:907-971`）。

**裁决**: **PASS** — 非 dir 候选全覆盖，secret/raw sqlite/db/text-path/leaf+ancestor symlink 进入 scanner 且 fail closed，missing/oversize invalid，唯一自排除是尚不存在的 report。

### 1.6 第二次存在性检查 + scan-to-open race triple guard

**入口**: `write_final_publication_scan_report()` (`cli_ci_run_observation.py:886-908`)

**证据链**:

1. **第一次检查**（line 876-879）: 进入函数后的第一道存在性门禁。
2. **candidate 枚举**（line 881-885）: 在两次检查之间；report 尚不存在所以不在 candidates 中。
3. **第二次检查**（line 886-889）: `absolute_report.exists() or absolute_report.is_symlink()` — candidate 枚举后再次检查，防枚举期间被其他进程创建。
4. **`scan_public_evidence_files`**（line 890-895）: report 不在 candidates 中，不被扫描。
5. **`open("x")` 独占创建**（line 903-908）: 若前两次检查后被其他进程创建 → `FileExistsError` → `RunObservationError("appeared before publication")`。

**Race 矩阵**（外部进程在以下窗口创建 report）:

| 窗口 | 检测点 | 结果 |
|---|---|---|
| 第一次检查前 | 第一次检查（line 876） | `must not already exist` |
| 第一次检查后 → 第二次检查前 | 第二次检查（line 886） | `must not already exist` |
| 第二次检查后 → scan 前 | `open("x")`（line 903） | `appeared before publication` |
| scan 中 → open 前 | `open("x")`（line 903） | `appeared before publication` |
| open 中（并发） | OS-level `O_EXCL` | `FileExistsError` |

**裁决**: **PASS** — 三重 guard（两次 exists + exclusive create）覆盖任意并发窗口，全部 fail closed。

### 1.7 已有 scanner 反例在 final-tree 中保持（逐项确认）

**入口**: `scan_public_evidence_files()` (`cli_ci_run_observation.py:685-815`)

| 反例 | 代码行号 | 验证 |
|---|---|---|
| outside_evidence_root (lexical) | 733-738 | ✅ `relative_to(root)` 失败 |
| symlink_forbidden (leaf + ancestor) | 740-752 | ✅ 逐组件 `is_symlink()` |
| outside_evidence_root (resolved escape) | 753-758 | ✅ `resolve(strict=False).relative_to(root)` |
| raw_database_file_forbidden (`.sqlite/.sqlite3/.db`) | 760-763 | ✅ suffix check |
| regular_file_missing (非 regular) | 765-768 | ✅ `is_file()` 失败 |
| file_size_limit_exceeded | 771-775 | ✅ `st_size > max_file_bytes` |
| OSError (读取失败) | 778-784 | ✅ typed error diagnostics |
| exact_value secret hit | 795-803 | ✅ `probe.value in text` |
| raw_database_path_forbidden (text regex) | 804-806 | ✅ `_RAW_DATABASE_PATH_PATTERN.search(text)` |

全部反例在 `write_final_publication_scan_report` 的 `scan_public_evidence_files` 调用中复用同一 scanner。测试 `test_final_publication_scan_enumerates_secret_database_and_symlink_candidates` 证明 final-tree 枚举**不遗漏**这些候选。

**裁决**: **PASS** — 全部反例在 final-tree 路径下保持 fail closed。

---

## 专题二：两个 Harness 的 Metadata → Scan 时序逐行确认

### 2.1 Prompt harness

**入口**: `prompt_observe_calibration.py` `main()` (line 3085-3107)

**执行顺序**（逐行）:

1. Line 3083-3084: `secret_scan_path.parent.mkdir(parents=True, exist_ok=True)` — 仅创建 parent 目录。
2. Line 3085-3102: `_write_json(run_root / "evidence/run-completion.json", ...)` — **final metadata 先落盘**。内容仅含 `"secret_scan": {"record_path": "evidence/public/secret-scan.json"}`，**不含 status/hits/digest**。
3. Line 3103-3107: `run_observation.write_final_publication_scan_report(...)` — **唯一 scan，在 metadata 之后**。

**裁决**: **PASS** — 先 final metadata（`run-completion.json`），再唯一 scan；metadata 仅 `record_path`，不含 scan verdict。

### 2.2 F14 harness

**入口**: `f14_real_cli_observation.py` `main()` (line 1321-1363)

**执行顺序**（逐行）:

1. Line 1309-1320: `_collect_public_evidence` + `_context_compaction_observation` + write context-compaction JSON — collection 阶段。
2. Line 1322-1329: `_aggregate_terminal_evidence` + `_aggregate_process_outcomes` + `_aggregate_dependency_gates` + `_top_evidence_status` — **纯数据聚合，不涉及 scan**。
3. Line 1332-1358: `_write_json(run_root / "evidence/execution-index-f15-f16.json", ...)` — **final index 先落盘**。内容仅含 `"secret_scan": {"record_path": "evidence/public/secret-scan.json"}`，**不含 status/hits/digest**。
4. Line 1359-1363: `run_observation.write_final_publication_scan_report(...)` — **唯一 scan，在 index 之后**。

**F14 `evidence_status` 不包含 scan verdict**:
- `_top_evidence_status()` (line 1096-1147) 仅检查 `run_terminal_evidence.status`、`context_compaction.status`、`public_evidence.tool_trace_exit_code`。
- 不读取 scan report、不调用 `scan_public_evidence_files`、不引用 `PublicEvidenceScanResult`。
- `evidence_status` 语义为 "Run/context/tool collection integrity"，不是 "publication scan verdict"。

**裁决**: **PASS** — 先 final index，再唯一 scan；metadata 仅 `record_path`；`evidence_status` 不含 scan verdict。

---

## 专题三：F15 Canonical Pair / Durable Freeze-Dispatch

### 3.1 唯一 canonical projection

**入口**: `_previous_compacted_view_pair_from_replacement()` (`compact_material.py:2603-2693`)

**证据链**:

1. Line 2618: `projection = _canonical_previous_replacement_projection(replacement)` — **唯一调用**，规范化全部五区文本叶子。
2. `_canonical_previous_replacement_projection()` (line 2696-2744) 对每个叶子调用 `_canonical_material_text()` → `normalized_material_text()` — 每个叶子恰好规范化一次。
3. Packed blocks (line 2619-2682) 和 readable view (line 2684-2688) 消费同一 `projection` 对象。
4. `_previous_block_from_canonical_text()` (line 2793-2836) 直接传 `_CanonicalMaterialText` 给 `_run_input_material_block_from_prepared_text`，**不**再次调用 normalizer。
5. `_canonical_answer_anchor_block_text()` (line 2778-2790) 先构造 typed `ReadableAnswerAnchorVNext`，再用 `previous_answer_anchor_block_text()` 正向渲染，**不从 packed string 逆向解析**。

### 3.2 accepted tool evidence 隔离

**入口**: `_run_input_material_block_from_prepared_text()` (`compact_material.py:917-989`)

**证据链**:

1. Line 963-964: `isinstance(text, (_CanonicalMaterialText, _AcceptedToolEvidenceText))` — typed union 门禁。
2. `_AcceptedToolEvidenceText` (line 893-914) 校验 `text == render_accepted_tool_evidence_for_llm(accepted_tool_evidence)` — shared renderer exact 校验。
3. Line 965-969: `_AcceptedToolEvidenceText` 要求 `accepted_tool_evidence is not None`；`_CanonicalMaterialText` 禁止携带 `accepted_tool_evidence`。
4. 两条路径无交叉：accepted evidence 不经 `normalized_material_text()`，canonical text 不得伪装为 accepted evidence。

### 3.3 durable reopen byte-exact

**入口**: `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` (`test_compact_material.py:2110-2143`)

**证据链**:

1. Writable store 构造 pair → 关闭。
2. 物理只读 `open_host_durable_read_store` reopen → 重新从 durable event/artifact 构造 pair。
3. `reopened_readable.to_json() == readable.to_json()` — 完整 JSON exact 相等。
4. 每个 block `(text, size_units, content_digest)` byte-exact 相等。

### 3.4 ordinary freeze/dispatch

**入口**: `test_durable_reopen_previous_pair_freezes_and_dispatches_next_ordinary_run` (`test_dispatch_scheduler.py:9031-9098`)

**证据链**:

1. 含格式矩阵的 accepted pair durable persist → 下一 ordinary `ACCEPTED` Run → 新 writable store/scheduler 完整 promotion/freeze/dispatch 链路。
2. `frozen_source.candidate.messages == accepted_request.messages` exact 相等。
3. `frozen_source.candidate.run_id == seeded.run_id`、`session_id` 同源。
4. Run 真实收口 `SUCCEEDED`。

**裁决**: **PASS** — canonical single projection 正确，accepted evidence 隔离，durable reopen byte-exact，ordinary freeze/dispatch 完整。

---

## 专题四：F14 Frontier / F16 Terminal Facts / Safe-Stop / Formal Unadjudicated

### 4.1 F14 frontier zero drift

全域审计确认：
- `compacted_source_refs` 实现 diff: 0 lines
- `validate_previous_compacted_view_pair()` diff: 0 lines
- `run_transition.py` diff: 0 lines
- oracle/scenario files diff: 0 lines
- prompts diff: 0 lines
- Engine diff: 0 lines

### 4.2 F16 terminal facts

已在上一份 DS final re-review 中逐项验证并通过，本轮重新确认：
- Canonical per-Run terminal + reason 与 process exit 分离 ✓
- Reason 只取 `reason_json.reason`，event-specific shape fail closed ✓
- Evidence 三态精确区分（complete/insufficient/invalid）✓
- Summary 与逐 Run 四类分布 exact 对账 ✓
- Session identity 强一致 + lifecycle owner 复用 ✓
- Duplicate terminal 拒绝 ✓
- Malformed JSON 拒绝 ✓
- Cancel/lost governance extra validation ✓

### 4.3 safe-stop

- `classify_remaining_actions_for_safe_stop()`: 只一次 EOT，全部 dependent not_run ✓
- 测试 `test_safe_stop_classifies_dependents_and_sends_one_cleanup_eot` ✓
- Process exit 不进入 dependency gate ✓

### 4.4 formal unadjudicated

- F14 harness `execution-index-f15-f16.json` 固定 `"oracle_status": "unadjudicated"` ✓
- 无 `accepted`/`ready`/`PASS`/`scenario_success` 字段 ✓

**裁决**: **PASS** — F14 frontier zero drift，F16 全部 contract 闭环，safe-stop 正确，unadjudicated 精确。

---

## 旧 Finding 关闭状态确认

| Finding | 修复前状态 | 本次独立验证 |
|---|---|---|
| MiMo 001-P2 — prompt harness 缺失 final scan | FIXED（review-fix gate） | `write_final_publication_scan_report` 在 `run-completion.json` 之后调用，completion 含 descriptors ✅ |
| MiMo 002-P3 — F14 index 未被 scan 覆盖 | FIXED（review-fix gate） | index 先写再 scan，`evidence_status` 不含 scan verdict ✅ |
| MiMo 001 — segment evidence invalid 崩溃 | FIXED | typed inspection + fallback → INVALID ✅ |
| MiMo 002 — index 字段不完整 | FIXED | process/terminal/dependency/compaction/secret-scan facts ✅ |
| MiMo 003 — INDEPENDENT 枚举 | REJECTED-WITH-REASON | role 保留 + pure projector ✅ |
| DS 016 — block 构造重复 | FIXED | typed wrappers + union ✅ |
| DS 017 — whitespace test 缺口 | FIXED | typed accept + strict read ✅ |
| DS 018 — 隐式 ordinal +1 | FIXED | typed pure helper ✅ |
| C01 — PTY 永久等待 | FIXED | safe-stop + 单 EOT + 10s cleanup ✅ |
| C02 — valid failure 误标 complete | FIXED | evidence 三态 ✅ |
| C03 — session/projector 不同源 | FIXED | session identity + lifecycle owner ✅ |
| C04 — adjudication 状态值 | FIXED | `"unadjudicated"` exact ✅ |
| C05 — artifact / SHA 不一致 | FIXED | SHA-256 一致 ✅ |
| A — 普通路径当 secret | FIXED | exact probes 仅含 actual secret ✅ |
| B — diagnostic 字符串推断 | FIXED | null，不反推 ✅ |
| C — summary 仅校验总数 | FIXED | 逐类 exact 对账 ✅ |
| D — raw DB 硬编码 false | FIXED | path hygiene 真实文件系统扫描 ✅ |

**全部 18 项旧 finding 已关闭。**

---

## Open Questions

无。

## Residual Risk

1. **Fresh production real rerun 未执行**: Accepted plan 要求 clean committed target 上执行真实 provider/AAPL rerun。当前未 commit，因此 rerun 未启动。这是 plan 明确分配给 subsequent post-commit validation gate 的工作。
2. **Harness 端到端行为**: 两个 ignored harness 的 `py_compile` + pyright 通过，但依赖实际 CLI CI workspace 的端到端行为（PTY orchestration、segment chain、evidence 写入、index 生成）由 deterministic tests 间接覆盖，非实际 workspace 运行。
3. **Formal financial/business Oracle** 保持 `unadjudicated`，owner 不在本 review gate。

---

## 最终裁决

**PASS** — 无新增 finding（P0-P3 均为零）。

本次 post-scan re-review 的核心增量——`write_final_publication_scan_report` 的逐行反例验证——得出以下结论：

- **Final completion/index descriptor coverage**: 两个 harness 均先落盘 final metadata（`run-completion.json` / `execution-index-f15-f16.json`），再执行唯一 scan。Metadata 的 descriptors 覆盖 completion/index + 全部 evidence 文件。✅
- **Secret-scan 唯一自排除**: report 在 candidate 枚举时不存在（第一次存在性检查保证），因而不在 candidates 中——这是唯一合法的自排除路径。✅
- **Stale report 拒绝**: regular file、directory、broken symlink、valid symlink 全部由第一次存在性检查（`exists() or is_symlink()`）拒绝。✅
- **Ancestor symlink**: 逐组件 `is_symlink()` 检查 report 所有中间目录组件。✅
- **Lexical traversal + resolved escape**: `".." in parts` 拒绝显式 traversal；双层 `relative_to(root)`（absolute + resolved）拒绝绕过。✅
- **Scan-to-open race**: 三重 guard（两次存在性检查 + `open("x")` 独占创建）覆盖任意并发窗口，全部 fail closed。✅
- **Special/non-dir 候选不遗漏**: `rglob("*")` + `is_symlink() or not is_dir()` 覆盖全部非目录候选（regular、symlink、broken symlink、FIFO/socket/device）。✅
- **Secret/raw DB/path/symlink/missing/oversize fail closed**: 全部反例在 final-tree 路径下复用同一 scanner 且行为不变。✅
- **Metadata 仅 `record_path`**: 两个 harness 的 final metadata 中 `secret_scan` 字段仅含 `record_path`，不含 status/hits/digest。✅
- **F14 collection status 不含 scan verdict**: `_top_evidence_status()` 仅检查 Run/context/tool collection integrity，不引用 scan。✅

F15 canonical single projection、durable freeze-dispatch、F14 frontier、F16 terminal facts/safe-stop/formal unadjudicated 全部 zero drift。

454 tests passed，pyright 0 errors，`git diff --check` clean，SHA-256 digests 一致。全部 18 项旧 finding 已关闭。
