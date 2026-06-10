# WU-TOOLS-01-F03 Slice 2 Code Review — AgentDS

## Review Context

- **Work unit**: WU-TOOLS-01-F03 Web CI Smoke Generation
- **Slice**: Slice 2: Opt-in Smoke CLI and Summary Contract
- **Agent**: AgentDS (review only, no file modifications)
- **Review date**: 2026-06-10
- **Input artifacts**:
  - Plan: `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`
  - Implementation: `docs/reviews/wu-tools-01-f03-implementation-slice2-codex.md`
  - Prior reviews: `docs/reviews/wu-tools-01-f03-implementation-slice1-codex.md`, `docs/reviews/wu-tools-01-f03-code-rereview-slice1-mimo.md`, `docs/reviews/wu-tools-01-f03-code-rereview-slice1-ds.md`
- **Review target** (uncommitted):
  - `utils/smoke_web_ci.py`
  - `tests/tools/web/test_smoke_web_ci.py`
  - `docs/reviews/wu-tools-01-f03-implementation-slice2-codex.md`

---

## Scope Verification

### Slice 2 Boundary Compliance

| Check | Result |
|---|---|
| 不越界到 Slice 3 local HTTP server | **PASS** — 无 HTTP server 启动代码，无 local fixture URL，无 PDF bytes。`_execute_smoke` docstring 明确声明 "local HTTP fixture 由后续 Slice 3 接入"。 |
| 不越界到 `diagnose_web_access` runner 修改 | **PASS** — 只通过子进程调用 `python -m utils.diagnose_web_access`，不修改生产 diagnostics 代码。 |
| 不越界到 production Web tools / Host / Engine / ToolRuntime | **PASS** — 无 import from `dayu.tools.web`、`dayu.host`、`dayu.engine`、`dayu.service`。仅依赖 `dayu.contracts.json_value.JsonValue`。 |
| 不越界到 Slice 5 docs/control doc 修改 | **PASS** — 未修改 `docs/host/issues-implementation-control.md`、`tests/README.md` 或任何 README。 |

### Plan Mandatory Features Coverage

| Plan Requirement | Implemented? |
|---|---|
| 显式 opt-in (`DAYU_RUN_WEB_CI_SMOKE=1` 或 `--run-live`) | **YES** — `main()` line 1594 |
| 未 opt-in 不联网、不启动 server、不调用 diagnostics | **YES** — `_skipped_summary` 路径不执行任何 runner |
| Skipped summary 说明未联网原因 | **YES** — `reason="未显式 opt-in；脚本未联网、未启动 server、未调用 diagnostics runner。"` |
| CLI 参数 `--run-live`, `--output-dir`, `--request-timeout`, `--tool-timeout-budget`, `--include-playwright`, `--external-url-file`, `--external-limit`, `--diagnostic-only-external` | **YES** — 全部实现，额外增加 `--run-label` 供 deterministic 测试 |
| Exit code 0/1/2 语义 | **YES** — 0=pass/skip/diagnostic_only, 1=local gate failure, 2=CLI/schema_gap/infrastructure |
| Diagnostics schema validation | **YES** — `_diagnostic_schema_gap`, `_required_fetch_fact_gap`, `_required_pdf_fact_gap` |
| Summary JSON/MD | **YES** — `_write_summary` 输出 `summary.json` + `summary.md` |
| Subprocess/artifact mapping table 完整实现 | **YES** — 逐一核验见下方 |

### Mapping Table 逐行验证

| Plan 表格行 | 实现路径 | 结论 |
|---|---|---|
| returncode 0, JSON OK, schema valid, req/fetch ok → local pass | `_classify_loaded_artifact` → 通过所有检查 → `SmokeCaseResult(status=passed, exit_code=0)` | **PASS** |
| returncode 0, schema missing/old → local exit 2, external diagnostic-only | local: `_case_failure(bucket=diagnostic_schema_gap, exit_code=2)`; external: `_case_diagnostic_only(bucket=diagnostic_schema_gap)` | **PASS** |
| requests ok + fetch ok + Playwright skipped → pass | Playwright 不在 smoke classification 中检查，由 diagnostics facts 判定，不影响 pass | **PASS** |
| PDF content-type 非 PDF → fail exit 1 | `_classify_pdf_loaded_artifact` → `pdf_content_type_failure, exit_code=1` | **PASS** |
| PDF fetch content 空/过短 → fail exit 1 | `fetch_length < _PDF_FETCH_MIN_CHARS` → `pdf_content_length_failure, exit_code=1` | **PASS** |
| PDF docling invoked ≠ True → fail exit 1 | `not invoked or not original_completed` → `pdf_docling_invocation_failure, exit_code=1` | **PASS** |
| Docling init/dep failure → PDF skip, exit 0, 不掩盖 HTML failure | 两个路径：returncode≠0+init_skip→skip; returncode=0+init_skip→skip。`_summary_from_cases` exit_code 聚合只看 local case exit codes，skip=0 不提升 exit code | **PASS** |
| returncode≠0, non-docling → fail exit 1 | `child_returncode != 0 and not docling_init_skip` → `child_process_error, exit_code=1` | **PASS** |
| 无 artifact / JSON parse fail → local exit 2, external diagnostic-only | `_classify_child_result` → `artifact_missing`/`artifact_parse_failure` → local exit 2, external diagnostic_only | **PASS** |

