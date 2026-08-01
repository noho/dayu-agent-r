# Code Re-Review — S6 DS findings 逐项复核

## Scope

- **Mode**: DS initial review findings 复核（no-fix re-review）
- **Base review**: `docs/reviews/code-review-wu-cli-interactive-02-s6-ds-20260802.md`
- **Controller adjudication**: `docs/reviews/gateflow-wu-cli-interactive-02-s6-code-review-adjudication-20260802.md`
- **Implementation artifact**: `docs/reviews/gateflow-wu-cli-interactive-02-s6-implementation-codex-20260802.md`
- **Branch**: `codex/interactive-oracle`
- **Base**: `9ad45cf7`
- **Output file**: `docs/reviews/code-rereview-wu-cli-interactive-02-s6-ds-20260802.md`
- **Re-review date**: 2026-08-02T03:12:33+08:00
- **MiMo rereview**: 未读取（遵守 no-fix re-review 约束）
- **S6 uncommitted diff**: 与 DS 初审完全一致（9 modified + 1 new untracked implementation artifact），未发生变化

### 复核范围

| 项目 | 类型 |
|---|---|
| F-001 | DS finding → Controller 裁决复核 |
| F-002 | DS finding → Controller 裁决复核 |
| F-003 | DS finding → Controller 裁决复核 |
| F-004 | DS finding → Controller 裁决复核 |
| 行为项 29 raw evidence | 独立核验 |
| G01-G07 calibration | 分类复核 |
| Baseline/residual 分类 | 分类复核 |

### 证据溯源

| 证据 | 路径 |
|---|---|
| `_canonical_digest` 源码 | `workspace/tmp/build_prompt_scenario_registry.py:117-131` |
| PR #189 closeout | `docs/reviews/wu-cli-prompt-01-final-closeout-controller.md` |
| PR #189 independent deepreview | `docs/reviews/code-review-20260731-205900.md` |
| 行为项 29 raw evidence | `/Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt/evidence/interactive.S6-compaction-provider-identity-attempt-02/` |
| 行为项 29 command.json | `command.json`（真实 argv、pipe stdin、`--label s6-compaction-identity`、DeepSeek 可用） |
| 行为项 29 sqlite-after.json | `sqlite-after.json` event_log row[6]（event_sequence=7, CONTEXT_COMPACTED） |

## F-001 — `implementation_findings_do_not_reduce_readiness=[]` 清空验证

### DS 初审主张

S6 将 6 条 implementation findings 清空为 `[]`，但 S6 未修改生产代码，清空正确性无法从 S6 diff 独立验证；缺少 readiness proof validator 的独立输出作为直接证据。

### Controller 裁决

`rejected_as_missing_prior-artifact-trace`。6 条 prompt finding 已由 PR #189 在 owner boundary 修复，并完成 321/321 frozen real CLI replay、1301 项受影响测试通过、独立 deepreview 确认无实质 finding。

### 复核证据

1. **PR #189 final closeout 文档**（`wu-cli-prompt-01-final-closeout-controller.md`）：
   - 六项 finding 的 owner-level closeout：逐项给出了 owner（`dayu.cli.output`、`dayu.cli.session_execution`、`dayu.cli.__main__`/`dayu.cli.agent_entrypoint`、`dayu.cli.arg_parsing`、`dayu.cli.errors`/`dayu.cli.main`、`dayu.cli.arg_parsing.parse_cli_args`）
   - 1301 passed, 7 skipped, 3 warnings
   - 321/321 frozen real CLI replay：`focused-real-pass`，failures 0
   - 完整 pyright：0 errors, 0 warnings, 0 informations
   - 最终裁决：`pass`

2. **PR #189 independent deepreview**（`code-review-20260731-205900.md`）：
   - 文件存在，verdict `pass`，无 blocking finding

3. **语义正确性**：`implementation_findings_do_not_reduce_readiness` 只应保存当前仍存在但经裁决不阻降的 finding。已由 owner 修复并完成真实 replay 的 finding 不应继续列入。清空是 resolved truth 的机械投影。

