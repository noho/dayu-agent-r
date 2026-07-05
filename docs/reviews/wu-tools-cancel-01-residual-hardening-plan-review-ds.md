# WU-TOOLS-CANCEL-01 Residual Hardening Plan — Adversarial Plan Review (DS)

## Review Metadata

- **Reviewed target**: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`
- **Review scope**: residual hardening plan only; no implementation, no code modification, no commit/push
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md`
- **Reopen decision**: `docs/reviews/wu-tools-cancel-01-residual-risk-reopen-controller.md`
- **Review date**: 2026-07-05
- **Review posture**: constructively adversarial; default assumption is skepticism until evidence supports sufficiency

## Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|-----------|----------|---------|
| A1 | Process envelope constants are duplicated across Host/tool_runtime.py, Doc, Fins, and Web tools | grep confirms `_PROCESS_ENVELOPE_*` in `tool_runtime.py:250-256`, `_DOC_PROCESS_*` in `doc_tools.py:77-82`, `_FINS_PROCESS_*` in `fins_tools.py:79-84`, `_WEB_PROCESS_*` in `web_tools.py:164-169` | **Confirmed** |
| A2 | Host `_failed_outcome_from_process_envelope` hardcodes `hint=None` | `tool_runtime.py:6606`: `hint=None` is hardcoded; `ToolResultFailure.hint` field already exists at `tool_result.py:91` | **Confirmed** |
| A3 | Tools append hints into `message` because Host doesn't consume `hint` | `web_tools.py:1645`: docstring says "不消费独立 hint 字段；因此这里把 hint 合入 message"; `doc_tools.py:1220` and `fins_tools.py:1334` also concatenate | **Confirmed** |
| A4 | `InterruptibleProcessHandle.terminate`/`.kill` target only direct `multiprocessing.Process` | `interruptible_process.py:182-234`: `self._process.terminate()` and `self._process.kill()` on the direct child only | **Confirmed** |
| A5 | Playwright backend creates nested `multiprocessing.Process` for worker | `web_playwright_backend.py:506-508`: `ctx.Process(target=_playwright_process_entry, ...)` inside `_run_playwright_worker_process` | **Confirmed** |
| A6 | `_PROCESS_CAPSULE_*` grace constants are raw hardcoded magic numbers | `tool_runtime.py:325-326`: `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS = 0.2` and `_PROCESS_CAPSULE_KILL_GRACE_SECONDS = 0.2` | **Confirmed** |
| A7 | AAPL 2024 10-K XBRL fixture exists and is complete | `ls workspace/portfolio/AAPL/filings/fil_0000320193-24-000123/`: 10 files including `.xsd`, `_cal.xml`, `_def.xml`, `_htm.xml`, `_lab.xml`, `_pre.xml`, `.htm`, `meta.json` | **Confirmed** |
| A8 | `dayu.contracts` does not import Host/Engine/Service/UI/Fins | `contracts/__init__.py:31-32`: "禁止 import dayu.engine 或上层任何包" | **Confirmed** |
| A9 | `dayu.runtime` does not import Host/Engine/Service/UI/Fins | `interruptible_process.py:1-5`: "只负责本地子进程启动...不理解 Host Run/Attempt、Engine 协议、工具语义或业务事实" | **Confirmed** |
| A10 | `ProcessBackedToolTarget` docstring describes current envelope shape (without hint) | `tool_execution.py:64-68`: envelope docstring lists `"completed": value` and `"failed": error_type, message` — no `hint` field | **Confirmed** |

## Findings

### F1-NEEDS-FIX-[中]-S1-wiring-path-omits-DeclaredToolExecutionCapsuleFactory

