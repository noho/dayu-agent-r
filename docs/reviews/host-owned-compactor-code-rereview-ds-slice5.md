# Host-owned compactor Slice 5 fix re-review artifact

## Review metadata

- **Reviewer**: 第二路独立 review Agent (DS re-review)
- **Review date**: 2026-05-19
- **Gate**: Slice 5 fix 后 re-review
- **Role**: 独立 review Agent，不修改文件，不提交
- **Branch**: `feat/host-p10-5-public-contract-freeze`
- **Design source of truth**: `docs/host/design.md`
- **Implementation plan**: `docs/host/host-owned-compactor-plan.md`
- **Previous review artifacts**: MiMo PASS / DS PASS / Codex fix artifact
- **Fix trigger**: 总控本地复跑 `pytest tests/host/test_public_compact_smoke.py -q -rs` 时真实 DeepSeek provider 出现非 final / proposal_failed

## Scope

- Mode: current changes (re-review of uncommitted Slice 5 fix diff)
- Base: `main`
- Included files:
  - `dayu/host/llm_compaction.py` (sanitization + non-final outcome diagnosis)
  - `tests/host/test_llm_compaction.py` (updated assertions + new sanitization test)
  - `tests/host/test_public_compact_smoke.py` (retry settings + artifact verification)
  - `utils/smoke_host_public_multiturn.py` (retry settings + compactor removal continuation)
  - `docs/reviews/host-owned-compactor-code-fix-codex-slice5.md` (fix artifact)
  - `docs/reviews/host-owned-compactor-code-review-ds-slice5.md` (DS review)
  - `docs/reviews/host-owned-compactor-code-review-mimo-slice5.md` (MiMo review)
- Excluded scope: `dayu/host/` 其他核心文件、`public_smoke_support.py`
- Re-review focuses: public contract integrity, sanitization safety, retry correctness, test coverage, old terminology residue

---

## Findings

### F1-[中]-`_safe_outcome_text` 的 `_ASSIGNMENT_SECRET_PATTERN` 排除字符集缺失 URL 参数边界符，诊断信息可能被过度脱敏

- **入口/函数**: `_safe_outcome_text()` → `_ASSIGNMENT_SECRET_PATTERN.sub()`
- **文件(行号)**: `dayu/host/llm_compaction.py:59-61`
- **输入场景**: Engine runner 返回的错误 message 包含 URL query string 形态的 key 信息，例如 `?error=timeout&api_key=secret&retry=1`
- **实际分支**: `_ASSIGNMENT_SECRET_PATTERN` 的排除字符集为 `[^,\s}\]]+`，不排除 `&`、`;`、`?`、`#` 等 URL 参数边界符。regex 会从 `api_key=` 开始一直匹配到下一个被排除字符（如换行或字符串结尾），吞噬掉相邻的查询参数。
- **预期行为**: 脱敏应只替换 key 值部分，保留相邻 query 参数的诊断信息。
- **实际行为**: 值匹配在无空格、无逗号的 URL query string 中可能跨越多组 key=value，例如 `api_key=secret&retry=1` 被整体替换为 `api_key=<redacted>`，丢失 `retry=1` 诊断信息。
- **直接证据**:
  - 第 59-61 行：`re.compile(r"(?i)((?:api[_-]?key|authorization)\s*[:=]\s*)[^,\s}\]]+")` — `&`、`;` 不在 `[^,\s}\]]` 排除集中。
  - 真实 Engine runner 的 provider error body 可能来自 HTTP response body，URL-encoded query string 是常见载体。
- **影响**: 仅影响诊断质量，不会造成安全泄漏（值被替换为 `<redacted>`）。但若关键诊断参数（如 `retry=1`、`region=us-east`）被吞噬，可能误导 Host diagnostics 和 oncall。
- **建议改法和验证点**: 在排除字符集中补充 `&;?#` 等常见 URL/header 参数边界符，改为 `[^,\s}\]&;?#]+`。补充单元测试用例：输入含 `api_key=secret&retry=1` 的 message，验证 `retry=1` 仍保留。
- **修复风险（低）**: 仅扩展排除字符集，不改变脱敏语义，不影响已有测试。
- **严重程度（中）**:

### F2-[低]-`_BEARER_SECRET_PATTERN` 替换后可能产生冗余 `<redacted>` token，诊断消息中出现多次重复标记

