# PR 190 Final PR Re-Review — AgentDS

**日期**: 2026-08-03
**审查人**: AgentDS（final re-review gate）
**PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190) — `fix(cli): close interactive conformance gaps`
**Head**: `codex/interactive-oracle` @ `0f7dc59168aca6e5f5b5bb30c059711465347bf2`
**Base**: `main` @ `113ea34d47b95812d79aa31705949bbb46bc6061`
**输入 artifact**:
- `docs/reviews/pr-190-final-pr-mimo-review-20260803.md`（MiMo final review）
- `docs/reviews/pr-190-final-pr-ds-review-20260803.md`（DS final review）
- `docs/reviews/pr-190-final-pr-review-fix-codex-20260803.md`（Codex fix artifact）
- 既有 controller adjudications（F01-F07 aggregate deepreview controller adjudication / draft PR pass controller adjudication / final closeout / compactor LLM-facing aggregate deepreview acceptance）

---

## Re-Review 方法

本 re-review 独立核验 no-code-fix 裁决的每一个前提，不依赖既有 review 或 fix artifact 的结论正确性。逐项采证后判定。

---

## 一、Exact-head 与 PR Metadata 独立核验

| 检查项 | 直接命令/证据 | 结论 |
|--------|--------------|------|
| 本地 HEAD | `git rev-parse HEAD` = `0f7dc59168aca6e5f5b5bb30c059711465347bf2` | **PASS** |
| PR head | `gh pr view 190 --json headRefOid` = 同一 OID | **PASS** |
| PR base | `gh pr view 190 --json baseRefName` = `main` | **PASS** |
| PR draft | `gh pr view 190 --json isDraft` = `true` | **PASS** |
| PR state | `gh pr view 190 --json state` = `OPEN` | **PASS** |
| PR branch | `gh pr view 190 --json headRefName` = `codex/interactive-oracle` | **PASS** |
| Merge base | `git merge-base main 0f7dc591` = `113ea34d47b95812d79aa31705949bbb46bc6061` | **PASS** |
| Commit count | `git rev-list --count main..0f7dc591` = **43**（DS artifact 误写为 45） | **PASS（修正）** |
| Follow-up commits | `git rev-list --count 7cf1027c..0f7dc591` = **6**（plan + S1-S4 + aggregate） | **PASS** |
| 工作树 | `git status --short` 仅含 3 个未跟踪 review artifact（MiMo/DS/Codex fix） | **PASS** |

---

## 二、Frozen Registry 零 Diff 独立核验

| 检查项 | 直接命令/证据 | 结论 |
|--------|--------------|------|
| Oracle JSON | `git diff --exit-code 7cf1027c..0f7dc591 -- docs/cli_ci_oracles.json` = exit 0 | **PASS** |
| Scenario JSON | `git diff --exit-code 7cf1027c..0f7dc591 -- docs/cli_ci_scenarios.json` = exit 0 | **PASS** |
| CLI CI Handbook | `git diff --exit-code 7cf1027c..0f7dc591 -- docs/cli_ci.md` = exit 0 | **PASS** |

**结论**: Compactor LLM-facing follow-up commits（plan/S1-S4/aggregate）未触碰 frozen oracle/scenario/handbook。Oracle/scenario 的变更（ESC predicate 新增、P25→P27R 重命名等）全部属于前序 F01-F07 closeout（`main..7cf1027c`），与前序 review 宣称一致。

---

## 三、no-code-fix 每一项独立核验

### 3.1 两路无新增 production finding

- MiMo final review 明确结论：`PASS — 无 blocking finding`，correctness/semantic ownership/LLM-facing/overcoupling/stability/v2 migration 均无 production finding。
- DS final review 明确结论：`无新增 Critical / High Finding`，merge readiness 为 `代码质量支持 merge`。

**独立核验**: 阅读两份 review 全文，确认不存在被标记为 production finding 且需要代码修复的条目。DS 的 finding summary（§十一）明确为 0 new finding，residual 列表全部是既有观察重述。**核验通过。**

### 3.2 intent_type / reason 保持 frozen v2 design

**独立核验**:
- `dayu/host/compaction.py:1224` — `CompactForwardIntentV2.intent_type: str`
- `dayu/host/compaction.py:1270` — `CompactReferenceContinuityV2.reason: str`
- `dayu/host/compaction.py:1237,1282` — 仅 `_require_non_empty` 校验，无枚举/pattern acceptance
- `docs/host/design.md` — v2 design 明确写为 `intent_type: str`、`reason: str`
- Compactor user prompt 提供自足业务语义约束和示例
- 既有 controller adjudication 已 `REJECT-WITH-REASON` 恢复旧枚举

