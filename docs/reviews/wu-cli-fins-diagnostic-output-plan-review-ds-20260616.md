# WU-CLI-FINS-DIAG-01 Plan Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS (DeepSeek)
- **Reviewed target**: `docs/host/wu-cli-fins-diagnostic-output-plan.md`
- **Work unit**: `WU-CLI-FINS-DIAG-01` (close residuals `WU-CLI-FINS-OBS-01-R3` and `WU-CLI-FINS-OBS-01-R5`)
- **Gate**: plan (code-generation-ready review only)
- **Timestamp**: 2026-06-16T15:00:52+08:00
- **Review posture**: Adversarial — default to finding the strongest evidence-based reasons the plan is not yet safe for implementation handoff
- **Design sources consulted**: `docs/host/design.md`, `docs/engine/design.md`, `docs/host/issues-implementation-control.md`, `AGENTS.md`
- **Code facts verified**: `dayu/runtime/log.py`, `dayu/cli/main.py`, `dayu/cli/output.py`, `dayu/cli/commands/fins.py`, `dayu/cli/arg_parsing.py`, `dayu/fins/direct_events.py`, `tests/cli/test_fins_commands.py`, `tests/runtime/test_log.py`

## Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|-----------|----------|---------|
| A1 | `_build_marker_handler` uses `sys.stdout` — the root cause of log/UI channel mixing | `log.py:250` — `logging.StreamHandler(stream=sys.stdout)` | **Confirmed** |
| A2 | `main()` calls `set_level_from_flags` without stream policy | `main.py:69-75` — passes resolved `args.log_level` with all boolean flags hardcoded `False` | **Confirmed** |
| A3 | argparse normalizes `--debug`/`--verbose`/`--quiet` into `args.log_level` | `arg_parsing.py:275-312` — all five flags share `dest="log_level"` via `store_const` | **Confirmed** |
| A4 | `_safe_text_value` redacts absolute paths | `output.py:316-331` — calls `_looks_like_absolute_path`, `_ABSOLUTE_PATH_PATTERN.sub` | **Confirmed** |
| A5 | `_log_fins_direct_event_received` only logs `operation`/`event_type`/`result_status` | `fins.py:730-749` — VERBOSE line has operation + event_type; DEBUG adds result_status | **Confirmed** |
| A6 | `FinsEvent` contract already rejects absolute paths in event fields | `direct_events.py:388-423` — `_validate_safe_text` checks `_ABSOLUTE_POSIX_PATH_PATTERN` and `_ABSOLUTE_WINDOWS_PATH_PATTERN` | **Confirmed — not noted in plan** |
| A7 | No production non-CLI caller of `runtime_log.configure()` exists | `grep -rn "configure(" dayu/` — only hit is `set_level_from_flags()` which calls `configure()`; other `configure` hits are unrelated downloader methods | **Confirmed** |
| A8 | Tests currently assert diagnostic logs in `captured.out` | Plan line 28 claim — verified by plan's explicit statement that tests need updating | **Accepted (plan self-reports)** |

## Findings

### F1-未修复-中-prompt/interactive stdout 洁净回归测试不作为必须项