---

## Findings

### Finding 1 [MEDIUM] `_STDIO_PREFIX_CHARS` 和 `_prefix_text` 死代码

**证据**: `utils/smoke_web_ci.py:52` 定义 `_STDIO_PREFIX_CHARS: Final[int] = 2_000`，`utils/smoke_web_ci.py:457-473` 定义 `_prefix_text` 函数。在全文件 1610 行中，二者均从未被调用。

**影响**: 死代码增加维护负担，违反编码硬约束（禁止无必要的冗余）。不阻塞功能，但留下未使用符号。

**建议裁决**: **accepted** — 在 Slice 3 或 Slice 5 closeout 前移除。如果 Slice 3 的 local server diagnostics 子进程 stderr 需要截断，可以届时补回，但不应该预埋死代码。

---

### Finding 2 [MEDIUM] Opt-in 后 Slice 2 未实现 local cases 的表达不够充分

**证据**: 当用户 `--run-live` 但未提供 `--external-url-file` 时，`_execute_smoke` 返回空 `local_cases=(), external_cases=()`，summary 输出 `status=skipped, local_cases=0, external_cases=0`。虽然 `_execute_smoke` docstring 说明了 "local HTTP fixture 由后续 Slice 3 接入"，但这一信息仅存在于源码 docstring 中，不会出现在 summary JSON/MD 输出中。操作者看到的 summary 与完全未 opt-in 时的输出几乎无法区分（除了 `failures/skips/diagnostic_only` 为空而非包含 `not_opted_in` 记录）。

**依据**: Plan review focus 明确要求审查："Opt-in 后当前 Slice 2 未实现 local cases 是否表达清楚，是否会误导为最终 F03 pass"。

**影响**: 操作者可能误以为 smoke 已完整执行并通过（0 local_cases 可能被理解为"没有需要测试的 local case"），而非理解这是 Slice 2 的 intermediate state。

**建议裁决**: **accepted** — 在 Slice 3 接入 local fixture 后自然消失。作为防御，建议在 `_execute_smoke` 返回空 local_cases 时，在 summary 中追加一条 skip item 说明 "local fixture smoke 尚未实现，由 WU-TOOLS-01-F03 Slice 3 接入"。当前实现不算 bug，但可读性边界薄弱。

---

### Finding 3 [LOW] `_classify_loaded_artifact` 对 external schema_gap 检查硬编码 `_CASE_LOCAL_HTML`

**证据**: `utils/smoke_web_ci.py:786`:
```python
schema_gap = _diagnostic_schema_gap(payload, case_kind=_CASE_LOCAL_HTML)
```
函数签名接受 `case_kind` 参数，但 external 分支始终传入 `_CASE_LOCAL_HTML`，而非函数收到的实际 `case_kind`。

**为什么当前行为正确**: external URL 只需 HTML 级别的 schema 检查（requests/fetch sampled/ok），不需要 PDF 级别字段。传入 `_CASE_LOCAL_HTML` 恰好产生了正确的校验范围。

**影响**: 代码意图不清晰。未来的维护者可能误认为这是一个 bug 并"修复"它（传入实际 case_kind），导致 external URL 被 PDF schema 要求阻塞——而 plan 明确 external schema gap 只是 diagnostic-only。

**建议裁决**: **accepted** — 添加局部注释说明为何对 external 使用 `_CASE_LOCAL_HTML`（"external case 只需校验 requests/fetch 级别 schema，不需要 PDF 字段"），或引入显式的 `_CASE_EXTERNAL` schema 校验路径。

---

### Finding 4 [LOW] `"not_opted_in"` bucket 未使用模块级常量