- **位置**: S1 "Add `ProcessCapsuleInterruptPolicy` and wire it from `HostToolingOptions` to `ToolRuntimeBuildRequest` to `ProcessBackedToolExecutionCapsule`"
- **问题类型**: 不可直接实施
- **当前写法**: Plan 描述 policy 的 wiring path 为 `HostToolingOptions` → `ToolRuntimeBuildRequest` → `ProcessBackedToolExecutionCapsule`，但没有提及中间的 `DeclaredToolExecutionCapsuleFactory`。
- **反例/失败场景**: Implementation agent 按 plan wiring path 实现时会发现中间断裂：`ToolRuntimeBuildRequest` 在 `DefaultToolRuntimeFactory.create_tool_runtime()`（line 3941）中被消费，它创建的是 `DeclaredToolExecutionCapsuleFactory(effective_bundle)`（line 3987），然后 `DeclaredToolExecutionCapsuleFactory.create_capsule()`（line 1556）通过 `_declared_capsule_for_execution()`（line 1621）创建 `ProcessBackedToolExecutionCapsule(target)`。policy 需要穿透三层：`ToolRuntimeBuildRequest` → `DefaultToolRuntimeFactory` → `DeclaredToolExecutionCapsuleFactory` → `ProcessBackedToolExecutionCapsule`。如果 plan 没有明确指出 `DeclaredToolExecutionCapsuleFactory` 也需要接受 policy，agent 可能把 policy 放在 `ToolRuntimeBuildRequest` 后面就认为 task 完成了，但实际 capsule 仍然用 hardcoded 0.2。
- **为什么有问题**: S1 的 allowed files 包括 `dayu/host/tool_runtime.py`，覆盖了 `ProcessBackedToolExecutionCapsule` 的定义位置，但没有显式要求 `DeclaredToolExecutionCapsuleFactory(init)` 增加参数，也没有说明 `_declared_capsule_for_execution` 需要透传 policy。agent 可能只改 `ProcessBackedToolExecutionCapsule.__init__` 加参数，然后发现调用方没有传入而编译失败，导致返工。
- **直接证据**: `tool_runtime.py:1544-1581` (`DeclaredToolExecutionCapsuleFactory` 当前无 policy 参数)、`tool_runtime.py:1584-1624` (`_declared_capsule_for_execution` 直接创建 capsule 无 policy)、`tool_runtime.py:1753-1756` (`ProcessBackedToolExecutionCapsule.__init__` 只接受 `target`)、`tool_runtime.py:3984-3987` (`DefaultToolRuntimeFactory` 创建 `DeclaredToolExecutionCapsuleFactory` 只传 `effective_bundle`)。
- **影响**: 实施 Agent 跑偏 → 后续返工
- **建议改法和验证点**: S1 的 "Exact changes" 中补充一句："`DeclaredToolExecutionCapsuleFactory.__init__` 接受并保存 `ProcessCapsuleInterruptPolicy`，`create_capsule` 在创建 `ProcessBackedToolExecutionCapsule` 时传入 policy；`DefaultToolRuntimeFactory.create_tool_runtime` 从 `request` 中提取 policy 传入 capsule factory。" S1 validation 中增加一条：`grep -rn "_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS\|_PROCESS_CAPSULE_KILL_GRACE_SECONDS" dayu/` 确认不再出现 hardcoded magic number。
- **修复风险（低）**: 只涉及 plan 文本细化，不改变设计方向。
- **严重程度（中）**: 不修复会导致 implementation agent 在正确的 wiring path 上走弯路。

### F2-NEEDS-FIX-[中]-S2-smoke-design-overclaims-real-browser-cleanup-proof

