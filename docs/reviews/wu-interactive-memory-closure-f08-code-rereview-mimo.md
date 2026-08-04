# Code Re-Review — F08 slice：summary null 的 LLM-facing 选择规则与 replacement contract

## Re-Review identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Re-Review slice：F08（summary null 的 LLM-facing 选择规则与 replacement contract）。
- 审查者：AgentMiMo（re-review，基于原 MiMo review + DS review + Codex no-op fix artifact）。
- 分支：`codex/interactive-oracle`。
- Accepted plan commit：`68ba4038`。
- Re-Review 时间：2026-08-04 16:32 CST。
- 输出文件：`docs/reviews/wu-interactive-memory-closure-f08-code-rereview-mimo.md`。

## Scope

本 re-review 的职责：

1. 读取当前完整 F08 diff（5 个 allowed files 相对 `68ba4038`）。
2. 读取原 MiMo code review、DS code review 与 Codex no-op fix artifact。
3. 验证 no-op fix 决策合理。
4. 验证代码/测试自两路 review 以来未发生未审改动。
5. 验证两路 PASS 证据仍成立。
6. 验证 baseline/digest 保持。

不覆盖 F09（Tool Trace）、F10（turn-group atomicity）或正式 CLI scenario evidence。

## 输入完整性

| Durable input | Recorded SHA-256（fix artifact） | Re-review 实测 SHA-256 | 一致 |
|---|---|---|---|
| `docs/reviews/wu-interactive-memory-closure-f08-code-review-mimo.md` | `78202cef...391ef1` | `78202cef...391ef1` | ✓ |
| `docs/reviews/wu-interactive-memory-closure-f08-code-review-ds.md` | `8a788bf1...fa13f` | `8a788bf1...fa13f` | ✓ |
| `docs/reviews/wu-interactive-memory-closure-f08-implementation-codex.md` | `a27f650b...c2f299` | `a27f650b...c2f299` | ✓ |
| `docs/reviews/wu-interactive-memory-closure-f08-code-review-fix-codex.md` | （本 artifact 自身） | `0fc6cb9c...61cee` | ✓（新写入） |

四份 review/fix/implementation artifact 均完整读取，SHA-256 与 fix artifact 记录一致。

## Verification 1：No-op fix 决策合理性

### 1.1 两路 review 结论

| Review | 结论 | Findings | 证据链 |
|---|---|---|---|
| AgentMiMo | PASS | 0 | 7 项 evidence-based verification，全部通过 |
| AgentDS | PASS | 0 | 8 项 positive confirmations + 8 项 adversarial checks，全部通过 |

两路 review 均独立完成、互不依赖，结论一致。

### 1.2 No-op 理由成立

F08 的根因是模型在明确 cap 下用占位字符代替 `null`。语义 owner 是 conversation compaction user prompt。Codex fix artifact 判定：为产生 diff 而修改 parser、Host validator、Memory projector、CLI、fixture 或 README，都会造成语义所有权漂移或 goal drift。

**Re-review 判定**：该推理正确。F08 的变更精确落在 prompt owner boundary 内——prompt 自足定义完整陈述、null 条件、禁止项与 whole-replacement 语义；Memory projector owner test 从生产链路验证 null replacement；publication digest 从最终 prompt raw bytes 派生。没有需要代码修复的 finding，no-op 决策合理。

## Verification 2：代码/测试未发生未审改动

### 2.1 Changed files 边界

`git diff --name-only 68ba4038 --` 输出恰好 5 个文件：

