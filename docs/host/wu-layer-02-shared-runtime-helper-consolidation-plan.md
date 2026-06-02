# WU-LAYER-02 Shared Runtime Helper Consolidation Plan

## 1. Gate / Role / Scope

- Gate: `planning`。
- Role: planning specialist；本 artifact 只提供 code-generation-ready implementation plan，不修改生产代码或测试，不 commit，不 push。
- Work unit: `WU-LAYER-02 Shared Validation / Redaction / JSON Helper Consolidation`。
- 设计真源: `docs/host/design.md`。
- 总控文档: `docs/host/host-core-followup-implementation-control.md`。
- 当前裁决: 动机成立但必须收窄；只处理层中立、跨层确实重复、没有 Host durable truth / Engine provider state / tool runtime 业务语义的 helper。

## 2. First Principles Motivation / Root Cause 判断

重复是否真实，先看 helper 的输入、输出、owner 与失败后果，而不是看名字是否相同。

真实问题:

- `dayu/engine/agent.py` 与 `dayu/host/compaction_operation.py` 都在处理“异常或错误文本进入诊断 / 日志 / diagnostic ref 前必须有界且不能泄漏 secret”这一层中立运行期问题。
- 两处实现已经分叉：Engine 选择“命中 secret 时整条 message 替换为固定 redacted 文本”，Host compaction 选择“保留非敏感上下文，只替换 secret value”。这两种调用方策略不同，但底层 secret-value detection、secret-value redaction、bounded text truncation 是同一类 runtime primitive。
- Root cause 不是 Host 或 Engine 状态机错误，而是缺少一个层中立 diagnostic text primitive owner，导致 regex、长度上限处理和截断语义在业务层重复演化。

同名但 owner 不同、不得机械合并:

- `dayu/engine/runners/openai/diagnostic_payload.py` 处理 provider JSON object / invalid UTF-8 chunk 的 bounded diagnostic payload。它的 source/kind、provider error sub-object、top-level preview、bare hex digest 和 payload version 都是 OpenAI-compatible runner diagnostic 语义，不是通用 runtime text redaction。
- `dayu/runtime/_digest.py` 已经是 runtime canonical JSON digest helper，但它输出 `sha256:<hex>`，且 `allow_nan=False`；OpenAI diagnostic payload 当前输出 bare hex，并记录 `canonical_byte_size`。直接替换会改变 diagnostic 文本和 JSON canonicalization 语义。
- Host durable codec / payload / artifact / EventLog / tool trace digest 是 Host durable truth 或审计 / trace 语义，不是层中立 helper 重复。它们即使也叫 canonical JSON / digest，也必须留在 Host durable owner。
- `dayu/runtime/tool_truncation.py` 是工具声明截断 policy helper，不是 diagnostic redaction；不应把 tool runtime truncation 和 exception diagnostic text 混成一个过宽 helper。

结论:

- 本 WU 的安全生产合并目标存在，但只能收窄为 `dayu.runtime` 下的 diagnostic text primitives。
- OpenAI provider JSON diagnostic payload 本轮只做 explicitly rejected candidate 记录，不下沉。
- runtime digest 本轮不改接口、不替换现有 Host / Engine digest 调用。

## 3. Direct Evidence / Code References

