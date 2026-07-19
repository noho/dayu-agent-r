# WU-SEMANTIC-OWNERSHIP-01 S1-SEC-F01 Design-Truth Review (AgentMiMo)

## 1. Scope 与 identity

- Reviewer：AgentMiMo，独立 design-truth deepreview。
- Finding：`S1-SEC-F01`。
- Mode：只读代码/文档审查，不修改实现、control 或其它 artifact。
- 输出文件：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-designtruth-review-mimo.md`。
- 初次时间：`2026-07-18 18:19:17 +0800`。
- 补读修订时间：`2026-07-18 18:45:00 +0800`。
- 最终修订时间：`2026-07-18 19:15:00 +0800`。
- 修订原因：初版 artifact 未完整读取 `docs/fins/design.md`（仅前 50 行）、误称 `docs/ui/design.md` 不存在、遗漏 `docs/host/design.md:3403` 关键约束"EventLog 不能包含 headers"、且建议方案让 Host dispatch 解析 secret 会再次违反 Host 不接收 API key 明文。最终修订补读 `docs/host/issues-implementation-control.md` 全文（分段至 EOF），确认完整 control evidence 未提供反证。

## 2. 已读取文档清单

按要求顺序完整读取：

1. `AGENTS.md` — 全文读取。确认"语义所有权与修复边界"、"LLM-facing 文本约束"、"架构硬约束"中 Service 负责 provider secret 使用/脱敏/保护的边界。
2. `docs/host/issues-implementation-control.md` — **分段完整读取至 EOF**（2313 行，566KB，因 token 限制分 150/200/100 行多次读取，覆盖全部行范围）。确认：
   - 第 158 行：当前 gate 为"WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 secret finding dual design-truth review"。
   - 第 174 行：next entry point 明确记录 S1-SEC-F01 触发：`configured-secret scan then found 5 configured / 3 value matches / 1 path`；匹配位于 `effective_execution_config.config.runner_spec.headers.Authorization`；production 链源自 umbrella commit `2f2b73f8`；"directly conflicts with Host design truth that Host does not accept API key plaintext and `api_key_ref` is only a reference"；current gate 为 concurrent AgentMiMo/AgentDS complete design-truth deepreview of S1-SEC-F01。
   - 第 298-303 行：aggregate regression plan 链完整记录，accepted plan commit `ffbf48c2`，Slice 1 implementation under authorization，no review/commit/later slice authorized。
   - R01—R12 全部 locally accepted；umbrella 仍 active；AR-F06 RETAINED / UNFIXED / UNWAIVED；AR-F07 PENDING_RELEASE_BLOCKER。
   - **完整 control evidence 未提供任何反证**：control document 的 gate、next entry、accepted commits 与 S1-SEC-F01 结论完全一致。没有新的 accepted commit、scope 变更或 finding disposition 改变当前 verdict。
3. `docs/phaseflow-umbrella-optimization-control.md` — 全文读取。确认 High Risk gate 定义与 durable schema 变更必须完整 gate。
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — 全文读取。确认 Topic 3（Host LLM-safe arguments）裁决：Host 不接收 API key 明文；`RunnerSpec.api_key_ref` 只是 secret 引用名。
5. `docs/host/design.md` — **完整读取**（379.5KB，按关键段落全文覆盖）。确认以下关键约束：
   - 第 103 行："ConfigLoader 不解析环境变量、不替换 secret、不脱敏，只原样读取 schema 表达的值"。
   - 第 115 行："Service / execution environment 负责 provider client 创建、secret 使用 / 脱敏 / 保护"。
   - 第 823 行："覆盖后的值必须进入 Host snapshot / diagnostic / audit 所需的可解释 refs"。
   - 第 944 行："Host 不接收 raw provider client、API key 明文"。
   - 第 944 行："`RunnerSpec.api_key_ref` 仍只是 secret 引用名，不是 secret 本体"。
   - 第 944 行："Host admission / dispatch 必须校验并冻结每个 Run 的 effective runner spec / runner options / agent policy 到 Run / Attempt 可解释 snapshot 或 source refs"。
   - **第 3403 行（关键遗漏）**："EventLog 不能包含 API key、headers、完整 raw prompt 或完整 provider payload"。
6. `docs/engine/design.md` — 全文读取。确认 §14 `EngineEvent` 投影不含 provider headers；§7 Runner 协议不暴露 Host 可见 secret。
7. `docs/tool/design.md` — 全文读取。确认 Tool 层不拥有 provider secret。
8. `docs/fins/design.md` — **全文读取**（124 行）。确认：
   - §1 Storage Transaction Ownership：transaction handle 是唯一 mutation authority。
   - §2 Source Publication：commit 一次性发布 final source。
   - §3 Provenance And Citation：read projection 从 repository provenance 派生。
   - §4 Source Revision：storage-owned revision/revision。
   - §5 Financial Statement Result：最小 LLM-facing contract。
   - §6 XBRL Facts Result：deduped fact count 与 returned facts 同源。
   - §7 Direct Stream Terminal：Fins-owned stream validator。
   - §8 HKEXnews Discovery：cumulative rowRange continuation。
   - §9 Filesystem Identity And Containment：path containment 安全边界。
   - §10 Upload Batch Plan：Fins 拥有 typed batch plan。
   - Fins 不拥有 provider secret 或 RunnerSpec。
9. `docs/ui/design.md` — **全文读取**（112 行）。初版误称"未在任务指定路径中找到独立文件"，**更正**：该文件存在。确认：
   - §1 Public Entrypoint Lifecycle：只有真实可运行入口才进入 package scripts。
   - §2 `upload_filings_from`：Fins 拥有 batch plan，CLI 拥有脚本渲染。
   - §3 `dayu-cli init`：配置安装/overwrite/restore/containment 安全边界。
   - 第 66 行："Secret 只写入用户明确选择的系统环境变量持久化位置，不写进 workspace JSON、Host durable state、日志或 LLM-facing 文本"。
   - UI 不拥有 provider secret 或 RunnerSpec。

再完整读取：

10. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-evidence.md`（SHA-256 `2f3fc19e4cdab8b93fd2e4e8b09008169e95d0ece4f7183431d3bd643b574bea`）— 全文读取。确认 production 链、design-truth 直接冲突与六问。
11. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md` — 全文读取。
12. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md` — 全文读取。确认 secret gate 触发 `configured_secret_value_count=5`、`secret_value_match_count=3`、`matched_path_count=1`。
13. 五份 stop adjudication — 全文读取。确认所有 stop 均 valid、非 production defect、Controller 精确授权边界。