```
dayu/config/prompts/scenes/conversation_compaction_user.md
docs/cli_init_workspace_manifest_v1.json
tests/cli/test_smoke_cli_init_provider_matrix.py
tests/host/test_llm_compaction.py
tests/host/test_memory_projection.py`
```

与 plan §6 F08 allowed files 完全一致。无超出边界的变更。

### 2.2 Diff 内容与 review 描述一致

| 文件 | 变更内容 | 与 MiMo review 描述一致 | 与 DS review 描述一致 |
|---|---|---|---|
| `conversation_compaction_user.md` | 新增 3 条 session_summary bullet（非 null 质量、null 触发条件、null replacement 语义） | ✓ | ✓ |
| `cli_init_workspace_manifest_v1.json` | 更新 `conversation_compaction_user.md` 的唯一 `content_sha256` entry | ✓ | ✓ |
| `test_smoke_cli_init_provider_matrix.py` | 更新 `FROZEN_MANIFEST_SHA256` 常量 | ✓ | ✓ |
| `test_llm_compaction.py` | 新增 10 项 session_summary 语义断言，移除 1 项旧文本断言 | ✓ | ✓ |
| `test_memory_projection.py` | 扩展 null-summary test：断言四类保留 + snapshot JSON round-trip | ✓ | ✓ |

逐行 diff 与两路 review 中描述的变更内容完全一致，无额外或遗漏变更。

### 2.3 旧语义文本清除确认

- 旧文本 `不影响同一 candidate 中其它四类业务语义项`：prompt 中 0 出现，test 中 0 出现。✓
- 新文本 `不表示保留旧 summary`、`其它四类业务语义项仍须根据本次材料各自独立输出`、`不得因 summary 为 null 而一并清空`：prompt 中均存在。✓

## Verification 3：两路 PASS 证据仍成立

### 3.1 Prompt 自足性（MiMo M1 + DS AC1/AC2/AC8）

当前 prompt 第 35–37 行自足定义：

- 非 null summary 构成条件：至少一条完整、脱离原会话也可独立理解的业务陈述
- null 触发条件：当前明确 cap 内无法形成完整陈述
- 禁止项：占位符、孤立字符、孤立标点、无上下文缩写、截断片段
- 维度反编造：不存在或后续不需要的维度不要编造补齐

无字符数/词数阈值、无正则、无语言检测、无 Host heuristic、无内部 Python 类型名。grep 验证 prompt 中无 `Compact*`、`compaction.py`、`context_governance` 等内部术语。**证据仍成立**。

### 3.2 null replacement 语义（MiMo M2 + DS AC4）

| 维度 | prompt 表达 | 与 plan 对齐 |
|---|---|---|
| null 清除旧 summary | "candidate 被接受后，当前会话摘要变为空，包括清除先前已接受的摘要，不表示保留旧 summary" | ✓ |
| 其它四类独立保留 | "其它四类业务语义项仍须根据本次材料各自独立输出，不得因 summary 为 null 而一并清空" | ✓ |
| 非 null 质量要求 | "至少一条完整、脱离原会话也可独立理解的业务陈述" | ✓ |

**证据仍成立**。

### 3.3 SHA 三级同源（MiMo M3 + DS C1/C2/C5）

| 环节 | 当前实测值 | 声明值 | 一致 |
|---|---|---|---|
| prompt raw SHA-256 | `5f5a5151...eb827c0` | implementation artifact / MiMo review | ✓ |
| manifest `content_sha256` entry | `5f5a5151...eb827c0`（diff 行） | prompt raw SHA-256 | ✓ |
| manifest raw SHA-256 | `9ebdeab5...47af6a1` | implementation artifact / MiMo review | ✓ |
| smoke test `FROZEN_MANIFEST_SHA256` | `9ebdeab5...47af6a1`（行 95） | manifest raw SHA-256 | ✓ |

三级链路同源，无中间重算或断点。**证据仍成立**。

### 3.4 测试断言 owner contract（MiMo M4 + DS AC4/AC6）

**prompt contract test**（`test_prompt_assets_are_self_contained_for_fresh_v2_contract`）：

- 断言 10 项新增 session_summary 语义
- 保留 strict JSON、whole replacement、untrusted material 边界断言
- 无"Host 接受占位符"的 negative acceptance test

**Memory replacement owner test**（`test_accepted_compact_without_summary_clears_prior_session_summary`）：

- 建立含旧 summary 的 snapshot → 接受 `session_summary=None` + 全部四类其它 memory
- 断言 `summary_text is None`、`event_id is None`
- 断言 facts、answer anchors、forward intents、reference continuity 逐项保留
- 断言 canonical snapshot JSON round-trip 后相等

测试走真实 accepted truth → EventLog → Memory projector → snapshot → JSON round-trip 生产链路。**证据仍成立**。

### 3.5 Frozen baseline/evidence（MiMo M6 + DS C3）

| 文件 | Accepted digest | Re-review 实测 | 一致 |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `da049231...07261201` | `da049231...07261201` | ✓ |
| `docs/cli_ci_scenarios.json` | `7c991d14...cbca2093` | `7c991d14...cbca2093` | ✓ |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543...d14b1b08` | `95a09543...d14b1b08` | ✓ |
| `workspace/tmp/interactive-memory-observed-behavior.md` | `ad643151...5658263` | `ad643151...5658263` | ✓ |
| `workspace/tmp/interactive-memory-report-freeze.json` | `7ba64926...98f5b` | `7ba64926...98f5b` | ✓ |