### 复核结论

**PASS** — Controller 裁决正确。prior-artifact trace（PR #189 closeout + independent deepreview）充分证明 6 条 finding 已在 owner boundary 修复，`implementation_findings_do_not_reduce_readiness=[]` 是正确的机械投影。DS 初审未追溯 PR #189 的 prior-artifact 闭合证据，导致 finding 不成立。

**无新 finding**。

---

## F-002 — dimension counts 机械重算证据

### DS 初审主张

dimension counts 从 `50/400/16/10/332/5` 变为 `33/383/16/8/319/5`，手工验证方向正确但缺少机械 validator proof 直接输出。

### Controller 裁决

`rejected_as_already_proven`。implementation artifact §4.2/§6 已记录 object/ref/readiness validator 通过；Controller 独立执行 scenario-id keyed object comparison，验证 17 删除、6 精确变更、436 不变对象。

### 复核证据

1. **Implementation artifact §4.2/§6**：明确记录 "registry object/ref/readiness validator 通过；dangling oracle/predicate/surface/evidence 均为 0"，dimension counts 均来自当前 scenario object 的机械聚合。

2. **Controller keyed comparison**：独立以 scenario_id 为 key 做对象级比较，确认除 17 删除 + 5 pairwise row + P37 外，其余 436 条 scenario object 完全相同。

3. **DS 分析中的事实偏差**：DS 初审将 `input_class_ids` 从 10 降到 8 归因于 "P30（有 stdin:EOF input class）被重新编号"。Controller 的 keyed comparison 证明 P30 object 完全不变（byte-identical）。实际原因更可能是被删除的 17 条 scenario 中有 2 条携带了未被任何保留 scenario 共享的 input class。这不影响 count 正确性，但说明 DS 的归因逻辑未经 independent keyed verification 确认。

### 复核结论

**PASS** — Controller 裁决正确。validator 通过 + Controller independent keyed comparison 构成双重机械验证证据。DS 初审对 input_class_ids 变化的归因（P30 "重新编号"）存在事实偏差，但不影响 finding 裁决结果。

**无新 finding**。

---

## F-003 — parser inventory 字段顺序与 canonical SHA-256

### DS 初审主张

parser inventory 重新生成后，每个 parameter 对象内部字段顺序变化（`dest` 从首位移到 `choices` 之后），导致新旧 canonical SHA-256 不可比，无法仅通过 digest 确认参数集等价性。

### Controller 裁决

`rejected_as_factually_incorrect`。现有 canonical owner `_canonical_digest` 使用 `json.dumps(..., sort_keys=True, separators=(",", ":"))`，pretty JSON 中 object member 的展示顺序不影响 canonical digest。

### 复核证据

1. **`_canonical_digest` 源码**（`workspace/tmp/build_prompt_scenario_registry.py:117-131`）：
   ```python
   payload = json.dumps(
       value,
       ensure_ascii=False,
       sort_keys=True,
       separators=(",", ":"),
   ).encode("utf-8")
   return hashlib.sha256(payload).hexdigest()
   ```
   `sort_keys=True` 确保 object keys 按字母序排列后再 hash，与 pretty-print 中的字段顺序完全无关。

2. **实证验证**：构造相同内容、不同 key 顺序的两个 dict，`sort_keys=True` 下 digest 完全一致；`sort_keys=False` 下 digest 不同。证实 canonical digest 不受 display order 影响。

3. **Digest 变化的真实原因**：inventory version 从 1 变为 2、`--config` action 被移除——这些是实际内容变化，不是字段排序漂移。

### 复核结论

**PASS** — Controller 裁决正确。DS 初审将 pretty JSON diff 中观察到的字段顺序变化误判为 canonical digest 输入变化，属于事实错误。`_canonical_digest` 的 `sort_keys=True` 从设计上保证了 digest 只反映内容变化，不受序列化展示顺序影响。

