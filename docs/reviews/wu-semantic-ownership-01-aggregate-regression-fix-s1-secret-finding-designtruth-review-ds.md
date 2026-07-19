# S1-SEC-F01 Design-Truth Security Review (AgentDS)

## Gate Identity

- **Reviewer**: AgentDS（独立 design-truth 审查，不修改任何文件）
- **Gate**: WU-SEMANTIC-OWNERSHIP-01 Slice 1 security finding 设计真源深度审查
- **Finding**: `S1-SEC-F01`
- **Evidence artifact**: `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-evidence.md`（SHA-256 `2f3fc19e4cdab8b93fd2e4e8b09008169e95d0ece4f7183431d3bd643b574bea`）
- **Status**: `COMPLETE / VERDICT BELOW`
- **Timestamp**: `2026-07-18T18:22:13+08:00`
- **本 artifact 不含任何 secret value、secret ref 名称或敏感 payload 正文**

---

## 1. 已读取文件清单（按顺序完整读取）

### 1.1 项目指令与设计真源

| # | 文件 | 读取状态 |
|---|------|---------|
| 1 | `AGENTS.md` | 完整读取 |
| 2 | `docs/host/issues-implementation-control.md` | 分段完整读取（566KB），重点读取 active work unit §WU-SEMANTIC-OWNERSHIP-01、R08 累计状态、current gate / next entry point |
| 3 | `docs/phaseflow-umbrella-optimization-control.md` | 完整读取 |
| 4 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 完整读取，重点读取 Topic 9（tool security）、Topic 3（Host LLM-safe arguments）、Topic 5（wait poller configuration ownership） |
| 5 | `docs/host/design.md` | 分段完整读取（379KB），重点读取 §2 分层边界、§3 runtime assembly（ConfigLoader/Service secret 保护职责）、§3.1 lane、per-run override contract（line 944 Host 不接收 API key 明文）、§18.4 Tool Authorization、CONTEXT_COMPACTION_ATTEMPT_REJECTED（EventLog 不能包含 API key） |
| 6 | `docs/engine/design.md` | 完整读取，重点读取 §8 RunnerSpec 与 RunnerCallOptions、§14 EngineEvent Stream、ToolExecutor handshake timeout |
| 7 | `docs/tool/design.md` | 完整读取，重点读取 §1 LLM-facing Tool Contract、§10 Tool Authorization And Defensive Safety |
| 8 | `docs/fins/design.md` | 完整读取 |
| 9 | `docs/ui/design.md` | 完整读取 |

### 1.2 S1-SEC-F01 证据与计划

| # | 文件 | 读取状态 |
|---|------|---------|
| 10 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-evidence.md` | 完整逐字节读取，SHA-256 已由 Controller 声明 |
| 11 | `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | 完整读取，重点读取 §2.2 AR-F01—AR-F07 closure matrix、§6.7 secret scan trigger、plan scope boundary |
| 12 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md` | 完整读取，重点 §4 已完成的 authorized implementation、§5 fresh command ledger、§6 stop rule 触发 |
| 13 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-stop-controller-adjudication.md` | 完整读取 |
| 14 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-second-stop-controller-adjudication.md` | 完整读取 |
| 15 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-third-stop-controller-adjudication.md` | 完整读取 |
| 16 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fourth-stop-controller-adjudication.md` | 完整读取 |
| 17 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md` | 完整读取 |
| 18 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md` | 完整读取 |

### 1.3 Production 代码链（逐行读取）

| # | 文件 | 读取范围 | 关键行 |
|---|------|---------|--------|
| 19 | `dayu/service/host_assembly.py` | line 1700-1765（`_runner_spec_from_model`、`_render_headers`） | `_render_headers` 从 `api_key_ref` 环境变量读取实际 API key，用 `str.replace()` 填进 Header 模板，返回含 `Authorization: Bearer <actual-key>` 的 `dict[str, str]` |
| 20 | `dayu/service/host_assembly.py` | line 1-100（模块导入、职责声明） | 模块声明 "不修改 Host public API" |
| 21 | `dayu/host/admission.py` | line 3517-3567（`_resolve_followup_effective_facts`） | 接收 effective `RunnerSpec`（含已渲染 Authorization），调用 `_effective_execution_config_json` 冻结为 JSON，写入 `USER_INPUT_ACCEPTED` |
| 22 | `dayu/host/admission.py` | line 3696-3731（`_replay_effective_execution_config`） | replay 时从 `source_execution_config` 还原 `RunnerSpec`（含已渲染 Authorization），重新冻结 |
| 23 | `dayu/host/_execution_config_projection.py` | 完整读取（613 行） | `runner_spec_json` line 169: `"headers": dict(sorted(runner_spec.headers.items()))` 原样投影所有 header 值（含 Authorization 明文）到冻结 JSON；`_headers_from_json` line 598-612 从 JSON 还原全部 header |
| 24 | `dayu/host/dispatch.py` | line 616-620（`PolicySnapshot` 定义）、line 3393-3417（`_build_run_input_with_lag_repair`）、line 3606-3617（`_local_policy_snapshot`）、line 4664-4679（`_policy_snapshot_from_effective_execution`） | dispatch/retry/replay 从 EventLog 冻结 JSON 还原 `PolicySnapshot.runner_spec`（含完整 headers），传入 `RunInputBuilder.build` |
| 25 | `dayu/host/run_input.py` | line 1869-1979（`RunInputBuilder.build`） | line 1975: `runner_spec=policy_snapshot.runner_spec` — 从 durable 还原的 `RunnerSpec`（含 Authorization 明文）直接传给 Engine `AgentRunRequest` |
| 26 | `dayu/engine/contracts/runner_spec.py` | line 250-369（`RunnerSpec` 定义） | `headers: Mapping[str, str]` 是 `RunnerSpec` 的必填冻结字段；`api_key_ref` 文档明确"不直接落 key 明文" |
| 27 | `dayu/engine/runners/openai/runner.py` | line 225-253（`_request_headers`） | line 237: `**dict(spec.headers)` 把 `RunnerSpec.headers` 的所有值（含 Authorization）直接作为 HTTP 请求头发送给 provider |
| 28 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md` | 完整读取 | Plan fix authorization scope |
| 29 | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-rereview-controller-adjudication.md` | 完整读取 | Plan re-review closure |

---

## 2. Code Evidence：完整 Production 链

以下链路基于以上 29 个文件的逐行直接证据，每一环均有具体行号支撑。

### 2.1 Secret 进入 `RunnerSpec`（Service 层）

**入口**: `dayu/service/host_assembly.py` line 1702-1733 `_runner_spec_from_model`

```text
host_assembly.py:1716  api_key_ref=model.api_key_ref
host_assembly.py:1717  headers=_render_headers(model.headers, api_key_ref=model.api_key_ref, env=env)
```

**渲染**: `dayu/service/host_assembly.py` line 1736-1764 `_render_headers`

```text
host_assembly.py:1749  api_key = env.get(api_key_ref)          # ← 从环境变量读取实际 key
host_assembly.py:1755  rendered_value = value.replace(         # ← 把 {{REF}} 替换为实际 key 值
                          f"{{{{{api_key_ref}}}}}", api_key.strip())
