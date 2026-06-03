# WU-ENG-02 Slice 2 Code Review — AgentDS

## Gate / Work Unit / Slice

- gate: code review
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 2 — RunnerSpec Policy And OpenAI-Compatible Header Mapping
- reviewer: AgentDS
- review target: 当前未提交 workspace changes for Slice 2

## 输入

- accepted plan: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- slice 2 implementation artifact: `docs/reviews/wu-eng-02-slice2-implementation-codex.md`
- control doc: `docs/host/issues-implementation-control.md`
- git diff: 37 files changed, 294 insertions(+), 46 deletions(-)

## 审查范围与方法

本审查对照 accepted plan 的 Slice 2 规格逐项检验，并额外检查：
- 是否引入 `Any` / `object` / 无类型签名（项目禁止）。
- 是否有 provider 字符串治理分支渗透。
- 是否有 Slice 3 / Tool Trace / Host ingest 越界实现。
- 构造点穷尽性：`RunnerSpec.client_correlation_policy` 为 required field 无默认值，所有构造点是否显式补齐。
- 测试覆盖是否满足 plan 列出的 scenario 矩阵。
- pyright 是否绝对干净。

审查不覆盖：Slice 1 既成代码、Tool Trace analyzer、README 同步（Slice 4 deferred）。

---

## Findings

### F1: `_build_request_headers` policy exhaustiveness 末尾守卫 unreachable 但安全

- **Severity**: Info
- **文件/行**: `dayu/engine/runners/openai/runner.py` line 191-194
- **证据**:
  ```python
  if spec.client_correlation_policy is ClientCorrelationPolicy.DISABLED:
      return headers
  if (
      spec.client_correlation_policy
      is ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID
  ):
      ...
      return headers
  raise ValueError(
      "unsupported client_correlation_policy: "
      f"{spec.client_correlation_policy.value}"
  )
  ```
  `ClientCorrelationPolicy` 是 `StrEnum`，仅有两个成员 `DISABLED` 和 `OPENAI_X_CLIENT_REQUEST_ID`。所有有效枚举值在前两个 `if` 分支中已穷尽，第三个分支在当前枚举定义下不可达。但该守卫在枚举新增成员时充当 fail-safe，防止静默忽略未知 policy。
- **影响**: 无功能影响。未消耗的守卫不会引入错误。
- **建议**: 保持现状。当前守卫是合理防御性编程。
- **可裁决状态**: 无需修改，记录即可。

### F2: 静态 header 冲突检测仅检查 key 存在，不检查 value

- **Severity**: Low
- **文件/行**: `dayu/engine/runners/openai/runner.py` line 197-209 (`_has_client_request_id_header`)
- **证据**:
  ```python
  def _has_client_request_id_header(headers: Mapping[str, str]) -> bool:
      for name, _value in headers.items():
          if name.lower() == _CLIENT_REQUEST_ID_HEADER_NAME_LOWER:
              return True
      return False
  ```
  `_has_client_request_id_header` 的 `_value` 被 `del` 风格忽略（变量名以下划线前缀表示不关心）。即使静态 headers 中 key 碰巧是 `x-client-request-id` 但 value 与动态计算值相同，当前实现仍然拒斥。这是 plan 的意图——plan 明确说 "static headers are not valid per-call identity and would make precedence ambiguous"。
- **影响**: 行为与 plan 一致。静态 header 无论 value 如何都会被拒斥，这是正确的安全决策。
- **建议**: 保持现状。接口文档已说明理由。
- **可裁决状态**: 无需修改。

### F3: `_build_request_headers` 抛出 `ValueError` 未在 `_call_impl` 上层被显式捕获并包装为 `RunnerEvent`

