# Interactive Conversation Memory closure F08：DS 第二路独立 code re-review

## Review identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Review slice：F08（summary null 的 LLM-facing 选择规则与 replacement contract）。
- 审查者：DS（独立第二路 re-review，不依赖 MiMo）。
- 审查模式：对 F08 的两路原始 code review（DS/MiMo）与 no-op fix artifact 做独立复核。
- 分支：`codex/interactive-oracle`。
- Base ref：`68ba4038`（`gateflow: accept plan for interactive-memory-closure-f08-f10`）。
- 输入 artifacts：
  - Original DS review：`docs/reviews/wu-interactive-memory-closure-f08-code-review-ds.md`（SHA-256 `8a788bf1...`）
  - Original MiMo review：`docs/reviews/wu-interactive-memory-closure-f08-code-review-mimo.md`（SHA-256 `78202cef...`）
  - No-op fix audit：`docs/reviews/wu-interactive-memory-closure-f08-code-review-fix-codex.md`（SHA-256 `8b891e25...`）
  - Implementation artifact：`docs/reviews/wu-interactive-memory-closure-f08-implementation-codex.md`（SHA-256 `a27f650b...`）
  - Accepted plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`
  - Frozen findings：`docs/reviews/wu-interactive-memory-closure-f08-f10.md`
- 输出文件：`docs/reviews/wu-interactive-memory-closure-f08-code-rereview-ds.md`。
- 审查时间：2026-08-04。

## Scope

本 re-review 只覆盖 F08 slice 的 5 个未提交变更文件：

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `docs/cli_init_workspace_manifest_v1.json`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_memory_projection.py`

不覆盖 F09（Tool Trace）、F10（turn-group atomicity）或正式 CLI scenario evidence。

## 复核方法

1. 独立读取 accepted plan、frozen findings、5 个文件的完整 diff、两份原始 review 和 no-op fix artifact。
2. 独立重新计算所有 SHA-256（prompt raw、manifest raw、3 份 frozen baseline、2 份 frozen evidence）。
3. 独立运行 focused test suite（158 tests）和最小 owner-focused tests（4 tests）。
4. 独立运行 pyright（3 个变更的 Python test 文件）。
5. 独立验证 `git diff --exit-code` 确认 frozen baselines 相对 accepted-plan commit 无字节变化。
6. 独立逐项复核两路原始 review 的每个 claim（DS 的 C1–C8 + AC1–AC8，MiMo 的 M1–M7），确认无失效。
7. Adversarial 检查是否有遗漏的 owner bug、语义所有权漂移或边界违规。

## 独立验证结果

### V1：Prompt SHA-256

```
$ python3 -c "import hashlib; print(hashlib.sha256(open('dayu/config/prompts/scenes/conversation_compaction_user.md','rb').read()).hexdigest())"
5f5a51519e11eae0f162e8623e3c55d3946e1613bd36bfe4c38cc3e61eb827c0
```

与 manifest entry `content_sha256` 完全一致。此值与 DS review C1、MiMo review 第 3 节一致。

### V2：Manifest SHA-256

```
$ python3 -c "import hashlib; print(hashlib.sha256(open('docs/cli_init_workspace_manifest_v1.json','rb').read()).hexdigest())"
9ebdeab528bfcf953107a7d0e94d7aba63aab4fe8c56f7e612251dd1247af6a1
```

与 `tests/cli/test_smoke_cli_init_provider_matrix.py:95` 的 `FROZEN_MANIFEST_SHA256` 常量完全一致。manifest 中仅更新了 `conversation_compaction_user.md` 的唯一 `content_sha256` entry，其余 40+ 条目未变。

### V3：Frozen baseline（相对 accepted-plan commit 68ba4038）

