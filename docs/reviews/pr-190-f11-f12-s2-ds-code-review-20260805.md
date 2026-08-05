# PR 190 F11/F12 S2 Structured-Output Engine Slice — 独立 Code Review

## Review metadata

- **Reviewer**: AgentDS (第二路独立 architecture/semantic-ownership/typing/test-gap/adversarial pass)
- **Gate**: `review`，slice `S2 — Engine generic structured output 与 config capability`
- **Work unit**: PR 190 F11/F12 Interactive Memory 收口
- **基线 HEAD**: `c8be3e5184b8b797c59458027e991f0284cbb3b5` (confirmed at review start)
- **Reviewed artifact**: 当前工作树未提交 diff（S2 implementation）
- **Review type**: 只读审查；不修改实现、不 stage/commit/push
- **Review independence**: 本 review 未参考、未等待、未消费 MiMo 审查结论
- **Authoritative S2 hash confirmation（总控直接确认）**:
  - `dayu/config/models.json` raw-byte SHA256 = `dc924f842be81599c00606dae0cbe464d6f766147581d4bbb4167e83044e5f2b`
  - `docs/cli_init_workspace_manifest_v1.json` raw-byte SHA256 = `0e1ec1047062eecbe6dc8eae89139460058219c881ce4d7960e6c96c7a182469`
- **Artifact path**: `docs/reviews/pr-190-f11-f12-s2-ds-code-review-20260805.md`

## Reviewer interference 声明

审查过程中，并行 MiMo Agent 违反约束执行 `git stash`，造成短暂基线窗口内以下伪观察：

- `StructuredOutputCapabilityConfig` import 失败（venv 中缺少未安装的开发版本符号）
- `models.json` SHA256 显示为 `d817...` 而非权威值
- `manifest` SHA256 显示为 `9ebd...` 而非权威值

以上全部作废，已从本 artifact 剔除。所有结论基于工作树恢复后从稳定基线重新读取/重验的直接证据。以下每条 finding 或 PASS 均附带稳定重验证据。

## 审查范围

已读取的必读文档：

- `AGENTS.md`（完整）
- `docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`（完整）
- `docs/gateflow/pr-190-f11-f12-s2-structured-output-implementation-20260805.md`（完整）
- `docs/host/design.md`（完整）
- `docs/engine/design.md`（完整，特别关注 §2、§4、§6、§7、§8、§15）

已审查的全部生产文件：

- `dayu/engine/contracts/structured_output.py`（new, 195 行）
- `dayu/engine/contracts/agent_run.py`（diff）
- `dayu/engine/contracts/runner.py`（diff）
- `dayu/engine/contracts/runner_spec.py`（diff）
- `dayu/engine/contracts/__init__.py`（diff）
- `dayu/engine/agent.py`（diff）
- `dayu/engine/__init__.py`（diff）
- `dayu/engine/runners/openai/payload.py`（diff）
- `dayu/engine/runners/openai/runner.py`（diff）
- `dayu/runtime/config_loader.py`（diff）
- `dayu/service/host_assembly.py`（diff）
- `dayu/host/_execution_config_projection.py`（diff）
- `dayu/config/models.json`（diff）
- `docs/cli_init_workspace_manifest_v1.json`（diff）

已审查的关键测试文件：