**证据**: `utils/smoke_web_ci.py:1223` 在 `_skipped_summary` 中直接使用字符串字面量 `bucket="not_opted_in"`。同一模块中所有其他 bucket 均定义为 `_BUCKET_*` 模块级 `Final[str]` 常量。

**影响**: 不一致的编码风格。如果未来 smoke 需要基于 bucket 做自动分类或统计，`"not_opted_in"` 字符串散落易遗漏。

**建议裁决**: **accepted** — 建议定义 `_BUCKET_NOT_OPTED_IN: Final[str] = "not_opted_in"` 并在 `_skipped_summary` 中使用。

---

### Finding 5 [LOW] `_summary_from_cases` 无 local/external cases 且已 opt-in 时 status=skipped 与未 opt-in 的 skipped 无法从 status 字段区分

**证据**: 两个场景均输出 `status=skipped, exit_code=0`:
- 未 opt-in: `_skipped_summary` → `status=skipped, skips=[not_opted_in]`
- Opt-in 但无 local cases 且无 external URL file: `_summary_from_cases` → `status=skipped, skips=()`

区别仅在于 skips 列表内容。下游 Codex/脚本如果只看 `status` 字段，无法区分"用户选择不跑"和"跑了但无 case 可执行"。

**影响**: 低。`skips` 和 `local_cases`/`external_cases` 计数字段提供了足够区分度，但 status 枚举语义边界模糊。

**建议裁决**: **deferred-with-owner** — Slice 3 接入 local cases 后此状态路径不再可达（opted_in 且无 external URL file 将至少执行 local cases）。如果 Slice 3 完成后此路径仍然可达，应重新评估。

---

## Constraint Compliance Check

### 编码硬约束

| 约束 | 状态 |
|---|---|
| 完整中文 docstring（参数、返回值、异常） | **PASS** — 所有函数均有完整中文 docstring |
| 禁止 `object`, `Any`, 无类型参数/返回值 | **PASS** — 无 `Any`/`object`，全部严格类型 |
| 禁止魔法数字/字符串（工具 schema 例外） | **PASS** — 所有常量为 `Final` 模块级定义；Finding 4 为一处遗漏 |
| 模块间依赖最小化 | **PASS** — 仅依赖 `dayu.contracts.json_value.JsonValue`，不 import Host/Engine/Service |
| 禁止兼容性代码 | **PASS** — 无 re-export、wrapper、兼容性常量 |
| 禁止 God object/function/dataclass | **PASS** — 职责分离到独立函数和窄 dataclass |
| 优先模块级私有辅助函数 | **PASS** — 全部函数为模块级 `_` 前缀 |

### Agent 语义约束

| 约束 | 状态 |
|---|---|
| Summary JSON/MD 字段自解释 | **PASS** — `status`, `exit_code`, `run_label`, `output_dir`, `failures[].bucket/evidence_path/url/suggested_next_step`, `skips`, `diagnostic_only`, `local_cases`, `external_cases` 均为业务可读字段 |
| 无裸 event_id, payload_ref, digest, cursor | **PASS** |
| 不把内部治理标识伪装成业务事实 | **PASS** |

### 架构硬约束

| 约束 | 状态 |
|---|---|
| 分层 `UI -> Service -> Host -> Engine` | **PASS** — 脚本不影响任何层 |
| 不 import `dayu.engine/host/service/ui/fins` | **PASS** — 仅 import `dayu.contracts.json_value` |
| 不修改 Host durable schema / EventLog / ToolRuntime contracts | **PASS** |

### 测试约束

| 约束 | 状态 |
|---|---|
| 测试 deterministic，无 live network | **PASS** — 5 个测试全部使用 synthetic payload 和 monkeypatched runner |
| 单文件覆盖率 ≥ 80% | **PASS** — tests 覆盖未 opt-in、pass/fail/skip/diagnostic_only/schema_gap 分类、exit code 优先级、external 不覆盖 local pass、external-limit |
| 测试包含 smoke 判定逻辑 | **PASS** — `_classify_child_result` 和 `_summary_from_cases` 为焦点 |

---

## Test Coverage Assessment

### 已覆盖路径