- **Severity**: Low
- **文件/行**: `dayu/engine/runners/openai/runner.py` line 378-381, line 395
- **证据**: `_build_request_headers` 在 `_call_impl` 的 `try` 块之前调用（line 378），因此 `ValueError` 直接向上传播给 Agent 调用方，不会被 `_call_impl` 的 `except _AttemptFailed*` 捕获。这意味着 policy/static header 冲突会导致 Agent 层的未处理异常，而非以 `RunnerHTTPErrorData` 收口。

  当前调用链：
  ```
  _call_impl() -> _build_request_headers() raises ValueError
  → 未被 try 块捕获 → 传播到 Agent._run_iteration()
  ```
- **影响**: 静态 header 冲突是配置错误（不是运行时 transient error），用异常形式 fail-fast 是合理的。但 Agent 调用方是否能正确处理 `ValueError` 并给出有意义的错误消息，目前无测试覆盖。plan 中将此列为"Reject or fail fast before HTTP post"，当前行为符合 fail-fast 语义。
- **建议**: 
  - 当前行为与 plan 的 fail-fast 语义一致，非阻塞。
  - 如果后续发现 Agent 层对 `ValueError` 的处理不友好，可以在 Agent 边界增加一层翻译（将配置冲突 `ValueError` 转为 Engine event 级别的 `RunFailedData`），但这属于 Slice 3 或后续改进范围。
- **可裁决状态**: 当前无修改，维持 plan 设计的 fail-fast 语义。

### F4: `_build_request_headers` 中枚举比较使用 `is` 而非 `==`

- **Severity**: Info
- **文件/行**: `dayu/engine/runners/openai/runner.py` line 174, 176-178
- **证据**:
  ```python
  if spec.client_correlation_policy is ClientCorrelationPolicy.DISABLED:
  ```
  由于 `ClientCorrelationPolicy` 继承自 `StrEnum`，而 `StrEnum` 成员是唯一 singleton，`is` 比较安全且正确。此外，`==` 比较会与等值 `str` 产生歧义（`ClientCorrelationPolicy.DISABLED == "disabled"` 为 `True`），因此 `is` 实际上比 `==` 更精确。
- **影响**: 无功能影响。`is` 比较是 的安全选择。
- **建议**: 保持现状。
- **可裁决状态**: 无需修改。

### F5: Test `_BaseSpecKwargValue` TypeAlias 声明类型宽度偏窄

- **Severity**: Info
- **文件/行**: `tests/engine/contracts/test_runner_spec.py` line 24-33
- **证据**:
  ```python
  _BaseSpecKwargValue: TypeAlias = (
      str | bool | float | int | dict[str, str]
      | ProviderRequestExtension | ClientCorrelationPolicy | None
  )
  ```
  `dict[str, str]` 是 `Mapping[str, str]`（RunnerSpec 字段类型）的子类型，在此测试 helper 中仅作为 kwargs value 传递，功能正确。从 `object` 迁移到具体 union 是类型安全改进。
- **影响**: 无功能影响。
- **建议**: 保持现状。比原来的 `object` 有明显改进。
- **可裁决状态**: 无需修改。

---

## 逐项检查结果

### ClientCorrelationPolicy enum 语义

| 检查项 | 结果 | 证据 |
|--------|------|------|
| docstring 声明 "不是 provider-name branches" | PASS | `runner_spec.py:73-78` |
| docstring 声明 "provider-protocol-specific outbound mapping policies" | PASS | `runner_spec.py:75` |
| Host / Agent 无 provider 字符串分支 | PASS | `runner.py:150-194` 仅在 `_build_request_headers` 用 `is` 比较 enum member，无 `if spec.provider == "openai"` 类分支 |
| enum export 正确 | PASS | `__init__.py:90,118` |

### RunnerSpec 新 required field

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `client_correlation_policy` 无默认值（required field） | PASS | `runner_spec.py:281` 类型注解无 `= ...` 默认值 |
| 生产代码构造点显式补齐 | PASS | `host_assembly.py:870`, `_execution_config_projection.py:183-185` |
| 测试工厂默认 DISABLED | PASS | `_factories.py:47-49` |
| 所有 30+ 直接构造点显式补齐 | PASS | 每个 diff 文件均增加 `client_correlation_policy=ClientCorrelationPolicy.DISABLED` |
| 无兼容 wrapper / 旧 schema 兼容读取 | PASS | `runner_spec_from_json` 使用 `required_json_text`，缺失字段直接 `HostDurableError` |

