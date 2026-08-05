# PR 190 F11/F12 S4 Harness Fix Re-Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `321893e423beeb20acf2768c03b2be3477c92903`
- Output file: `docs/reviews/pr-190-f11-f12-s4-harness-mimo-rereview-20260805.md`
- Included scope:
  - `utils/smoke_host_public_conversation_memory_scenarios.py`（harness diff）
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`（test diff）
  - `docs/reviews/pr-190-f11-f12-s4-harness-review-adjudication-20260805.md`（裁决）
  - `docs/reviews/pr-190-f11-f12-s4-harness-mimo-review-20260805.md`（前次 MiMo review）
  - `docs/reviews/pr-190-f11-f12-s4-harness-ds-review-20260805.md`（DS review）
  - `docs/reviews/pr-190-f11-f12-s4-harness-fix-20260805.md`（fix artifact）
  - `docs/reviews/code-review-20260805-210138.md`（首次 DS review）
- Excluded scope: 生产 contract 修改、oracle/scenario、external evidence root、未受本 slice 影响的仓库代码
- Parallel review coverage: 3 个 Explore subagent 分别验证 S4-REVIEW-001 闭合、DS-002/DS-003 闭合、无生产变更

---

## Gate Acceptance Criteria 逐项验证

裁决文档 `pr-190-f11-f12-s4-harness-review-adjudication-20260805.md` 定义了 5 项 gate acceptance criteria。以下逐项独立验证：

### Criterion 1: real-provider suites 缺少 `--evidence-output-dir` 时 fail closed；pressure-mode 与 evidence-dir 分别测试

**PASS**

`parse_args`（`smoke_host_public_conversation_memory_scenarios.py:2473-2491`）包含三个独立 `parser.error` 守卫：

1. **行 2473-2482**：pressure-mode 检查。`SuiteMode` 在 pressure-required 集合中且 `pressure_mode is PressureMode.OFF` 时 fail。
2. **行 2483-2487**：禁止 fake compact suites 使用 `--evidence-output-dir`。
3. **行 2488-2491**：evidence-output-dir fail-closed。`evidence_output_text is None and pressure_suite in _REAL_PROVIDER_SUITES` 时 fail，可操作错误消息为 `f"--suite {pressure_suite.value} requires --evidence-output-dir"`。

三个守卫顺序求解，互不依赖。`_REAL_PROVIDER_SUITES`（行 679-688）包含全部 6 个 real-provider suite。

测试覆盖：
- `test_real_provider_cli_requires_pressure_mode_independently`（行 397-423）：parametrize `_REAL_PRESSURE_SUITE_NAMES`（5 个 suite），预置 `--evidence-output-dir`，不传 `--pressure-mode`，断言 `SystemExit` 且 stderr 包含 `"requires --pressure-mode auto"`。**evidence-dir 约束已预满足，唯一触发源为 pressure-mode**。
- `test_real_provider_cli_requires_evidence_output_dir_independently`（行 426-451）：parametrize `_REAL_PROVIDER_SUITE_NAMES`（全部 6 个 suite），对非 reconnect 传 `--pressure-mode auto`，不传 `--evidence-output-dir`，断言 `SystemExit` 且 stderr 包含 `"requires --evidence-output-dir"`。**pressure-mode 约束已预满足或不适用，唯一触发源为 evidence-dir**。

两个测试的 SystemExit 来源被显式断言，不存在由错误分支偶然通过的风险。

### Criterion 2: fresh path、digest self-exclusion/content digest、public/canonical equal 与 mismatch、failure export 关键边界有 deterministic tests

**PASS**

| 测试 | 覆盖的 contract | 断言精度 |
|---|---|---|
| `test_s4_evidence_fresh_file_and_directory_are_not_overwritten`（行 454-488） | `_write_fresh_json` FileExistsError；`_export_s4_invocation_evidence` 目录级 fresh-write guard | 用 `read_bytes()` 断言原内容不变；目录 `iterdir()` 断言为空 |
| `test_s4_evidence_digest_excludes_itself_and_hashes_file_contents`（行 491-528） | `_evidence_digest_json` 自排除（3 个文件 → `file_count==2`）、SHA-256 与 `hashlib.sha256(content).hexdigest()` 逐字节一致、`size_bytes` 与 `len(content)` 一致 | 覆盖嵌套目录、二进制内容（`b"beta\x00gamma"`）、stale `digest.json` |
| `test_s4_public_canonical_equality_reports_equal_and_mismatch`（行 531-571） | `_public_canonical_equality_json` equal 路径（`finding_count==0`）与 mismatch 路径（`finding_count==1, reason=="public-canonical-binding-mismatch"`） | 使用 `dataclasses.replace()` 修改 `proposal_manifest_digest` 构造 mismatch；用 `build_context_compaction_attempt_rejected_payload` 构造真实 canonical payload |
| `test_s4_failure_export_does_not_mask_active_business_exception`（行 574-605） | `_handle_s4_evidence_export_error` 两个分支：有 active exception 时保留原异常、无 active exception 时抛出 export error | 用 `raised.value is business_error`（identity 断言，非仅类型）验证异常未被替换；stderr 断言精确格式 |

所有测试均调用真实生产函数，无 mock/fake/stub。fixture `_s4_rejected_terminal_fixture`（行 1577-1637）使用 `CompactorProposalManifestReference`、`build_context_compaction_attempt_rejected_payload`、`ToolTraceCompactorResponseSummary` 等真实 Host 类型构造同源事实。

### Criterion 3: 仓库内 gate/review artifact 的 base SHA 精确

**PASS**

| artifact | base SHA | 状态 |
|---|---|---|
| `code-review-20260805-210138.md` | `321893e423beeb20acf2768c03b2be3477c92903`（行 7） | 已修正，含 Correction Note（行 48） |
| `pr-190-f11-f12-s4-harness-mimo-review-20260805.md` | `321893e423beeb20acf2768c03b2be3477c92903`（行 7） | 已修正，含 Correction Note（行 258） |
| `pr-190-f11-f12-s4-harness-ds-review-20260805.md` | `321893e423beeb20acf2768c03b2be3477c92903`（行 7） | 已修正，含 Artifact Correction Note（行 308） |
| `pr-190-f11-f12-s4-harness-review-adjudication-20260805.md` | `321893e423beeb20acf2768c03b2be3477c92903`（行 7） | 正确 |
| `pr-190-f11-f12-s4-harness-fix-20260805.md` | `321893e423beeb20acf2768c03b2be3477c92903`（行 8） | 正确 |
| `pr-190-f11-f12-s4-harness-mimo-rereview-20260805.md` | `321893e423beeb20acf2768c03b2be3477c92903`（行 7） | 本 artifact |

旧 external bundle `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-HeHeLm/` 标记为 `immutable / superseded partial evidence`，未回写。`code-review-20260805-210138.md` 行 36/48 明确声明此状态。

### Criterion 4: S4-001 仍明确归 production owner slice，不得在 harness/renderer/fixture 补偿

**PASS**

- fix artifact（行 67）：`S4-001` 状态为 `未修复`，`继续归 production fallback current-input material construction/digest owner 的独立 work unit`。
- harness 代码中无 normalization、digest fallback 或 fixture 补偿。`_write_fresh_json`、`_evidence_digest_json`、`_public_canonical_equality_json` 均为纯 evidence 导出函数，不触及 `compact_pipeline.py` / `context_fallback.py` / `compact_material.py` / `run_input.py` 的生产 contract。
- 测试 fixture 使用真实 Host 类型构造，不伪造 digest 或 material block。

### Criterion 5: 新 evidence root 重跑时再验证 capture 数量

**PASS（条件性）**

- fix artifact（行 66/74）：`DS-001` 状态为 `证据失效`，不作为本 gate 代码 finding，不加临时 debug；待 `S4-001` 修复后在全新 root 重跑。
- 本 re-review 确认 harness 中无临时 debug 噪声。`_RealCompactorCaptureRunner` 仅做 capture append + real runner 调用，无额外 print/log。
- 此 criterion 的完全闭合依赖 `S4-001` 修复后的独立取证 run，不在本 gate 范围内。

---

## 生产变更 / 伪冒 / 补偿 / 异常遮蔽 检查

### 无生产代码变更

`git diff --name-only` 确认仅 2 个文件被修改：
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`