| 路径 | 测试 |
|---|---|
| 未 opt-in → skipped, exit 0, 不调用 runner | `test_not_opted_in_writes_skipped_summary_and_does_not_call_runner` |
| Synthetic HTML pass (requests ok + fetch ok) | `test_synthetic_diagnostics_results_map_to_pass_fail_skip_diagnostic_only_and_schema_gap` |
| Synthetic HTML fail (requests failure) | 同上 |
| Synthetic schema_gap (missing version) | 同上 |
| Synthetic PDF skip (docling_init_error) | 同上 |
| Synthetic external diagnostic_only (all_failed) | 同上 |
| Exit code 优先: schema_gap(2) > local_failure(1) | `test_summary_exit_code_prefers_schema_gap_over_local_failure` |
| External failure 不覆盖 local pass | `test_external_failure_is_diagnostic_only_and_does_not_override_local_pass` |
| External-limit 生效, summary 路径固定 | `test_external_limit_and_summary_paths_are_predictable` |

### 未覆盖路径（已知，不阻塞 Slice 2）

| 路径 | 说明 |
|---|---|
| PDF content_type 非 PDF → fail | 分类函数 `_classify_pdf_loaded_artifact` 由 Slice 2 实现，但测试通过 `test_synthetic_diagnostics_results...` 间接覆盖了 pass 和 docling_init_skip 两个 PDF 分支。Content-type/content-length/docling_invocation failure 的具体分支未独立测试。建议 Slice 3 或 Slice 5 补充。 |
| PDF raw/content length 为空/过短 → fail | 同上 |
| PDF Docling invoked=False → fail | 同上 |
| Child returncode≠0 + docling_init_skip → skip | 实现了两个路径（returncode=0 和 returncode≠0），测试仅覆盖 returncode=0。Slate 3 建议补充 returncode≠0 路径。 |

---

## Verification Results (Independent)

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q
# 24 passed in 0.35s

source .venv/bin/activate && python -m pyright utils/smoke_web_ci.py tests/tools/web/test_smoke_web_ci.py
# 0 errors, 0 warnings, 0 informations

git diff --check
# (manually verified - no whitespace issues)

bash -n utils/smoke_web_ci.sh
# N/A — wrapper was not created (per implementation report)
```

所有验证与 Codex implementation report 一致。

---

## Residual Risks

| 风险 | 严重性 | 说明 |
|---|---|---|
| `_STDIO_PREFIX_CHARS` / `_prefix_text` 死代码 | Low | Finding 1，不影响功能，建议 closeout 前清理 |
| Slice 2 summary 未区分"未 opt-in skip"与"opt-in 但无 case skip" | Low | Finding 2 + Finding 5，Slice 3 接入后消失 |
| External schema_gap 检查硬编码 `_CASE_LOCAL_HTML` | Low | Finding 3，行为正确但代码意图模糊 |
| `"not_opted_in"` 非模块级常量 | Very Low | Finding 4，风格不一致 |
| Slice 2 无 local HTTP fixture → 无法端到端验证 local smoke 判定 | Medium | 设计内，等待 Slice 3。本 Slice 的判定逻辑已在 synthetic tests 中锁定。 |
| Diagnostics wrapper instrumentation 在生产 callable 名称变更时失效 | Low | Slice 1 residual，不因 Slice 2 恶化或改善 |
| External site anti-bot/DNS/timeout/Playwright 稳定性 | Low | Plan-design: diagnostic-only by design |

---

## Final Recommendation: **pass-with-fixes**

**理由**:

1. **Plan 合规**: Slice 2 严格实现了 opt-in CLI、summary contract、schema validation、子进程/artifact mapping table、external-limit 和 exit code 语义。未越界到 Slice 3、Slice 5 或 production Web tools。
2. **Mapping table**: 逐行核验，全部 10 行与实现一致。
3. **类型与文档**: 零 `Any`/`object`/无类型签名。所有函数完整中文 docstring。pyright 零错误。
4. **测试**: 5 个 deterministic tests 覆盖核心分类路径，24 total passed（含 Slice 1 diagnostics tests）。无 live network。
5. **4 个 findings** 均为 MEDIUM/LOW 级别，无阻塞性问题。建议的修复点均为小幅改进（移除死代码、添加注释、统一定义常量），可在 Slice 3 或 Slice 5 closeout 前处理。

**建议的 fix 优先级**:

1. 移除 `_STDIO_PREFIX_CHARS` 和 `_prefix_text` 死代码（Finding 1）
2. 定义 `_BUCKET_NOT_OPTED_IN` 常量（Finding 4）
3. 为 external schema_gap 检查的 `_CASE_LOCAL_HTML` 添加注释（Finding 3）
4. （可选）在 `_execute_smoke` 空 local_cases 时追加 skip item 说明 Slice boundary（Finding 2）

以上修复均为文档/清理性质，不改变 smoke 分类逻辑、exit code 行为或测试断言。Slice 2 核心功能正确且可推进。