- `tests/engine/contracts/test_runner_spec.py`
- `tests/engine/contracts/test_agent_run.py`
- `tests/engine/runners/openai/test_payload_build.py`
- `tests/engine/runners/openai/test_protocol_surface.py`
- `tests/engine/runners/openai/_factories.py`
- `tests/engine/test_protocols_surface.py`
- `tests/engine/test_metadata_boundary.py`
- `tests/engine/test_config_models.py`
- `tests/engine/test_package_exports.py`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`

已审查的 README：

- `dayu/engine/README.md`
- `dayu/config/README.md`
- `dayu/README.md`

---

## 1. Engine 是否是 generic structured-output 唯一 owner

### 1.1 结论：PASS

### 1.2 直接证据

**Owner 定义位置**：`dayu/engine/contracts/structured_output.py`（195 行，new file）是以下类型的唯一定义真源：

- `StructuredOutputCapability`（`StrEnum`: `NONE`, `JSON_OBJECT`, `JSON_SCHEMA`）
- `JsonObjectStructuredOutputRequest`（无字段 variant）
- `JsonSchemaStructuredOutputRequest`（`name: str`, `schema: Mapping[str, JsonValue]`, `strict: bool`）
- `StructuredOutputRequest`（封闭联合 TypeAlias）
- `validate_structured_output_request`（capability/request 矩阵校验器）

**消费路径**：所有生产模块通过 `dayu.engine.contracts.structured_output` 直接 import Engine-owned 类型，不经过 runtime 中转或别名：

```text
dayu/engine/contracts/runner_spec.py  -> StructuredOutputCapability
dayu/engine/contracts/agent_run.py    -> StructuredOutputRequest, validate_structured_output_request
dayu/engine/contracts/runner.py       -> StructuredOutputRequest
dayu/engine/runners/openai/runner.py  -> StructuredOutputRequest
dayu/engine/runners/openai/payload.py -> 全部 variant + validate_structured_output_request
dayu/host/_execution_config_projection.py -> StructuredOutputCapability (Engine owned)
dayu/service/host_assembly.py         -> StructuredOutputCapability (Engine owned)
```

**设计文档对齐**：`docs/engine/design.md:112-123` 定义了精确的 `StructuredOutputCapability`、两种 variant 与封闭联合；代码实现完全匹配。

### 1.3 runtime 重复 enum 是否是架构必要机械配置 contract

**是，架构必要。** 理由：

- `dayu.runtime` 受架构硬约束，不得 import `dayu.engine`（`AGENTS.md` 与 `docs/host/design.md §3` 明确要求）。
- 因此 `dayu/runtime/config_loader.py` 必须定义独立的 `StructuredOutputCapabilityConfig`（`StrEnum`），用于从 `models.json` 解析配置层的 capability 值。
- Service 层 `host_assembly.py:1807-1808` 执行机械映射：`StructuredOutputCapability(model.structured_output_capability.value)` — 从 runtime enum 取 `.value` 字符串，构造 Engine enum。
- Engine 不反向引用 runtime enum（已验证：`grep -rn 'StructuredOutputCapabilityConfig' dayu/engine/` → 零结果）。

### 1.4 映射是否 fail-fast 且不会漂移

**稳定重验证证据**：

```
runtime enum values:  {'none', 'json_object', 'json_schema'}
engine enum values:   {'none', 'json_object', 'json_schema'}
ENUMS MATCH
```

**Fail-fast 保障**：

1. ConfigLoader 解析层：`_parse_structured_output_capability` 拒绝未知字符串 → `ConfigFieldError`
2. Service 映射层：`StructuredOutputCapability("unknown_value")` → `ValueError`（`StrEnum` 构造失败）
3. `RunnerSpec.__post_init__`：`isinstance` 校验拒绝非 `StructuredOutputCapability` 实例 → `TypeError`
4. `AgentRunRequest.__post_init__`：调用 `validate_structured_output_request` 拒绝非法 capability/request 组合 → `ValueError`
5. `build_request_payload`：再次调用同一 validator 作为 defense-in-depth

**漂移风险评估**：当前没有自动化测试直接断言两个 enum 的成员集合完全一致（例如逐 member name/value 对比）。这构成低风险的残留漂移窗口：如果未来一方新增 member 而另一方遗漏，ConfigLoader 解析或 Service 映射会 fail-fast（见上），因此漂移不会静默发生，但错误信息可能不如直接枚举对比清晰。此风险不计入 finding，不阻塞 acceptance。

### 1.5 反例检查

- ❌ Engine 类型未在 runtime 层重复定义
- ❌ 不存在第三份 capability 定义
- ❌ Host 不定义 capability enum
- ❌ Config 不写 provider-specific capability 字符串

---

## 2. 兼容 alias/wrapper、loose parser、provider-specific special case、extra bag、隐式 downgrade、God helper

### 2.1 结论：PASS

### 2.2 逐项证据

#### 兼容 alias / re-export

- `dayu/engine/__init__.py` 直接 import 并 re-export 来自 `dayu.engine.contracts.structured_output` 的符号；这不是兼容 alias，而是 Engine 包根的稳定公开导出。
- `dayu/engine/contracts/__init__.py` 同样直接 import 同源符号；不是重复定义。
- 无旧符号名保留、无旧 import 路径转发。

#### Loose parser

- `validate_structured_output_request` 使用 strict `isinstance` + `match/case` + `assert_never` 穷尽匹配。
- `JsonSchemaStructuredOutputRequest.__post_init__` 对 name（非空、无首尾空白）、schema（Mapping）、strict（bool）逐字段做 strict typed validation。
- `_validate_json_mapping` + `_validate_json_value` 递归校验：拒绝非字符串 key、非 JSON 类型值、非有限浮点数。
- ConfigLoader 侧 `_parse_structured_output_capability` 通过 `StructuredOutputCapabilityConfig(value)` 构造（`StrEnum` fail-fast），拒绝未知字符串。
- 无 `try/except ValueError: fallback to default`、无 loose `dict.get` with default、无类型宽恕路径。

#### Provider-specific special case

- `_apply_structured_output_request` 在 `payload.py:297-333` 使用 `match/case` + `assert_never`，仅按 concrete variant 类型派发，不读取 `spec.provider`、`spec.model` 或任何 provider 名称。
- 全量 grep 结果：`structured_output` 相关代码在 Engine/Runtime/Service/Host 中无任何 `if provider ==` / `if "deepseek" in` / `if model.startswith` 等 provider-name 分支。

#### Extra bag

- Engine transport 使用独立顶层 `response_format` field（`payload.py:443: _apply_structured_output_request(payload, structured_output)`）。
- `_apply_structured_output_request` 直接写入 `payload["response_format"]`，不经过 `extra_body`、`provider_request_extension`、headers 或 metadata。
- Owner test `test_json_object_structured_output_exact_payload` 显式断言 `"extra_body" not in payload`。
- Owner test `test_json_schema_structured_output_preserves_owner_schema_identity` 显式断言 `"extra_body" not in payload`。
- Meta-boundary test `test_explicit_options_do_not_leak_into_extra_body` 覆盖显式参数不渗透。

#### 隐式 downgrade

- `validate_structured_output_request` 对非法组合抛 `ValueError`，无 fallback、无自动降级。
- `build_request_payload` 调用同一个 validator fail-fast，不在 provider 拒绝后重试为较弱 mode。
- Owner test `test_provider_rejection_does_not_downgrade_or_retry_schema_mode`：provider 400 拒绝 JSON Schema 后只发送一次，`len(session.calls) == 1`，不降级重试。

#### God helper

- `validate_structured_output_request`：单一职责 matrix validator（~30 行逻辑）。
- `_apply_structured_output_request`：单一职责 transport projector（~35 行逻辑）。
- `_request_mode`：仅用于错误消息的 mode 文本提取（~10 行）。
- `_validate_json_mapping` + `_validate_json_value`：递归 JSON 校验（~50 行合计）。
- 无 God function、God dataclass、God builder。

---

## 3. Required signatures 是否真正阻止遗漏；AgentRunRequest 构造时 matrix validation 是否在正确 boundary

### 3.1 结论：PASS（附一条 LOW 级 consistency note）

### 3.2 Protocol boundary

- `AsyncRunner.call`（`runner.py:29-32`）：`structured_output` 是 **required keyword-only**（`*` 后第一个参数，无 default）。
- `AsyncOpenAIRunner.call`（`runner.py:365-368`）：签名完全一致，required keyword-only，无 default。
- `AsyncOpenAIRunner._call_impl`（`runner.py:410-413`）：签名完全一致。
- Agent 唯一 production call site（`agent.py:1345`）：显式传递 `structured_output=self._request.structured_output`，无 `if` 分支。
- Test `test_call_signature_no_kwargs`：反射验证参数名、kind（`KEYWORD_ONLY`）、无 default。
- Test `test_async_runner_structured_output_parameter_is_required`：独立验证 Protocol 签名。

**遗漏不可能发生**：任何 Runner 实现或 fake 缺少 `structured_output` parameter 都会导致 `TypeError`（Protocol mismatch）或 pyright 类型错误。

### 3.3 AgentRunRequest boundary

- `AgentRunRequest.structured_output` 有 `= None` default。**这是正确设计**：`None` 显式表达"本次 run 不请求 structured output transport"，与 plan 中"runner call 必须显式传递"不矛盾——AgentRunRequest 是 Host→Engine 的请求构造边界，`None` 是合法业务语义，不是省略。
- `AgentRunRequest.__post_init__`（`agent_run.py:143-145`）调用 `validate_structured_output_request(capability=..., request=...)`，在构造时 fail-fast。
- Test `test_agent_run_request_rejects_unsupported_structured_output` 验证构造期拒绝非法组合。

### 3.4 build_request_payload 的 `= None` default（consistency note）

`build_request_payload`（`payload.py:408`）的 `structured_output` 参数有 `= None` default。

- **功能安全性**：所有生产调用路径（`_call_impl` → `build_request_payload`）显式传递该参数；函数内部仍调用 `validate_structured_output_request` 做 defense-in-depth 校验；测试中 `= None` 只是便利默认值。
- **架构一致性偏离**：plan 强调 `AsyncRunner.call` 的 required parameter 原则（"不得用 `=None` default 隐藏漏传"），但 `build_request_payload` 作为内部 helper 保留 default 降低了同一原则的内部一致性。
- **Owner 分析**：`build_request_payload` 是 OpenAI-compatible Runner 的私有 payload 构造 helper，其调用者只有 `_call_impl`（单一 production call site）。如果调用者遗漏传参，`validate_structured_output_request` 仍会在 spec 具有 `JSON_SCHEMA` capability 且 request 应为 non-None 时静默接受 `None`（因为 `JSON_SCHEMA` 合法接受 `None`）。
- **实际暴露面**：该函数不作为 Engine public API 导出；新增 caller 只能来自 Runner 内部维护者。
- **Severity**: LOW — 不影响运行时正确性，不阻塞 acceptance。

### 3.5 全仓 fake/stub migration

已验证 `_MetadataBoundaryRunner`（test_metadata_boundary.py）、`_MetadataBoundaryRunner` 的 `call` 方法、`utils/smoke_async_agent_providers.py` 中的 RunnerSpec 构造均新增 `structured_output` parameter 或 `structured_output_capability` field。所有 fake/stub 与 Protocol 签名一致，不存在仍使用旧签名的遗漏 call site。

---

## 4. Schema mapping 是否拒绝 non-string key / 非 JSON / 空 name 等全部不变量；json_schema strict transport 是否 exact

### 4.1 结论：PASS

### 4.2 不变量覆盖矩阵

| 不变量 | 校验位置 | 拒绝方式 | 测试覆盖 |
|---|---|---|---|
| name 非空 | `JsonSchemaStructuredOutputRequest.__post_init__` | `ValueError` | `test_json_schema_request_rejects_invalid_name` (parametrize: `""`, `" schema"`, `"schema "`) |
| name 无首尾空白 | 同上 | `ValueError` | 同上（`" schema"`, `"schema "`） |
| name 必须是 str | 同上 | `TypeError` | 类型系统 + pyright |
| schema 必须是 Mapping | 同上 | `TypeError` | 类型系统 + pyright |
| strict 必须是 bool | 同上 | `TypeError` | 类型系统 + pyright |
| schema key 必须是 str | `_validate_json_mapping` | `TypeError` | `_validate_json_mapping` 递归覆盖 |
| schema value 必须是合法 JSON | `_validate_json_value` | `TypeError` | 递归覆盖：None/bool/int/float/str/list/dict accept，其他 reject |
| 拒绝 NaN/Inf | `_validate_json_value` | `ValueError` | `test_json_schema_request_rejects_non_finite_json_number` |
| 递归校验 nested object | `_validate_json_value` → `_validate_json_mapping` | N/A | 递归调用链 |
| 递归校验 nested array | `_validate_json_value` → `_validate_json_value` | N/A | 递归调用链 |

### 4.3 json_schema transport exactness

`_apply_structured_output_request`（`payload.py:321-333`）投影逻辑：

```python
payload["response_format"] = {
    "type": "json_schema",
    "json_schema": {
        "name": name,
        "strict": strict,
        "schema": schema,
    },
}
```

Owner test `test_json_schema_structured_output_preserves_owner_schema_identity`：

- `transported_schema is canonical_schema`（Python object identity — 同一对象引用）✓
- `_canonical_schema_digest(transported_schema) == expected_digest`（SHA-256 再算一致）✓
- `schema_definition["name"] == request.name` ✓
- `schema_definition["strict"] is request.strict` ✓
- `response_format["type"] == "json_schema"` ✓

**transport 是 exact identity pass-through**：schema object 在 `JsonSchemaStructuredOutputRequest` 构造时完成递归 JSON 值校验，随后原样（同一引用）进入 transport payload，不需要拷贝、不需要 normalize、不需要二次序列化。schema 的 name、strict 字段同样原样投影。无 provider-specific 字段注入。

---

## 5. Model catalog capability 继承、DeepSeek=json_object、MiMo/未证明 provider=none

### 5.1 结论：PASS

### 5.2 稳定重验证证据

从恢复后的工作树直接读取 `models.json`，逐记录验证：

```text
deepseek-v4-flash                   extends=None      soc=json_object
deepseek-v4-flash-thinking          extends=deepseek-v4-flash  soc=MISSING (inherits)
deepseek-v4-pro                     extends=None      soc=json_object
deepseek-v4-pro-thinking            extends=deepseek-v4-pro    soc=MISSING (inherits)
gpt-5.4                             extends=None      soc=none
gpt-5.4-thinking                    extends=gpt-5.4   soc=MISSING (inherits)
claude-sonnet-4-6                   extends=None      soc=none
claude-sonnet-4-6-thinking          extends=claude-sonnet-4-6 soc=MISSING (inherits)
gemini-2.5-flash                    extends=None      soc=none
... (all 8 gemini base records)     extends=None      soc=none
... (all 8 gemini thinking)         extends=...       soc=MISSING (inherits)
mimo-v2.5-pro                       extends=None      soc=none
... (all 4 mimo base records)       extends=None      soc=none
... (all 4 mimo thinking/plan)       extends=...       soc=MISSING (inherits)
qwen-plus                           extends=None      soc=none
qwen-plus-thinking                  extends=qwen-plus soc=MISSING (inherits)
ollama                              extends=None      soc=none
```

**关键规则验证**：

- **Base records 必填**：所有 `extends=None` 的 base record 均有显式 `structured_output_capability`。
- **派生记录继承不重复写**：所有 `extends=...` 的 derived record 均 `MISSING`（不写该字段），由 ConfigLoader 从父记录解析。
- **DeepSeek = json_object**：两个 DeepSeek base records（`deepseek-v4-flash`, `deepseek-v4-pro`）均为 `json_object`。
- **MiMo / 未证明 provider = none**：MiMo、GPT、Claude、Gemini、Qwen、Ollama 的 base records 均为 `none`。
- **当前无 json_schema record**：无任何 record 标记为 `json_schema`。
- **Catalog 测试断言**：`test_default_model_structured_output_capability_matrix` 逐 provider prefix 验证 resolved capability，覆盖 DeepSeek=`JSON_OBJECT`、MiMo=`NONE`、其他=`NONE`、全 catalog 无 `JSON_SCHEMA`。
- **ConfigLoader 继承测试**：`test_single_extends_chain_resolves_to_complete_typed_record` 验证 derived model 的 `structured_output_capability is StructuredOutputCapabilityConfig.NONE`（继承 resolved）。
- **ConfigLoader required 测试**：`test_model_structured_output_capability_is_required` 验证 base record 缺失字段 → `ConfigFieldError`。
- **ConfigLoader unknown enum 测试**：`test_model_structured_output_capability_rejects_unknown_enum` 验证非法字符串 → `ConfigFieldError`。

### 5.3 反例检查

- ❌ 无 `json_schema` 虚标
- ❌ 无 DeepSeek thinking 变体复写 `json_object`（正确继承）
- ❌ 无 provider-name 硬编码 capability 表在 Engine 层

---

## 6. Publication manifest/hash test raw-byte truth；README 边界

### 6.1 结论：PASS

### 6.2 稳定重验证证据

```
models.json raw-byte SHA256: dc924f842be81599c00606dae0cbe464d6f766147581d4bbb4167e83044e5f2b
                              MATCH implementation doc