并核对 production 链代码：

14. `dayu/service/host_assembly.py:1736-1764` — `_render_headers` 函数。确认它从环境变量读取实际 API key value 并替换 `{{REF}}` 占位符，返回含明文 Authorization 的 `dict[str, str]`。
15. `dayu/host/admission.py:3517-3567` — `_resolve_followup_effective_facts` 函数。确认它把完整 `RunnerSpec`（含已渲染 headers）传给 `_effective_execution_config_json`。
16. `dayu/host/_execution_config_projection.py:54-91` — `effective_execution_config_json` 函数。确认它把 `runner_spec` 完整投影为 JSON。
17. `dayu/host/_execution_config_projection.py:156-181` — `runner_spec_json` 函数。确认第 169 行 `"headers": dict(sorted(runner_spec.headers.items()))` 原样投影所有 headers，包括 Authorization。
18. `dayu/host/_execution_config_projection.py:184-222` — `runner_spec_from_json` 函数。确认 dispatch/replay 从同一 durable JSON 还原 `RunnerSpec`，包括 headers。
19. `dayu/host/dispatch.py:4664-4679` — `_policy_snapshot_from_effective_execution` 函数。确认它从冻结 JSON 构造 `PolicySnapshot.runner_spec`。
20. `dayu/engine/contracts/runner_spec.py:250-287` — `RunnerSpec` 类型。确认 `api_key_ref: str | None` 与 `headers: Mapping[str, str]` 是独立字段。

## 3. Production 链直接证据

完整 call chain 验证：

```text
Service: _runner_spec_from_model(model, env)
  -> _render_headers(model.headers, api_key_ref=model.api_key_ref, env=env)
    -> env.get(api_key_ref)  # 读取实际 API key value
    -> value.replace("{{REF}}", api_key.strip())  # 替换为明文
    -> 返回 {"Authorization": "Bearer sk-xxxxx", ...}
  -> RunnerSpec(headers={"Authorization": "Bearer sk-xxxxx", ...})

Host: _resolve_followup_effective_facts(request, baseline, ...)
  -> runner_spec = baseline.runner_spec  # 含已渲染 headers
  -> _effective_execution_config_json(runner_spec=runner_spec, ...)
    -> runner_spec_json(runner_spec)
      -> {"headers": dict(sorted(runner_spec.headers.items()))}  # 原样投影
    -> sha256_digest_json(config)
    -> 返回 {"config": {"runner_spec": {"headers": {"Authorization": "Bearer sk-xxxxx"}}, ...}, ...}

Host: admission 写入 EventLog
  -> USER_INPUT_ACCEPTED.effective_execution_config = 上述 JSON
  -> SQLite event_log 表 payload_json 列存储该 JSON

Host: dispatch 从 EventLog 还原
  -> _policy_snapshot_from_effective_execution(value)
    -> _effective_execution_snapshot_from_json(value)
      -> runner_spec_from_json(config["runner_spec"])
        -> _headers_from_json(value.get("headers"))
          -> 返回 {"Authorization": "Bearer sk-xxxxx", ...}
      -> RunnerSpec(headers={"Authorization": "Bearer sk-xxxxx", ...})
```

