# Code Review

## Scope

- Mode: current changes (deepreview — WU-TOOLS-CANCEL-01 residual hardening Slice S4)
- Branch: `phase/wu-tools-cancel-01`
- Base: commit `98cdc872` (S3 accepted slice commit)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-code-review-ds.md`
- Review date: 2026-07-05T16:32:35+08:00
- Reviewer: AgentDS (code-review stance)
- Included scope:
  - `dayu/README.md` (unstaged modification)
  - `dayu/host/README.md` (unstaged modification)
  - `docs/host/issues-implementation-control.md` (unstaged modification)
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-implementation-codex.md` (new, untracked)
- Excluded scope: production code, test code — S4 is explicitly a docs-only slice with no behavior changes.
- Parallel review coverage: 无。本次 review 范围集中在 3 个文档改动文件和 1 个 implementation artifact，由单一 reviewer 完整走读。
- Design sources: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md` S4 章节、`docs/host/design.md`、`docs/engine/design.md`、`dayu/README.md` Agent更新约束、`dayu/host/README.md` Agent更新约束。
- Implementation artifact under review: `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-implementation-codex.md` (AgentCodex).

## Evidence Collected

### Code-level verification (independent of AgentCodex claims)

1. **Contract helpers exist in code**: `process_tool_completed_envelope`, `process_tool_failed_envelope`, `parse_process_tool_envelope` are defined in `dayu/contracts/tool_execution.py` (lines 86, 99, 125) and exported from `dayu/contracts/__init__.py` (lines 82-84, 177-179). Verified.

2. **Hint mapping chain verified**:
   - `dayu/contracts/tool_execution.py:52`: `ToolResultFailure.hint: str | None` exists.
   - `dayu/contracts/tool_execution.py:99-121`: `process_tool_failed_envelope` writes `hint` to envelope only when non-None and non-blank.
   - `dayu/contracts/tool_execution.py:192-200`: `_parse_process_tool_failed_envelope` extracts hint, validates it must be string when present, returns only non-empty hint.
   - `dayu/host/tool_runtime.py:6573-6587`: `_tool_outcome_from_process_envelope` calls `parse_process_tool_envelope` from contracts, passes `parsed.hint` to `_tool_failed_outcome`.
   - `dayu/host/tool_runtime.py:7343-7362`: `_tool_failed_outcome` constructs `ToolResultFailure(hint=hint)`.
   - **Conclusion**: hint → `ToolResultFailure.hint` mapping is a single continuous data path. The Host README claim is accurate.

3. **No duplicated envelope constants in tools**: `grep -rn "_DOC_PROCESS_\|_FINS_PROCESS_\|_WEB_PROCESS_" dayu/tools/ dayu/fins/tools/` returns zero matches. Tools now use `dayu.contracts` helpers exclusively. Verified.

4. **Config README already documents process capsule interrupt policy**: `dayu/config/README.md:147` documents `process_capsule_interrupt_policy` with `terminate_grace_seconds`, `kill_grace_seconds`, finite non-negative validation, bool/NaN/infinity rejection, and distinction from `tool_execution_timeout_seconds`. The S4 artifact's claim is verified correct — no additional config README update needed.

5. **Host README process capsule policy mentions**: `dayu/host/README.md:92` describes `HostToolingOptions.process_capsule_interrupt_policy` in the `OpenHostOptions` section; `dayu/host/README.md:242` lists `ProcessCapsuleInterruptPolicy` in the Host 专属契约 section. Both are pre-existing from prior slices.

6. **No hint-into-message concatenation remains**: grep for `hint.*message` patterns in tool code shows hint and message are separate fields in business failure exceptions and process targets. The old concatenation pattern has been removed (S3).

## Findings

### 01-未修复-低-control-doc  gate 字段使用未在状态约定中显式定义的 `implementation completed`

- **入口/函数**: `docs/host/issues-implementation-control.md` 当前状态表 `gate` 行
- **文件(行号)**: `docs/host/issues-implementation-control.md:158`
- **输入场景**: S4 implementation 完成后更新 gate 字段
- **实际分支**: gate 值从 `implementation` 改为 `implementation completed`
- **预期行为**: 状态约定（第 169-181 行）定义了 `implementation`（"正在实施或修复"）但未定义 `implementation completed`。从状态机语义看，`implementation` 之后的 gate 是 `review`。
- **实际行为**: 使用了一个不在已定义状态集合中的 gate 值来描述 "implementation 已完成但 review 尚未开始" 的中间态。
- **直接证据**: 状态约定列表（第 169-181 行）包含 `implementation` 但不包含 `implementation completed`。
- **影响**: 轻微。gate 字段的语义从上下文和 `next entry point`（"Aggregate / final review"）可以明确推断。但严格来说，控制文档的状态机定义不完备，未来自动化 gate 流转或新 reviewer 可能对此产生歧义。
- **建议改法和验证点**: 可保留 `implementation completed` 并在状态约定中补充该值（例如 `implementation completed`：implementation 已完成，等待 review gate），或者改用 `review` 作为 gate 值并在 status 文本中说明 S4 已完成。无论采用哪种方式，均需确认控制文档的 gate 状态机与 Gateflow 的 gate order 一致。
- **修复风险（低）**: 纯文档修改，不影响代码行为。
- **严重程度（低）**: 不影响 correctness，不影响 S4 内容正确性，仅影响控制文档自身的状态机完备性。

### 02-未修复-低-S4-implementation-artifact 对 dayu/fins/README.md 和 tests/README.md 的 "无需更新" 判断缺少直接证据

- **入口/函数**: S4 implementation artifact 的 Docs Decision 节
- **文件(行号)**: `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-implementation-codex.md:26-27`
- **输入场景**: S4 artifact 声明 `dayu/fins/README.md` 和 `tests/README.md` 已检查且无需更新
- **实际分支**: artifact 给出结论性判断但未提供具体检查证据
- **预期行为**: review-quality 的 implementation artifact 应至少记录检查了什么（如 "当前 Fins README 第 X 段已描述 process-backed 边界"）或提供 grep 输出作为证据
- **实际行为**: 仅给出 "checked; no new change needed because..." 的结论性叙述，无具体行号、段落引用或 grep 证据
- **直接证据**: artifact 第 26-27 行对 fins/README 和 tests/README 的判断仅为结论性文字，缺少可验证的引用。对比：对 config/README 的判断（第 25 行）虽然也是结论性，但本次 review 已独立验证该判断正确（config/README.md:147 确实已包含所需文档）。
- **影响**: 轻微。plan 的 S4 触发条件对 fins/README 是 "only if Fins read tool process-backed/XBRL behavior description changes beyond tests"，对 tests/README 是 "only if a new fixture category, marker, or test running rule is added"。这两个触发条件在当前 S4（纯 docs slice）下几乎一定不成立，因此判断本身大概率正确。但 artifact 作为 controller 裁决依据时，缺少可独立验证的证据会降低 confidence。
- **建议改法和验证点**: 在 artifact 中补充简短的具体引用，例如 fins/README 中已有的 process-backed 描述段落位置，或 tests/README 中不包含新 marker/fixture 的确认。
- **修复风险（低）**: artifact 补充性修改，不影响任何生产或测试代码。
- **严重程度（低）**: 不影响 S4 实施正确性，仅影响 review artifact 的证据完备性。

## 逐项审查结论

### 1. README 改动是否符合各 README 的 Agent 更新约束和读者边界

**dayu/README.md**:
- Agent更新约束要求："只写当前代码已实现的总揽级设计意图"、"不写未来计划、路线图、未落地能力或实现细节"
- 新增行描述了 `process_tool_completed_envelope` 等三个已存在于 `dayu/contracts/tool_execution.py` 的公共函数，属于当前已实现能力的总揽级描述 ✓
- 放置在 `dayu.contracts` 公共契约导出列表中的正确位置（工具声明类型之后、工具调用请求之前）✓
- 未引入 Host runtime 细节、未伪装为业务事实 ✓
- **结论：符合约束，无问题。**

**dayu/host/README.md**:
- Agent更新约束要求："只写当前代码已实现的设计意图...当前代码已实现的开发接口"
- ToolRuntime 段落的修改全部描述当前已实现行为（envelope 来源、hint 映射、schema 边界）✓
- 未引入未来计划或未落地能力 ✓
- **结论：符合约束，无问题。**

### 2. Host README 关于 process-backed envelope、structured hint、ToolSchema/LLM schema 边界是否准确

- "只返回 `dayu.contracts` 定义的 JSON 信封"：已验证 helpers 在 `dayu/contracts/tool_execution.py`，tools 通过 `dayu.contracts` import，无本地重复常量 ✓
- "failed 信封的 `hint` 会映射到结构化 `ToolResultFailure.hint`，不拼入 `message`"：已验证完整数据链路 `parse_process_tool_envelope → _tool_outcome_from_process_envelope → _tool_failed_outcome → ToolResultFailure(hint=hint)` ✓
- "execution capability 与 process-backed 信封字段不进入 Engine-facing `ToolSchema` 或 LLM-facing schema"：与 plan、design 和 `tests/contracts/test_tool_declaration.py` 覆盖一致 ✓
- **结论：描述准确，与代码真源一致。**

### 3. dayu/README 的 contracts summary 是否准确表达 public contract

- "工具子进程和 Host / ToolRuntime 共享的 process-backed 执行信封契约"：准确 —— tools 构造信封（通过 `process_tool_failed_envelope` 等），Host/ToolRuntime 解析信封（通过 `parse_process_tool_envelope`）✓
- "只表达子进程完成或失败结果"：准确 —— completed/failed 是子进程允许表达的唯一业务结果 ✓
- "不进入 LLM-facing tool schema"：准确 —— envelope 字段不在 `ToolSchema` 中 ✓
- "也不承载 Host cancel / timeout / awaiting 状态机"：准确 —— 这些是 Host-governed，不进入 envelope contract ✓
- **结论：描述准确，不把 Host runtime 细节伪装成业务事实。**

### 4. 总控状态是否正确

- gate: `implementation` → `implementation completed`：反映 S4 implementation 已完成，但未提前写 `review` 或 `final-closeout-pass` ✓
- implementation status：新增 S4 完成记录，artifact 路径正确 ✓
- next entry point："Aggregate / final review for WU-TOOLS-CANCEL-01 residual hardening after Slice S4"：正确表达下一步是 aggregate/final review，不是 final-closeout-pass ✓
- WU-TOOLS-CANCEL-01 行：status 更新为 `implementation completed`，定位文本更新为 "当前下一步为 aggregate / final review" ✓
- PR/issue 状态：未修改。仍然声明 "PR #170 不得 mark ready 或 merge，直到 reopened gates 再次到达 final-closeout-pass" ✓
- 默认 next work unit：仍然是 WU-WAIT-04（等待 WU-TOOLS-CANCEL-01 完成后）✓
- **结论：控制状态正确。S4 implementation completed，aggregate/final review next，未提前写 final-closeout-pass，未改 PR/issue 状态。**（见 Finding 01 关于 gate 字段值的次要观察）

### 5. S4 validation artifact 是否记录了足够证据，且残余风险归属准确

- 测试验证矩阵完整：Host 89 passed、runtime interruptible process 19 passed、Web 34 passed + 1 skipped（已说明 skip 原因）、Fins 33 passed、Service assembly 52 passed ✓
- pyright 0 errors ✓
- git diff --check passed ✓
- import-boundary tests 25 passed ✓
- contracts tool declaration 10 passed ✓
- Grep 证据：`_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` / `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` 在 tool_runtime.py 中无匹配 ✓
- Grep 证据：`_DOC_PROCESS_*` / `_FINS_PROCESS_*` / `_WEB_PROCESS_*` 在 tools/fins 中无匹配 ✓
- 残余风险归属准确：
  - Live browser cleanup → 归属于 S2B 环境依赖，非 S4 blocker ✓
  - Web process cold-start → 归属于 prior controller 裁决（performance-only），非 S4 blocker ✓
- config/README.md 的 "已包含" 判断经本次 review 独立验证为正确（line 147）✓
- **结论：validation 证据充分，残余风险归属准确。**（见 Finding 02 关于 fins/README 和 tests/README 证据完备性的次要观察）

## Open Questions

无。

## Residual Risk

- **Control doc gate taxonomy**: `implementation completed` 未在状态约定中显式定义（Finding 01）。不影响当前 WU 推进，但建议在 control doc 状态约定中补充该值，或在进入 review gate 时改用已定义的 gate 值。
- **S4 artifact evidence completeness**: 对 fins/README 和 tests/README 的 "无需更新" 判断缺少直接引用证据（Finding 02）。判断本身大概率正确（两个 README 的触发条件在纯 docs slice 下几乎一定不成立），但 artifact 的 review-quality 可进一步提升。
- **S4 是纯 docs slice**：无生产代码或测试代码变更。所有行为风险（live browser cleanup、Web cold-start）已在 S2B/S3 中归属，S4 未引入新风险。

## Conclusion

**PASS**

S4 的三项文档改动（dayu/README.md、dayu/host/README.md、docs/host/issues-implementation-control.md）均：
- 与 S4 plan 一致
- 与代码真源一致（经独立验证）
- 符合各自 README 的 Agent 更新约束
- 准确表达 process-backed envelope contract、hint 映射和 schema 边界
- 正确标记控制状态为 S4 implementation completed → aggregate/final review next，未提前写 final-closeout-pass

两项低严重度 finding（control doc gate 字段值、artifact 证据完备性）均不影响 S4 正确性或 WU 推进，可在 aggregate/final review 或后续 control doc 维护中处理。