manifest raw-byte SHA256:    0e1ec1047062eecbe6dc8eae89139460058219c881ce4d7960e6c96c7a182469
                              MATCH implementation doc
manifest content_sha256 for models.json: dc924f... MATCH actual file
FROZEN_MANIFEST_SHA256 in test:         0e1ec104... MATCH actual manifest
```

**Hash 更新链验证**：

1. `models.json` raw-byte SHA256 → manifest `content_sha256` for `config/models.json`：`dc924f...` = `dc924f...` ✓
2. Manifest raw-byte SHA256 → `FROZEN_MANIFEST_SHA256` in CLI smoke test：`0e1ec...` = `0e1ec...` ✓
3. Implementation doc 记录的 hash → 实际文件 hash：均已确认匹配 ✓

### 6.3 README 边界审查

| README | 审查结论 | 证据 |
|---|---|---|
| `dayu/engine/README.md` | **PASS** | 新增 `StructuredOutputCapability` / `StructuredOutputRequest` 说明（§公共契约）；新增 `AsyncRunner.call` required parameter（§公共契约）；新增 payload 校验规则（§Runner 协议）；新增 capability catalog 约束（§扩展点）。已核对 `部署前自检` block 无要求本 slice 修改的检查项。 |
| `dayu/config/README.md` | **PASS** | 新增 `structured_output_capability` 字段说明（§models.json 字段表、继承规则、catalog coverage）；Service 机械投影说明（§models.json 末尾段）。已核对：workspace 覆盖示例未机械更新 capability 字段，但示例是"最小覆盖"示意，不需要包含所有必填字段。 |
| `dayu/README.md` | **PASS** | 跨层 request flow 摘要中补充了 structured-output 链路。 |
| 根 `README.md` | **判断不更新** | 用户可见 CLI/安装/工作区流程无变化，符合 plan 判定。 |
| Service / tests README | **判断不更新** | Service 无新增公开职责，tests 无新增 test layer/fixture system。 |

---

## 7. 全量迁移触及大量 tests 是否只有 typed breakage 的必要机械变更

### 7.1 结论：PASS

### 7.2 变更分类分析

全量 diff 涉及 76 files（+973 / -31 lines）。分类如下：

**A. Production 新类型/新逻辑（9 files）**：
- `structured_output.py`（new）、`agent_run.py`、`runner.py`、`runner_spec.py`、`__init__.py`（contracts）、`agent.py`、`payload.py`、`runner.py`（openai）、`__init__.py`（engine）
- 这些是 S2 的核心实现，不是迁移。

**B. Config / Runtime / Service 投影（4 files）**：
- `config_loader.py`、`host_assembly.py`、`_execution_config_projection.py`、`models.json`
- 这些是 capability 在配置层→Service→Host 的机械投影，不包含行为分支。

**C. 测试工厂（1 file）**：
- `tests/engine/runners/openai/_factories.py`：`make_spec` 新增 `structured_output_capability` 参数（默认 `NONE`）。机械追加。

**D. 深层 owner test（~8 files）**：
- `test_runner_spec.py`、`test_agent_run.py`、`test_payload_build.py`、`test_protocol_surface.py`、`test_protocols_surface.py`、`test_metadata_boundary.py`、`test_config_models.py`、`test_package_exports.py`
- 这些是新增的 owner-level 验证，不是迁移。

**E. 机械 typed breakage 迁移（~50 files）**：
- 所有 `tests/host/test_*.py`、部分 `tests/engine/test_*.py`、`utils/smoke_async_agent_providers.py`
- 变更模式完全一致：在 `RunnerSpec(...)` 构造中新增 `structured_output_capability=StructuredOutputCapability.NONE`。部分文件同时新增 import。
- **无行为变更**：所有迁移均使用 `NONE`（默认安全值），保持原有测试语义不变。

### 7.3 隐藏行为修改检查

逐文件审查所有非 `NONE` explicit capability 使用：

| 位置 | capability | 是否 behavior change |
|---|---|---|
| `_factories.py:make_spec` default | `NONE` | 否（等同于旧行为：无 structured output） |
| `test_payload_build.py` | `JSON_OBJECT`, `JSON_SCHEMA` | 否（新增测试，测试新行为） |
| `test_protocol_surface.py` | `JSON_SCHEMA` | 否（新增测试） |
| `test_agent_run.py` | `JSON_SCHEMA` | 否（新增测试） |
| `utils/smoke_async_agent_providers.py` | `json_object` (DeepSeek), `none` (others) | 否（新 smoke helper，不改变现有测试） |

**结论**：所有既有测试的行为完全保留（`NONE` capability + 无 structured output request = 旧行为）。所有 `JSON_OBJECT` / `JSON_SCHEMA` 的使用仅出现在新增 owner test 中。无隐藏行为修改。

### 7.4 `utils/smoke_async_agent_providers.py` 变更

该文件是 smoke helper（非 production），显式标注 DeepSeek 为 `json_object`，MiMo/Gemini/Qwen 为 `none`。这是 plan allowed 中的 smoke helper 更新，不涉及 production 行为变更。

---

## 8. 为 S3 Host compactor 接入留下的接口是否最小、无重复结构真源

### 8.1 结论：PASS

### 8.2 Engine 暴露的 S3 可用接口

```
StructuredOutputCapability        # "none" | "json_object" | "json_schema"
StructuredOutputRequest           # JsonObjectStructuredOutputRequest | JsonSchemaStructuredOutputRequest
JsonObjectStructuredOutputRequest # 无字段 variant
JsonSchemaStructuredOutputRequest # name: str, schema: Mapping[str, JsonValue], strict: bool
validate_structured_output_request # (capability, request) -> None | ValueError
```

### 8.3 S3 Host compactor 接入路径

根据 accepted plan，Host compactor 在 S3 的接入链路为：

```text
1. 读取 RunnerSpec.structured_output_capability
2. 若 capability == NONE → 不构造 StructuredOutputRequest
3. 若 capability == JSON_OBJECT → 构造 JsonObjectStructuredOutputRequest()
4. 若 capability == JSON_SCHEMA → 构造 JsonSchemaStructuredOutputRequest(
       name=compact_output_json_schema_digest_v3() 产生的 stable schema name,
       schema=compact_output_json_schema_v3(),
       strict=True,
   )