host_assembly.py:1763  rendered[name] = rendered_value        # ← 写入渲染后的 header dict
```

此时 `RunnerSpec.headers` 已包含类似 `{"Authorization": "Bearer sk-..."}` 的明文 secret。

### 2.2 Secret 进入 Host 并冻结到 EventLog（Host admission）

**入口**: `dayu/host/admission.py` line 3517-3567 `_resolve_followup_effective_facts`

```text
admission.py:3539  runner_spec = request.runner_spec if ... else baseline.runner_spec
                    # ↑ 含已渲染 Authorization 的 RunnerSpec
admission.py:3552  execution_config = _effective_execution_config_json(runner_spec=runner_spec, ...)
admission.py:3565  effective_execution_config=execution_config  # ← 写入 payload
```

**冻结投影**: `dayu/host/_execution_config_projection.py` line 156-181 `runner_spec_json`

```text
_projection.py:169  "headers": dict(sorted(runner_spec.headers.items()))
                     # ↑ 把含 Authorization 明文的 headers 完整写入 JSON
```

该 JSON 经过 `effective_execution_config_json` (line 54-90) 被包裹为 `{policy_snapshot_ref, policy_snapshot_digest, config: {runner_spec: {headers: {...}}}}`，最终写入 EventLog 的 `payload_json` 列，`event_type=USER_INPUT_ACCEPTED`，`event_class=canonical_fact`。

Controller 证据文档确认该 payload 在真实 compactor smoke `host.sqlite3` 的 `event_log` 表中被 plaintext secret scan 命中：
- `rowid=2`、`rowid=13`，共 2 条 canonical fact
- matched JSON path: `effective_execution_config.config.runner_spec.headers.Authorization`

### 2.3 Retry/Replay/Recovery 从 EventLog 还原 Secret

**Replay 入口**: `dayu/host/admission.py` line 3696-3731 `_replay_effective_execution_config`

```text
admission.py:3720  snapshot = _effective_execution_snapshot_from_json(source_execution_config)
admission.py:3721  runner_spec = snapshot.runner_spec  # ← 从 SQLite 还原的含 Authorization 的 RunnerSpec
admission.py:3724  _effective_execution_config_json(runner_spec=runner_spec, ...)
                    # ↑ 再次冻结（仍含 Authorization），写入新 RUN_STARTED
```

**Dispatch 还原**: `dayu/host/dispatch.py` line 4664-4679 `_policy_snapshot_from_effective_execution`

```text
dispatch.py:4673  snapshot = _effective_execution_snapshot_from_json(value)
dispatch.py:4674  PolicySnapshot(runner_spec=snapshot.runner_spec, ...)
                   # ↑ 从 durable JSON 还原含 Authorization 的 RunnerSpec
```

**RunInput 传递**: `dayu/host/run_input.py` line 1975

```text
run_input.py:1975  runner_spec=policy_snapshot.runner_spec
                    # ↑ 传给 AgentRunRequest，最终到达 Engine
```

**Engine 消费**: `dayu/engine/runners/openai/runner.py` line 235-237

```text
runner.py:235  headers = {"Content-Type": "application/json", **dict(spec.headers)}
                # ↑ Authorization 明文直接成为 HTTP 请求头
```

### 2.4 链路总结

```
ConfigLoader (读取 api_key_ref) → Service/Env (读实际 key)
  → host_assembly._render_headers ({{REF}} → 明文)
  → _runner_spec_from_model (RunnerSpec.headers 含 Authorization 明文)
  → Host admission._resolve_followup_effective_facts (接受含密文 RunnerSpec)
  → _execution_config_projection.runner_spec_json (headers → JSON)
  → EventLog payload_json (SQLite 明文存储)
  → [retry] admission._replay_effective_execution_config (从 SQLite 还原含密文 RunnerSpec)
  → [dispatch] dispatch._policy_snapshot_from_effective_execution (还原 PolicySnapshot)
  → RunInputBuilder.build (runner_spec=...)
  → AgentRunRequest.runner_spec
  → Engine OpenAIRunner._request_headers (Authorization 发送到 provider)