- **位置**: S2 "Playwright backend smoke using a fake picklable worker that starts a nested subprocess or long-lived child; assert cleanup returns promptly and no child PID remains on POSIX"
- **问题类型**: 测试缺口
- **当前写法**: Plan 提出用 "fake picklable worker" 做 Playwright cleanup smoke，并在 residual risks 中承认 "Live Playwright browser cleanup may remain environment-dependent if browser binaries are unavailable; deterministic nested-child smoke is still required."
- **反例/失败场景**: Fake worker 创建的是普通 `multiprocessing.Process` 嵌套子进程，但真实的 Playwright Chromium 浏览器子进程是通过 `browser.launch()` → `popen.spawn` 创建的，它们的进程组继承行为可能与 `multiprocessing.Process` 子进程不同。Synthetic test 通过后，agent 可能错误地声称 "Playwright cleanup is proven"，但真实浏览器环境（尤其是 headless Chromium 的 zygote 进程、GPU 进程、renderer 进程、utility 进程等多层子进程树）可能仍有 survivor processes。
- **为什么有问题**: Plan 在 success signal 中写 "Playwright cleanup smoke proves no same-process fallback and no surviving worker process in the tested cancellation/timeout path"，但 fake worker smoke 只能证明 synthetic nested child 被清理，不能证明 real Chromium 子进程树被清理。这不是 plan 设计缺陷——plan 的 residual risks 已诚实记录了这个限制——但 success signal 的措辞可能让 reviewer 误以为 real browser 清理已被充分证明。
- **直接证据**: Plan 行 188: "Add a Playwright backend smoke using a fake picklable worker that starts a nested subprocess or long-lived child; assert cleanup returns promptly and no child PID remains on POSIX."；Plan 行 292: "Live Playwright browser cleanup may remain environment-dependent if browser binaries are unavailable; deterministic nested-child smoke is still required."
- **影响**: review 不可验收 → 风险后移
- **建议改法和验证点**: (a) 将 success signal 中的 "no surviving worker process" 限定为 "no surviving synthetic nested child process"; (b) S2 中增加一条 explicit validation assertion: 当浏览器二进制可用时，运行一次真实 Playwright browser cleanup 验证（可以作为 manual smoke 或 `test_smoke_web_ci.py` 的变体），若浏览器不可用时明确记录 skipped；或 (c) 在 S2 stop condition 中补充："If real Playwright browser binaries are available in the test environment, the cleanup smoke must also exercise a real browser launch and verify no surviving Chromium subprocesses after kill."
- **修复风险（低）**: 只调整 success signal 措辞和 stop condition，不改变实现策略。
- **严重程度（中）**: 不修复会导致 review/controller 验收时对 "Playwright cleanup is proven" 产生分歧。

### F3-NEEDS-FIX-[低]-S3-grep-test-scope-narrower-than-duplicated-constants

- **位置**: S3 "Add a grep-style test or assertion to prevent local `_DOC_PROCESS_STATUS_FIELD`, `_FINS_PROCESS_STATUS_FIELD`, and `_WEB_PROCESS_STATUS_FIELD` from reappearing"
- **问题类型**: 测试缺口
- **当前写法**: Plan 只列出了三个 `_STATUS_FIELD` 常量，但每个工具包实际复制了 6 个常量。
- **反例/失败场景**: 迁移完成后，某个工具包可能重新引入 `_DOC_PROCESS_VALUE_FIELD = "value"` 或其他未被 grep-test 覆盖的常量，而现有的 grep assertion 不会捕获。
- **为什么有问题**: Plan 要求 single-source contract，但只验证了 status field 没有被重新引入。`value`、`error_type`、`message`、`completed`、`failed` 字段常量同样被复制且同样需要防止回退。如果只 grep status field，一个 future change 可能在工具包中重新定义 `_WEB_PROCESS_MESSAGE_FIELD = "message"` 而测试不会失败。
- **直接证据**: `doc_tools.py:77-82` 定义 6 个常量 (`_DOC_PROCESS_STATUS_FIELD` 到 `_DOC_PROCESS_MESSAGE_FIELD`)；`fins_tools.py:79-84` 定义 6 个常量；`web_tools.py:164-169` 定义 6 个常量。Plan S3 行 230 只列出 3 个 status field 常量。
- **影响**: 后续返工（未来变更重新引入未覆盖的重复常量）
- **建议改法和验证点**: S3 的 grep-test 应覆盖 ALL 已迁移的 envelope 字段常量。建议改为："Add a grep-style test or assertion to prevent any local `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, or `_WEB_PROCESS_*` envelope constant from reappearing after migration." 或者列出完整的 6 字段集合：`STATUS_FIELD`, `COMPLETED_STATUS`, `FAILED_STATUS`, `VALUE_FIELD`, `ERROR_TYPE_FIELD`, `MESSAGE_FIELD`。
- **修复风险（低）**: 纯属测试 grep pattern 扩展。
- **严重程度（低）**: 当前的 status field grep 至少覆盖了最关键的重复点，但不够完整。

### F4-NEEDS-FIX-[低]-ProcessBackedToolTarget-docstring-stale-after-hint-contract-change