- **入口/函数**: `_safe_outcome_text()` 两步替换顺序
- **文件(行号)**: `dayu/host/llm_compaction.py:86-91`
- **输入场景**: 错误消息同时包含 `Authorization:` 赋值形式和 `Bearer` token 形式，例如 `"Authorization: Bearer deepsecret api_key=plainsecret"`
- **实际分支**: 第一步 `_BEARER_SECRET_PATTERN` 把 `Bearer deepsecret` 替换为 `Bearer <redacted>`；第二步 `_ASSIGNMENT_SECRET_PATTERN` 匹配到 `Authorization: Bearer`（即 Header 名后紧跟字面量 `Bearer` + 空格前的部分），再次替换为 `Authorization: <redacted>`。最终消息中出现 `Authorization: <redacted> <redacted> <redacted>` 三个 token（Bearer 原始 token、Authorization header 值字面 `Bearer`、api_key 值）。
- **预期行为**: 两条脱敏规则不应在同一个语义段落上交叉触发，产生多余 token。
- **实际行为**: 同一段 original secret 被两条规则各自匹配一次，加上 api_key 规则再匹配一次，生成 3 个 `<redacted>` token 对应 2 个原始 secret。不影响安全，但诊断消息可读性下降。
- **直接证据**:
  - 第 58 行：`_BEARER_SECRET_PATTERN` 匹配 `Bearer <token>`
  - 第 59-61 行：`_ASSIGNMENT_SECRET_PATTERN` 也匹配 `Authorization: <任意值>`（第一步替换后 `Authorization:` 后的值是字面 `Bearer`）
  - 测试第 152-158 行只验证 `deepsecret not in message` / `plainsecret not in message`，不验证 `<redacted>` token 出现次数。
- **影响**: 仅影响诊断可读性，不影响安全。3 个 `<redacted>` vs 2 个 secret 的关系对 oncall 不透明。
- **建议改法和验证点**: 可考虑先执行 `_ASSIGNMENT_SECRET_PATTERN` 再执行 `_BEARER_SECRET_PATTERN`，或使用更精确的 regex 避免 Authorization header 字面值 "Bearer" 被二次捕获。低优先级改进。
- **修复风险（低）**: 调整替换顺序不影响安全语义。
- **严重程度（低）**:

### F3-[低]-`_run_agent_request_sync` 的 `raise state.error` 路径绕过脱敏

- **入口/函数**: `_run_agent_request_sync()` → `raise state.error`
- **文件(行号)**: `dayu/host/llm_compaction.py:245-246`
- **输入场景**: Engine async runner (`run_agent_and_wait`) 在线程中抛出包含敏感信息的异常（如 provider SDK 的 HTTPError 包含 Authorization header）。
- **实际分支**: `_run_agent_request_in_thread` 在第 305 行 catch `BaseException` 并存入 `state.error`，`_run_agent_request_sync` 在第 245-246 行直接 `raise state.error` 原样透传。
- **预期行为**: 所有从 `LLMContextCompactor.compact()` 抛出的异常都应经过脱敏处理。
- **实际行为**: 若 Engine runner 抛出的异常消息包含 API key / Bearer token / Authorization header，会绕过 `_non_final_outcome_message` 和 `_safe_outcome_text` 的脱敏路径，原样泄漏到上层 Host compaction operation。
- **直接证据**:
  - 第 232-249 行：`_run_agent_request_sync` 对 `run_agent_and_wait` 返回非 final outcome 走 `_non_final_outcome_message` 脱敏；但第 245-246 行 `raise state.error` 是直接 re-raise 原始异常，无脱敏。
  - 第 303-306 行：`_run_agent_request_in_thread` 的 `except BaseException as exc: state.error = exc` 捕获所有异常类型。
- **影响**: 若 Engine 抛出的原生异常消息中包含密钥，可能通过 Host 日志或异常链泄漏。Engine 层本身应有自己的脱敏，但 Host 不应假定 Engine 已脱敏——defense in depth 原则要求 Host 侧也对 Engine 异常做 sanitization。
- **建议改法和验证点**: 在 `raise state.error` 前对 `state.error` 的消息做 `_safe_outcome_text` 包装，或将 `state.error` 包装为 `LLMCompactionProposalError` 并附加原始异常链（cause）。验证：构造 Engine 抛 `RuntimeError("Bearer secret")` 的测试，确认异常消息不包含 `secret`。
- **修复风险（中）**: 改变异常类型可能影响上层 catch 逻辑。需确认 Host compaction operation 是否依赖异常类型做分支。建议使用 `raise LLMCompactionProposalError(...) from state.error` 保留 cause chain。
- **严重程度（低）**: Engine 层本身已有协议层脱敏预期，且真实 provider SDK 抛出的异常通常不包含完整 Authorization header。风险存在但概率较低，且属于先前已存在的路径（fix 未改变此行为）。