- `docs/host/design.md:61` 至 `docs/host/design.md:65` 定义 `dayu.runtime` 是层中立运行期基础设施，不得承载业务语义、Host durable truth 或 Engine 协议状态机。
- `docs/host/host-core-followup-implementation-control.md:623` 至 `docs/host/host-core-followup-implementation-control.md:645` 明确 WU-LAYER-02 只合并层中立 helper，非目标包括不机械迁移 Host durable canonical JSON / digest / timestamp，不改变 audit / tool trace / EventLog 语义。
- `dayu/engine/agent.py:180` 至 `dayu/engine/agent.py:188` 定义 Engine 私有 redaction / truncation 常量和 secret regex。
- `dayu/engine/agent.py:205` 至 `dayu/engine/agent.py:228` 的 `_exception_diagnostic_message` 生成 `RunFailedData.message` 用异常类型 + 有界安全消息；命中 secret 时整条替换为 `exception message redacted`。
- `dayu/engine/agent.py:231` 至 `dayu/engine/agent.py:263` 的 `_contains_sensitive_exception_value` 与 `_safe_log_message` 重复实现 secret detection 与 bounded log text。
- `tests/engine/test_agent_phase2.py:802` 至 `tests/engine/test_agent_phase2.py:870` 已覆盖 Engine 异常诊断截断、`api key` 空格写法、Bearer / api_key / apikey / authorization / password / secret / token 明文值 redaction，以及普通 `JWT token` 文本不误伤。
- `dayu/host/compaction_operation.py:44` 至 `dayu/host/compaction_operation.py:49` 定义 Host compaction 私有安全消息长度、截断后缀、redacted marker 与 secret regex。
- `dayu/host/compaction_operation.py:649` 至 `dayu/host/compaction_operation.py:659` 把 compactor exception 安全消息写入 diagnostic suffix；这是 Host compaction operation diagnostic ref 语义，不应下沉整体 ref 构造。
- `dayu/host/compaction_operation.py:717` 至 `dayu/host/compaction_operation.py:751` 的 `_exception_error_code` 与 `_safe_exception_message` 分别负责 Host-specific `error_code=` 提取和通用 secret-value redaction / truncation。只有后者的 redaction / truncation primitive 是 runtime candidate。
- `tests/host/test_compaction_operation.py:506` 至 `tests/host/test_compaction_operation.py:521` 已覆盖 compaction diagnostic refs 不持久化 Bearer token、api_key、token、secret 明文。
- `dayu/engine/runners/openai/diagnostic_payload.py:21` 至 `dayu/engine/runners/openai/diagnostic_payload.py:63` 定义 provider diagnostic payload 版本、大小上限、key preview、source/kind、bare digest 字段与 provider error fields。
- `dayu/engine/runners/openai/diagnostic_payload.py:66` 至 `dayu/engine/runners/openai/diagnostic_payload.py:168` 暴露 provider error、protocol object、invalid UTF-8、HTTP error diagnostic payload helper，均是 OpenAI runner 内部 JSON diagnostic payload。
- `dayu/engine/runners/openai/diagnostic_payload.py:171` 至 `dayu/engine/runners/openai/diagnostic_payload.py:252` 计算 canonical byte size 与 bare SHA-256 digest；不得偷换成 runtime `_digest.canonical_json_digest` 的 `sha256:` 格式。
- `tests/engine/runners/openai/test_diagnostic_payload.py:50` 至 `tests/engine/runners/openai/test_diagnostic_payload.py:260` 已直接锁定 OpenAI diagnostic payload 的结构、redaction、fallback、invalid UTF-8 byte size 和 bare digest 语义。
- `dayu/runtime/_digest.py:19` 至 `dayu/runtime/_digest.py:58` 已提供 runtime JSON normalization 与 `sha256:<hex>` canonical digest；它是已有 runtime owner，不需要本 WU 重建。
- `dayu/runtime/__init__.py:1` 至 `dayu/runtime/__init__.py:28` 记录 runtime 当前能力清单且包根不 re-export 模块符号；新增 helper 也应保持不从包根 re-export。
- `tests/host/test_import_boundary.py:257` 至 `tests/host/test_import_boundary.py:270` 已守护 runtime 不反向 import Host / Engine / Service / UI / Fins。
- `tests/runtime/test_weak_typing_guard.py:1` 至 `tests/runtime/test_weak_typing_guard.py:203` 扫描 runtime 全部 Python 文件，阻止 `Any`、`object`、无类型签名和裸容器注解。

## 4. Candidate Files

Production candidates:

- `dayu/runtime/diagnostic_text.py`：新增层中立 diagnostic text primitive owner；只依赖标准库。
- `dayu/runtime/__init__.py`：仅更新中文概览 docstring 的 runtime 能力清单；不 re-export 新符号。
- `dayu/engine/agent.py`：删除 Engine 私有 secret regex / truncate primitive，改为调用 runtime primitive；保留 Engine 的异常类型拼接、整条 redacted 策略、错误码和 Agent 状态机。
- `dayu/host/compaction_operation.py`：删除 Host compaction 私有 secret-value redaction / truncate primitive，改为调用 runtime primitive；保留 Host 的 `error_code=` 提取、diagnostic ref 结构、attempt rejection 状态机。