| 文件 | Accepted digest | 本 re-review 重算 | git diff --exit-code |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `da049231...` | `da049231...` | exit 0 |
| `docs/cli_ci_scenarios.json` | `7c991d14...` | `7c991d14...` | exit 0 |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543...` | `95a09543...` | exit 0 |

### V4：Frozen evidence

| 文件 | Accepted digest | 本 re-review 重算 | 一致 |
|---|---|---|---|
| `workspace/tmp/interactive-memory-observed-behavior.md` | `ad643151...` | `ad643151...` | ✓ |
| `workspace/tmp/interactive-memory-report-freeze.json` | `7ba64926...` | `7ba64926...` | ✓ |

### V5：Focused test suite

```
$ pytest -q tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/cli/test_smoke_cli_init_provider_matrix.py
158 passed, 3 warnings in 4.21s
```

3 条 warning 均为第三方 `edgar` deprecation warning，非 F08 回归。

### V6：最小 owner-focused tests

```
$ pytest -q \
  tests/host/test_llm_compaction.py::test_prompt_assets_are_self_contained_for_fresh_v2_contract \
  tests/host/test_memory_projection.py::test_accepted_compact_without_summary_clears_prior_session_summary \
  tests/cli/test_smoke_cli_init_provider_matrix.py::test_frozen_manifest_matches_fresh_real_publication_tree \
  tests/cli/test_smoke_cli_init_provider_matrix.py::test_checked_in_manifest_digest_is_stable_across_validation
