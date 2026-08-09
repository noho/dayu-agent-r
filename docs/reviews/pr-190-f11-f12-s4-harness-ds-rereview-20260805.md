# PR 190 F11/F12 S4 Harness DS Re-Review

## Scope

- **Mode**: current changes（独立 DS re-review，只读代码/测试/全部 S4 artifact）
- **Branch**: `codex/interactive-oracle`
- **Base**: `321893e423beeb20acf2768c03b2be3477c92903`
- **Output file**: `docs/reviews/pr-190-f11-f12-s4-harness-ds-rereview-20260805.md`
- **Included scope**:
  - `utils/smoke_host_public_conversation_memory_scenarios.py`（完整 diff vs base）
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`（完整 diff vs base）
  - `docs/reviews/code-review-20260805-210138.md`（Codex review artifact，base 已修正）
  - `docs/reviews/pr-190-f11-f12-s4-harness-mimo-review-20260805.md`（MiMo review）
  - `docs/reviews/pr-190-f11-f12-s4-harness-ds-review-20260805.md`（前次 DS review）
  - `docs/reviews/pr-190-f11-f12-s4-harness-review-adjudication-20260805.md`（adjudication）
  - `docs/reviews/pr-190-f11-f12-s4-harness-fix-20260805.md`（fix artifact）
- **Excluded scope**: 生产 contract (`dayu/`)、oracle、scenario、external evidence root `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-HeHeLm/`
- **Parallel review coverage**: 无；主 reviewer 独立完成
- **角色**: AgentDS；只审查不修改代码，不 stage/commit/push

## 验证方法

1. 独立运行 `pytest` 与 `pyright` 确认全部通过
2. 沿实际代码路径逐行走读 parser 校验顺序、finally 异常处理、evidence 导出、digest 计算、equality 比较
3. 逐项对照 test assertions 与被测 owner function contract，确认 assertions 直接断言 owner 行为而非间接副作用
4. 对 parser 校验顺序做 adversarial 穷举：每个 suite 与 argument 组合的命中分支与错误消息
5. 确认 `git diff --name-only` 仅包含 harness 与 test 两个文件

## 独立验证结果

### pyright

```
0 errors, 0 warnings, 0 informations
```

### pytest

```
36 passed, 3 warnings in 7.22s
```

Warnings 全部来自 `edgar` 已弃用模块，与本次 change 无关。

### git diff --name-only

```
tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
utils/smoke_host_public_conversation_memory_scenarios.py
```

仅两个文件变更。无生产代码、oracle、scenario、external evidence 修改。

---

## Finding 逐项验证

### S4-REVIEW-001 — evidence export owner-level deterministic tests

**裁决**: ACCEPTED（adjudication）。要求补齐 fresh-write、digest、public/canonical equal/mismatch、failure export 的 deterministic owner tests。

**验证结论**: **PASS — 已关闭。**

逐项证据：

#### Fresh file/dir 不可覆盖

- **Test**: `test_s4_evidence_fresh_file_and_directory_are_not_overwritten`（test:454–488）
- **被测 owner**: `_write_fresh_json`、`_export_s4_invocation_evidence`
- **断言**:
  - `_write_fresh_json` 对已存在文件抛出 `FileExistsError`（`match="evidence file already exists"`）
  - 原文件 bytes 未被修改（`assert evidence_file.read_bytes() == original_bytes`）
  - `_export_s4_invocation_evidence` 对已存在目录抛出 `FileExistsError`（`match="evidence output directory already exists"`）
  - 目录内容保持为空（`assert tuple(evidence_dir.iterdir()) == ()`）
- **Owner 验证**: 两个被测函数（`utils:7037–7049`、`utils:6425–6427`）分别拥有 fresh-write guard；测试直接调用 owner 函数，不做 smoke invocation 间接覆盖。

#### Digest 排除自身且校验实际内容

- **Test**: `test_s4_evidence_digest_excludes_itself_and_hashes_file_contents`（test:491–528）
- **被测 owner**: `_evidence_digest_json`
- **断言**:
  - `file_count == 2`（同目录下包含 `digest.json`、`first.txt`、`nested/second.bin` 三个文件，排除自身后为 2）
  - 每个文件的 `size_bytes` 与 `hashlib.sha256(content).hexdigest()` 精确匹配
  - 使用 binary content `b"beta\x00gamma"`（含 null byte）验证 SHA-256 对任意字节正确
  - 在调用前写入 stale `digest.json`（内容 `"stale-self"`），验证该文件被排除而非被读入索引
- **Owner 验证**: 直接调用 `_evidence_digest_json`（`utils:7056–7081`），owner 行 `path != digest_path`（`utils:7067`）被显式验证。

#### Public/canonical equality 的 equal 与 mismatch

- **Test**: `test_s4_public_canonical_equality_reports_equal_and_mismatch`（test:531–571）
- **被测 owner**: `_public_canonical_equality_json`
- **Fixture 构造**: `_s4_rejected_terminal_fixture`（test:1577–1648）使用生产 owner 函数构造 canonical 事实：
  - `build_context_compaction_attempt_rejected_payload`（Host production owner）构造 rejected payload
  - `EventLogRow` 携带 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` event type
  - `ToolTraceCompactorResponseSummary` 携带与 canonical binding 同源的字段值