**无新 finding**。

---

## F-004 — `docs/cli_ci.md` 新增段 heading style

### DS 初审主张

新增的 parser/source-of-truth 规则段没有独立 `###` heading，可能被读者误认为是上一段的延续，建议增加 subsection heading。

### Controller 裁决

`rejected_as_style_preference`。新增规则紧接 `Registry-level readiness proof`，随后才进入原有 parser leaf 定义，适用范围和上下文明确；不存在错误 owner、断链引用或不可导航的既有 heading。

### 复核证据

1. **实际 diff**（`docs/cli_ci.md` 行 524-541，新增 18 行）：
   - 新增段第一句以 "当前 Agent CLI capability inventory 还必须遵守这些 parser/source-of-truth 规则：" 开头，语义上明确是新规则段的起始
   - 紧跟 `Registry-level readiness proof` 段落后，在其与 `parser leaf` 定义之间
   - 内容自足：描述了 `--config` 删除、`--ticker` 归属、label slot、parser inventory 导出、旧 argv 场景删除、interactive dynamic owner boundary 等具体规则

2. **DS 初审自身评级**：严重程度为"低"，明确写 "不影响正确性，仅文档结构可读性"

3. **CLAUDE.md 审查纪律**："不要用 style feedback、naming feedback、低价值 cleanup 或无证据猜测稀释严重问题"

### 复核结论

**PASS** — Controller 裁决正确。新增段落的语义边界、适用范围和上下文均明确，不存在导航性或 owner 归属问题。增加 subsection heading 属于纯样式偏好，不构成 correctness/stability/maintainability defect。

**无新 finding**。

---

## 行为项 29 raw evidence 独立核验

### DS 初审验证

行为项 29 已取得真实 successful compactor durable identity raw evidence，脱敏正确（effective provider/model + present provider_request_id + 零敏感字段）。

### 独立复核证据

直接从 external evidence root 的 `sqlite-after.json` 读取 `event_log` row[6]（`event_sequence=7`, `event_type=CONTEXT_COMPACTED`）中的 `successful_response_identity`：

| 字段 | 值 |
|---|---|
| `effective_provider` | `deepseek` |
| `effective_model` | `deepseek-v4-flash` |
| `provider_request_id_availability` | `present` |
| `provider_request_id` | 存在（`47842cddf53f1f5ab4f7e6e7fc01dfcc`） |
| `runner_request_identity.runner_call_index` | `1` |
| `runner_request_identity.attempt_id` | `None` |
| `runner_request_identity.execution_id` | `None` |
| `runner_request_identity.client_correlation_id` | 存在 |

从 `command.json` 确认：
- 真实 argv：`dayu-cli interactive --base ... --label s6-compaction-identity --no-detail --no-thinking`
- pipe stdin（非 fake/deterministic）
- DeepSeek 凭证可用
- exit_code: 0, duration: 6.38s

**敏感字段扫描**：endpoint, credential, api_key, secret, header, token, bearer — 零命中。

**同源性验证**：identity 与 operation_id、accepted_proposal_manifest_digest、accepted_candidate 在同一 `CONTEXT_COMPACTED` durable payload 中绑定，未从配置、manifest、usage 或相邻事件反推。

### 复核结论

**PASS** — DS 初审对行为项 29 的验证完全正确。Raw evidence 是真实 provider successful compaction durable identity，脱敏正确，同源绑定完整。

**无新 finding**。

---

## G01-G07 calibration 分类复核

### DS 初审分类

G01-G07 全部未裁决，保持冻结。Formal report renderer 硬编码旧 target commit，因此不登记 accepted scenario。

### Controller 确认

G01-G07 全部保持后续 CLI calibration obligation，global registry 继续 `calibration`。

### 复核

- Implementation artifact §5.2 明确："G06 与 G01-G07 均未裁决"
- Implementation artifact §8 明确："行为项 29 已有本次真实 provider successful compaction raw durable evidence，但 G06 及 G01-G07 仍冻结为未裁决"
- DS residual risk #2 正确分类为冻结状态