### F4-[低]-`EngineRunOutcomeCancelled` 的 `reason` 字段未进入诊断消息

- **入口/函数**: `_non_final_outcome_message()` EngineRunOutcomeCancelled 分支
- **文件(行号)**: `dayu/host/llm_compaction.py:267-268`
- **输入场景**: compactor runner 被取消，`EngineRunOutcomeCancelled.reason` 包含被取消的有意义上下文。
- **实际分支**: 返回固定字符串 `"compactor runner was cancelled"`，不包含 `reason`。
- **预期行为**: 诊断消息应包含脱敏后的取消原因摘要，帮助区分主动取消 vs 超时取消 vs 资源回收取消。
- **实际行为**: 所有取消原因被压平为同一消息，Host compaction operation 无法区分类别。
- **直接证据**: 第 267-268 行：直接 `return "compactor runner was cancelled"`，未使用 `outcome.reason`。
- **影响**: 取消根因诊断信息丢失，但不构成安全泄漏。当前选择是 conservative-safe 策略（宁可不暴露也不泄漏），但 `_safe_outcome_text` 已足够安全。
- **建议改法和验证点**: 改为 `f"compactor runner was cancelled reason={_safe_outcome_text(outcome.reason)}"`（与 Suspended 分支一致）。验证取消诊断信息可区分类别。
- **修复风险（低）**: `_safe_outcome_text` 已在 Failed/Suspended 分支验证安全，扩展到 Cancelled 无新增风险。
- **严重程度（低）**:

### F5-[信息]-`public_smoke_support.py` 仍有多处 "slice6" 残留

- **入口/函数**: N/A（共享支持模块的常量/字符串）
- **文件(行号)**: `tests/host/public_smoke_support.py:243,498,858,890,976,981,1193,1316,1371,1406`
- **输入场景**: 阅读代码或搜索 slice 编号时。
- **实际分支**: 不影响运行时行为。
- **直接证据**: grep 结果显示 10+ 处 `slice6` 硬编码引用（lane name、source_id、worker_id、model name、operation_name、scenario、tool_call_id、tags）。
- **影响**: 与 `test_public_compact_smoke.py`（已改为 "Slice 5"）和 `smoke_host_public_multiturn.py`（无 slice 编号）形成术语不一致，可能误导后续维护者。
- **建议改法和验证点**: 建议在 Slice 6 或独立清理 PR 中统一批量更新为 `slice5`，或在下一个 major slice 中全局重命名。
- **修复风险（低）**: 纯字符串替换，不改变行为。
- **严重程度（信息）**:

---

## 专项反例检查

### 1. Public contract：Service 不知道 ContextCompactor / Host prompt/candidate/quality

**结论：PASS**

证据链：

- `dayu/host/api.py:921-962`：`CompactorRunnerBaseline` 仅含 4 个字段：`compactor_runner_spec: RunnerSpec`、`compactor_runner_options: RunnerCallOptions`、`compact_artifact_root: pathlib.Path`、`compact_artifact_create_parent_dirs: bool`。无 `context_compactor`、`prompt`、`candidate_mapper`、`quality_check` 或 `policy_ref` 字段。
- `dayu/host/api.py:1022`：`OpenHostOptions.compactor_runner_baseline: CompactorRunnerBaseline | None` — 与 `CompactorExecutionBaseline` 已完全解除耦合。
- `dayu/host/__init__.py:58`：导出 `CompactorRunnerBaseline`，不导出 `CompactorExecutionBaseline`。
- `utils/smoke_host_public_multiturn.py`：全文搜索 `ContextCompactor` 零命中。不 import `dayu.host.compaction`。`_open_options()` 不再返回 compactor 实例。
- `tests/host/test_public_compact_smoke.py`：全文搜索 `ContextCompactor` 零命中。不 import `dayu.host.compaction`。
- `dayu/host/llm_compaction.py`：`LLMContextCompactor` 仅在 Host 内部模块，Service 不直接引用。其 `compact()` 完全由 `_agent_request()` + `_candidate_from_summary()` 内部实现 prompt 构造和 candidate 映射。

**反例检查**：未发现 Service 侧任何可接触 ContextCompactor、CompactionRequest、CompactionCandidate 或 prompt 的路径。Service 只传 RunnerSpec/RunnerCallOptions 和 artifact 路径——全部是基础设施配置语义。

### 2. 非 final runner outcome 脱敏诊断：是否泄漏 API key/Authorization/provider payload