- **断言**:
  - Equal case: `finding_count == 0`、`equal is True`、`reason is None`
  - Mismatch case: 用 `replace(response, proposal_manifest_digest=...)` 修改 public manifest digest
  - `finding_count == 1`、`equal is False`、`reason == "public-canonical-binding-mismatch"`
- **Owner 验证**: 直接调用 `_public_canonical_equality_json`（`utils:6897–6970`），走完整 canonical parse 路径（`parse_context_compaction_attempt_rejected_terminal_binding`），测试 true owner contract。

#### Failure export 不遮蔽业务异常

- **Test**: `test_s4_failure_export_does_not_mask_active_business_exception`（test:574–605）
- **被测 owner**: `_handle_s4_evidence_export_error`
- **断言**:
  - 业务异常 + export 失败 → `raised.value is business_error`（**identity check** `is`，非类型相等或 `isinstance`）
  - stderr 包含 `"SMOKE EVIDENCE_EXPORT_FAILED OSError: evidence write failed"`
  - 无业务异常 + export 失败 → `raised.value is export_error`（export error 原样 raise）
- **Owner 验证**: 直接调用 `_handle_s4_evidence_export_error`（`utils:7104–7126`），覆盖两条分支。`is` identity check 确保证明 `sys.exception()` 返回的正是正在传播的异常对象，而非拷贝或替代。

**总评**: S4-REVIEW-001 所要求的四项 deterministic owner tests 均直接调用被测 owner 函数，断言精确到 owner contract 级字段值（size/SHA-256/finding_count/equal/reason/exception identity），不存在通过 smoke invocation、real provider 或间接副作用验证的情况。**已关闭。**

---

### DS-002 — parser fail closed for missing --evidence-output-dir

**裁决**: ACCEPTED（adjudication）。real-provider suites 缺少 `--evidence-output-dir` 时 parser 必须 fail closed 并给出可操作错误。

**验证结论**: **PASS — 已关闭。**

#### Parser 实现

`parse_args`（`utils:2488–2491`）：

```python
if evidence_output_text is None and pressure_suite in _REAL_PROVIDER_SUITES:
    parser.error(
        f"--suite {pressure_suite.value} requires --evidence-output-dir"
    )
```

`_REAL_PROVIDER_SUITES` 包含全部六个 real-provider suites（`utils:150–158`）：`MEMORY_REAL_BASELINE`、`MEMORY_REAL_BOUNDARY`、`MEMORY_REAL_REPLACEMENT`、`MEMORY_REAL_REPAIR`、`MEMORY_RECONNECT_PROBE`、`MEMORY_REAL_FALLBACK`。

#### Test

`test_real_provider_cli_requires_evidence_output_dir_independently`（test:426–451）：
- Parametrized over `_REAL_PROVIDER_SUITE_NAMES`（六个 suite）
- 对 pressure suite 先满足 `--pressure-mode auto`（消除压力模式检查的干扰）
- 对 reconnect-probe 不添加 `--pressure-mode auto`（因 reconnect-probe 不在 pressure-mode 检查中）
- 断言 `SystemExit` 且 `capsys.readouterr().err` 包含 `"--suite {suite} requires --evidence-output-dir"`

#### Adversarial 穷举

| Suite | `--pressure-mode auto` | `--evidence-output-dir` | 命中分支 | 结果 |
|---|---|---|---|---|
| real-baseline | 无 | 无 | pressure-mode check (line 2473) | `SystemExit`: requires --pressure-mode auto |
| real-baseline | 有 | 无 | evidence-dir check (line 2488) | `SystemExit`: requires --evidence-output-dir |
| real-baseline | 有 | 有 | none | 正常通过 |
| real-baseline | 无 | 有 | pressure-mode check (line 2473) | `SystemExit`: requires --pressure-mode auto |
| reconnect-probe | N/A | 无 | evidence-dir check (line 2488) | `SystemExit`: requires --evidence-output-dir |
| reconnect-probe | N/A | 有 | none | 正常通过（test:362–374 已验证） |
| reactive-compact | N/A | 有 | forbids check (line 2483) | `SystemExit`: forbids deterministic fake compact suites |