Test candidates:

- `tests/runtime/test_diagnostic_text.py`：新增 runtime helper 直接测试。
- `tests/runtime/test_weak_typing_guard.py`：如决定显式列入 helper coverage set，则只更新扫描覆盖清单；不得降低弱类型守卫。
- `tests/engine/test_agent_phase2.py`：迁移后保留并补强 Engine exception diagnostic 行为测试。
- `tests/host/test_compaction_operation.py`：迁移后保留并补强 Host compaction diagnostic ref redaction 行为测试。
- `tests/host/test_import_boundary.py`：作为验证 runtime import boundary 的受影响测试，不一定需要修改。

README candidates:

- `dayu/README.md`：若新增 `dayu.runtime.diagnostic_text`，需要在 `dayu.runtime` 能力清单中增加一条稳定说明。
- `tests/README.md`：若新增 `tests/runtime/test_diagnostic_text.py`，需要在 `tests/runtime/` 分层说明中增加 diagnostic text helper 覆盖事实。

## 5. Explicitly Rejected Candidates / Scope

- `dayu/engine/runners/openai/diagnostic_payload.py`：保持 Engine OpenAI-compatible runner 内部 owner。不得下沉 provider JSON diagnostic payload builder、provider error sub-object summary、invalid UTF-8 chunk payload、payload version、`canonical_byte_size` 或 bare `sha256_digest`。
- `tests/engine/runners/openai/test_diagnostic_payload.py`：除非未来单独做 Engine runner diagnostic payload work，否则本 WU 不改这些测试。
- `dayu/runtime/_digest.py`：不新增或修改 digest API；不把 OpenAI diagnostic payload digest、Host durable digest、tool trace digest 迁入此模块。
- `dayu/host/durable/codec.py`、`dayu/host/durable/payload.py`、`dayu/host/durable/artifact.py`、`dayu/host/durable/event_log.py`、`dayu/host/durable/tool_trace.py`、`dayu/host/durable/audit.py`：Host durable canonical JSON / digest / timestamp / payload descriptor owner，不属于 runtime helper consolidation。
- `dayu/host/tool_runtime.py` 及 tool trace / duplicate governance 相关模块：tool runtime digest、normalized arguments digest、semantic digest 和 truncation diagnostics 有业务 owner；本 WU 不碰。
- `dayu/runtime/tool_truncation.py`：层中立 tool truncation helper 已有清晰 owner，不与 diagnostic redaction 合并。
- 各层业务字段校验 helper：例如 Host durable row codec、EventLog payload validation、compaction quality check、Runner protocol object validation。它们是 owner-specific validation，不因为“validation”同名迁到 runtime。

## 6. Non-goals / Contract Decisions

- 不迁移 Host durable canonical JSON / digest / timestamp。
- 不改变 digest 文本、JSON canonicalization、audit / tool trace / EventLog 语义。
- 不改变 OpenAI provider diagnostic payload 字段、大小上限、digest 格式或 tests。
- 不迁移 tool runtime digest、normalized arguments digest、semantic digest、fetch_more / truncation / duplicate governance 语义。
- 不引入 overbroad helper：runtime 只提供 diagnostic text primitive，不提供“万能 exception formatter”、不接收 callback / factory / profile / query。
- 不改 public contract：`dayu.runtime` 包根仍不 re-export；Engine `RunFailedData.message` 与 Host compaction diagnostic refs 的既有外部形状不因本 WU 改为新 public DTO。
- 不做兼容性 wrapper / facade / re-export。
- 不使用 `object`、`Any`、无类型参数、无类型返回值。
- 不使用 `hasattr` / `getattr` 规避类型边界。
- 不把显式参数塞进 extra payload。

## 7. Proposed Runtime API

新增模块: `dayu/runtime/diagnostic_text.py`。

模块职责:

- 只处理层中立 diagnostic text 的 secret-value detection、secret-value redaction 和 bounded truncation。
- 不知道 Exception、Run、Attempt、provider、Host diagnostic ref、EventLog、tool trace 或业务字段。

建议函数:

```python
def contains_sensitive_diagnostic_value(message: str) -> bool:
    ...

def redact_sensitive_diagnostic_values(
    message: str, *, redaction_marker: str
) -> str:
    ...

def truncate_diagnostic_text(
    message: str, *, max_chars: int, truncated_suffix: str
) -> str:
    ...
```