```

每一步的证据均记录在上述文件与行号中。

---

## 3. Design-Truth Direct Contradiction

以下两条 design truth 与 production 链存在直接矛盾，证据不依赖间接推断。

### 3.1 矛盾 A：Host 不接收 API key 明文 vs Host 接受含密文 RunnerSpec

**Design truth**: `docs/host/design.md` §3 runtime assembly line ~944

> Host 不接收 raw provider client、**API key 明文**、callable、无结构 dict override、extra payload 或 `policy_overrides`。`RunnerSpec.api_key_ref` 仍只是 **secret 引用名**，不是 secret 本体。

**Production behavior**: `dayu/host/admission.py` line 3539-3552

`_resolve_followup_effective_facts` 接收的 `request.runner_spec` 或 `baseline.runner_spec` 是一个完整的 `RunnerSpec` 实例，其 `headers` 字段已经包含 `_render_headers` 渲染后的 `Authorization: Bearer <actual-key>` 明文。Host 不做任何脱敏或拒绝，直接将整个 `RunnerSpec`（含 Authorization 明文）冻结为 durable JSON。

**直接证据**: `dayu/host/_execution_config_projection.py` line 169 `"headers": dict(sorted(runner_spec.headers.items()))` 没有对 `Authorization` 或任何敏感 header 名做 redaction/filter。所有 header key/value 原样进入 durable JSON。

### 3.2 矛盾 B：Service 负责 secret 脱敏/保护 vs Service 把已渲染密文传给 Host

**Design truth**: `docs/host/design.md` §3 line ~103

> ConfigLoader 不解析环境变量、不替换 secret、不脱敏，只原样读取 schema 表达的值。

> Service / execution environment 负责 provider client 创建、**secret 使用 / 脱敏 / 保护**、多 Run workflow、artifact、parser、replay、retry 与 stop policy。

**Production behavior**: `dayu/service/host_assembly.py` line 1736-1764

Service 的 `_render_headers` 确实渲染了 secret（职责正确），但随后把渲染后的 `RunnerSpec`（含明文 Authorization）直接传给 Host，没有在传给 Host 之前做脱敏。Host 接收后立即冻结到 EventLog。Service 的"保护"职责在 `RunnerSpec` 越过 Host boundary 时没有兑现——secret 以明文进入了 Host durable store。

### 3.3 矛盾 C：EventLog 不能包含 API key vs EventLog 实际包含

**Design truth**: `docs/host/design.md` §CONTEXT_COMPACTION_ATTEMPT_REJECTED line ~3403

> EventLog 不能包含 API key、headers、完整 raw prompt 或完整 provider payload

**Production behavior**: Controller 证据文档 §2 通过 fresh secret scan 证明真实 `host.sqlite3` 的 EventLog 中精确存在 2 条 `USER_INPUT_ACCEPTED` canonical fact，JSON path `effective_execution_config.config.runner_spec.headers.Authorization` 包含匹配的 secret value。

**直接证据**:
- `configured_secret_value_count=5`、`secret_value_match_count=3`、`matched_path_count=1`
- `event_type=USER_INPUT_ACCEPTED`、`event_class=canonical_fact`
- `matched_json_path=effective_execution_config.config.runner_spec.headers.Authorization`

### 3.4 矛盾 D：api_key_ref 只是引用 vs headers 中的渲染值使引用语义无效

**RunnerSpec 契约**: `dayu/engine/contracts/runner_spec.py` line 260-261

```python
:param api_key_ref: API key 引用名（不直接落 key 明文）；``None`` 表示
    本地或免鉴权 provider 不需要 API key header。