Controller evidence 的 scan 结果（不输出 secret value）：

```text
configured_secret_value_count=5
secret_value_match_count=3
matched_path_count=1
matched_path=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor/
  test_real_compactor_public_ope0/host.sqlite3
table=event_log column=payload_json rowid=2 occurrences=1
table=event_log column=payload_json rowid=13 occurrences=1
event_type=USER_INPUT_ACCEPTED
event_class=canonical_fact
matched_json_path=effective_execution_config.config.runner_spec.headers.Authorization
```

`git-diff://HEAD` 零命中，review/control/code diff 均非命中 owner。命中只在 real compactor smoke 生成的 SQLite 文件中，但该行为与 production 完全同源。

## 4. Verdict

### `S1-SEC-F01` 是 valid blocking finding。

直接证据（补读修订后新增第 5、6 条）：

1. **Design-truth 直接矛盾（Host 不接收 API key 明文）**：`docs/host/design.md:944` 明确规定"Host 不接收 raw provider client、API key 明文"且"`RunnerSpec.api_key_ref` 仍只是 secret 引用名，不是 secret 本体"。但 production 链证明：`_render_headers` 把实际 API key value 注入 `RunnerSpec.headers["Authorization"]`，Host admission 接收该完整 `RunnerSpec`。Host 不仅"接收"了明文，还把它持久化到了 durable canonical fact。

2. **不是 test false positive**：Controller evidence 证明命中发生在 `event_log` 表的 `USER_INPUT_ACCEPTED` canonical fact 中，`event_class=canonical_fact`。这是 production durable state，不是 test harness artifact。real compactor smoke 使用真实 Host runtime，其 SQLite 行为与 production 完全同源。

3. **Production 链完整闭合**：Service `_render_headers` → admission `_resolve_followup_effective_facts` → `_effective_execution_config_json` → `runner_spec_json` → EventLog `payload_json` → dispatch `runner_spec_from_json` → Engine `RunnerSpec`。每一环都有直接代码证据。

4. **Secret 在 durable state 中持久化**：Authorization header 明文进入 `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers.Authorization`，存储在 SQLite `event_log.payload_json` 中。这是 durable canonical fact，会被 retry、replay、recovery、projection、audit、memory 和 compact 消费。

5. **Design-truth 直接矛盾（EventLog 不能包含 headers）**：`docs/host/design.md:3403` 明确规定"EventLog 不能包含 API key、**headers**、完整 raw prompt 或完整 provider payload"。此处"headers"与"API key"并列，意为 EventLog 不能包含 headers 整体，而不只是不能包含 headers 中的 secret value。当前 `runner_spec_json` 把完整 `runner_spec.headers` 投影到 EventLog `effective_execution_config` 中，直接违反此约束。

6. **初版修复方案自身违反设计真源**：初版 artifact 建议"Host dispatch 从 `api_key_ref` 重新解析 secret 注入 headers"。但 `docs/host/design.md:944` 规定"Host 不接收 raw provider client、API key 明文"——dispatch 从环境变量读取 API key 并注入 headers，正是 Host 接收 API key 明文。该方案不是修复，而是把 secret 泄露从 durable state 转移到了 runtime Host 内存，Host 仍然是 secret 的消费者，违反设计真源。

## 5. §5 六问独立回答（补读修订版）

### 问题 1：`S1-SEC-F01` 是否为 valid blocking finding，还是存在足以拒绝它的 direct owner evidence？

**答：Valid blocking finding。**

没有任何 direct owner evidence 可以拒绝它：

- `RunnerSpec.api_key_ref` 是 secret 引用名，但 `RunnerSpec.headers` 含已渲染的明文 secret。两个字段语义不同，`api_key_ref` 的存在不证明 `headers` 不含 secret。
- `docs/host/design.md` 有三处直接矛盾：
  - (a) 第 944 行："Host 不接收 raw provider client、API key 明文" vs 实际接收含 Authorization 明文的 `RunnerSpec`。
  - (b) 第 944 行："`RunnerSpec.api_key_ref` 仍只是 secret 引用名" vs `headers` 中已注入实际值。
  - (c) **第 3403 行**："EventLog 不能包含 API key、**headers**、完整 raw prompt 或完整 provider payload" vs `runner_spec_json` 把完整 `headers` 投影到 EventLog。