所有 6 个 real-provider suites 缺 evidence dir 时均 fail closed。Parser 校验顺序符合 CLI "逐错误修复"惯例——同时缺两个参数时先报告第一个。

**总评**: Parser 对全部 6 个 real-provider suites 的 evidence-dir 缺失强制执行 fail closed，对应 test 独立于 pressure-mode 约束。**已关闭。**

---

### DS-003 — pressure-mode 与 evidence-dir 约束拆分为独立测试

**裁决**: ACCEPTED（adjudication）。将 pressure-mode 与 evidence-dir 两个 CLI 约束拆成独立断言，避免测试由错误分支偶然通过。

**验证结论**: **PASS — 已关闭。**

#### 拆分结果

| Test | 参数化范围 | 被测约束 | 传入参数 |
|---|---|---|---|
| `test_real_provider_cli_requires_pressure_mode_independently`（test:396–423） | `_REAL_PRESSURE_SUITE_NAMES`（5 suites，不含 reconnect-probe） | pressure-mode 缺失 | 有 `--evidence-output-dir`，无 `--pressure-mode auto` |
| `test_real_provider_cli_requires_evidence_output_dir_independently`（test:426–451） | `_REAL_PROVIDER_SUITE_NAMES`（6 suites，含 reconnect-probe） | evidence-dir 缺失 | 有 `--pressure-mode auto`（若需要），无 `--evidence-output-dir` |

#### 证据

- **pressure-mode 测试**: 显式提供 `--evidence-output-dir`，只省略 `--pressure-mode auto`，确保 `SystemExit` 来源唯一——`parser.error("... requires --pressure-mode auto")`。断言 `capsys.readouterr().err` 包含 `"requires --pressure-mode auto"`。
- **evidence-dir 测试**: 先传入 `--pressure-mode auto`（若 suite 需要），只省略 `--evidence-output-dir`，确保 `SystemExit` 来源唯一——`parser.error("... requires --evidence-output-dir")`。断言 `capsys.readouterr().err` 包含 `"requires --evidence-output-dir"`。
- 两个测试各自断言独立的错误消息文本，不会因对方约束的改变而误通过/误失败。

**总评**: 两个 CLI 约束已拆分为独立 parametrized tests，各自断言唯一 `SystemExit` 来源。**已关闭。**

---

### Base artifact correction — review artifacts base SHA

**裁决**: ACCEPTED（adjudication）。三份 review artifact 与 Codex review 误写 base SHA，应由各自 owner 修为实际 base。

**验证结论**: **PASS — 已关闭。**

| Artifact | Base SHA | 状态 |
|---|---|---|
| `code-review-20260805-210138.md`（Codex review） | `321893e423beeb20acf2768c03b2be3477c92903`（line 7） | ✅ 已修正 |
| `pr-190-f11-f12-s4-harness-mimo-review-20260805.md`（MiMo review） | `321893e423beeb20acf2768c03b2be3477c92903`（line 7） | ✅ 已由 owner 修正（Correction Note:258） |
| `pr-190-f11-f12-s4-harness-ds-review-20260805.md`（DS review） | `321893e423beeb20acf2768c03b2be3477c92903`（line 7） | ✅ 已由 owner 修正（Section 9:308–309） |
| `pr-190-f11-f12-s4-harness-review-adjudication-20260805.md`（adjudication） | `321893e423beeb20acf2768c03b2be3477c92903`（line 6） | ✅ 始终正确 |

Adjudication 明确要求 "external bundle 已声明 immutable，不得回写"。fix artifact 确认未修改 external evidence root。**已关闭。**

---

### S4-001 — exhausted fallback digest mismatch

**裁决**: ACCEPTED — deferred to production owner slice（adjudication）。Harness 不补偿。

**验证结论**: **PASS — 未被补偿，生产 owner 边界未破坏。**