`dayu/` 目录无任何变更。`docs/reviews/` 下的 5 个文件均为新增 untracked 文件，未修改既有文件。external evidence root 未被触及。

### 无 fake provider 伪冒

`_RealCompactorCaptureRunner`（行 1021-1075）是 capture-only wrapper：调用 `self._original_runner(request, timeout_seconds=timeout_seconds)` 并在调用前后追加 capture。不替换 request、不修改 outcome、不伪造 response。`_capturing_real_compactor_requests`（行 2136-2162）在 `finally` 中恢复原始 runner。

### 无下游补偿 / 兼容代码

- 无 `__all__` re-export、兼容 wrapper 或 facade。
- `_handle_s4_evidence_export_error` 不是补偿——它是在 `finally` 块中保持业务异常优先的正确模式，由独立测试覆盖两个分支。
- `_repeat_to_budget_tokens` 使用 Host 统一 estimator（`estimate_budget_text_tokens`），不自行实现 token 估算。

### 无异常遮蔽

三处 `except` 块均正确：
1. `_RealCompactorCaptureRunner.__call__` 的 `except Exception`：记录 `error_type` 后 `raise`（无条件重新抛出）。
2. `_capturing_real_compactor_requests` 的 `except AttributeError`：包装为 `RuntimeError` 并 `from exc` 链式传递，提供 fail-fast 诊断。
3. `run_smoke` finally 的 `except Exception as export_error`：委托给 `_handle_s4_evidence_export_error`，有 active exception 时仅打印 stderr，无 active exception 时原样抛出。由 `test_s4_failure_export_does_not_mask_active_business_exception` 独立验证。