5. 将 request 传入 AgentRunRequest(structured_output=request)
```

Engine 侧所有 S3 需要的类型已完备：

- capability 查询：`RunnerSpec.structured_output_capability` ✓
- JSON object 请求：`JsonObjectStructuredOutputRequest()` ✓
- JSON Schema 请求：`JsonSchemaStructuredOutputRequest(name=, schema=, strict=)` ✓
- 校验接入：`validate_structured_output_request` 或 AgentRunRequest 自动校验 ✓
- Engine 内部不拥有 compact schema：`JsonSchemaStructuredOutputRequest.schema` 类型为 `Mapping[str, JsonValue]`，Engine 不解释其业务含义。✓

### 8.4 无重复结构真源

- Engine 不定义 compact output 的 JSON Schema、template、parser、field names。
- Engine 不拥有 `compact_output_template_v3()`、`compact_output_json_schema_v3()`、`parse_compact_candidate_v3()` 等 Host-owned 函数（这些将在 S3 的 `dayu/host/compact_structure.py` 定义）。
- `digest` 不在 Engine request 类型中（已确认 `JsonSchemaStructuredOutputRequest` 仅含 `name/schema/strict`，无 `digest` 字段）。
- Engine `StructuredOutputCapability` 的三值 (`none/json_object/json_schema`) 是 provider-neutral transport capability，不表达 Host 的 compact business schema。
- Schema name/digest 的"同源"要求由 S3 Host 测试从同一 canonical structure 核对 transport identity，不建立 Engine 侧第二持久字段。

**S3 不需要新增 Engine 类型或字段。**

---

## 特别挑战：逐项裁决

### SC1: `build_request_payload` 的 `structured_output=None` default

**裁决**：已在 §3.4 记录为 LOW consistency note。功能安全（单一 caller 显式传参 + 内部 validator defense-in-depth），不阻塞 acceptance。

**Owner**：`dayu/engine/runners/openai/payload.py::build_request_payload`

### SC2: `AgentRunRequest` 的 `None` default

**裁决**：正确设计。`None` 是合法业务语义（不请求 structured output），不是省略。Plan 要求的 "required、无 default" 针对的是 `AsyncRunner.call`（Runner 调用边界），不是 `AgentRunRequest`（Host→Engine 请求构造边界）。

### SC3: runtime/Engine enum 双份定义

**裁决**：架构必须。已在 §1.3–§1.4 详细论证。runtime 不 import Engine → 需要独立 enum；Service 机械映射 fail-fast；当前值一致。残留 LOW 级关注（无自动化枚举对齐测试），已在 §1.4 记录。

### SC4: schema digest 只在测试断言中出现是否造成 owner drift

**裁决**：不造成 owner drift。Plan 明确要求 "schema name/digest 同源只要求测试从同一个 canonical schema bytes/structure 核对 transport identity，不建立第二持久字段"。当前实现严格遵守：

- `_canonical_schema_digest` 函数仅存在于测试文件 `tests/engine/runners/openai/test_payload_build.py`，是 owner test 的验证 helper。
- `JsonSchemaStructuredOutputRequest` 无 `digest` 字段。
- 生产代码中 digest 计算（如有）将在 S3 Host `compact_structure.py` 中作为 `compact_output_json_schema_digest_v3()` 暴露，由 Host 拥有。

---

## 综合评估

### 核心 PASS 项

| # | 审查维度 | 结论 |
|---|---|---|
| 1 | Engine 是 generic structured-output 唯一 owner | **PASS** |
| 2 | 无 compat alias / loose parser / provider special case / extra bag / downgrade / God helper | **PASS** |
| 3 | Required signatures 阻止遗漏；matrix validation 在正确 boundary | **PASS** (附 LOW consistency note) |
| 4 | Schema mapping 拒绝全部不变量；json_schema transport exact | **PASS** |
| 5 | Catalog capability 继承正确；DeepSeek=json_object、MiMo=none 基于显式配置 | **PASS** |
| 6 | Publication hash 完整一致；README 边界准确 | **PASS** |
| 7 | 全量迁移仅 typed breakage 机械变更，无隐藏行为修改 | **PASS** |
| 8 | S3 接口最小，无重复结构真源 | **PASS** |

### Findings 汇总

**HIGH severity（阻塞）**：0

**MEDIUM severity（建议修复）**：0

**LOW severity（consistency note，不阻塞）**：2

| ID | Severity | 描述 | Owner | 最小修复 |
|---|---|---|---|---|
| DS-LOW-01 | LOW | `build_request_payload(structured_output=None)` default 与 plan "required param" 原则的架构一致性偏离；功能安全（单一 caller + validator defense-in-depth） | `dayu/engine/runners/openai/payload.py:408` | 移除 default，要求所有 call site 显式传参（仅 `_call_impl` 一处） |
| DS-LOW-02 | LOW | runtime `StructuredOutputCapabilityConfig` 与 Engine `StructuredOutputCapability` 无自动化枚举对齐测试 | `tests/runtime/test_config_loader.py` 或 `tests/engine/contracts/test_runner_spec.py` | 新增 `test_runtime_and_engine_capability_enums_are_identical` 逐 member name/value 断言 |

### Reviewer interference 剔除确认

- `StructuredOutputCapabilityConfig` import 失败 → **作废**（venv 无开发安装）
- `models.json` SHA=`d817...` → **作废**（git stash 后基线偏离）
- `manifest` SHA=`9ebd...` → **作废**（同上）
- 以上伪观察均已在稳定基线重验后排除，不进入任何 finding。

### 最终结论

**S2 Engine structured-output slice: PASS（可进入 S2 review acceptance gate）**

所有 architecture/semantic-ownership/typing/test-gap 维度均通过独立 adversarial review。两条 LOW consistency note 不阻塞 acceptance，可由 controller 裁决是否在 S2 内修复或记录为后续 cleanup。

---

## 审查后状态

本 artifact 完成后，AgentDS 停在 idle。不执行任何 Git mutation、不派发 reviewer、不做 controller adjudication。所有后续 gate 动作（两路 re-review、controller 裁决、acceptance）由总控决定。