- **位置**: S1 和 `dayu/contracts/tool_execution.py:64-68`
- **问题类型**: 契约缺失
- **当前写法**: Plan S1 描述新的 failed envelope 包含 `hint` 字段，但没有显式要求更新 `ProcessBackedToolTarget.__call__` docstring 中的 envelope shape 描述。
- **反例/失败场景**: 新的 `process_tool_failed_envelope(...)` helper 返回包含 `hint` 的 envelope，但 `ProcessBackedToolTarget` Protocol 的 docstring 仍描述旧 shape `{"status": "failed", "error_type": str, "message": str}`，导致工具开发者参考 docstring 时遗漏 `hint` 字段。
- **为什么有问题**: `ProcessBackedToolTarget` 是公共 Protocol，其 docstring 是工具开发者理解 process-backed envelope contract 的主要入口。如果 contract helpers 已经更新但 Protocol docstring 仍是旧的，会产生文档与实现不一致。
- **直接证据**: `tool_execution.py:64-68`: envelope docstring 仅为 `"completed"`, `"value"` 和 `"failed"`, `"error_type"`, `"message"`，没有 `hint` 字段。
- **影响**: review 不可验收 → 文档与契约不一致
- **建议改法和验证点**: S1 "Add contract constants/helpers/parser" 中补充："Update `ProcessBackedToolTarget.__call__` docstring to include optional `hint` field in the failed envelope shape." 同时作为 S4 validation 的 grep：确认 `tool_execution.py` 中的 envelope docstring 包含 `hint`。
- **修复风险（低）**: docstring 更新。
- **严重程度（低）**: 不影响代码正确性，但会误导未来工具开发者。

### F5-DEFER-CANDIDATE-[低]-Web-cold-start-and-S2-process-group-cleanup-interaction-unexplored

- **位置**: Non-goals "Do not optimize Web process cold-start unless inspection proves it weakens cancellation robustness" 与 S2 process-group cleanup
- **问题类型**: open question 未收敛
- **当前写法**: Plan 将 Web cold-start 判定为 performance-only 并 defer，同时 S2 引入新的进程组清理机制。
- **反例/失败场景**: 如果 Playwright 浏览器进程树在冷启动期间尚未完全形成（例如 zygote 进程已创建但 renderer 进程尚未 fork），此时 cancel 触发的 process-group kill 可能只杀掉部分进程树，留下 orphan GPU 进程或 utility 进程。当前（S2 前）的 direct-child-only kill 同样有这个问题，所以 S2 没有引入新风险，但 S2 也没有让情况更安全——它只是声称比 direct-child 更完整。
- **为什么有问题**: 这不是 S2 引入的新缺陷，而是 cold-start + process-group cleanup 的固有边界条件。Plan 在 residual risks 中提到了 cold-start 仍 deferred，但没有说明 S2 的 process-group cleanup 在冷启动边界条件下的预期行为。
- **直接证据**: Plan 行 291: "Web process cold-start remains deferred as performance-only unless S2 proves it weakens cancellation robustness." Plan 行 127: "Do not encode Web or Playwright names in runtime."
- **影响**: 风险后移（后续 phase 需要重新验证冷启动下的 cleanup 行为）
- **建议改法和验证点**: 在 S2 stop condition 或 residual risks 中增加一条："如果 process-group cleanup 测试发现浏览器冷启动期间部分子进程的进程组归属不稳定（例如 zygote 在 fork 前未继承父进程组），记录为已知 OS 边界条件，不作为 S2 blocker。"
- **修复风险（低）**
- **严重程度（低）**: Defer 候选；不阻塞当前 plan 实施。

## Architecture Boundary Verification

逐条核对 plan 是否违反架构硬约束：