- **位置**: Slice 1 validation (lines 162-164) 与 Aggregate Validation (lines 311-315)
- **问题类型**: 测试缺口
- **当前写法**: Slice 1 验证只跑 `tests/runtime/test_log.py` 和 `tests/cli/test_arg_parsing.py`；更广回归 (`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`) 标记为 "Recommended wider CLI regression if time permits"（line 319-321），不强制。
- **反例/失败场景**: Slice 1 改变中央 `configure()` 默认流为 stderr 后，prompt 和 interactive 命令的 stdout 理应自动清洁。但若日志装配在 prompt/interactive 路径中通过其他 handler（如 root logger handler、第三方库 handler、caplog 交互）间接写入 stdout，则仅靠 `test_log.py` 和 `test_arg_parsing.py` 的单元测试无法发现。实现 Agent 可能在 Slice 1 完成后认为工作已结束，遗留 prompt/interactive stdout 污染未被检测。
- **为什么有问题**: 用户明确要求验证覆盖 "prompt/interactive stdout clean"（用户指令第 5 条 challenge）。R5 success signal 明确说 "CLI stdout contains only stable command result / user UI content"（plan line 38）——这是跨所有命令的全局断言，但验证矩阵只覆盖了 log 单元测试和 Fins 命令测试。prompt/interactive 是最重要的用户可见面，缺少必须验证违反 R5 success signal 的闭环要求。
- **直接证据**: Plan lines 319-321 将 prompt/interactive 回归列为 "recommended" 而非 required；Aggregate Validation (lines 311-315) 不包含 `test_prompt_command.py` 或 `test_interactive_command.py`。
- **影响**: 实施 Agent 可能漏掉 prompt/interactive stdout 污染回归；review gate 缺少必须信号来判断 R5 是否真正达成。
- **建议改法和验证点**: 在 Aggregate Validation（或 Slice 1 完成条件）中将 prompt/interactive stdout cleanliness 提升为必须验证项。至少要求一条显式测试：启动 prompt 或 interactive 命令（含 `--verbose`），断言 `captured.out` 不含 `[VERBOSE]`、`[DEBUG]` 等日志行。该测试可放在 `test_arg_parsing.py`（已有 CLI-main-level 测试模式）或新建专用测试。
- **修复风险（低）**: 只需新增一条测试，不改生产代码路径。
- **严重程度（中）**: 不阻塞 plan 结构正确性，但缺少此验证会导致 R5 success signal 的关键维度在 gate 间不可判定。

### F2-未修复-低中-FinsEvent contract 路径过滤与 output.py 脱敏的两层关系未在 plan 中调和

- **位置**: Slice 2 (lines 178-221)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan 的 Slice 2 仅关注移除 `output.py` 的 `_safe_text_value` 路径脱敏，测试只验证 `_safe_text_value` 的独立行为（"`_safe_text_value('/tmp/a') == '/tmp/a'`"）。Plan 未提及 `FinsEvent` contract 层（`direct_events.py`）已通过 `_validate_safe_text` 拒绝事件字段中的绝对路径。
- **反例/失败场景**: 实施 Agent 移除 `output.py` 的路径脱敏后运行测试，发现 FinsEvent 相关测试仍然不会产生含路径的输出（因为 contract 层已拦截）。Agent 可能困惑于"移除是否真的生效"，或错误地认为 contract 层也需要修改。更糟的情况：Agent 可能修改 contract 层的路径验证以让路径通过，从而破坏 FinsEvent 的数据安全边界。
- **为什么有问题**: Plan 未解释两层防御的关系——contract 层（数据边界）已阻止路径进入 FinsEvent 字段，output 层（展示边界）是冗余的第二道防线。移除展示层防线是安全的（因为数据层已守住），但 plan 未说明这一点，导致实施 Agent 可能：
  1. 不知道为何测试看不到路径出现；
  2. 误判 contract 层验证为"需要修改"的范围；
  3. 在非 FinsEvent 路径（如 `_failure_message_or_fallback` 读取的 `result.error_message`）上不清楚安全性。