### 复核结论

**PASS** — G01-G07 分类正确。全部保持冻结/未裁决状态，global `registry_status` 继续 `calibration`。

**无新 finding**。

---

## Baseline/residual 分类复核

### DS 初审分类

| 项目 | DS 分类 | 依据 |
|---|---|---|
| 六条 phase5 failure | baseline（已知 scheduler/test race） | S5 clean base 独立复现 |
| Residual #1 — formal renderer 旧 target pin | 已知 harness owner gap | fail closed，未伪造 ready |
| Residual #2 — G01-G07 冻结 | 已知未裁决 | 待授权 campaign owner |
| Residual #3 — `interactive_calibration_plan.py` removed-option obligations | 已知 harness owner gap | 不在 S6 write scope |
| Residual #4 — awaiting entrypoint smoke callback port drift | 已知 harness/public-contract gap | S1-S5 范围 |
| Residual #5 — parser inventory 字段顺序不确定性 | tooling 风险 | 不影响正确性 |

### Controller 确认

六条 phase5 failure 精确为已在 S5 clean base 复现的 phase5 scheduler/test race。所有 residual risks 均为已知、已分类、已由 implementation artifact 透明记录的 gap。

### 复核

- 六条 failure 节点精确匹配 S5 裁决（`dispatched == 0`），S6 未修改相关代码、测试或时序
- Residual #1-#4 均有明确 owner 归属和 fail-closed 处置
- 无未分类或误分类的 residual risk
- Residual #5（parser inventory 字段顺序）经 F-003 复核确认不构成实际风险（`sort_keys=True` 保证 digest 稳定）

### 复核结论

**PASS** — Baseline/residual 分类全部正确。六条 phase5 failure 精确为既有 race，五项 residual risk 均为已知、已分类、已透明记录。

**无新 finding**。

---

## Calibration 观察

以下不属于新 finding，仅记录 DS 初审中的一处事实偏差供 calibration 参考：

- **F-002 中的 P30 归因偏差**：DS 初审将 `input_class_ids` 从 10 降到 8 归因于 "P30（有 stdin:EOF input class）被重新编号"。Controller 的 scenario-id keyed comparison 证明 P30 object 完全不变（byte-identical）。该归因不是 count owner 的直接证据，但不影响 count 值本身的正确性，也不影响 F-002 的最终裁决（rejected_as_already_proven）。

此偏差不影响 S6 diff 的正确性、稳定性或 owner boundary，仅作为 DS review 方法论的 calibration note。

---

## 总结

| 项目 | 状态 | 新 finding | 判定 |
|---|---|---|---|
| F-001 — readiness_proof 清空 | Controller 裁决正确，PR #189 prior-artifact trace 充分 | 无 | **PASS** |
| F-002 — dimension counts | Controller 裁决正确，validator + keyed comparison 双重验证 | 无 | **PASS** |
| F-003 — canonical SHA-256 字段顺序 | Controller 裁决正确，`sort_keys=True` 从设计上消除字段顺序影响 | 无 | **PASS** |
| F-004 — heading style | Controller 裁决正确，纯样式偏好 | 无 | **PASS** |
| 行为项 29 raw evidence | DS 验证正确，真实/同源/脱敏均确认 | 无 | **PASS** |
| G01-G07 calibration | DS 分类正确，全部冻结 | 无 | **PASS** |
| Baseline/residual 分类 | DS 分类正确，全部已知/已分类 | 无 | **PASS** |

四项 DS finding 均被 Controller 正确驳回，每条裁决有直接证据支撑。无新 finding 出现。S6 uncommitted diff 无 correctness、stability 或 owner-boundary defect。DS 初审中 F-002 对 P30 的归因存在事实偏差（不影响裁决结果），已在 Calibration 观察中记录。

**最终判定：PASS** — DS 四项 finding 均不成立，S6 exact diff 可进入下一 gate。