### Host `_execution_config_projection` freeze / restore

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `runner_spec_json` 序列化 `client_correlation_policy` | PASS | `_execution_config_projection.py:154-156` |
| `runner_spec_from_json` 反序列化 `ClientCorrelationPolicy(value)` | PASS | `_execution_config_projection.py:183-185` |
| 缺失字段触发 `HostDurableError`（fresh-schema 行为） | PASS | `required_json_text` 在字段不存在时抛出 |
| 测试覆盖 round-trip | PASS | `test_effective_execution_config.py:261-296` |
| round-trip 使用 `is` identity 验证 | PASS | `test_effective_execution_config.py:292-295` |

### OpenAI runner header helper

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Content-Type 默认 `application/json` | PASS | `runner.py:170-171` |
| 静态 `RunnerSpec.headers` 合并 | PASS | `runner.py:172` `**dict(spec.headers)` |
| Policy DISABLED → 不发送 header | PASS | `runner.py:174-175` |
| Policy OPENAI + identity 非 None → 发送 header | PASS | `runner.py:186-189` |
| Policy OPENAI + identity None → 不发送 header | PASS | `runner.py:186` 条件 `if request_identity is not None` |
| 静态 header 冲突 case-insensitive 检测 | PASS | `runner.py:197-209` `name.lower() == _CLIENT_REQUEST_ID_HEADER_NAME_LOWER` |
| 冲突在 HTTP post 前失败 | PASS | `_build_request_headers` 在 `_do_attempt` 调用前执行 |
| Transport retry 复用同一 header | PASS | `_call_impl:378-381` headers 在 retry loop 外构建一次，传入每次 `_do_attempt` |

### Response `x-request-id` 采集

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `_extract_provider_request_id` 未修改 | PASS | diff 中无 `_extract_provider_request_id` 变更 |
| 采集路径完整（HTTP error / SSE / non-stream） | PASS | 所有 `provider_request_id` 赋值点不变 |
| `_do_attempt` 仅新增 `headers` 参数传入，不改 response 处理 | PASS | diff 显示 `_do_attempt` 签名增加 `headers` 参数，body 处理不变 |

### 直接 RunnerSpec 构造点同步

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 所有构造点仅增加 `DISABLED`，不改变行为 | PASS | 逐个 diff 检验：每个构造点增加 `client_correlation_policy=ClientCorrelationPolicy.DISABLED` |
| 无越过 Slice 3 / Tool Trace / Host ingest 行为 | PASS | diff 范围严格限制在 Slice 2 allowed files + 直接构造点同步 |
| `_factories.py` `make_spec` 默认 DISABLED | PASS | `_factories.py:47-49` |

### Tests

| 检查项 | 结果 | 证据 |
|--------|------|------|
| enabled → 发送 header | PASS | `test_request_identity.py:130-143` |
| disabled → 不发送 header | PASS | `test_request_identity.py:147-157` |
| identity=None → 不发送 header | PASS | `test_request_identity.py:161-171` |
| static header conflict → ValueError | PASS | `test_request_identity.py:175-188` |
| transport retry → same header | PASS | `test_request_identity.py:192-229` |
| effective config round-trip | PASS | `test_effective_execution_config.py:261-296` |
| `RunnerSpec` field set 包含 `client_correlation_policy` | PASS | `test_runner_spec.py:187` |
| `ClientCorrelationPolicy` values 枚举测试 | PASS | `test_runner_spec.py:95-100` |

### pyright

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 0 errors, 0 warnings, 0 informations | PASS | 本地执行 pyright 输出 |

---

## Blocking Open Questions

无 blocking open questions。

本 Slice 2 实现完全在 plan 允许范围内，所有 stop conditions 均已处理或记录在 implementation artifact 中：

- 直接构造点同步（超出原始 allowed files）已在 implementation artifact 中记录，属于 pyright 驱动的必要补齐，不涉及行为变更。
- 其余 stop conditions 未触发。