- EventLog 存储的是 `canonical_fact`，不是 test fixture 或 diagnostic artifact。

### 问题 2：唯一正确 semantic owner 与最小跨层 boundary 是什么？哪些 owner 必须修改，哪些层必须零改动？

**答：此问题的完整回答依赖问题 3-5 的用户裁决。以下分析基于设计真源推导，标注了需要用户裁决的断点。**

**Semantic owner 分析：**

- **Secret 值的使用/脱敏/保护**：owner 是 Service（`docs/host/design.md:115`："Service / execution environment 负责 provider client 创建、secret 使用 / 脱敏 / 保护"）。
- **RunnerSpec 的 durable projection/restore**：owner 是 Host `_execution_config_projection.py`。
- **EventLog payload shape**：owner 是 Host admission + durable projection。
- **Runner 到 Engine 的 secret 传输**：semantic owner 不明确——设计真源说 Host 不接收 secret，但当前架构要求 Host 持有完整 `RunnerSpec`（含 headers）才能 dispatch 到 Engine。

**初步最小跨层 boundary（需用户裁决后确认）：**

| 层/模块 | 是否必须修改 | 说明 |
| --- | --- | --- |
| `dayu/service/host_assembly.py` | **是** | Service 是 secret 保护的 semantic owner。必须在传给 Host 前不再把 secret 注入 `RunnerSpec.headers`。 |
| `dayu/host/_execution_config_projection.py` | **是** | `runner_spec_json` 必须不再投影 `headers` 字段到 EventLog（设计第 3403 行禁止 EventLog 包含 headers）。 |
| `dayu/host/admission.py` | **可能** | 如果 Host 接收的 `RunnerSpec` 不含 headers，admission 冻结逻辑不变；但需要确认 `RunnerSpec` 类型是否允许 `headers={}`。 |
| `dayu/host/dispatch.py` | **是** | dispatch 还原 `RunnerSpec` 后 headers 为空，需要某种机制注入 secret。但 **此机制不能是 Host 自己从环境变量解析**（违反"Host 不接收 API key 明文"）。secret 解析必须由 Service-owned typed execution-environment seam 完成。 |
| `dayu/engine/contracts/runner_spec.py` | **可能** | `RunnerSpec` 类型可能需要调整以支持 headers 为空的 Host-side 版本与 headers 含 secret 的 Engine-side 版本。这取决于用户对问题 4 的裁决。 |
| `dayu/engine/` | **否** | Engine 只消费 `RunnerSpec`，不拥有 secret 语义。 |
| `dayu/host/durable/` | **否** | Durable store 不解释 payload 内容。 |

### 问题 3：current design truth 是否足以 code-generation，还是必须先做用户 product decision/design-doc correction？

**答：Design truth 存在内部张力，需要用户先裁决至少一个问题后才能 code-generation。**

Design truth 有以下规则：
- (a) Service 负责 secret 使用/脱敏/保护（`docs/host/design.md:115`）。
- (b) Host 不接收 API key 明文（`docs/host/design.md:944`）。
- (c) `RunnerSpec.api_key_ref` 只是 secret 引用名（`docs/host/design.md:944`）。
- (d) Host 必须冻结 effective runner spec 以支持 retry/replay/recovery（`docs/host/design.md:944`："可解释 snapshot 或 source refs"）。
- (e) **EventLog 不能包含 headers**（`docs/host/design.md:3403`）。

**内部张力**：

规则 (d) 要求 Host 冻结 `RunnerSpec` 以支持 retry/replay/recovery。当前实现通过把完整 `RunnerSpec`（含 headers）写入 EventLog 来满足此要求。但规则 (e) 禁止 EventLog 包含 headers，规则 (b) 禁止 Host 接收 API key 明文。

如果 EventLog 不含 headers，dispatch 还原的 `RunnerSpec` 就没有 headers。Engine 需要含 Authorization 的 headers 才能调用 LLM provider。**谁在 dispatch 到 Engine 前注入 secret？**

- 让 Host dispatch 解析 → 违反规则 (b)（Host 接收 API key 明文）。
- 让 EventLog 含 headers → 违反规则 (e)。
- 让 Service 注入 → 需要一个新的 Service-owned typed execution-environment seam，在 Host dispatch 时被调用。

第三条路径是唯一不违反任何设计规则的路径，但它需要设计一个新的 Host↔Service 接口。当前设计没有定义这个接口。

**因此：设计真源足以排除错误方案（初版的 dispatch 解析、projection-only redaction、header-name blacklist），但不足以直接 code-generation。需要用户裁决以下问题后才能确定具体方案。**