---

## 测试独立运行验证

- `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`：**36 passed, 3 warnings**（warnings 均来自 `edgar` 已弃用模块）
- `pyright tests/... utils/...`：**0 errors, 0 warnings, 0 informations**

---

## Findings

未发现实质性问题。

所有已接受的 gate acceptance criteria 均经独立验证闭合。harness 代码正确实现了 CLI fail-closed、evidence fresh-write、digest self-exclusion、public/canonical equality、failure export 不遮蔽原异常。测试使用真实生产合约，无 mock/fake/兼容代码。无生产代码变更。

## Open Questions

无。

## Residual Risk

1. **S4-001 生产 blocker 未修复**：`fallback current-input material construction/digest` 的 semantic ownership 问题继续归 production owner slice。harness 不补偿。
2. **DS-001 capture 数量待验证**：`10-deepseek-exhausted-fallback-blocker` 的 `compactor-attempts.json` 为空数组，root cause 待 `S4-001` 修复后从全新 evidence root 重跑验证。不加临时 debug。
3. **MiMo fallback no-downgrade 子项未实测**：产品 blocker 后停止取证，诚实 `stopped-after-product-bug` gap。
4. **`_repeat_to_tokens` 二分搜索性能**：adjudication 已不采纳为代码 finding（DS-004），本 re-review 确认未修改此实现。

## Closeout

S4 harness fix 的 5 项 gate acceptance criteria 均经独立代码走读与测试运行验证闭合。无生产变更、无伪冒、无下游补偿、无异常遮蔽。本 gate 的 harness/test 层面工作完成，可提交；随后进入 `S4-001` production owner slice。

---

*AgentMiMo re-review — 2026-08-05T21:30:41*