Semantics:

- `contains_sensitive_diagnostic_value` 命中以下 value-bearing pattern 时返回 `True`：
  - `Bearer <token-like-value>`。
  - `api key <value>`、`API key <value>`、`api_key=<value>`、`api-key:<value>`、`api-key: <value>`、`apikey=<value>`。
  - `authorization=<value>`、`password=<value>`、`secret=<value>`、`token=<value>` 及 `:` 变体。
- `contains_sensitive_diagnostic_value` 不因普通词汇误伤，例如 `JWT token has expired`、`Content-Type header is invalid`。
- `redact_sensitive_diagnostic_values` 只替换敏感 value，不删除非敏感上下文；Bearer 统一替换为 `Bearer {redaction_marker}`，赋值类字段保留字段名前缀和分隔符。
- `redaction_marker` 是替换敏感值的字面文本，不是待脱敏原文。实现必须用 callable replacement 或等效方式传给 `re.sub()`，保证 marker 中的 `\1`、`\g<name>`、反斜杠等字符不会被 regex replacement 解释。
- `truncate_diagnostic_text` 在 `len(message) > max_chars` 时返回 `message[:max_chars - len(truncated_suffix)] + truncated_suffix`。
- `truncate_diagnostic_text` 在 `len(message) <= max_chars` 时 no-op，必须原样返回 `message`；空字符串也是 no-op。
- `truncate_diagnostic_text` 对 `max_chars <= 0` 或 `len(truncated_suffix) >= max_chars` fail fast `ValueError`，避免负数切片和不可见 body。
- 所有常量使用模块级私有 `Final`，regex 编译在模块级，函数有完整中文 docstring。
- Runtime regex 采用 word-boundary + assignment-operator guard 作为 false-positive 控制：敏感 key 前需要词边界，`authorization` / `password` / `secret` / `token` 等普通词只有后接 `:` 或 `=` 才命中；`api key` / `apikey` 类 key 才允许空白分隔的 value。这是为了保留 `JWT token has expired`、`Content-Type header is invalid` 等普通诊断文本。

Engine / Host 当前 regex 差异矩阵:

| Pattern 类别 | Engine 当前行为 | Host 当前行为 | Runtime 计划行为 | Host migration 后新增命中 |
|---|---|---|---|---|
| Bearer | 使用 `\b` word-boundary，匹配 `Bearer <token>` | 无 `\b`，更容易在单词内部误匹配 | 采用 Engine 风格 `\b` word-boundary | 收窄误伤面；不应影响正常 `Bearer <token>` |
| `api key <value>` 空格写法 | 覆盖 | 不覆盖 | 覆盖 | 是 |
| `api_key=<value>` / `api-key=<value>` | 覆盖 | 覆盖 | 覆盖 | 否 |
| `api-key:<value>` / `api-key: <value>` | 覆盖 | Controller adjudication 按当前 Host 不覆盖处理 | 覆盖 | 是 |
| `apikey=<value>` | 覆盖 | `api[_-]?key` 不覆盖无分隔 `apikey` | 覆盖 | 是 |
| `password=<value>` | 覆盖 | 不覆盖 | 覆盖 | 是 |
| `authorization=<value>` / `token=<value>` / `secret=<value>` | 覆盖但不捕获前缀 | 覆盖且捕获赋值前缀 | 覆盖且捕获赋值前缀供 value redaction 保留字段名 | 否 |
| Capturing prefix | Engine 不需要，因为整条 redacted | Host 使用捕获组保留字段名前缀 | Runtime assignment regex 必须捕获字段名前缀和分隔符 | 保持 Host value-redaction 语义 |

Layer mapping:

- Engine Agent 继续使用整条 redacted 策略：先 `contains_sensitive_diagnostic_value(raw_message)`，命中则返回 `RuntimeError: exception message redacted`；未命中才 `truncate_diagnostic_text(...)`。
- Host compaction 继续使用局部 value redaction 策略：先 `redact_sensitive_diagnostic_values(message, redaction_marker="<redacted>")`，再 `truncate_diagnostic_text(...)`。
- Host `_exception_error_code` 不迁移；它解析 `error_code=` 是 compaction proposal diagnostic 语义。
- Host `_exception_diagnostic_suffix` 不迁移；它拼接 attempt diagnostic ref suffix，是 Host owner 语义。