- `utils/` 中新增的 `_export_s4_invocation_evidence` 通过 `open_host_durable_store` → public Host API 读取 durable state，不做 SQLite 旁路或 raw SQL
- `_RealCompactorCaptureRunner` 是 capture-only wrapper，调用 `self._original_runner`（真实 runner），不替换 response
- 压力 padding 使用 `estimate_budget_text_tokens`（Host owner），不复用 `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN` 或本地估算
- `_compact_pressure_padding_with_reserve` 新增 `tool_pressure_tokens` 参数（从 caller 传入），不做本地 `_tool_pressure_estimated_tokens()` 二次估算
- Memory policy 通过 `digest_memory_projection_policy`（Host owner）计算 digest
- Canonical equality 通过 `parse_context_compacted_terminal_binding` / `parse_context_compaction_attempt_rejected_terminal_binding`（Host owner）解析 canonical payload
- S4-001 的 root cause（`compact_pipeline.py:1123-1129` raw text vs `compact_material.py:782` normalized text digest mismatch）未被 harness 补偿、fallback、normalize 或 workaround

**总评**: S4-001 继续归生产 owner slice；harness/test 未做任何 normalization、digest fallback 或 fixture 补偿。**保持 open，归属正确。**

---

### DS-001 — compactor captures 为空

**裁决**: 暂不接受为代码 finding，转为重跑验证项（adjudication）。产品修复后从全新 root 重跑，验证 `compactor-attempts.json` 与 canonical attempt 数量一致。

**验证结论**: **PASS — 未在本次 fix 中加入临时 debug。**

- fix artifact（line 65）明确记录：`不作为本 gate 代码 finding，不加临时 debug`
- 代码中 `_capturing_real_compactor_requests` 的 `self._captures` 是 `list[RealCompactorAttemptCapture]`，被传入 `_export_s4_invocation_evidence` 的 `compactor_captures` 参数
- 无新增 `print`、`logging`、debug marker 或临时观测代码
- **已关闭（按 adjudication 处置）。**

---

### DS-004 — _repeat_to_budget_tokens 二分搜索

**裁决**: REJECTED（adjudication）。不采纳。

**验证结论**: **PASS — 未修改，保持原实现。**

- `_repeat_to_budget_tokens`（`utils:7076–7092`）使用二分搜索 + slice
- fix artifact（line 66）明确：`adjudication 已不采纳，本 gate 未修改`
- **已关闭（不采纳）。**

---

### S4-REVIEW-002 — _sanitize_error_text 大小写

**裁决**: REJECTED（adjudication）。`text.lower()` 已处理大小写。

**验证结论**: **PASS — 不成立，未修改。**

- `_sanitize_error_text`（`utils:4786–4795`）的 `lowered = text.lower()` 已覆盖所有大小写变体
- **已关闭（不成立）。**

---

### S4-REVIEW-003 — compactor-attempts.json 包含完整 request messages

**裁决**: ACCEPTED as known low risk（adjudication）。不改实现，secret scan 继续为 0。

**验证结论**: **PASS — 未修改，secret scan 设计正确。**

- `_compactor_capture_json`（`utils:6721–6761`）的 `messages` 字段序列化 `role` + `content`，不含 headers/credentials
- `secret-scan.json` 外部 evidence 已确认 `finding_count=0`
- **已关闭（accepted as low risk）。**

---

## Adversarial 重点检查

### 1. Parser 校验顺序

已在上方 DS-002 穷举中完整覆盖。所有 suite × argument 组合均命中正确分支。无 branch ordering bug（宽条件未抢先命中更具体分支）。

### 2. Failure finally active exception identity

`test_s4_failure_export_does_not_mask_active_business_exception` 使用 Python `is` identity operator 验证 `raised.value is business_error`：
- `sys.exception()` 在 Python 3.11 中返回正在传播的 exception instance（不是拷贝）
- `_handle_s4_evidence_export_error` 的 `active_exception is None` 分支正确：有 active exception 时 suppress export error；无 active exception 时 `raise export_error`
- 原有 `finally` 块在 `_handle_s4_evidence_export_error` 返回后，Python runtime 自动继续传播原异常
- **无 exception chaining 或 replacement risk**。

### 3. Digest/fresh-write/public-canonical mismatch tests 断言真正 owner

- `test_s4_evidence_digest_excludes_itself_and_hashes_file_contents`: 直接调用 `_evidence_digest_json`（harness helper），用 `hashlib.sha256` 独立计算期望值 → 断言 owner 计算的等价性，不做 loose match
- `test_s4_evidence_fresh_file_and_directory_are_not_overwritten`: 直接调用 `_write_fresh_json` 和 `_export_s4_invocation_evidence`，验证 FileExistsError + 原内容不变 → 断言 owner guard 有效
- `test_s4_public_canonical_equality_reports_equal_and_mismatch`: 通过 `build_context_compaction_attempt_rejected_payload`（Host production owner）构造 canonical fixture，再用 `_public_canonical_equality_json`（harness helper）比较 → 双方均使用各自 owner 构造/比较事实，不存在下游自行反推 canonical 语义
- `test_s4_failure_export_does_not_mask_active_business_exception`: 使用 `is` identity check → 断言异常对象本身未被替换