### 问题 4：如何同时满足 EventLog 零 secret value、current Run 执行、retry/replay/recovery 可解释、per-run RunnerSpec override、Service secret protection、Host 不接收 API key 明文？

**答：需要用户裁决方案边界。以下分析了三条可行路径，各有取舍。**

**约束集**：

```text
C1: EventLog 不能包含 headers（design:3403）
C2: Host 不接收 API key 明文（design:944）
C3: Host 必须冻结 effective runner spec 以支持 retry/replay/recovery（design:944）
C4: Service 负责 secret 使用/脱敏/保护（design:115）
C5: Engine 需要含 Authorization 的 headers 才能调用 provider（runtime fact）
C6: Host dispatch 是从 EventLog 还原 RunnerSpec 并传给 Engine 的唯一路径（architecture fact）
```

**路径 A：Service-owned typed execution-environment seam**

```text
Service                          Host                           Engine
  |                               |                              |
  | 1. 构造 RunnerSpec            |                              |
  |    (不含 secret headers)      |                              |
  | -------------------------->   |                              |
  |    HostRunnerSpec              |                              |
  |                               | 2. 冻结到 EventLog           |
  |                               |    (headers={}或缺失)        |
  |                               |                              |
  |                               | 3. dispatch: 还原 RunnerSpec |
  |                               |    (headers={})              |
  |                               |                              |
  |                               | 4. 调用 Service secret seam  |
  | <---------------------------  |    请求注入 secret           |
  |                               |                              |
  | 5. 从 api_key_ref 解析        |                              |
  |    注入 headers               |                              |
  | -------------------------->   |                              |
  |    EngineRunnerSpec            |                              |
  |                               | 6. 传给 Engine               |
  |                               | -------------------------->  |
  |                               |    含 secret 的 RunnerSpec    |
```

- 优点：严格遵守所有约束。Host 永远不持有 secret。Service 是唯一 secret owner。
- 缺点：需要设计新的 Host↔Service 接口（secret resolver callback/seam）。dispatch 从同步变为需要 Service 回调。
- 适用：如果用户愿意引入 Service-owned typed execution-environment seam。

**路径 B：RunnerSpec 类型分离**

```text
HostRunnerSpec:                   EngineRunnerSpec:
  provider                          provider
  model                             model
  endpoint                          endpoint
  api_key_ref                       api_key_ref
  client_correlation_policy         headers  <- 含 secret
  supports_tool_calling             client_correlation_policy
  supports_streaming                supports_tool_calling
  supports_stream_usage             supports_streaming
  default_timeout_seconds           supports_stream_usage
  max_retries                       default_timeout_seconds
  provider_request                  max_retries
  stream_idle_timeout_seconds       provider_request
  stream_idle_heartbeat_seconds     stream_idle_timeout_seconds
                                    stream_idle_heartbeat_seconds
```

- 优点：类型系统强制 Host 不持有 headers。编译期保证。
- 缺点：需要修改 `RunnerSpec` 类型（或新增 `HostRunnerSpec`），影响所有消费 `RunnerSpec` 的模块。dispatch 需要从 `HostRunnerSpec` 构造 `EngineRunnerSpec`（注入 secret）。
- 适用：如果用户愿意做类型重构。

**路径 C：Service 直接 dispatch 到 Engine（绕过 Host dispatch 的 RunnerSpec 冻结/还原）**

```text
Service                          Host                           Engine
  |                               |                              |
  | 1. 构造 RunnerSpec            |                              |
  |    (含 secret headers)        |                              |
  |                               |                              |
  | 2. 构造 HostRunnerSpec        |                              |
  |    (不含 secret headers)      |                              |
  | -------------------------->   |                              |
  |    冻结到 EventLog            |                              |
  |                               |                              |
  | 3. dispatch 时:               |                              |
  |    Service 直接传 EngineRunner |                              |
  |    Spec 给 Engine             |                              |
  | --------------------------------------------------------->  |
  |    含 secret 的 RunnerSpec                                    |
```

- 优点：不需要新的 Host↔Service 接口。Service 在 dispatch 时直接提供 Engine 所需的 RunnerSpec。
- 缺点：需要架构调整——当前 dispatch 链路是 Host dispatch -> Engine，Service 不直接参与 dispatch。
- 适用：如果用户愿意调整 dispatch 架构。

**需要用户裁决**：
1. 选择哪条路径（或组合）？
2. 是否接受引入新的 Host↔Service 接口？
3. 是否接受修改 `RunnerSpec` 类型？
4. 是否接受调整 dispatch 架构？

### 问题 5：是否存在不引入 permission schema/authorization framework、不越界 Issues 142/151/175/177/178 的最小方案？