## 8. Implementation Slices

Sequencing note:

- Slice 2 与 Slice 3 都只依赖 Slice 1，彼此没有生产代码或测试依赖。计划仍按 Slice 1 -> Slice 2 -> Slice 3 串行推进，只是为了缩小每次 implementation review 的变更面和语义对照范围；若 controller 后续要求并行，也必须保持 allowed files 不交叉。

### Slice 1: Runtime Diagnostic Text Primitive

Objective:

- 建立唯一层中立 diagnostic text primitive owner。
- 先用直接测试锁定 primitive 语义，再迁移业务层调用。

Allowed files:

- `dayu/runtime/diagnostic_text.py`
- `dayu/runtime/__init__.py`
- `tests/runtime/test_diagnostic_text.py`
- `tests/runtime/test_weak_typing_guard.py`
- `dayu/README.md`
- `tests/README.md`

Exact changes:

- 新增 `dayu/runtime/diagnostic_text.py`，按第 7 节 API 实现。
- 模块只 import `re` 与 `typing.Final`；不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- 新增模块级私有常量：
  - `_REDACTED_BEARER_PREFIX: Final[str] = "Bearer "`
  - `_BEARER_SECRET_PATTERN`
  - `_ASSIGNED_SECRET_VALUE_PATTERN`
  - 必要的 pattern / validation error message 常量。
- `redaction_marker` 必须是显式参数，不使用模块级固定业务 marker；marker 作为字面文本处理，不能让 `re.sub()` 解释其中的反斜杠或 group reference。
- `truncate_diagnostic_text` 必须先校验 `max_chars` 与 suffix 长度，再执行截断。
- `dayu/runtime/__init__.py` 只更新 docstring 能力清单，说明 runtime 包含层中立 diagnostic text helper；不从包根 re-export。
- `tests/runtime/test_diagnostic_text.py` 直接覆盖：
  - Bearer / api key 空格写法 / api_key / apikey / api-key:<value> / api-key: <value> / authorization / password / secret / token 命中 detection。
  - `JWT token has expired`、`Content-Type header is invalid` 不误判。
  - value redaction 不泄漏 secret value，保留字段名前缀和非敏感上下文。
  - `redaction_marker` 包含反斜杠、`\1` 或类似 group reference 文本时必须按字面值进入结果，不得被 regex replacement 解释。
  - `truncate_diagnostic_text` 在 `len(message) < max_chars` 与 `len(message) == max_chars` 时 no-op 原样返回；exact-boundary case 必须直接断言。
  - truncation 超限时长度正好等于 `max_chars` 且显式 suffix。
  - 空字符串不被 runtime 特判为 redacted；`contains_sensitive_diagnostic_value("")` 返回 `False`，`redact_sensitive_diagnostic_values("", redaction_marker="...")` 和 `truncate_diagnostic_text("", ...)` 均返回 `""`。
  - redact+truncate 组合路径：先 value-redact 再 truncate 后仍不泄漏 secret；如实现自然满足，也增加 redaction 幂等性测试，即重复 redaction 不继续改变结果。
  - `truncate_diagnostic_text` 非法 `max_chars` / suffix 长度 fail fast。
- `tests/runtime/test_weak_typing_guard.py` 如维护显式 runtime helper 文件集合，则把 `diagnostic_text.py` 加入集合；不得放宽扫描。
- `dayu/README.md` 的 `dayu.runtime` 能力清单增加一条稳定说明：`diagnostic_text` 只提供层中立 diagnostic 文本脱敏和有界截断，不承载 Host / Engine 诊断事件语义。
- `tests/README.md` 的 `tests/runtime/` 分层说明增加 diagnostic text helper 测试事实。

Tests:

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/runtime/test_weak_typing_guard.py tests/host/test_import_boundary.py
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

README trigger decision:

- `dayu/README.md`: yes，新 runtime capability 加入开发手册总览能力清单。
- `tests/README.md`: yes，新增 runtime helper 测试类别。
- 根目录 `README.md`: no，用户手册入口、命令和 workflow 不变。
- `dayu/engine/README.md`: no，Engine public contract 尚未改变。
- `dayu/host/README.md`: no，Host public contract 和状态机不变。