### 4. 无生产/oracle/scenario/external evidence 变更

`git diff --name-only` 仅返回两个文件：`utils/smoke_host_public_conversation_memory_scenarios.py` 和 `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`。无 `dayu/`、oracle、scenario 或 external evidence root 修改。

### 5. 新增 tests 未固化偶然行为

- `_s4_rejected_terminal_fixture` 通过 production owner function（`build_context_compaction_attempt_rejected_payload`）构造事实，不手工拼装 payload dict
- `test_s4_public_canonical_equality_reports_equal_and_mismatch` 的 mismatch 通过 `replace(response, proposal_manifest_digest=...)` 构造，修改的是明确的 public contract 字段
- `test_s4_failure_export_does_not_mask_active_business_exception` 的 business error 使用 `RuntimeError` 实例，identity 验证不依赖消息文本匹配

---

## 未覆盖与已知 Gaps

1. **`_response_summary_identity_equal` 的 non-None identity 路径无 deterministic unit test**: `_s4_rejected_terminal_fixture` 的 `successful_response_identity=None`。Non-None identity 比较由真实 evidence（04/06/07/09 equal=true）间接验证，无独立 unit test。风险低——identity 字段比较逻辑是简单属性相等，且真实 evidence 已通过。
2. **`_RealCompactorCaptureRunner` 的 `build_request_payload` 异常路径无 test**: 若 `build_request_payload` 对特定 request 抛出异常，wrapper 会在 try 之前失败。`build_request_payload` 是纯函数，当前对所有合法输入不抛异常，但此路径无 test 覆盖。
3. **S4-001 与 DS-001 仍 open**: 两个 finding 都依赖生产修复后的全新 evidence root 重跑。本次 fix 未改变此状态。
4. **Real provider campaign 未重跑**: fix artifact 明确记录 `本 harness fix gate 未重跑`。DS-001 的验证需要在 S4-001 修复后从全新 evidence root 执行。

---

## Open Questions

无。所有 accepted findings 的 closeout 状态可由代码与 test 直接证据确定。

---

## Residual Risk

1. **S4-001**: production fallback current-input material normalization/digest 仍不同源。S4 mandatory exhausted fallback/single terminal 继续阻塞。
2. **DS-001**: 生产修复后必须用全新 evidence root 重跑，核对 capture 与 canonical attempt 数量。
3. **Evidence 部分写入**: `_write_fresh_json` 非原子写入；进程崩溃可残留部分文件。`FileExistsError` guard 阻止覆盖但不清理部分文件。对 smoke harness 可接受。
4. **`_handle_s4_evidence_export_error` 的 active exception 为 KeyboardInterrupt/SystemExit 时**: 代码当前将其当作一般 `BaseException` 处理（`active_exception is not None` → suppress export error）。对于 KeyboardInterrupt，这可能掩盖 evidence 导出错误——但 KeyboardInterrupt 本身应优先传播，这是正确行为。

---

## Closeout

本 DS re-review 独立验证了 adjudication 接受的 4 项（S4-REVIEW-001、DS-002、DS-003、base artifact correction）均已真正关闭：

- **S4-REVIEW-001**: 四项 evidence export contract 的 deterministic owner tests 均直接调用被测函数，断言精确到 owner contract 级字段值（identity、SHA-256、finding_count、equal/reason）。
- **DS-002**: 六个 real-provider suites 缺 `--evidence-output-dir` 均 parser fail closed；test 独立于 pressure-mode 约束。
- **DS-003**: pressure-mode 与 evidence-dir 已拆分为独立 parametrized tests，各自断言唯一 `SystemExit` 来源。
- **Base artifact correction**: 三份 review artifact 的 base SHA 均为实际 `321893e423beeb20acf2768c03b2be3477c92903`；external bundle 未被回写。

其他 accepted/not-adopted finding（DS-001、DS-004、S4-REVIEW-002、S4-REVIEW-003、S4-001）均按 adjudication 处置正确执行或保持不动。

**Harness fix gate: 可进入 accepted commit / re-review closeout。S4-001 继续归 production owner slice。**