**结论**: v2 有意设计，frozen contract。DS 自身也承认是设计决策非 bug。无新证据推翻既有裁决。**核验通过。**

### 3.3 VT100 parser 无 broad catch

**独立核验**:
- `dayu/cli/run_keys.py:260-261` — `select.select` 捕获 `OSError, ValueError`
- `dayu/cli/run_keys.py:270-271` — `os.read`/`decode` 捕获 `OSError, UnicodeDecodeError`
- `dayu/cli/run_keys.py:276-287` — `_feed_parser_resolution`（含 `parser.feed`）、`_classify_running_key_batch` 为同步内部 invariant，无 try/except
- `PromptToolkit` 的 `Vt100Parser.feed/flush` 在合法或畸形 TTY 输入下不抛异常（库 contract）
- 既有 controller 已 `REJECT-WITH-REASON` 关闭 broad catch 建议

**结论**: DS 未提供 `Vt100Parser.feed/flush` 抛出异常的可复现数据。添加 `except Exception: break` 会掩盖 invariant error，也不会向 `wait_next` 投递 typed terminal——不能修复其声称的永久等待。**核验通过。**

### 3.4 handoff 竞态不存在

**独立核验**:
- `dayu/cli/composer.py:540-557` — `_flush_submit_handoff_input` 的执行顺序：
  1. `await asyncio.sleep(...)` — 唯一 await 点（行 551）
  2. `application.is_done` — 同步检查（行 553）
  3. `application.input.flush_keys()` — 同步调用（行 555）
  4. `application.key_processor.feed_multiple(keys)` — 同步调用（行 556）
  5. `application.key_processor.process_keys()` — 同步调用（行 557）
- 步骤 2-5 在同一 asyncio event-loop task 内同步执行，无 `await`，其他 coroutine 无法在 is_done/flush 之间切换

**结论**: DS 假设的 check/flush 竞态窗口不存在。既有 controller 已据此 `REJECT-WITH-REASON`。无新调度点或失败数据。**核验通过。**

### 3.5 multi-pass session summary 无新证据

**独立核验**: DS final review 未提供新的 coherence predicate 或失败样本。既有 controller 已以 disjoint material、frozen pass order 与 root-level 全量 revalidation 证据 `REJECT-WITH-REASON`。**核验通过。**

### 3.6 DS commit count 应为 43

**独立核验**: `git rev-list --count main..0f7dc591` 直接输出 `43`。DS artifact 元数据写为 `45` 是统计误述，不影响 reviewed tree、diff 内容或 owner contract。Codex fix artifact 已记录此修正。**核验通过。**

### 3.7 MiMo corrected artifact 严格分离两组真实证据

**独立核验**: 阅读 MiMo final review 全文：
- E3（前序 F01-F07 full-real bundle）明确标注 `该 bundle 属于前序 F01-F07 closeout`
- E4（本次 follow-up）明确标注 Mimo/DeepSeek 均为 `network_unavailable`，标记为 `not_observed`
- 全文严格区分前序 `main..7cf1027c` 证据与本次 `7cf1027c..0f7dc591` 证据

**结论**: 未用前序 full-real bundle 冒充本 follow-up 的真实模型行为证据。**核验通过。**

### 3.8 previous-* 未逐 kind 参数化不构成 marker owner gap

**独立核验**:
- `dayu/host/llm_compaction.py:706-719` — `_compaction_request_prompt_block_vnext` 对完整的 `request.to_json()` 只应用一对 `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END` marker
- `dayu/host/compaction.py:2224-2242` — `_previous_source_kind` 只做 kind 映射，不产生 trust-policy 分支
- `CompactInputV2.to_json()` 统一序列化 `current_input` 与完整 `source_boundary`，不按 `source_kind` 分支
- Trust boundary 的唯一 owner 是包围完整 typed input JSON 的 renderer marker，不是各 source kind
- 当前四个不同材料位置的 adversarial canary 已证明 production renderer 的共同路径

**结论**: 穷举 previous-* kind 不会增加 owner contract 证明。prompt aggregate acceptance 已逐项作出同一裁决。**核验通过。**

### 3.9 not_observed 正确阻止 behavior/conformance pass，不阻止 Gateflow closeout

**独立核验**:
- `tests/README.md:391-395` — 明确记录 "不能写成 behavior pass"
- `tests/host/test_public_compact_smoke.py:1313` — Mimo/DeepSeek `network_unavailable` 时 exact skip
- Real compactor smoke 在环境不可用时正确 skip，不执行 injection/cap assertions
- Deterministic test matrix 只证明 owner contract 与 typed boundary，不替代真实模型行为
- Gateflow code-review/fix/re-review/final-closeout 记录不依赖真实模型行为 pass