| 检查项 | 结论 | 证据 |
|--------|------|------|
| `dayu.contracts` 不 import Host/Engine/Service/UI/Fins | **通过** | `contracts/__init__.py:31-32` 已声明禁止；plan S1 将 envelope contract 放在 `dayu.contracts.tool_execution`，该模块当前只 import `dayu.contracts.json_value` 和 `dayu.contracts.tool_call` |
| `dayu.runtime` 不 import Host/Engine/Service/UI/Fins | **通过** | `interruptible_process.py` 当前无此类 import；plan S2 只增加 OS-level 抽象，不引入业务层依赖 |
| Host 不 import 具体 tool 包 | **通过** | Plan non-goals 明确 "Do not make Host import `dayu.tools`, `dayu.fins`, or concrete Web/Doc/Fins modules"；S1 stop condition 有验证 |
| Tools 不 import Host internals | **通过** | Plan S3 要求 tools 使用 `dayu.contracts` helpers 而非 Host 常量 |
| 无反向依赖 | **通过** | 所有依赖方向为 `contracts ← runtime ← host ← service`，plan 未引入反向 import |
| `dayu.runtime` 层中立 | **通过** | Plan S2 明确 "Do not encode Web or Playwright names in runtime" |
| 无 `Any`/`object`/untyped 签名 | **需实施时验证** | Plan 提出 typed `ProcessCapsuleInterruptPolicy` dataclass，符合要求；具体实现时需验证 |
| 工具 schema 不暴露 envelope/governance 字段 | **通过** | Plan non-goals 明确 "Do not expose process envelope governance fields in LLM-facing tool schema" |

## Special Lens Reviews

### Over-engineering Review

Plan 没有引入注册表、通用 supervisor、新状态机、durable schema 或平台化能力。增加的 contract（process envelope helpers）和 typed policy（`ProcessCapsuleInterruptPolicy`）都对应已存在的隐式约定。Process-group cleanup 只因为 Playwright 引入嵌套子进程而需要。**无过度设计发现。**

### Over-coupling Review

S1 将 `ProcessCapsuleInterruptPolicy` 通过 `HostToolingOptions` → `ToolRuntimeBuildRequest` → `ProcessBackedToolExecutionCapsule` 链传递。这条链已经在当前代码中存在（`HostToolingOptions` 的 wait adapter/registry 也是沿此路径流转），不是 plan 新引入的耦合。**无新增过度耦合。**

但有一个可优化点：`ProcessCapsuleInterruptPolicy` 的 default 0.2/0.2 同时出现在 plan（contract definition）、`host_runtime.json`（config default）、和 `HostRuntimeProfileConfig`（typed config default）三处。Plan S1 说 "Default values should preserve current behavior unless tests prove a larger value is required: 0.2 / 0.2 as named defaults are acceptable." 但没有指定哪一层是 single source of default truth。如果 config loader 的 default 和 typed dataclass 的 default 不一致，会产生难以发现的漂移。建议在 S1 中明确默认值的单真源位置（推荐 typed dataclass 的 `field(default=0.2)`，config default 只在不提供时 fall through）。

### Optimal-solution Review

Plan 选择的方案是最小路径：把现有的 duplicated 常量和 hardcoded 数字提升为 typed contract/policy。其它可能方案（在 tools 中保留本地常量但做 import-time assert 校验一致性，或把 process-group cleanup 放到 Web backend 而非 runtime）复杂度更高或违反 layering。**当前方案是最优的。**

### Best-practice Review

Process envelope contract 放在 `dayu.contracts` 符合项目已建立的 pattern（`tool_await.py`, `tool_call.py`, `tool_declaration.py` 等都在 contracts 包中）。Process capsule policy 通过 typed dataclass + config → assembly → capsule 链传递符合 Host 现有的 config/projection 模式。Process-group cleanup 在 runtime 层提供 OS abstracted primitive 符合 `interruptible_process.py` 现有的单一职责。**符合项目最佳实践。**

## Slice 切分评估

Plan 的 4 slices 边界清晰：

- S1 (contract/policy/config): 可独立验证——contract helpers 可单独测试，config parsing 可单独测试，无需 tool migration。
- S2 (process-group cleanup): 可独立验证——有独立的 OS-level 测试和 Web smoke，不依赖 S1 contract。
- S3 (tool migration + XBRL fixture): 依赖 S1 contract 被定义后才能迁移 tools；S2 不阻塞 S3。
- S4 (docs/validation): 依赖前三个 slices 完成后才能做最终验证。

S2 和 S3 可以并行（S2 不依赖 S1 contract，S3 依赖 S1），适合 pipeline 执行。