- **直接证据**: `direct_events.py:388-423` — `_validate_safe_text` 检查 `_ABSOLUTE_POSIX_PATH_PATTERN` 和 `_ABSOLUTE_WINDOWS_PATH_PATTERN`，拒绝含绝对路径的事件字段。`output.py:316-331` — `_safe_text_value` 使用不同 regex `_ABSOLUTE_PATH_PATTERN` 做嵌入路径脱敏。两层 regex 不同，覆盖子集可能不同。
- **影响**: 实施 Agent 可能浪费精力在理解两层关系上，或在 contract 层做不应做的修改。
- **建议改法和验证点**: 在 Slice 2 的 "Exact allowed changes" 前新增一个说明段落，明确：(1) `FinsEvent` contract 已在数据层拒绝绝对路径进入事件字段；(2) `output.py` 的路径脱敏对 FinsEvent 来源的文本是冗余防线；(3) 移除展示层脱敏后，FinsEvent 字段仍不会包含路径（由 contract 保证）；(4) 非 FinsEvent 来源的文本（如 `_failure_message_or_fallback` 读取的 `result.error_message`）同样受 contract 层保护。实施 Agent 不应修改 `direct_events.py` 的 `_validate_safe_text`。
- **修复风险（低）**: 仅新增说明段落，不改变 Slice 的技术内容。
- **严重程度（低中）**: 不阻塞正确实施，但增加了实施 Agent 的认知负担和出错概率。

### F3-未修复-低-Slice 1 stop condition 的调用方审计应在 plan review 完成而非推迟到 implementation

- **位置**: Slice 1 stop conditions (lines 174-176)
- **问题类型**: 不可直接实施
- **当前写法**: "Stop if moving runtime logs to stderr breaks non-CLI callers that explicitly require stdout and cannot be repaired by the optional stream parameter."
- **反例/失败场景**: 若存在未被发现的非 CLI caller（例如 Host bootstrap、Service entrypoint、WeChat/GUI adapter），implementation 中途触发 stop condition，需回退 Slice 1 并重新设计。Plan review 阶段本可完成此审计。
- **为什么有问题**: Stop condition 的触发条件应在 plan review 中提前验证，而不是留给 implementation agent 在编码中意外发现。这浪费 implementation 时间，也可能导致 plan 需要重写。
- **直接证据**: `grep -rn "set_level_from_flags\|runtime_log.configure" dayu/ --include="*.py"` 结果：仅 `dayu/cli/main.py` 调用 `set_level_from_flags`；仅 `set_level_from_flags` 调用 `configure()`。当前无已知非 CLI 生产调用方。Plan 可将此 stop condition 替换为已验证事实："经审计，`configure()` 的唯一生产调用路径为 CLI `main()` → `set_level_from_flags()`；无 Host/Service/Engine 生产代码调用。"若未来新增调用方，`stream` 参数提供显式控制。
- **影响**: 实施 Agent 可能浪费时间做审计（本应是 plan review 职责），或更糟——不审计直接实施。
- **建议改法和验证点**: 将 stop condition 替换为已完成的审计结论。若 plan review 阶段不便修改 plan 文本，至少在 review artifact 中记录此结论供 implementation agent 参考。
- **修复风险（低）**: 审计结果已知，只需文本更新。
- **严重程度（低）**: 已知审计结果降低了实际风险；但 plan 本身未体现这一审计，属于 process gap。

## Focus Area Responses

### R3/R5 同一 work unit 处理

Plan 的论证成立：R3（脱敏过度）和 R5（通道混流）是同一输出政策的两个面。R5 先把诊断日志从 stdout 移走，R3 再把留在 stdout/stderr 上的 Fins 输出中的路径脱敏移除。两者共享 `output.py`、`fins.py`、`log.py` 的修改面，切分到两个 work unit 反而需要协调 slice 顺序。

**没有发现 hidden coupling 会因合在一起而产生意外后果。** R3 和 R5 的 slice 在文件级有交集（都触碰 `output.py`），但 slice 顺序（先日志通道分离、再 UI 脱敏移除、再诊断富化）是合理的：先确保通道正确，再调整各通道的内容策略。

### stderr 作为 runtime/CLI diagnostic log stream

**安全**。审计结果：`runtime_log.configure()` 的唯一生产调用路径是 CLI `main()` → `set_level_from_flags()` → `configure()`。没有 Host、Service、Engine 或 Fins 生产代码直接调用 `configure()`。测试代码直接调用 `configure()`，但测试应跟随新的流约定。