```

`api_key_ref` 确实被保留为引用名（`RunnerSpec.api_key_ref` 仍然是环境变量名），但 `RunnerSpec.headers` 在同一对象中包含了渲染后的明文 Authorization。两个字段在同一 frozen 对象中给出了互相矛盾的语义承诺：

- `api_key_ref` 说："这是密钥引用，不是密钥本身"
- `headers.Authorization` 说："这是密钥本身"

当整个 `RunnerSpec` 被冻结到 EventLog 后，`api_key_ref` 只是一个未被使用的注释——真正生效的是 `headers.Authorization` 中的明文值。

---

## 4. Adversarial 检查

### 4.1 Finding 是否为 valid blocking finding？

**结论：是 blocking finding，不接受任何 rejection argument。**

逐条排除可能的 rejection：

| 潜在 rejection | 为何不成立 | 直接证据 |
|---------------|-----------|---------|
| "只是 test false positive" | Controller 证据扫描的是真实 `host.sqlite3`（real compactor smoke 产出），不是测试 fixture；扫描命中了 EventLog 的 canonical fact，不是临时文件或测试 artifact | 证据 §2: `matched_path=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor/test_real_compactor_public_ope0/host.sqlite3` |
| "设计真源不矛盾" | 三个独立 design truth 陈述同时与本 production 链矛盾（见 §3） | design.md line 944, 103, 3403 |
| "这只是 smoke SQLite，不应 block Slice 1" | Production 链证明非 smoke 专有行为：`host_assembly._render_headers` → `admission._resolve_followup_effective_facts` → `_execution_config_projection.runner_spec_json` 是生产代码路径，任何 `open_host + submit_followup` 都会触发同一链 | 见 §2 完整链路 |
| "git diff 零命中，本 WU 未引入" | Controller 确认该投影实现来自 umbrella commit `2f2b73f8`（R3-A S1），属于本 umbrella 已实施代码的 remediation 审查范围 | 证据 §3 |
| "SQLite 文件 gitignored，不泄露" | gitignore 只保护 remote 不泄露；本地进程仍可读 SQLite，且设计真源明确要求 EventLog 不能包含 API key | design.md line 3403 |

### 4.2 是否存在足以拒绝该 finding 的直接 owner evidence？

**不存在。** 已完整检查 29 个文件，Design truth 一致指向 Host 不应接收/持久化 API key 明文、Service 负责密封 secret。Production 链中没有任何一处明确表示"Host 有意通过 `effective_execution_config` 持久化已渲染 Authorization 是设计意图"。

### 4.3 是否为 test false positive？

**不是。** 扫描命中的是真实 `host.sqlite3` 中 real compactor smoke 产出的 `USER_INPUT_ACCEPTED` canonical fact。这不是测试用的 synthetic key、不是 mock 注入的 fake value、不是测试 fixture 构建的构造 payload。命中路径 `workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor/` 是 plan §6.7 要求的 real smoke 产出。

### 4.4 是否存在禁止的局部方案？

按 Controller 证据 §4，以下均为不可接受的局部修复：

1. **局部 redaction**（仅在 `runner_spec_json` 中删除 Authorization，restore 时从 env 重新读取）：此为必要修复方向的一部分，但若只做 projection-side filter 而不同时修改 restore/replay 的补注逻辑，retry/replay 将使用无 Authorization 的 headers 导致 provider 鉴权失败。

2. **test shim**（替换 smoke 测试用的 synthetic key、skip real compactor 或在扫描中加 waiver）：不成立。Production 链证明非测试专有行为。

3. **下游 fallback/compatibility branch**：不成立。设计真源禁止下游补偿。

4. **统一 authorization framework**：越界且未设计。Topic 9 已明确当前 WU 不实现统一权限框架。

5. **把明文移到另一个 payload ref**：不解决根本问题。任何 durable 存储都不应包含 API key 明文。

---

## 5. §5 六问独立回答

### 5.1 S1-SEC-F01 是否为 valid blocking finding？

**是 blocking finding。**

Finding 基于 Controller fresh secret scan 的路径级证据（2 条 canonical fact、精确 JSON path），且直接关联到 production 链中 7 个具体代码位置的逐行证据。Design truth 三处独立陈述与本 production 链直接矛盾。没有一条证据可以推翻该 finding。

### 5.2 唯一正确 semantic owner 与最小跨层 boundary？

**Semantic owner 判定**:

| 语义 | 正确 Owner | 当前实际 Owner (错误) |
|------|-----------|---------------------|
| API key 明文值 | **Service / execution environment**（design.md line 115） | `RunnerSpec.headers`（Engine public contract 不设防字段）+ EventLog durable projection（Host internal） |
| Secret 脱敏/保护 | **Service**（design.md line 115, 944） | 无人执行——Service 把已渲染密文传给 Host，Host 不做脱敏直接冻结 |
| 冻结执行配置（供 replay/retry） | **Host admission** 冻结 stripped 配置 + **Service** 在 replay 时重新注入 secret | 当前 Host admission 冻结了含密文的完整 `RunnerSpec`，replay 直接从 durable truth 读取 |
| `api_key_ref` → 实际 key 的解析 | **Service**（在传递给 Runner 的最后时刻） | 当前 Service 在构造 Host 输入之前就解析并嵌入 `RunnerSpec.headers` |

**最小修改边界**:

```
必须修改的 owner:
  1. dayu/host/_execution_config_projection.py::runner_spec_json
     → headers 投影去除敏感值（Authorization 等），保留 header 模板与 api_key_ref
  2. dayu/host/_execution_config_projection.py::_headers_from_json
     → 还原后 headers 不含已渲染的敏感值
  3. dayu/service/host_assembly.py
     → replay 路径：从 restored header 模板 + api_key_ref 重新渲染
     或由 Host 提供 replay injection point 让 Service 注入 secret

必须零改动的层:
  - Engine（RunnerSpec 契约不变，但 headers 在进入 Engine 前必须已含渲染后的值）
  - Fins（不参与 provider auth）
  - UI（不参与 provider auth）
  - dayu.runtime（层中立基础设施）

可能需要设计真源补充的层:
  - docs/host/design.md
    → 明确 durable RunnerSpec projection 的 header redaction boundary
    → 明确 replay/retry 的 header re-render injection point