**结论：PASS（带 F1-F3 保留意见）**

证据链：

- `dayu/host/llm_compaction.py:252-271`：`_non_final_outcome_message()` 对 4 种非 final outcome 做分类脱敏，不会把 provider payload 全文、provider_request_id 或 raw outcome dump 进异常消息。
- `dayu/host/llm_compaction.py:274-290`：`_safe_outcome_text()` 做两层脱敏（Bearer token + api_key/Authorization assignment），截断 240 字符。
- `tests/host/test_llm_compaction.py:117-158`：新增脱敏测试覆盖 `Bearer deepsecret`、`api_key=plainsecret`、`provider-request-1` 三类不泄漏断言，同时保留 503 / transient 诊断文本断言。

**反例检查发现**：
- `EngineRunOutcomeFailed.error_code` 直接拼接进异常消息（第 261-263 行），不经过 `_safe_outcome_text`。如果 Engine 错误地将敏感信息置入 `error_code` 字段，会泄漏。但 `error_code` 按 Engine contract 是"中性错误码"，不应包含秘密。风险存在于 Engine contract violation 场景，属于 defense-in-depth 缺口（低概率）。
- `_run_agent_request_sync` 的 `raise state.error` 路径（F3）绕过脱敏。

### 3. retry/attempt 设置：是否合理，不隐藏真实失败

**结论：PASS**

证据链：

- `tests/host/test_public_compact_smoke.py:35-36`：`_COMPACTOR_PROVIDER_MAX_RETRIES = 1`、`_COMPACTOR_MAX_ATTEMPTS_PER_OPERATION = 2`
- `utils/smoke_host_public_multiturn.py:80-81`：同上常量定义。
- 语义分析：
  - `RunnerSpec.max_retries=1`：Engine runner 层，首次调用失败后再重试 1 次（最多 2 次 API 调用）
  - `ContextBudgetPolicy.max_compaction_attempts_per_operation=2`：Host compaction operation 层，首次 proposal + 最多 1 次 retry（最多调用 `compact()` 2 次）
  - 最坏情况：2 × 2 = 4 次 API 调用，但若所有 attempt 均失败，operation 最终写 `CONTEXT_COMPACTION_FAILED`，Run 终态 FAILED——真实失败不会被隐藏。
  - 如果 provider 返回 `recoverable=True` 的 `EngineRunOutcomeFailed`，Host 会看到异常消息中的 `recoverable=True`，但当前实现中 Host 不解析该字段（F3 中提及的消息串解析问题），而是依赖 `max_compaction_attempts_per_operation` 做计数控制。这是正确的——recoverable 标识是给人类/日志看的诊断，不做控制流。

**反例检查**：如果真实 provider 连续 2 次返回非 final outcome，smoke test 会 FAIL（`skip_if_provider_terminal_failed` 只对 terminal event 做 skip，对 `except RuntimeError` 做 `skip_if_provider_exception`）。fix artifact 第 64-65 行承认此残余风险。当前设置不会把真实失败伪装成成功。

### 4. 测试覆盖：public opener -> Host-owned compactor -> artifact -> 多轮闭环

**结论：PASS**

证据链：

- `tests/host/test_public_compact_smoke.py:46-160`：`test_real_compactor_public_opener_compacts_and_preserves_continuity`
  - public opener：`open_host(options)` at line 109
  - Host-owned compactor：通过 `CompactorRunnerBaseline` 配置，Host 内部构造 `LLMContextCompactor`
  - artifact 验证：lines 148-159 通过文件系统对比 + JSON 解析验证 artifact 产生且内容有效
  - 多轮闭环：run1 (compact-first) → run2 (compact-second) — 两轮均通过 public `watch_session_events()` + `submit_followup()` 走完整 public contract
  - continuity 验证：line 146 `second_terminal.final_answer.content.strip() != ""` + session_id/run_id 对齐 (lines 142-145)
- `tests/host/test_llm_compaction.py`：6 个单元测试覆盖 final answer mapping、空/非 final 输出拒绝、脱敏、refs/evidence 保持、runner retry 透传。
- `utils/smoke_host_public_multiturn.py`：手工 3 轮闭环 (tool fact → memory/compact → continuity) 覆盖完整生产接线。

**反例检查**：
- 单元测试全部使用 mock Engine runner（`_fake_run_factory`），不依赖真实网络。
- Smoke test 的 provider skip 保持 env-gated，默认无网络。
- Artifact 验证的 `expected_candidate_id = f"llm-compact:{run_id}"` 硬编码了 Host 内部 candidate ID 格式（已知的知识耦合，前两路 review 已记录）。