Plan 通过 `stream: TextIO | None = None` 可选参数保留显式控制能力。`main()` 显式传递 `stream=sys.stderr`，使 CLI 的通道策略在装配点可见。非 CLI caller（若未来出现）可通过 `stream=sys.stdout` 恢复旧行为。

**但需注意**: `_HANDLER_MARKER_VALUE = "dayu.runtime.log:stdout"` (log.py:45) 在默认流变为 stderr 后语义不再准确。Plan line 106 提到 "Rename internal marker wording away from `stdout` if needed"。建议改为 `"dayu.runtime.log:diagnostic"` 等流中立名称，避免误导调试。

### 移除 Fins UI path redaction

**符合用户裁决**。用户明确："真正敏感项只限 `dayu/config/models.json` 引用的 API key；不要泛化脱敏"。

从代码事实看：
- `FinsEvent` contract（`direct_events.py`）已在数据边界层拒绝绝对路径进入事件字段
- `output.py` 的 `_safe_text_value` 路径脱敏对 FinsEvent 来源文本是冗余防线
- Plan 正确识别了仅 API key 为敏感项，路径/文档标签/业务摘要不应被脱敏

**一条注意**: `_safe_text_value` 还被 `_failure_message_or_fallback` 使用（`output.py:370`），该函数读取 `FinsResultSummary.error_message`，同样受 contract 层保护。移除展示层脱敏后，若未来有人绕过 contract 直接构造 FinsEvent（例如测试中），路径可能出现在输出中。但这是测试问题，不是生产代码问题，且 plan 的测试更新会覆盖此场景。

### Fins direct enriched diagnostics 具体性

**足够具体，不会引入 contract 混淆**。Plan 明确：
- VERBOSE 和 DEBUG 各包含哪些字段（lines 117-118）
- 使用私有常量和 helper（line 119）
- 只传标量日志参数，不传 event 对象或 raw payload（line 120）
- 不包含 `job_id`、`sequence`、durable cursor 或 artifact ref（line 240-241）
- 不修改 `FinsEvent` contract、Service call path、Host EventLog 或 Tool Trace（Non-goals lines 244-246）

Plan 未指定精确的 helper 签名和格式字符串，但给出了字段清单和 bounded rendering 约束，对 implementation agent 足够。

### Slices code-generation-readiness

**Slice 1**: Code-generation-ready。有明确的文件列表、参数签名变更、stop conditions、验证命令和预期断言。

**Slice 2**: Code-generation-ready，但缺失 FinsEvent contract 层与 output 层的关系说明（见 F2）。

**Slice 3**: Sufficiently ready。字段清单和约束明确；helper 签名留给 implementation agent 是合理的。

**Slice 4**: 文档 closeout slice，天然 ready。

**Validation 覆盖**:
- Prompt/interactive stdout clean: **未覆盖为必须项**（见 F1）
- Fins stdout/stderr: Slice 2 和 Slice 3 的验证覆盖
- Runtime log stderr: Slice 1 的验证覆盖

### Scope boundary (issue-144, issue-145, Engine/provider redaction, diagnostic artifact)

**Plan 正确维护了所有边界**:
- Issue #144 (activity UI): 明确列为 non-goal（line 76），不做 prompt/interactive activity stream
- Issue #145 (session management): 明确列为 non-goal（line 77），不做 session resume/list/purge
- Engine/provider diagnostic redaction: 明确列为 non-goal（line 81），不重写 OpenAI-compatible runner 的诊断脱敏
- Diagnostic artifacts: 明确列为 non-goal（line 78），不新增 diagnostic artifact
- Host durable schema/EventLog/Tool Trace: 明确列为 non-goal（line 79-80）
- Fins storage/repository/ingestion contracts: 明确列为 non-goal（line 82）

没有发现 scope creep 或边界误碰。