五份 frozen baseline/evidence 全部未改变。**证据仍成立**。

### 3.6 README 不改判定（MiMo M5 + DS AC7）

- `dayu/config/README.md`：F08 只改变一个 scene prompt 的业务文本与派生 digest，不改变配置层级/加载/schema。✓
- `tests/README.md`：F08 只扩展既有 prompt contract 与 Memory owner test，不改变测试层级/运行方式。✓
- 根 `README.md`：用户可见安装、CLI 参数、入口、输出通道均未变化。✓
- `dayu/host/README.md`：F08 不修改 Host 生产代码。✓

**判定仍成立**。

### 3.7 无 Host semantic verifier / 阈值 / 兼容代码（DS AC3/C7）

当前 tracked diff 只有 prompt 文本、manifest digest 和测试断言/SHA 常量。无任何 Host 生产 Python 文件被修改。无 `len(text)`、正则、词表、停用词或语言检测。无兼容性 import、re-export 或 fallback 分支。**证据仍成立**。

## Verification 4：Baseline/digest 保持

### 4.1 Frozen baseline SHA-256

已在 Verification 3.5 中确认全部 5 份 frozen baseline/evidence 的 SHA-256 与 accepted plan checkpoint 完全一致。

### 4.2 Publication derivation

| Owner bytes / consumer | SHA-256 | 一致 |
|---|---|---|
| `conversation_compaction_user.md` raw bytes | `5f5a5151...eb827c0` | 与 manifest asset entry 一致 |
| `cli_init_workspace_manifest_v1.json` raw bytes | `9ebdeab5...47af6a1` | 与 smoke frozen constant 一致 |

### 4.3 `git diff --exit-code` on frozen files

```bash
git diff --exit-code 68ba4038 -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/reviews/wu-interactive-memory-closure-f08-f10.md workspace/tmp/interactive-memory-observed-behavior.md workspace/tmp/interactive-memory-report-freeze.json
```

exit code 0，无字节变化。✓

## Verification 5：Focused test suite 与 pyright

```
pytest tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/cli/test_smoke_cli_init_provider_matrix.py -q
→ 158 passed, 3 warnings in 4.20s
```

三条 warning 均为既存第三方 `edgar` deprecated import，非 F08 回归。

```
pyright tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/cli/test_smoke_cli_init_provider_matrix.py
→ 0 errors, 0 warnings, 0 informations
```

`git diff --check` 通过。

## Residual Risk

1. **Real-provider 遵守度**：prompt 规则在文本层面自足且清晰，但模型在真实 cap 压力下是否稳定输出 `null` 而非占位符仍需正式 CLI scenario 验证。该风险按 accepted plan 分类为 `assigned to later work unit`（`interactive.g06.summary-null` scenario），不由 F08 implementation gate 承担。

2. **"cap" 术语在 session_summary section 内未独立定义**：prompt 第 36 行的 "当前明确 cap" 依赖 `policy_limit` drop reason 中对 cap 的说明以及 repair feedback message 中的具体数值。null 规则的实际触发仅在 repair 场景，不构成实际歧义。不构成 finding。

3. **Test fixture 默认值耦合**：`_accepted_compact_payload` 的默认 anchor/intent/reference 值被 test 显式断言。若 fixture 默认值被修改，该测试将失败，但这是显式契约。不构成 finding。

## Conclusion

**PASS**

F08 re-review 确认：

1. **No-op fix 合理**：两路 review（MiMo + DS）均 PASS、0 findings；Codex fix artifact 正确判定无需代码修复。
2. **代码/测试未发生未审改动**：changed files 精确限于 5 个 F08 allowed files；逐行 diff 与两路 review 描述完全一致；旧语义文本已彻底清除。
3. **两路 PASS 证据仍成立**：prompt 自足性、null replacement 语义、SHA 三级同源、测试 owner contract、frozen baseline/evidence、README 判定、无 Host verifier/阈值/兼容代码——全部 7 项证据经独立重验后仍成立。
4. **Baseline/digest 保持**：5 份 frozen baseline/evidence SHA-256 与 accepted plan checkpoint 完全一致；publication derivation 三级链路同源。

F08 slice 实现正确，可进入 controller adjudication 或下一 gate。