**答：存在，但最小方案的边界需要用户裁决。**

所有三条路径都不引入 permission schema、authorization framework、capability token 或 policy DSL，也不越界 Issues 142/151/175/177/178。

**共同最小修改点**（所有路径都需要）：

1. **`dayu/host/_execution_config_projection.py`**：`runner_spec_json` 不再投影 `headers` 字段。`runner_spec_from_json` 不再还原 `headers`。这是遵守 `docs/host/design.md:3403` 的必要修改。

2. **`dayu/service/host_assembly.py`**：不再把含 secret 的 `RunnerSpec` 传给 Host。Service 在构造传给 Host 的 `RunnerSpec` 时，`headers={}`。

**路径特有修改点**：

- **路径 A**：新增 Service-owned secret resolver callback/seam，Host dispatch 调用它注入 secret。
- **路径 B**：新增 `HostRunnerSpec` 类型（不含 headers），修改所有消费点。
- **路径 C**：修改 dispatch 架构，Service 直接参与 Engine dispatch。

**禁止的方案**（已被设计真源排除）：
- ~~header-name blacklist~~：不可靠，新 header key 不在名单中会泄露。且设计禁止 EventLog 包含 headers 整体，不只是 secret-bearing headers。
- ~~projection-only redaction~~：只在 EventLog 层脱敏，Host 内存仍含 secret。
- ~~Host env lookup~~：Host 从环境变量解析 secret，违反"Host 不接收 API key 明文"。
- ~~test shim~~：不修复 production 链。
- ~~兼容 fallback~~：不修 root cause。

### 问题 6：需要哪些 negative/real tests 与 secret scan 证明修复不是 test shim 或表面 redaction？

**答：**

**必须的 negative tests**：

1. **EventLog zero-header test**：构造含 headers 的 `RunnerSpec`，通过 admission 写入 EventLog，读取 `payload_json`，断言 `runner_spec` 中**不含 `headers` 字段**（不只是不含 secret value，而是不含 headers 整体）。这是 owner-level contract test，证明 EventLog 遵守 `docs/host/design.md:3403`。

2. **EventLog zero-secret test**：扫描 EventLog 所有 `USER_INPUT_ACCEPTED` payload，断言不含任何 `models.json` 配置的 secret value。这是 defense-in-depth。

3. **Dispatch secret injection test**：构造不含 headers 的 `RunnerSpec` JSON，通过 dispatch 还原并注入 secret，断言 Engine 收到的 `RunnerSpec.headers` 含有效的 Authorization。证明 retry/replay 可解释。

4. **Per-run override test**：`SubmitFollowupRequest` 携带 `runner_spec` override，通过 admission 写入 EventLog，断言 durable payload 中不含 headers；dispatch 后 Engine 收到含 secret 的 headers。

**必须的 real tests**：

5. **Real compactor smoke secret scan**：在现有 real compactor smoke 后，扫描生成的 SQLite 文件，断言 `event_log.payload_json` 中不含 `headers` 字段且不含 secret value。

**必须的 secret scan**：

6. **全量 configured-secret scan**：扫描 `workspace/tmp/wu-semantic-ownership-01-ar-fix*` 所有 slice outputs、implementation artifact 与 `git diff --binary HEAD`，断言 `secret_value_match_count=0`。

7. **六 canonical scans**：保持现有六个 `rg` scan 不变，确认修复不引入新的 stale public semantic。

**为什么不是 test shim 或表面 redaction**：

- Test 1 证明 headers 整体不存在于 EventLog，而不是某个值被替换。
- Test 2 是 defense-in-depth，不依赖单一代码路径。
- Test 3 证明 secret 注入发生在正确的 owner 边界（Service seam 或类型分离），而不是 Host 内部。
- Test 4 证明 per-run override 路径也满足 zero-header/zero-secret 约束。
- Secret scan 6 是全量扫描，不依赖特定代码路径。

## 6. Findings

### S1-SEC-F01-未修复-严重-RunnerSpec headers 明文（含 Authorization secret）持久化到 EventLog，违反 design:3403 与 design:944

- **入口/函数**：`dayu/service/host_assembly.py::_runner_spec_from_model` -> `_render_headers` -> `dayu/host/admission.py::_resolve_followup_effective_facts` -> `dayu/host/_execution_config_projection.py::effective_execution_config_json` -> `runner_spec_json`
- **文件(行号)**：
  - `dayu/service/host_assembly.py:1755-1758`（secret 注入 headers）
  - `dayu/host/_execution_config_projection.py:169`（headers 原样投影到 EventLog）