Stop condition:

- 如果 runtime helper 需要理解 Exception 类型、Host diagnostic ref、Runner event、provider JSON object 或调用方 profile，停止；该抽象过宽。
- 如果实现必须使用 `Any` / `object` 或动态属性访问才能通过类型检查，停止并重新设计 API。

Completion signal:

- 新 runtime helper 通过直接测试、runtime weak typing guard 和 runtime import boundary。
- 包根不 re-export 新 helper。

### Slice 2: Engine Agent Exception Diagnostic Migration

Objective:

- 删除 Engine Agent 内重复的 secret regex / truncation primitive。
- 保持 Engine exception diagnostic message 的现有用户可见语义。

Allowed files:

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase2.py`

Exact changes:

- 在 `dayu/engine/agent.py` import:
  - `contains_sensitive_diagnostic_value`
  - `truncate_diagnostic_text`
- 删除 Engine 私有 `_BEARER_SECRET_PATTERN`、`_API_KEY_VALUE_PATTERN`、`_ASSIGNED_SECRET_VALUE_PATTERN` 和 `_contains_sensitive_exception_value`。
- `_exception_diagnostic_message` 保持输出策略：
  - 空异常消息返回异常类型名。
  - 命中 `contains_sensitive_diagnostic_value(raw_message)` 时返回 `f"{exc_type}: {_EXCEPTION_MESSAGE_REDACTED}"`。
  - 未命中时用 `truncate_diagnostic_text(raw_message, max_chars=_EXCEPTION_MESSAGE_MAX_LENGTH, truncated_suffix=_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX)`。
  - 最终仍返回 `f"{exc_type}: {safe_message}"`。
- `_safe_log_message` 保持输出策略：
  - 空白字符串返回 `_EXCEPTION_MESSAGE_REDACTED`。
  - 命中 sensitive value 时返回 `_EXCEPTION_MESSAGE_REDACTED`。
  - 未命中时用 runtime truncation primitive。
- 保留 Engine 私有 marker `_EXCEPTION_MESSAGE_REDACTED`、长度和 suffix 常量；这些是 Engine display / diagnostic policy，不是 runtime truth。
- 不改 Agent 状态机、RunnerEvent 提升、RunFailedData 字段、error code、metadata 或 public contract。
- 更新 `tests/engine/test_agent_phase2.py`：
  - 既有 `test_exception_diagnostic_message_*` 必须继续通过。
  - 增加或保留 `api key` 空格写法、`api-key:<value>` 变体和普通 `JWT token` / header word 不误伤测试。
  - 增加 `_safe_log_message` 直接测试矩阵；这是 Engine 调用策略，不放到 runtime 测试里：
    - 空字符串和全空白字符串返回 `_EXCEPTION_MESSAGE_REDACTED`。
    - 包含 sensitive value 的消息整条返回 `_EXCEPTION_MESSAGE_REDACTED`，不保留局部上下文。
    - 普通超长消息按 `_EXCEPTION_MESSAGE_MAX_LENGTH` 与 `_EXCEPTION_MESSAGE_TRUNCATED_SUFFIX` 截断。
    - `JWT token has expired` 等普通 token 词不误伤，未超长时原样返回。

Tests:

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/engine/test_agent_phase2.py
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

README trigger decision:

- `dayu/engine/README.md`: no，Engine `raw_payload` / Event / public contract 不变，异常 message 语义保持。
- `tests/README.md`: no，未新增测试层级或运行方式；只更新既有 Engine Agent 测试。
- `dayu/README.md`: no，Slice 1 已记录 runtime capability，Engine 架构边界不变。

Stop condition:

- 如果迁移导致 `RunFailedData.message` 文本、truncation suffix 或 secret redaction marker 变化，停止并修正为兼容当前语义；本 WU 不改变用户可见 failure message contract。
- 如果为了共享而把 Engine exception formatter 整体放进 runtime，停止；这是 overbroad helper。

Completion signal:

- `dayu/engine/agent.py` 不再编译私有 secret regex。
- Engine exception diagnostic tests 继续证明旧语义未变。

### Slice 3: Host Compaction Exception Diagnostic Migration

Objective:

- 删除 Host compaction operation 内重复的 secret-value redaction / truncation primitive。
- 保持 Host compaction attempt rejection、failure reason、diagnostic ref 结构和 `error_code=` 提取 owner 不变。

Allowed files:

- `dayu/host/compaction_operation.py`
- `tests/host/test_compaction_operation.py`

Exact changes:

- 在 `dayu/host/compaction_operation.py` import:
  - `redact_sensitive_diagnostic_values`
  - `truncate_diagnostic_text`
- 删除 Host compaction 私有 `_BEARER_SECRET_PATTERN`、`_ASSIGNMENT_SECRET_PATTERN`。
- 保留 `_ERROR_CODE_PATTERN` 和 `_exception_error_code`；它是 Host compaction proposal diagnostic code extraction，不是 runtime primitive。
- `_safe_exception_message` 保持调用方策略：
  - `exc is None` 返回 `"none"`。
  - 空白异常消息返回异常类名。
  - 非空消息先 `redact_sensitive_diagnostic_values(message, redaction_marker=_REDACTED_SECRET)`。
  - 再 `truncate_diagnostic_text(..., max_chars=_MAX_SAFE_EXCEPTION_MESSAGE_CHARS, truncated_suffix=_TRUNCATED_SUFFIX)`。
- `_exception_diagnostic_suffix` 保持异常类型前缀与 message 拼接规则。
- 不改 `CompactionAttemptRejected` dataclass、`diagnostic_refs` 结构、failure category、repair budget、quality check、multi-pass merge 或 Host Context Governance。
- 更新 `tests/host/test_compaction_operation.py`：
  - 既有 `test_run_compaction_operation_redacts_exception_diagnostic_refs` 必须继续通过。
  - 更新 `_SensitiveFailingCompactor` 的异常消息，使其覆盖既有模式和 Host migration 后新增检测模式：`Bearer <value>`、`api_key=<value>`、`token=<value>`、`secret=<value>`、`password=<value>`、`api key <value>`、`apikey=<value>`、`api-key:<value>` 或 `api-key: <value>`。
  - 对每个 secret 原文断言 diagnostic ref 不泄漏，并断言 `<redacted>` 出现，证明 Host 继续使用局部 value redaction。
  - 明确列出 Host migration 后新增检测范围：`api key <value>`、`apikey=<value>`、`password=<value>`、`api-key:<value>` / `api-key: <value>`；这些是 diagnostic-only security hardening，不改变 compaction 状态机。
  - 增加覆盖普通 `JWT token has expired` 不被整体删除；Host 应保留非敏感上下文，只 redacts value-bearing secret。
  - 增加覆盖 `_exception_diagnostic_suffix` 空消息路径：当异常 `str(exc)` 为空时，suffix 只返回异常类名，不拼接 `:<message>`，保持 Host 现有语义。
  - 保留 `proposal failed` diagnostic suffix 与 retry 行为断言，证明 Host owner 语义未迁移。

Tests:

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/host/test_compaction_operation.py
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

README trigger decision:

- `dayu/host/README.md`: no，Host public contract、状态机、Context Governance 语义不变；只是内部 helper owner 收敛。
- `tests/README.md`: no，未新增 Host 测试层级或运行方式。
- `dayu/README.md`: no，Slice 1 已记录 runtime capability。

Stop condition:

- 如果迁移要求改变 diagnostic ref prefix、failure category、attempt number、repairable decision 或 `error_code=` 提取，停止；这些属于 Host compaction owner。
- 如果 migration 试图把 `_exception_diagnostic_suffix` 或 `_attempt_rejected` 整体搬到 runtime，停止；这是 Host diagnostic ref 语义泄漏。

Completion signal:

- `dayu/host/compaction_operation.py` 不再编译私有 secret-value redaction regex。
- Host compaction tests 证明 secret 不泄漏且 compaction retry / reject 语义未变。

## 9. Review Gates

### Plan Review Gate

Before implementation:

- 由至少两个 reviewer 对本 artifact 做 adversarial plan review，重点检查：
  - 是否误把 Host durable truth / Engine provider diagnostic payload / tool runtime digest 迁到 runtime。
  - runtime API 是否过宽、是否泄漏 Host / Engine owner 语义。
  - slices 的 allowed files 是否足够窄。
  - tests 是否覆盖旧语义保持与新增 runtime primitive。
- 建议 artifact:
  - `docs/reviews/wu-layer-02-plan-review-mimo-20260602.md`
  - `docs/reviews/wu-layer-02-plan-review-ds-20260602.md`
  - `docs/reviews/wu-layer-02-plan-review-controller-adjudication-20260602.md`
- Controller adjudication 必须明确 accepted findings、deferred findings 和是否允许进入 Slice 1 implementation。

### Implementation Review Gate

After each slice:

- 生成 slice implementation report，列出实际改动、测试输出、pyright 输出、README trigger 处理。
- 对该 slice 做 code review，重点检查：
  - runtime 不 import 上层。
  - 无 `Any` / `object` / 无类型签名。
  - 没有兼容 wrapper / re-export。
  - 没有改变 rejected scope 的 digest / JSON / durable / tool trace 语义。
  - Engine / Host 行为测试证明 owner-specific 策略未被 runtime 吞掉。
- 建议 artifact:
  - `docs/reviews/wu-layer-02-slice1-implementation-report-20260602.md`
  - `docs/reviews/wu-layer-02-slice1-code-review-*.md`
  - `docs/reviews/wu-layer-02-slice2-implementation-report-20260602.md`
  - `docs/reviews/wu-layer-02-slice2-code-review-*.md`
  - `docs/reviews/wu-layer-02-slice3-implementation-report-20260602.md`
  - `docs/reviews/wu-layer-02-slice3-code-review-*.md`

### Aggregate Review Gate

After all slices:

- 做一次 aggregate review，重点检查跨 slice 后的最终 owner 边界：
  - `dayu.runtime.diagnostic_text` 仍是纯 text primitive，不知道 Exception / Host / Engine / provider。
  - `dayu/engine/runners/openai/diagnostic_payload.py` 未被不必要迁移。
  - `dayu/runtime/_digest.py`、Host durable codec / payload / tool trace digest 未被改写。
  - `dayu/README.md` 与 `tests/README.md` 只记录当前已落地事实，不写过程状态或未来计划。
  - 没有新增 public root export。
- 建议 artifact:
  - `docs/reviews/wu-layer-02-aggregate-review-mimo-20260602.md`
  - `docs/reviews/wu-layer-02-aggregate-review-ds-20260602.md`
  - `docs/reviews/wu-layer-02-aggregate-review-controller-adjudication-20260602.md`

## 10. Final Validation Commands

Implementer 完成全部 slices 后运行:

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/runtime/test_weak_typing_guard.py tests/host/test_import_boundary.py
source .venv/bin/activate && pytest -q tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py
source .venv/bin/activate && pytest -q tests/runtime tests/engine/test_agent_phase2.py tests/host/test_compaction_operation.py tests/host/test_import_boundary.py
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Optional broader confidence command if time allows:

```bash
source .venv/bin/activate && pytest -q tests/runtime tests/engine tests/host/test_compaction_operation.py tests/host/test_import_boundary.py
```

## 11. Residual Risks / Watch Items

- Regex unification intentionally broadens Host compaction redaction for `api key <value>`、`apikey=<value>`、`password=<value>`、`api-key:<value>` / `api-key: <value>` while adding word-boundary / assignment-operator false-positive guards. This is a security-hardening diagnostic-only change, but tests must explicitly assert no secret leakage and no ordinary `token` word false positive.
- Engine uses whole-message redaction while Host uses value redaction. Runtime must not erase this policy difference; if implementation collapses both into a single `safe_exception_message(...)`, review should reject it as overbroad.
- OpenAI diagnostic payload has its own sensitive-key redaction for JSON object previews. It intentionally remains separate from text redaction; future work can revisit only if a second non-OpenAI JSON diagnostic payload owner appears with identical semantics.
- `dayu.runtime._digest` currently has no dedicated direct test file in the inspected evidence. This WU must not opportunistically add digest behavior changes; if digest tests are desired, schedule separate runtime digest hardening work.
- README updates are intentionally minimal. Over-documenting internal helper details in Host / Engine README would violate README responsibility boundaries.