### 5. 旧 Slice 6 术语 / compactor_baseline / caller-owned compactor 语义残留

**结论：PASS（带 F5 保留意见）**

证据链：

- `tests/host/test_public_compact_smoke.py:1`：模块 docstring 正确为 `"P10.5 Slice 5 public real-compactor smoke"`。
- `tests/host/test_public_compact_smoke.py:98`：`policy_ref="slice5-real-compact-policy"`（已从 `slice6` 改为 `slice5`）。
- `utils/smoke_host_public_multiturn.py`：全文搜索 `compactor_baseline` / `CompactorExecutionBaseline` / `slice6` / `caller-owned` — 零命中。
- 两文件均不再 import `CompactorExecutionBaseline`，改用 `CompactorRunnerBaseline`。
- 两文件均不再 import `dayu.host.compaction` 下的任何类型。
- 两文件均不再包含任何 `ContextCompactor` 子类实现。

**反例检查**：
- `dayu/host/README.md:18`：仍声明 `CompactorExecutionBaseline` 为公共导出，应与 `__init__.py` 实际导出（`CompactorRunnerBaseline`）同步。此项属于 Slice 6 的 README sync 职责。
- `tests/host/public_smoke_support.py`：10+ 处 `slice6` 引用（F5），不在本 fix diff 范围内。

---

## Open Questions

1. **Engine 异常脱敏责任归属**：`_run_agent_request_sync` 的 `raise state.error` 路径（F3）依赖 Engine 层自身做脱敏。是否应在 Engine public contract 中明确要求 `run_agent_and_wait` 不通过异常消息泄漏密钥？当前 Engine contract 文档是否已有此约束？
2. **`error_code` 字段的 sanitization 责任**：`_non_final_outcome_message` 直接将 `outcome.error_code` 拼入异常消息而不经 `_safe_outcome_text`。若 Engine 违反 contract 在 `error_code` 中放入敏感信息，Host 侧无 defense-in-depth 保护。是否需要在 Engine contract 中显式规定 `error_code` 不得包含密钥/PII？

## Residual Risk

| 风险 | 严重性 | 说明 |
|------|--------|------|
| Engine runner 异常消息泄漏密钥 | 低 | `raise state.error` 直接透传，依赖 Engine 层脱敏。F3 详述。 |
| `error_code` 字段的 defense-in-depth 缺失 | 低 | `error_code` 不经过 `_safe_outcome_text`，依赖 Engine contract 保底。 |
| `_ASSIGNMENT_SECRET_PATTERN` URL 参数过度脱敏 | 低 | `&;?#` 不在排除集中，可能导致诊断信息损失。F1 详述。 |
| 真实 provider 连续 2 次非 final | 中 | smoke 会 FAIL 而非伪装成功，符合设计意图。但当前无 retry 预算耗尽后的 structured skip，可能增加 CI 噪音。 |
| README `CompactorExecutionBaseline` → `CompactorRunnerBaseline` 未同步 | 低 | `dayu/host/README.md:18`。Slice 6 职责。 |
| `public_smoke_support.py` slice6 残留 | 信息 | 10+ 处。与其他文件 slice5 不一致。 |

---

## 结论

**PASS**

本次 Slice 5 fix 达成以下目标：

1. **Public contract 不退化**：`CompactorRunnerBaseline` 不包含 `ContextCompactor`、prompt、candidate builder、quality check 或 policy seam。Service 仍只传 RunnerSpec/RunnerCallOptions 和 artifact 路径。
2. **脱敏有效且不误导诊断**：`_non_final_outcome_message` + `_safe_outcome_text` 对 Bearer token、api_key/Authorization assignment 做模式脱敏，保留 error_code、recoverable 和截断后的短消息。provider_request_id 不进入异常消息。发现两处可改进的 defense-in-depth 缺口（F1 过度脱敏、F3 Engine 异常透传），均不构成阻塞。
3. **retry 设置合理**：runner 层 max_retries=1 + Host 操作层 max_compaction_attempts_per_operation=2，不隐藏真实持久失败。
4. **测试覆盖完整**：public opener → Host-owned compactor → artifact → 多轮闭环全链路有真实 provider smoke + 6 个 mock 单元测试。
5. **无旧术语残留**（在修改文件内）：`slice6`、`CompactorExecutionBaseline`、`compactor_baseline`、`ContextCompactor` 子类、caller-owned compactor 语义均已在修改文件内清理干净。仅 `public_smoke_support.py`（未修改文件）仍有残留。

阻塞性发现：**无**。