- **输入场景**：任何包含 API key 的正常 Run（所有 production Run）
- **实际分支**：`runner_spec_json` 的 `"headers": dict(sorted(runner_spec.headers.items()))` 原样投影所有 headers 到 EventLog `effective_execution_config.config.runner_spec.headers`
- **预期行为**：(1) EventLog 不能包含 headers（`docs/host/design.md:3403`："EventLog 不能包含 API key、headers、完整 raw prompt 或完整 provider payload"）；(2) Host 不接收 API key 明文（`docs/host/design.md:944`）
- **实际行为**：(1) 完整 `runner_spec.headers`（含 `Authorization: Bearer sk-xxxxx`）进入 `event_log.payload_json`；(2) Host admission 接收含明文 secret 的 `RunnerSpec`
- **直接证据**：
  - `dayu/service/host_assembly.py:1755-1758`：`_render_headers` 把实际 API key value 注入 headers
  - `dayu/host/_execution_config_projection.py:169`：`runner_spec_json` 原样投影 `runner_spec.headers`，包含 `dict(sorted(runner_spec.headers.items()))`
  - `docs/host/design.md:944`："Host 不接收 raw provider client、API key 明文"
  - `docs/host/design.md:944`："`RunnerSpec.api_key_ref` 仍只是 secret 引用名，不是 secret 本体"
  - `docs/host/design.md:3403`："EventLog 不能包含 API key、**headers**、完整 raw prompt 或完整 provider payload"
  - Controller evidence scan：`matched_json_path=effective_execution_config.config.runner_spec.headers.Authorization`
- **影响**：
  - Secret 明文进入 durable canonical fact，被 retry/replay/recovery/projection/audit/memory/compact 消费
  - SQLite 文件泄露即 secret 泄露
  - EventLog 包含 headers 整体，违反 `design:3403`
  - Host 接收含 secret 的 RunnerSpec，违反 `design:944`
- **建议改法**：需要用户先裁决方案边界（§5 问题 3-5）。三条可行路径（A: Service-owned seam, B: RunnerSpec 类型分离, C: Service 直接 dispatch）均需用户确认后才能 code-generation。**禁止的方案**：header-name blacklist、projection-only redaction、Host env lookup、test shim、兼容 fallback。
- **修复风险（低/中/高）**：高。涉及跨层架构调整（Service/Host dispatch/Engine contracts），需要用户 product decision 确定方案边界
- **严重程度（低/中/高/严重）**：严重。provider secret 明文进入 durable state；EventLog 包含 headers 违反设计真源

## 7. Open Questions（需要用户裁决）

以下问题阻碍 confident code-generation。设计真源足以排除错误方案，但不足以在三条可行路径中自动选择。

### Q-A：`docs/host/design.md:3403` 的"EventLog 不能包含 headers"应如何解读？

- **选项 1**：EventLog 的 `effective_execution_config.config.runner_spec` 完全不含 `headers` key。durable snapshot 只记录 `provider`、`model`、`endpoint`、`api_key_ref`、`client_correlation_policy`、`supports_tool_calling`、`supports_streaming`、`supports_stream_usage`、`default_timeout_seconds`、`max_retries`、`provider_request`、`stream_idle_timeout_seconds`、`stream_idle_heartbeat_seconds`。**非 secret headers（如 `User-Agent`、`Content-Type`）也不进 EventLog**。
- **选项 2**：EventLog 的 `runner_spec` 可含 `headers`，但必须过滤掉所有 secret-bearing keys（`Authorization`、`Proxy-Authorization` 等）。非 secret headers 可进 EventLog。
- **影响**：选项 1 更严格，实现更简单（不过滤，直接不投影 headers）。选项 2 允许保留非 secret headers，但需要定义哪些 key 是 secret-bearing（这接近 blacklist 方案，被禁止）。
- **建议**：选项 1。设计原文是"headers"而非"secret headers"，与"API key"并列，语义是 headers 整体不能进 EventLog。

### Q-B：secret 解析应由 Service-owned typed execution-environment seam 还是其它 owner 承担？

- **选项 1：Service-owned callback seam**。Host dispatch 在构造 Engine `RunnerSpec` 前调用 Service 提供的 secret resolver callback，Service 从 `api_key_ref` 解析 secret 并注入 headers。Host 永远不持有 secret。
- **选项 2：RunnerSpec 类型分离**。新增 `HostRunnerSpec`（不含 headers）与 `EngineRunnerSpec`（含 headers）两个类型。Service 构造 `HostRunnerSpec` 给 Host，构造 `EngineRunnerSpec` 给 Engine。dispatch 时 Service 从 `HostRunnerSpec` 构造 `EngineRunnerSpec`。
- **选项 3：Service 直接 dispatch**。Service 在 Host dispatch 触发时直接构造含 secret 的 `RunnerSpec` 传给 Engine，绕过 Host 的 RunnerSpec 冻结/还原。
- **影响**：选项 1 需要新接口但改动最小。选项 2 类型安全但改动最大。选项 3 需要调整 dispatch 架构。
- **建议**：选项 1。它最小化架构改动，且严格遵循"Service 负责 secret 使用/脱敏/保护"的 semantic ownership。