**结论**: `not_observed` 不产生 production failure，不阻止完成本 re-review gate。真实模型行为与 formal conformance 的最终裁决保留给 user/Oracle controller。**核验通过。**

---

## 四、Semantic Ownership 交叉核验

独立 trace 完整 compaction 语义链，确认每个语义有唯一清晰 owner，消费者从 owner 或 owner-defined public contract 读取，无下游 fallback、重算或兼容 shim：

| 语义 | Owner | 消费者 | 核验 |
|------|-------|--------|------|
| accept/reject truth | `context_governance.accept_compact_candidate_v2` | `_COMPACT_ACCEPTANCE_PERMIT` | **PASS** |
| repair feedback 构造 | `context_governance.build_compact_repair_feedback_v2` | `LLMContextCompactor.compact` | **PASS** |
| LLM-facing repair projection | `llm_compaction._repair_feedback_prompt_json_vnext` | `_user_prompt_vnext` | **PASS** |
| strict parser | `llm_compaction.parse_conversation_compact_output_vnext` | `LLMContextCompactor` | **PASS** |
| trust boundary marker | `llm_compaction._compaction_request_prompt_block_vnext` | system/user prompt renderer | **PASS** |
| terminal commit guard | `compaction_terminal.begin_compaction_terminal_commit_in_transaction` | `engine_ingest` | **PASS** |
| compact input projection | `CompactionRequest.compact_input` → `CompactInputV2` | `llm_compaction` renderer | **PASS** |
| `intent_type` / `reason` 语义 | Compactor prompt（LLM-facing contract） | accept barrier（仅校验非空） | **PASS — v2 design** |

**无 semantic ownership drift 发现。**

---

## 五、Working Tree 状态确认

| 文件 | 状态 | 评价 |
|------|------|------|
| `docs/reviews/pr-190-final-pr-mimo-review-20260803.md` | 未跟踪 | 预期 — MiMo review artifact |
| `docs/reviews/pr-190-final-pr-ds-review-20260803.md` | 未跟踪 | 预期 — DS review artifact |
| `docs/reviews/pr-190-final-pr-review-fix-codex-20260803.md` | 未跟踪 | 预期 — Codex fix artifact |
| `docs/reviews/pr-190-final-pr-rereview-ds-20260803.md` | 本文件 | 本 gate 唯一新增 artifact |

工作树只含预期 review artifact。无代码、测试、prompt、design、README、oracle 或 scenario 变更。

---

## 六、Re-Review 结论

### PR-REREVIEW-PASS

独立核验全部通过：

1. **no-code-fix accepted**: 两路 final review 均无新增 production finding。Codex fix artifact 正确裁定 4 项旧观察保持 closed（intent_type/reason、VT100 broad catch、handoff 竞态、multi-pass summary），无新证据推翻既有 frozen contract 或 controller 裁决。

2. **Commit count 修正**: DS 的 `45` → 实际 `43`（`git rev-list --count main..0f7dc591`），metadata only，不影响 reviewed code/tree/diff。

3. **MiMo corrected artifact 合规**: 前序 F01-F07 full-real bundle 与本 follow-up `network_unavailable`/`not_observed` 严格分离，未交叉冒充。

4. **previous-* 未逐 kind 参数化不构成 gap**: Trust boundary 的唯一 owner 是 renderer 层单对 marker，不按 source_kind 分支；穷举 previous-* kind 不增加 owner contract 证明。

5. **not_observed 语义正确**: 阻止宣称真实 behavior/formal conformance pass，不阻止 Gateflow code-review/fix/re-review/final-closeout 记录。最终 formal conformance 与 PR 决策保留给 user/Oracle controller。

6. **Frozen registry 零 diff**: `7cf1027c..0f7dc591` 的 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/cli_ci.md` 变更量为零。

7. **PR metadata/head 一致**: head=0f7dc591, draft=true, base=main, mergeable=MERGEABLE，工作树只含预期 review artifact。

### Residual Owner

- **真实模型行为 `not_observed`**: owner = user / Oracle controller（formal conformance 与最终 PR 裁决）
- **intent_type / reason 设计决策**: owner = v2 design（`docs/host/design.md`），frozen contract
- **VT100 parser 线程防御**: owner = 独立 runtime failure channel design（不在本 gate scope）
- **F01-F07 既有 residual**（Host public-cancel test-order flake、Oracle registry overall calibration 等）: owner = 原 controller / 后续 work unit

---

*Generated by AgentDS final PR re-review on 2026-08-03.*