---

## Validation Evidence

### 测试执行

```
source .venv/bin/activate && pytest \
  tests/engine/contracts/test_runner_spec.py \
  tests/engine/runners/openai/test_request_identity.py \
  tests/engine/runners/openai/test_streaming_capability_and_content_type.py \
  tests/engine/runners/openai/test_http_error_event.py \
  tests/host/test_effective_execution_config.py -q

61 passed in 0.40s
```

### pyright

```
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

### 逐文件 diff 检验

37 个变更文件逐文件审核：
- 4 个核心实现文件：`runner_spec.py`, `__init__.py`, `runner.py`, `_execution_config_projection.py`
- 1 个生产装配文件：`host_assembly.py`
- 1 个 smoke 脚本：`smoke_async_agent_providers.py`
- 28 个测试文件：直接构造点同步
- 2 个新文件：`test_request_identity.py`, `wu-eng-02-slice2-implementation-codex.md`
- 1 个 control doc：`issues-implementation-control.md`（已有修改，未在本次触及）

---

## Residual Risks

| 风险 | 等级 | Owner | 说明 |
|------|------|-------|------|
| `_build_request_headers` ValueError 传播到 Agent | Low | Slice 3 / 后续 | Policy 冲突是配置错误，fail-fast 语义正确。若 Agent 层未妥善处理 `ValueError`，可能导致未格式化的异常日志。risk 不在 Slice 2 范围内。 |
| 生产装配默认 DISABLED | Info | 产品/配置决策 | `host_assembly.py` 设置 `DISABLED`，启用需要显式配置或 profile 变更。plan 已明确此设计。 |
| 全部直接构造点使用 DISABLED，未在生产路径测试 ENABLED | Low | Slice 3 / future | 除 `test_request_identity.py` 外，所有 test/host 使用 `DISABLED`。enabled 行为仅在 OpenAI runner 层单测覆盖，未在 Host 集成路径测试。符合 Slice 2 范围，但需在 Slice 3 集成测试注意。 |
| Native Anthropic / Claude Code gateway 未实现 | Info | future adapter | plan 明确标注为 future work unit。 |

---

## Docs Decision

README 同步按 approved plan 的 Slice 4 deferred，本 Slice 2 不修改 README。确认：

- `dayu/engine/README.md`：未修改（deferred to Slice 4）
- `dayu/host/README.md`：未修改（deferred to Slice 4）
- `tests/README.md`：未修改（deferred to Slice 4）
- 根 `README.md`：无需修改（CLI/config/user workflow 不变）

符合 plan 的 Slice 4 deferred 决策。

---

## 结论

**Pass.**

Slice 2 实现质量良好：
- `ClientCorrelationPolicy` enum 语义与 docstring 严格对齐 plan 的 provider-protocol-specific 设计要求，无 provider 字符串分支。
- `RunnerSpec.client_correlation_policy` 为 required field 无默认值，所有 30+ 构造点已显式补齐，无兼容 wrapper 或旧 schema 兼容读取。
- Host freeze/restore 正确序列化/反序列化，fresh-schema 行为完整（缺失字段 → HostDurableError）。
- OpenAI runner header helper 正确实现 Content-Type + static headers + conditional X-Client-Request-Id，policy 与 identity 条件逻辑完整，冲突检测 case-insensitive 且在 HTTP post 前失败，transport retry 复用同一 header。
- Response `x-request-id` 采集路径完全未动。
- 所有 30+ 直接构造点仅增加 `ClientCorrelationPolicy.DISABLED`，无越过 Slice 3 / Tool Trace / Host ingest 行为。
- 测试覆盖 enabled/disabled/None/conflict/retry/effective config 全部 scenario，pyright 0 errors。

**Findings**: 5（0 Critical, 0 High, 0 Medium, 2 Low, 3 Info），全部无需修改或已确认 plan 预期行为。

**Blocking open questions**: 无。

**修改范围**: 仅产出此 review artifact，不修改任何代码。