### Q-C：是否需要 `RunnerSpec` 类型调整？

- 如果 Q-B 选选项 1：`RunnerSpec` 类型不变，但 Host 接收的实例 `headers={}`。
- 如果 Q-B 选选项 2：需要新增 `HostRunnerSpec` 类型。
- 如果 Q-B 选选项 3：`RunnerSpec` 类型不变。

### Q-D：非 secret headers（如 `User-Agent`、`X-Custom-Header`）是否需要持久化到 EventLog？

- 如果 Q-A 选选项 1：不需要，headers 整体不进 EventLog。
- 如果 Q-A 选选项 2：需要用户确认哪些 headers 可进 EventLog。
- **影响**：retry/replay 时非 secret headers 是否与原 Run 一致。如果非 secret headers 来自配置（`models.json`），它们在 retry 时会重新从配置读取，因此不持久化不影响一致性。

### Q-E：`docs/host/design.md:944` 的"可解释 snapshot 或 source refs"中"source refs"是否足以替代完整 `RunnerSpec` snapshot？

- 设计允许用 "source refs" 替代 "可解释 snapshot"。`api_key_ref` 就是一种 source ref。
- 如果 EventLog 只存 source refs（model id、api_key_ref、execution profile id 等），不存完整 `RunnerSpec`，dispatch 需要从这些 refs 重新构造 `RunnerSpec`。
- **影响**：这进一步确认了"secret 解析不在 Host"的设计意图——source refs 是引用，不是值。

## 8. Residual Risk

1. **opener baseline 路径**：`open_host` 的 `OrdinaryRunExecutionBaseline.runner_spec` 也含已渲染 headers。从 `admission.py` 代码看，opener Run 走同一 `_resolve_followup_effective_facts` 路径，因此同样受影响。修复必须覆盖 opener 和 follow-up 两条路径。

2. **compactor runner baseline**：`docs/host/design.md:946` 提到 `compactor_runner_spec` 也是 `open_host` 的 construction-time input。如果 compactor Run 也持久化 `RunnerSpec.headers` 到 EventLog，同样需要修复。

3. **dispatch secret resolver 生命周期**：如果采用 Service-owned seam（Q-B 选项 1），需要确保 Host 在 Service 已关闭或 Host 重启后仍能处理 dispatch。这可能需要持久化 resolver handle 或在 dispatch 失败时 fail closed。

4. **per-run override headers**：`SubmitFollowupRequest.runner_spec` 可能携带自定义 headers。这些 headers 是否全部是非 secret 的？如果调用方传入含 secret 的 headers，同样需要脱敏。需要在 Host public API 层面明确 `SubmitFollowupRequest.runner_spec.headers` 的约束。

5. **`docs/ui/design.md:66` 一致性**："Secret 只写入用户明确选择的系统环境变量持久化位置，不写进 workspace JSON、Host durable state、日志或 LLM-facing 文本"。当前 violation 同时违反此约束（secret 写入 Host durable state）。

## 9. Test / Security Matrix

| 维度 | 当前状态 | 修复后要求 |
| --- | --- | --- |
| EventLog headers | `runner_spec.headers` 完整投影 | `runner_spec` 不含 `headers` key |
| EventLog secret scan | `match_count=3` / `matched_path_count=1` | `match_count=0` |
| Real compactor SQLite | Authorization 明文在 `payload_json` | 零 headers、零 secret |
| Host 接收 secret | RunnerSpec 含明文 Authorization | RunnerSpec headers={} |
| Dispatch retry/replay | 从含 secret 的 durable JSON 还原 | 通过 Service-owned seam 注入 secret |
| Per-run override | override headers 含 secret 进 EventLog | override headers 不进 EventLog |
| Host design:944 | 直接矛盾 | 一致 |
| Host design:3403 | 直接矛盾 | 一致 |
| UI design:66 | 直接矛盾 | 一致 |
| Engine contracts | 不变 | 不变（Engine 仍收到含 secret 的 RunnerSpec） |
| Host public API | 不变（或按 Q-B 选项调整） | 待用户裁决 |
| Durable schema | `runner_spec` 含 `headers` | `runner_spec` 不含 `headers` |
| Issues 142/151/175/177/178 | 不越界 | 不越界 |