```

### 5.3 当前 design truth 是否足以 code-generation？

**不足以 code-generation。** 存在以下具体缺口：

1. **Host durable projection 没有定义 header redaction boundary。** `docs/host/design.md` §3 只说 Service 负责脱敏保护，但没有说明 Host durable projection 应该投射 `headers` 的哪些部分（模板？引用？subset？），以及谁在什么时刻负责重建。

2. **replay/retry 路径没有定义 secret re-injection point。** 当前 design truth 只说 Host admission/dispatch 冻结 effective config 以支持 replay/recovery，但没有任何说明 replay 时如何从 `api_key_ref` 重新获得 key 而不经过 durable 存储。

3. **`SubmitFollowupRequest.runner_spec` 的 contract 没有明确 header 语义。** 当前 design truth line 944 说 per-run override 必须为 typed value 但不能含 API key 明文——但如果 override 的 `RunnerSpec` 需要不同的 auth header，且 `api_key_ref` 只是引用不是值，那么 override 的 headers 中应放什么？占位符模板？空 headers 然后 Service 按 `api_key_ref` 渲染？

**需要用户裁决的 product decision**:

- **(A)** Header 模板（含 `{{api_key_ref}}` 占位符）进入 durable frozen config + `api_key_ref`，replay 时 Service 从 env 重新渲染。
- **(B)** `api_key_ref` 进入 durable frozen config，headers 不含任何 auth 相关 key；replay 时 Service 从 model config 重新构造 auth header。
- **(C)** Host 完全不持久化 headers，replay 时从 opener baseline 重新取 `RunnerSpec`。

本 reviewer 推荐 **(A)**，因为它保留了 per-run header override 的语义（非 auth headers 如自定义 tracking headers 可以 freeze），同时将 auth header 的渲染推迟到使用时。

### 5.4 如何同时满足所有约束？

六个约束的同时满足方案（基于推荐方案 A）：

| 约束 | 如何满足 |
|------|---------|
| **EventLog 零 secret value** | `runner_spec_json` 中 `headers` 投影时：对于 key 大小写不敏感匹配 `authorization`、`api-key`、`x-api-key` 等已知 auth header 名，写入占位符字符串 `"{{<api_key_ref>}}"` 而非实际值；或更简单地，直接不写入 auth header 而仅依赖 `api_key_ref` 重建 |
| **Current Run 执行** | 不变：Service 在构造 `RunnerSpec` 时仍渲染完整 headers（含 Authorization），传给 Host admission → dispatch → Engine RunInputBuilder → AgentRunRequest → Engine Runner。当前 run 的执行路径与现在完全一致 |
| **Retry/Replay/Recovery 可解释** | `effective_execution_config` 冻结 `api_key_ref` + 非 auth header 模板 + `runner_spec_source`（如 `"opener_baseline"` 或 `"request"`）。replay 时，从 durable config 还原 `api_key_ref`，然后 Service 在 replay admission 路径中调用 re-render helper 重建完整 headers。retry 同理 |
| **Per-run RunnerSpec override** | 若请求显式提供了 `runner_spec`（含新的 `api_key_ref` 或不同的 header 模板），`_resolve_followup_effective_facts` 将其冻结为 durable config 时遵循同一 redaction 规则。replay 用同一 `api_key_ref` 重建 |
| **Service secret protection** | Service 是唯一能调用 `_render_headers` 的层。Host 永远不持有可渲染 secret 的 env access；在 durable path 中只存储模板/引用，在 dispatch 时不自行渲染 |
| **Host 不接收 API key 明文** | Host admission 接收的 `RunnerSpec.headers` 在 freeze 到 EventLog 时已经 strip auth values。Host durable store 中永不存在 API key 明文。Host dispatch 从 durable 还原的 `RunnerSpec.headers` 不含 Authorization，但在传给 Engine 之前，由 Service/Runtime assembly 在 dispatch boundary 补注 |

具体实现 seam：

1. `_execution_config_projection.py::runner_spec_json` 中 headers 投影时识别并过滤 auth headers（具体策略待用户从 §5.3 A/B/C 中选择）。
2. `_execution_config_projection.py::_headers_from_json` 还原时 headers 不含已过滤的 auth header。
3. `host_assembly.py` 新增 `_restore_headers_from_template_or_render` helper，在 replay/retry admission 或 dispatch boundary 将 `api_key_ref` + header 模板重新渲染为含 Authorization 的完整 headers。
4. admission.py `_replay_effective_execution_config` 调用上述 helper 重建完整 `RunnerSpec.headers`。
5. Secret scan 新增 negative test：断言 real smoke 产生的 `host.sqlite3` EventLog 零 secret match。

### 5.5 是否存在不引入 authorization framework 的最小方案？

**存在。** 上述方案（§5.4）不引入：

- 统一 authorization framework（Topic 9 明确当前 WU 不实现）
- permission schema / role model / capability token
- 新的 deferred Issue 能力
- Issues #142（workspace migration）、#151（write assets）、#175（Fins process isolation）、#177（TruncationManager）、#178（browser storage-state lifecycle）的越界修改

方案只修改三个既有 owner boundary：
1. `_execution_config_projection.py`（Host internal）：header redaction rule
2. `host_assembly.py`（Service）：header re-render helper
3. `admission.py`（Host internal）：replay re-render call site

这完全在设计真源已授权的 Service/Host boundary 内，且仅在既有 `effective_execution_config` durable contract 上增加 header projection 的敏感字段过滤，不新建 storage schema、不改变 EventLog shape（headers 仍是一个 JSON object，只是 auth 字段值为占位符或空）。

### 5.6 需要哪些 negative/real tests 与 secret scan？

| 测试类别 | 具体要求 | 验证信号 |
|---------|---------|---------|
| **Negative test: durable projection redaction** | 构造 `RunnerSpec` 含 `Authorization` / `api-key` / `x-api-key` header，调用 `runner_spec_json`，断言输出 JSON 中不包含原始 secret value。断言 `api_key_ref` 字段保留 | `runner_spec_json` 输出 JSON 中 `headers.Authorization` 不存在或为占位符 |
| **Negative test: round-trip redaction** | `runner_spec_json` → `_headers_from_json` 还原后，断言 `Authorization` 不在 headers 中。断言 `api_key_ref` 正确还原 | Restored `RunnerSpec.headers` 无 auth values |
| **Negative test: replay restores auth** | replay 路径从含 `api_key_ref` 的 durable config 还原后，通过 re-render helper 重建 headers，断言 `Authorization` 存在且值从 env 正确读取 | Replay `RunnerSpec.headers.Authorization` 为当前 env 中的值 |
| **Negative test: missing env on replay fails fast** | `api_key_ref` 指向不存在的 env var 时，replay 在 admission 阶段抛出 clear error（非静默以无 auth header 发送请求） | `ValueError("missing env ...")` |
| **Negative test: env value changed between runs** | 第一次 run 冻结 config 后改 env var 值，replay 使用当前 env 值（非历史值） | Replay `Authorization` = 当前 env var value |
| **Real smoke: fresh secret scan zero match** | 方案实施后，重新执行 real compactor smoke，运行同等 secret scan。断言 `secret_value_match_count=0` | `matched_path_count=0` |
| **Smoke: EventLog header projection invariant** | real smoke 后读 EventLog，断言 `effective_execution_config.config.runner_spec.headers` 不含已知 auth header key；断言 `api_key_ref` 值为有效的环境变量引用名 | Durable JSON headers 中无 `Authorization`/`api-key`/`x-api-key` key |
| **Existing regression: RunInputBuilder dispatch** | 现有 dispatch 测试确认 policy_snapshot → AgentRunRequest.runner_spec 的完整链路仍通过，`Authorization` 在工作请求中存在（仅从 Service re-render，非从 durable read） | 受影响的 dispatch/run_input tests 全部通过 |

**Secret scan 规则**（不可弱化）:
- 扫描对象：implementation 后的 fresh `host.sqlite3`（real compactor smoke 产出）
- 匹配项：所有 `event_type=USER_INPUT_ACCEPTED` 且 `event_class=canonical_fact` 且 JSON path 包含 `runner_spec.headers` 的记录
- 通过标准：`secret_value_match_count=0`
- 不接受：waiver、skip、解为 test-only、缩小扫描范围、换 synthetic key

---

## 6. Findings

### F-01 [严重] EventLog 持久化含 API key 明文——设计真源直接矛盾

- **入口/函数**: `dayu/host/admission.py::_resolve_followup_effective_facts` → `dayu/host/_execution_config_projection.py::runner_spec_json`
- **文件(行号)**:
  - `dayu/host/_execution_config_projection.py:169`（headers 原样投影）
  - `dayu/service/host_assembly.py:1755`（secret 渲染）
  - `dayu/host/admission.py:3552`（冻结到 EventLog）
- **输入场景**: 任何 `submit_followup` 调用，Service 已将 `api_key_ref` 渲染为实际 Authorization header value，构造了 `RunnerSpec`，传给 Host admission
- **实际分支**: `runner_spec_json` 对 `headers` 字段执行 `dict(sorted(runner_spec.headers.items()))`——对所有 header key/value 无差别投影，不识别 `Authorization` 或任何 auth header
- **预期行为**（按 design truth line 944, 103, 115, 3403）: Host 不接收 API key 明文；`RunnerSpec.api_key_ref` 只是引用名；EventLog 不能包含 API key；Service 负责 secret 脱敏/保护
- **实际行为**: API key 明文通过 `RunnerSpec.headers.Authorization` 写入 EventLog canonical fact（SQLite），在 real smoke 中精确命中 2 条记录、matched JSON path 为 `effective_execution_config.config.runner_spec.headers.Authorization`
- **直接证据**:
  - `_execution_config_projection.py:169` 无 header name-based filter
  - Controller fresh secret scan：`configured_secret_value_count=5, secret_value_match_count=3, matched_path_count=1`
  - 命中位置：`event_type=USER_INPUT_ACCEPTED, event_class=canonical_fact, matched_json_path=effective_execution_config.config.runner_spec.headers.Authorization`
  - Production 链在 7 个代码位置被逐行验证（见 §2）
- **影响**: API key 明文存储在本地 SQLite 文件中，任何可读取 workspace 的进程/用户可获取 provider API key；违反设计真源中 Host 不接收 API key 明文、EventLog 不能包含 API key、Service 负责 secret 保护的三个独立约束
- **建议改法和验证点**:
  1. `runner_spec_json` 中 headers 投影时，识别并排除 auth header（`Authorization`、`api-key`、`x-api-key` 等），保留 `api_key_ref` 字段
  2. `_headers_from_json` 还原后 headers 不含 auth header
  3. replay/retry admission 中新增 re-render step：从 `api_key_ref` + header 模板（或从 opener baseline）重建完整 headers
  4. 验证点见 §5.6 完整 test/security matrix
- **修复风险**: 中（需要精确处理 replay/retry/dispatch 三条路径的 header 重建；需要确保 `RunnerSpec` 的 `api_key_ref` 在各个路径中正确传递）
- **严重程度**: **严重** — 设计真源直接矛盾、安全敏感数据泄露到 durable store、影响所有 production run 路径（非边角路径或 smoke-only）

### F-02 [高] `RunnerSpec` 契约自相矛盾：`api_key_ref` 声称不落明文但 `headers` 同时包含明文

- **入口/函数**: `dayu/engine/contracts/runner_spec.py::RunnerSpec` + `dayu/service/host_assembly.py::_render_headers`
- **文件(行号)**:
  - `dayu/engine/contracts/runner_spec.py:260-262`（docstring: "不直接落 key 明文"）
  - `dayu/engine/contracts/runner_spec.py:287`（`headers: Mapping[str, str]` — 无类型区分）
  - `dayu/service/host_assembly.py:1755`（渲染 `{{REF}}` → 明文）
- **输入场景**: Service 从 `ModelConfig` 构造 `RunnerSpec`，`api_key_ref` 是 `"MY_API_KEY"`，`headers` 包含 `{"Authorization": "Bearer {{MY_API_KEY}}"}` 模板
- **实际分支**: `_render_headers` 将模板渲染为含明文的 `{"Authorization": "Bearer sk-..."}`；`RunnerSpec.headers` 是 `Mapping[str, str]`，对 auth vs non-auth header 无类型区分
- **预期行为**: 如果 `api_key_ref` 已经承载了 API key 引用语义，则 `headers` 不应再包含同一个已渲染的 key value；或 `headers` 应有显式区分（auth headers vs static headers）
- **实际行为**: 同一 `RunnerSpec` 实例中，`api_key_ref` 声明它是引用，`headers.Authorization` 包含实际值——两个字段给出互相矛盾的语义承诺。当整个对象被冻结到 EventLog 时，`api_key_ref` 成为未被消费的注释
- **直接证据**: `RunnerSpec` dataclass line 286-287 的 `api_key_ref: str | None` 和 `headers: Mapping[str, str]` 无互斥约束、无 auth header 过滤、无 construction-time invariant（`__post_init__` 不检查 headers 是否包含与 `api_key_ref` 对应的已渲染值）
- **影响**: `api_key_ref` 虽然是引用名，但其存在与否不影响任何下游行为（Engine Runner 只读 `headers`，不读 `api_key_ref`）——这是一个 dead field，导致设计意图（"不直接落 key 明文"）无法通过类型系统强制
- **建议改法和验证点**: 修复 F-01 后，`headers` 在进入 Host 前/被冻结到 EventLog 前不应含 auth 明文，`api_key_ref` 成为重建 auth header 的准确引用
- **修复风险**: 低（只涉及明确 existing auth header 集的过滤规则，不需要改 `RunnerSpec` 类型定义本身）
- **严重程度**: 高 — 契约矛盾导致设计约束无法被代码强制，是 F-01 的 root cause 之一

### F-03 [中] Design truth 缺少 durable header projection 的 redaction boundary 定义

- **入口/函数**: N/A（design doc gap）
- **文件(行号)**: `docs/host/design.md` §3（runtime assembly boundary）、`docs/host/design.md` §per-run override contract（line 944）
- **输入场景**: 设计真源当前状态：
  - line 944: "Host 不接收 API key 明文"、"`api_key_ref` 是 secret 引用名"
  - line 103: "Service 负责 secret 脱敏/保护"
  - line 115: "Service 负责 provider secret 使用/脱敏/保护"
  - line 3403: "EventLog 不能包含 API key"
  - 但没有定义：Host durable projection 中 `headers` 的 redaction boundary 是什么、replay 时谁负责重建
- **实际分支**: 无分支——这是一个 specification gap
- **预期行为**: Design truth 应明确：
  1. `effective_execution_config.runner_spec.headers` 在 durable JSON 中不包含哪些 key（auth headers: `Authorization`, `api-key`, `x-api-key`, `Proxy-Authorization` 等）
  2. Replay admission 时，谁从 `api_key_ref` 重建 `Authorization`（Service via injection point / Host assembly helper）
  3. `SubmitFollowupRequest.runner_spec` override 的 header 语义（override 中 headers 是否允许包含 auth header？是否只允许模板占位符？）
- **实际行为**: 生产代码按"headers 全量冻结"的默认行为运行（因为未经 redaction 约束），导致 F-01
- **直接证据**: 当前 `docs/host/design.md` 全文搜索无 "header redact" / "header filter" / "durable header projection" / "replay header render" 等短语
- **影响**: 没有 design truth 的 redaction boundary，即使代码修了 F-01，后续 maintainer 也可能因为"headers 应全量冻结以支持 replay"而恢复当前行为
- **建议改法和验证点**: 实施 F-01 后补写 design truth：
  - `docs/host/design.md` §3 / §per-run override 中新增 : "Host durable effective execution config projection must redact authentication header values (Authorization, api-key, x-api-key, Proxy-Authorization) before EventLog append. Replay admission must reconstruct authentication headers from api_key_ref by delegating to Service assembly or a well-defined re-render injection point."
- **修复风险**: 低（纯 design doc 补写）
- **严重程度**: 中 — specification gap 是 F-01 的 root cause

---

## 7. Slice 1 实现与 Secret Finding 的关系

当前 Slice 1 的三个 test delta（`test_host_admin.py` wait_poller_policy fixture、`test_smoke_web_ci.py` logging harness、`test_public_compact_smoke.py` current schema oracle）与 S1-SEC-F01 不共享同一个 semantic owner：

- AR-F01（wait_poller_policy fixture）→ test fixture owner
- AR-F03（logging harness）→ test harness owner
- AR-F04（compact manifest/artifact association）→ test oracle owner
- S1-SEC-F01（secret in EventLog）→ Host durable projection + Service header rendering boundary owner

S1-SEC-F01 的修复边界完全在 `_execution_config_projection.py` + `admission.py`（replay）+ `host_assembly.py`（re-render helper）——这些生产代码不属于 Slice 1 的三个 authorized test 范围。因此：

- S1-SEC-F01 是 A NEW FINDING，不是对 S1 已有三个 test delta 的 review 发现
- S1-SEC-F01 的修复是一个新的 implementation slice（或 S1 的补充工作），需要独立的 plan authorization
- Controller 已裁定 "AgentCodex不得自行修复；三测试delta与implementation artifact保持protected"

---

## 8. 需要用户裁决的问题

| # | 问题 | 推荐方案 | 影响 |
|---|------|---------|------|
| Q1 | Header 模板 vs api_key_ref only：replay 时如何重建 headers？（§5.3 A/B/C） | **方案 A**：headers 模板 + `api_key_ref` 进入 durable config，replay 时 Service 从 env 重新渲染 | 决定 `runner_spec_json` 的 header filter 精确逻辑和 `_restore_headers` 的实现 shape |
| Q2 | 此修复放在哪个 slice？ | 推荐作为 S1-SEC-F01 remediation（非 AR-F01/F03/F04 修复），可并入 S1 的 authorized scope 或作为独立 remediation slice | 影响 S1 review gate 和 Controller adjudication 的 scope |
| Q3 | Auth header 名称闭集：`Authorization`、`api-key`、`x-api-key`、`Proxy-Authorization` 是否足够？ | 推荐使用固定闭集（case-insensitive match），不引入动态配置 | 决定 `runner_spec_json` 中 header filter 的具体实现 |
| Q4 | Replay 时 env var missing 的行为：fail fast 还是使用 opener baseline？ | **推荐 fail fast**（`ValueError` 而非静默降级） | 决定 replay admission 错误语义 |
| Q5 | `SubmitFollowupRequest.runner_spec` override 中 headers 是否允许包含 auth header 值？ | **推荐不允许**：override 只能传 `api_key_ref` + 非 auth header 模板。若 override 需要不同的 auth，应通过不同的 `api_key_ref` 表达 | 决定 per-run override validation 的 invariant |

---

## 9. Test/Security Matrix

| 编号 | 类别 | 测试 | 通过标准 |
|------|------|------|---------|
| T-N1 | Negative | `runner_spec_json` 输入含 `Authorization: Bearer sk-abc`，输出 JSON `headers` 中无 `Authorization` key；`api_key_ref` 保留 | Authorization absent from durable JSON |
| T-N2 | Negative | `runner_spec_json` 输入含 `api-key: value`、`x-api-key: value`、`Proxy-Authorization: Basic xxx`，所有被过滤 | All auth headers absent |
| T-N3 | Negative | `runner_spec_json` 输入含 `X-Custom-Tracker: track-123`（非 auth header），保留 | Non-auth headers preserved |
| T-N4 | Negative | `runner_spec_json` → `_headers_from_json` round-trip，还原后 auth headers 不存在，non-auth headers 正确 | Round-trip preserves non-auth, strips auth |
| T-R1 | Real | Replay admission：从含 `api_key_ref` + header 模板的 durable config 重建 `RunnerSpec`，`Authorization` 正确渲染 | Replay RunnerSpec.headers.Authorization = env[api_key_ref] |
| T-R2 | Real | Replay admission：`api_key_ref` 指向 missing env var，抛出 `ValueError("missing env ...")` | Fail fast, clean error |
| T-R3 | Real | Replay admission：env var 值在 freeze → replay 之间变更，使用当前值 | Authorization matches current env |
| T-S1 | Security scan | Real compactor smoke → fresh `host.sqlite3` → secret scan：`secret_value_match_count=0` | Zero match in EventLog |
| T-S2 | Security scan | 扫描 `effective_execution_config.config.runner_spec.headers` 下所有值，无 auth header key | No Authorization/api-key/x-api-key/Proxy-Authorization key |
| T-E1 | Existing | dispatch `PolicySnapshot` → `RunInputBuilder.build` → `AgentRunRequest.runner_spec` 链路正常 | Existing dispatch/run_input tests pass |
| T-E2 | Existing | admission `submit_followup` → `USER_INPUT_ACCEPTED` 完整链路 | Existing admission tests pass |
| T-E3 | Existing | Host admin smoke / public compact smoke / real compactor smoke | All existing smoke tests pass |
| T-C1 | Coverage | `_execution_config_projection.py` header redaction path 有独立 test coverage | ≥80% |

---

## 10. Residual Risk

| 风险 | 影响 | 缓解 |
|------|------|------|
| **Service 在 Host 之前渲染 secret 的模式未根本改变** | Secret 在 Service 进程中以明文存在于内存。如果 Service 进程被 dump，secret 仍可泄露。这是 Service 进程级安全问题，超出本 WU 的 Host 边界 | 当前方案只解决 durable 泄露（SQLite），不解决内存泄露。Service 进程安全是运维/部署层面问题，不属于 Host 设计真源范围 |
| **Replay 依赖环境变量在 replay 时刻可用** | 如果 replay 发生在不同部署环境、env var 未配置或已过期，replay 将失败 | 设计选择（Q4 fail fast）而非静默降级。如果业务要求跨环境 replay，需 future design 考虑 secret manager/vault 集成 |
| **Header filter 闭集可能不完整** | 如果 provider 使用非标准 auth header 名，可能漏过滤 | 推荐使用 `api_key_ref` 的语义来确定 auth header（因为 `api_key_ref` 已知对应的 header key 是 `Authorization`），而不是仅靠名称启发式。这是实现阶段的细节 |
| **此修复方案从 umbrella WU R3-A S1 (`2f2b73f8`) 反向修正** | 修正路径涉及同一个文件的既有实现，需确保不引入 regression | full existing test suite + real smoke 覆盖 |

---

## 11. Verdict

**S1-SEC-F01 是 valid blocking finding。**

理由：
1. **设计真源直接矛盾**：三处独立 Host design truth 陈述（Host 不接收 API key 明文、EventLog 不能包含 API key、Service 负责 secret 脱敏/保护）与当前 production 链在 7 个代码位置逐行矛盾。
2. **不是 test false positive**：命中位置是 real compactor smoke 产出的真实 `host.sqlite3` EventLog canonical fact。
3. **唯一 semantic owner 清晰**：Service 应拥有 secret 渲染与保护，Host 应只存储 `api_key_ref` + header 模板，在 durable boundary 执行 auth header redaction。
4. **最小方案存在**：只需修改 `_execution_config_projection.py`（header filter）、`host_assembly.py`（re-render helper）、`admission.py`（replay re-render call site）。不需要 authorization framework、不需要新 Issue。
5. **当前 design truth 不足以 code-generation**：缺少 durable header projection redaction boundary 定义和 replay re-injection point 定义。需要用户先确认 §8 Q1-Q5。

本 review 不修改任何文件，不启动 subagent，不 review 当前三测试实现本身。AgentDS 完成独立 design-truth 审查后停止。