四片符合 control doc 的 "中型跨 contract / provider / projection work: 3-5 个 implementation slices" budget。Plan 在 "Why This Is Not Over-Designed" 中解释了不同 failure mode 的隔离需求，理由充分。

**Slice 切分合理，无需调整。**

## Test Coverage Assessment

| 测试 | 覆盖目标 | 评估 |
|------|----------|------|
| S1 Host envelope tests | completed, failed with/without hint, malformed, reserved/unknown statuses | **充分** — 覆盖了 plan 的 contract 变更的所有路径 |
| S1 Host tooling/options tests | default policy and invalid values | **充分** — 默认值验证和非法值 fail-fast |
| S1 Service assembly test | config → HostToolingOptions 透传 | **充分** |
| S2 `test_interruptible_process_group_kills_nested_child_on_posix` | process-group terminate/kill能杀掉嵌套子进程 | **充分** — synthetic nested child 覆盖了 runtime 层 |
| S2 `test_interruptible_process_group_reports_unsupported_when_not_available` | 不支持的 OS 正确 fallback | **充分** |
| S2 `test_playwright_worker_process_cleanup_kills_nested_child_on_posix` | Web worker 清理走 process-group 路径 | **见 F2** — fake worker 不能完全替代真实 Playwright |
| S3 Doc/Web/Fins envelope hint tests | hint 与 message 分离 | **充分** |
| S3 Fins XBRL fixture test | `query_xbrl_facts` 通过 process capsule + AAPL fixture | **待实现验证** — fixture suitability 是已知 stop condition |
| S3 grep-test | 防止重复常量回退 | **见 F3** — scope 偏窄 |
| S4 validation commands | pytest + pyright + git diff | **充分** — 覆盖所有 affected test 文件 |

## Open Questions

| # | 问题 | 状态 |
|---|------|------|
| OQ1 | AAPL XBRL fixture 的 `xbrl_file_discovery` / processor 是否需要网络访问 taxonomy？ | Plan S3 stop condition 已覆盖：如需网络则 blocker。属于实现期验证项。 |
| OQ2 | Windows process-group cleanup 的具体行为？ | Plan S2 已将 Windows 标记为 unsupported/fallback。属于 deferred risk。 |
| OQ3 | `process_capsule_interrupt_policy` 的 config 默认值 typed dataclass default 和 `host_runtime.json` default 如何保证一致？ | Plan 未明确单真源。建议在 typed dataclass 做 single source of default truth，config 缺失时 fall through。见 Over-coupling Review 备注。 |

## Residual Risks

| 风险 | 跟踪目标 |
|------|----------|
| Web process cold-start 与 process-group cleanup 交互未验证 | 后续 phase / cold-start 专项 |
| Real Playwright browser cleanup 在真实浏览器下的验证 | S2 后 manual smoke / `test_smoke_web_ci.py` 变体 |
| Windows process-group cleanup fallback 行为 | 当前标记 unsupported，后续跨平台 phase |
| AAPL fixture 可能因 taxonomy 网络依赖不适用 | S3 implementation 时验证 |

## Plan Review Conclusion

**Verdict: PASS**

Plan 对五项用户升级的 must-fix 项（process envelope hint 结构、Playwright cleanup smoke、Fins XBRL fixture breadth、process envelope contract single-source、process capsule grace tuning）均给出了直接、基于代码证据的方案，且每个方案都有明确的 stop condition、allowed files 和验证命令。

Web process cold-start 正确保持 deferred（performance-only），不影响 cancellation robustness 判断。

Architecture layering 验证通过：contract 在 `dayu.contracts`（层中立）、process-group primitives 在 `dayu.runtime`（层中立）、Host 不 import 具体 tool 包、tools 不 import Host internals。

4 个 findings 均无 blocking severity，F1 和 F2 为中等需要修复的 plan 文本细化，F3 和 F4 为低严重度补充。F5 为 defer 候选。

修复 F1–F4 后，plan 可以安全交给 implementation agent。

### Controller-Facing Summary

```text
READY_FOR_CONTROLLER
Artifact: docs/reviews/wu-tools-cancel-01-residual-hardening-plan-review-ds.md
Verdict: PASS
Blocking findings: 0
Non-blocking findings: 4
Deferred findings: 1
Blocking open question: None
```