4 passed, 3 warnings in 1.36s
```

### V7：Pyright

```
$ pyright tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/cli/test_smoke_cli_init_provider_matrix.py
0 errors, 0 warnings, 0 informations
```

### V8：旧语义文本清除

```
$ grep -c '不影响同一 candidate' dayu/config/prompts/scenes/conversation_compaction_user.md tests/host/test_llm_compaction.py tests/host/test_memory_projection.py
0（全部文件均为 0 匹配）
```

新 replacement 语义文本（`不表示保留旧 summary`、`四类业务语义项仍须根据本次材料各自独立输出`、`不得因 summary 为 null 而一并清空`）均在 prompt 第 37 行存在，prompt contract test 中也有对应断言。

### V9：Host 禁止术语泄漏

```
$ grep -cE 'schema_version|current_input_anchor|evidence_backed_facts|reference_continuity_items|Compact|compaction\.py|context_governance|memory\.py|MemoryProjectionPolicy|SessionSummaryMemoryView|event_id|payload_ref' dayu/config/prompts/scenes/conversation_compaction_user.md
0
```

prompt contract test（第 432–447 行）通过 `assert forbidden not in user_prompt` 逐项强制执行同一 forbidden 列表。

### V10：Diff 完整性

```
$ git diff --check HEAD -- <5 F08 files>
（无输出 — 通过）
```

变更文件恰好 5 个，全部在 accepted plan 的 Slice F08 allowed files 列表中。

## 两路原始 review claim 逐项复核

### DS positive confirmations（C1–C8）：全部仍成立

| Claim | 原始结论 | 本 re-review 独立重验 | 状态 |
|---|---|---|---|
| C1：prompt SHA 与 manifest entry 一致 | PASS | 独立重算一致（见 V1） | **未失效** |
| C2：manifest SHA 与 smoke constant 一致 | PASS | 独立重算一致（见 V2） | **未失效** |
| C3：frozen baseline/evidence 未改变 | PASS | 独立重算全部 5 份一致（见 V3/V4） | **未失效** |
| C4：旧语义文本清除，新文本存在 | PASS | 独立 grep 确认（见 V8） | **未失效** |
| C5：focused suite 通过 | PASS | 158 passed（见 V5） | **未失效** |
| C6：pyright 零新增 | PASS | 0 errors（见 V7） | **未失效** |
| C7：无 Host verifier/阈值/兼容 | PASS | diff 中无生产 Python 变更 | **未失效** |
| C8：改动文件限于 allowed files | PASS | 5 文件，精确匹配 plan | **未失效** |

### DS adversarial checks（AC1–AC8）：全部仍成立

| Claim | 原始结论 | 本 re-review 独立重验 | 状态 |
|---|---|---|---|
| AC1：模型知道何时 null | PASS | prompt 第 35–36 行自足定义三条规则 + 禁止项 | **未失效** |
| AC2：无歧义或误要求 | PASS | "不存在或后续不需要的维度不要编造补齐" 消除凑维度风险 | **未失效** |
| AC3：无 Host verifier/阈值 | PASS | diff 无生产 Python 变更 | **未失效** |
| AC4：测试从 owner projection 同源 | PASS | candidate → accepted_truth → EventLog → production projector → snapshot → JSON round-trip 全链路生产代码 | **未失效** |
| AC5：两个 SHA consumer 精确 | PASS | manifest entry + smoke constant 精确对应 | **未失效** |
| AC6：测试字符串无脆弱或遗漏 | PASS | 有意耦合，owner-level 关键路径已覆盖 | **未失效** |
| AC7：scope/README/digest 正确 | PASS | 5 文件精确，README 判定正确 | **未失效** |
| AC8：无 Host 术语泄漏 | PASS | forbidden term grep 0 匹配（见 V9） | **未失效** |

### MiMo review claims（M1–M7）：全部仍成立

| Claim | 原始结论 | 本 re-review 独立重验 | 状态 |
|---|---|---|---|
| M1：prompt 自足、低认知负担 | PASS | 第 34–37 行纯业务语言，无内部术语 | **未失效** |
| M2：null replacement 语义准确 | PASS | 三个维度与 plan §5.4/§6.F08 一致 | **未失效** |
| M3：三级 SHA 同源 | PASS | prompt → manifest → smoke constant 链路完整 | **未失效** |
| M4：测试断言 owner contract | PASS | prompt contract + Memory replacement test 走生产者真链路 | **未失效** |
| M5：README 不改判定正确 | PASS | 四份 README 均不触发更新条件 | **未失效** |
| M6：frozen baseline 未改变 | PASS | 3 份 baseline + 2 份 evidence 均一致 | **未失效** |
| M7：allowed files 边界准确 | PASS | 5 个 tracked files + implementation artifact | **未失效** |

## 遗漏 owner bug 检查

本 re-review 对以下潜在漏洞做了独立 adversarial 检查，确认两路原始 review 均未遗漏：

### OB1：prompt 中 "cap" 术语的歧义性

**检查**：prompt 第 36 行使用 "当前明确 cap"，但在 `session_summary` section 内未独立定义 "cap"。`policy_limit` drop reason（第 69 行）解释了 cap 来自 "当前 repair feedback 已明确给出一个具体 cap"。首次请求无 repair feedback，无 explicit cap，因此第 36 行的 null 条件不触发。此设计正确：null 规则是针对 repair 场景的精准约束。

**结论**：无遗漏。DS review AC2 已覆盖此点。术语依赖 `policy_limit` 对 cap 的说明是 prompt 内自足的（同一文档内），不构成跨文档依赖。**PASS**。

### OB2：null 是否可能被错误触发于首次请求

**检查**：首次请求无 explicit cap（repair feedback 不存在），第 36 行的 "当前明确 cap 内无法形成" 条件的前提 "当前明确 cap" 不成立，因此模型不会进入 null 分支。模型在首次请求中应正常产生 summary，若超 cap 则由 Host deterministic validator 拒绝并进入 repair。此设计确保 null 规则只在 repair 场景生效。

**结论**：无遗漏。DS review AC1 已分析 "首次请求不触发" 的逻辑。**PASS**。

### OB3：测试 fixture 默认值是否掩盖了 projection bug

**检查**：`_accepted_compact_payload` 始终提供默认 anchor/intent/reference 值（`"收入口径"`、`"下一轮继续核对费用率。"`、`"该公司继续指向当前分析主体。"`）。当 `summary_text=None` 时，Event 1（含旧 summary）与 Event 2（null summary + 默认四类值）的 anchor/intent/reference 使用了相同的 fixture 默认值，因此仅通过值相等无法区分散"旧值保留"与"旧值被替换为新默认值"。但 Memory projector 的整体 replacement 行为（latest event wins）在 `build_conversation_memory_snapshot_from_events` 中由其他测试充分覆盖；本测试的职责是验证 null summary **不清空**其他四类——该职责由对四个非空 tuple 的显式断言完成（`assert tuple(...) == ("收入口径",)` 等四行）。

**结论**：无遗漏。DS review AC4 的 residual observation 已记录此点。**PASS**。

### OB4：是否有任何语义所有权漂移

**检查**：自然语言 summary 选择规则的唯一 owner 是 conversation compaction user prompt。Host 只拥有 shape、cap、coverage 和 replacement 等确定性 contract。当前 diff 的变更完全在 prompt owner boundary 内——prompt 文本 + prompt contract test + Memory owner test + publication digest。未修改 parser、Host validator、Memory projector、CLI、fixture 或任何生产 Python 文件。

**结论**：无语义所有权漂移。修复在正确 owner 边界内闭环。**PASS**。

### OB5：publication digest 是否有遗漏的 consumer

**检查**：prompt raw bytes 有两个 consumer：(1) manifest `content_sha256` entry，(2) 通过 manifest raw bytes 派生的 smoke test `FROZEN_MANIFEST_SHA256` 常量。两个 consumer 均已同步更新。init smoke test 通过真实 `dayu-cli init` 流程验证 publication tree 与 manifest 一致，构成完整的 publication integrity 闭环。

**结论**：无遗漏 consumer。**PASS**。

## No-op fix decision 复核

本 re-review 独立确认：

1. 两路原始 review（DS + MiMo）的结论均为 **PASS**，无任何 production finding、test-contract finding、docs finding 或 blocking open question。
2. No-op fix audit 逐项响应了两路 review 的每个 claim，理由充分且由当前代码/测试/digest 直接证据支撑。
3. 无任何需要代码修复的 finding。为产生 diff 而修改 parser、Host validator、Memory projector、CLI、fixture 或 README 都会造成语义所有权漂移或 goal drift。

**No-op decision 合理。** 两路 review 的一致 PASS 结论不是"互相背书"的同义反复——DS review 是独立第二路，其验证方法（SHA 重算、focused test 重跑、forbidden term grep、prompt 自足性逐行检查）与 MiMo review 的方法论独立。

## 测试/digest/baseline 不变性确认

| 检查项 | 方法 | 结果 |
|---|---|---|
| Frozen baselines vs `68ba4038` | `git diff --exit-code 68ba4038 -- <3 files>` | exit 0，无字节变化 |
| Frozen evidence vs accepted digests | 独立 SHA-256 重算 | 5 份全一致 |
| Prompt SHA vs manifest | 独立重算 | 一致 |
| Manifest SHA vs smoke constant | 独立重算 | 一致 |
| Focused suite (158 tests) | 独立运行 | 全通过 |
| Owner-focused tests (4 tests) | 独立运行 | 全通过 |
| Pyright (3 test files) | 独立运行 | 0 errors |
| Diff scope | `git diff --name-only` | 5 文件，精确匹配 |

## Residual observations

以下为本 re-review 独立识别但已正确分类的非 finding 观察：

1. **"cap" 术语在 session_summary section 内未独立定义**：依赖同文档内 `policy_limit` drop reason 对 cap 的说明。若未来 prompt 重构分离了两部分规则，应注意保持术语一致性。DS review AC2 与 fix audit 均已记录。**非 finding。**

2. **Test fixture 默认值耦合**：`test_accepted_compact_without_summary_clears_prior_session_summary` 断言了 fixture 默认值。若 fixture 默认值被修改，该测试将失败，但这属于显式契约——修改 fixture 的人必须同步更新测试。DS review AC4/AC6 与 fix audit 均已记录。**非 finding。**

3. **Real-provider 遵守度未在 deterministic gate 覆盖**：prompt 规则在文本层面自足且清晰，但模型在真实 cap 压力下是否稳定输出 `null` 而非占位符仍需正式 CLI scenario（`interactive.g06.summary-null`）验证。该风险按 accepted plan 分类为 `assigned to later work unit`，不由 F08 implementation gate 承担。两路原始 review 与 fix audit 均已记录。**非 finding。**

## Verdict

**PASS**

F08 slice 的 5 个文件变更正确、自足且从 owner boundary 实施。两路原始 code review（DS + MiMo）的 PASS 结论均未失效。独立复核确认：

- 所有 SHA-256 digest 链完整且一致
- 全部 frozen baseline/evidence 未改变
- 全部 focused/owner-focused tests 通过
- Pyright 零新增错误
- 无遗漏的 owner bug、语义所有权漂移或边界违规
- No-op fix decision 合理——accepted production findings = 0，无需任何代码修复
- Prompt 变更精确关闭了 MC14 观察到的根因（模型在明确 cap 内输出占位符而非 null），不引入 Host semantic verifier、阈值判断、兼容分支或下游补偿

无 blocking finding。下一 gate：按 accepted plan 推进 F09（Tool Trace canonical manifest 同源修复）或进入 F08 code review controller adjudication。