## Open Questions

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| Q1 | `_HANDLER_MARKER_VALUE = "dayu.runtime.log:stdout"` 在默认流变为 stderr 后是否应改为流中立名称（如 `"dayu.runtime.log:diagnostic"`）？ | 低 — marker 是私有的，但名称误导调试。 | Plan 已提到 "if needed"；建议在 implementation 中直接改为中立名称，避免留下 `stdout` 字面量。 |
| Q2 | Plan line 106 说 "Rename internal marker wording away from `stdout` if needed; marker remains private." "If needed" 的判断标准是什么？ | 极低 — 不影响功能。 | 建议 implementation agent 在 Slice 1 中直接改名，无需额外裁决。 |
| Q3 | `main()` 当前硬编码所有 boolean flag 为 `False`（`main.py:70-74`）。Plan 不改此行为，仅新增 `stream=sys.stderr`。这依赖于 argparse 已将所有 flag 归一化到 `args.log_level`。若未来有人新增独立的 boolean-only flag（不共享 dest），`set_level_from_flags` 将无法感知。 | 低 — 当前所有 flag 共享 `dest="log_level"`（arg_parsing.py:275-312），无独立 boolean flag。 | 当前无需处理；若未来 arg_parsing 改变 flag 结构，需同步更新 `main()` 的调用方式。 |

## Residual Risks

| # | 风险 | 严重程度 | 建议追踪目标 |
|---|------|---------|-------------|
| R1 | 测试环境中 `caplog` 默认抓 root logger。`configure()` 设置 `propagate=False` 后 `caplog` 不自动抓 `dayu` logger 日志。若实现 Agent 不熟悉此行为，测试迁移时可能用错误方式断言日志。 | 低 | Plan 的 `log.py` docstring 已说明此事（line 14-16）。Implementation agent 应阅读 `test_log.py` 中现有 `caplog.set_level(level, logger="dayu")` 用法。 |
| R2 | FinsEvent contract（`_DISALLOWED_TEXT_FRAGMENTS` in `direct_events.py:36-51`）禁止 `job_id`、`sequence`、`cursor` 等内部治理标识出现在事件字段中。Plan 的 Slice 3 富化诊断日志使用 VERBOSE/DEBUG logging（不在 FinsEvent contract 管辖范围），不会触发此限制。但实施 Agent 若误将 diagnostic 字段写入 FinsEvent，会被 contract 拒绝。 | 低 | Slice 3 的 Non-goals 明确 "Do not change `FinsEvent` contract"（line 244）。Implementation agent 应注意区分 diagnostic log（logging 框架）和 event field（FinsEvent dataclass）。 |

## Conclusion

**PASS-WITH-RISKS**

Plan 的核心设计是正确的：R3 和 R5 作为同一输出政策的两个面合在一起处理是合理的；stderr 作为默认诊断流安全（唯一生产调用方是 CLI main）；移除路径脱敏符合用户裁决且因 contract 层已有过滤而安全；Fins direct 诊断富化有足够具体的字段清单；scope 边界（issue #144、#145、Engine 脱敏、diagnostic artifact）维护正确。

两个 material findings 均可在 plan 文本中低成本修复，不要求重写 plan 结构：

1. **F1（中）**: 将 prompt/interactive stdout cleanliness 回归从 "recommended" 提升为必须验证项。
2. **F2（低中）**: 在 Slice 2 中新增一段说明，调和 FinsEvent contract 路径过滤与 output.py 路径脱敏的两层关系。

F3 是 process gap（审计应在 plan review 完成），不影响 plan 技术内容正确性，可在 review artifact 中记录审计结论供 implementation agent 参考。

无 blocking findings。所有 open questions 和 residual risks 有明确 owner 或处理方式。

---

*Review conducted 2026-06-16 by AgentDS against plan `docs/host/wu-cli-fins-diagnostic-output-plan.md` and code facts at `1286d293`.*
