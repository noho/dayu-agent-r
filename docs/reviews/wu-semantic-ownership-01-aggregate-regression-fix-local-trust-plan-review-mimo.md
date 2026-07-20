# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Local-Trust Plan Review (AgentMiMo)

## 1. Gate identity

- Reviewer：AgentMiMo，完整 adversarial plan review。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Gate：local-trust user decision 后的 design-truth / aggregate plan correction 双路完整 plan review。
- Mode：只读文档/代码审查，不修改实现、control 或其它 artifact。
- Status：`PASS`。
- 本 artifact 不记录任何 configured secret value、secret ref 名称或命中正文。

## 2. 严格完整读取清单

按用户指定顺序完整读取前九项设计真源与总控文件，随后核验四份指定 artifact 的 SHA-256 与完整内容，并读取全部既有 secret evidence、MiMo/DS secret review、Slice 1 implementation artifact 与五次 stop adjudication。

| 顺序 | 文件 | SHA-256（本次读取版本） |
| ---: | --- | --- |
| 1 | `AGENTS.md` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| 2 | `docs/host/issues-implementation-control.md` | `4b6488ff4fc9004b8373af5f785ca503d86fd884c6904632d9b1367aef64bcbb`（分段读取至 EOF） |
| 3 | `docs/phaseflow-umbrella-optimization-control.md` | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
| 4 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| 5 | `docs/host/design.md` | `2be90cc2e107ce14fd5ee594c85e2a223217b9d6689b2d4a0cafba2adf3ec628`（完整读取至 EOF） |
| 6 | `docs/engine/design.md` | `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31` |
| 7 | `docs/tool/design.md` | `ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c` |
| 8 | `docs/fins/design.md` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| 9 | `docs/ui/design.md` | `ed25d5d4577864cbf7ca6860aad043607921bd7db4f72cffb876c871fb99b4b7` |

SHA-256 核验：

| 指定 artifact | 用户要求 SHA-256 | 本次 `sha256sum` 验证 |
| --- | --- | --- |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-user-decision-controller-record.md` | `4a75899...` | ✓ 匹配 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-codex.md` | `116e9a7...` | ✓ 匹配 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-controller-validation.md` | `6fba19b...` | ✓ 匹配 |
| `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | `afaa18c...` | ✓ 匹配 |

额外读取：

- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-evidence.md`（SHA `2f3fc19...`）
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-designtruth-review-mimo.md`（SHA `fd18974...`）
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-designtruth-review-ds.md`（SHA `0aef51d...`）
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-adjudication.md`（SHA `ff64706...`）
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md`（SHA `0580091...`）
- 五份 stop adjudication（SHA `db221c9...`、`7174396...`、`52524fd...`、`ac5cf52...`、`220bf5f...`）
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md`（SHA `cad213b...`）
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-controller-authorization.md`（SHA `ebb6a9d...`）

## 3. Adversarial findings

### Finding 1：旧 design-truth 冲突文本已彻底清除

- Severity：none
- 证据：`docs/host/design.md` 第 83 行已写入"本地 Config 与 Host SQLite / EventLog 属于同一受信任产品域"与"这个内部持久化副本不是 public contract，也不得被直接复用为 Tool Trace、audit、HostEvent、outbox、memory、compact、runner-call observation、LLM-facing 文本或日志的输出 payload"。第 948 行已写入"它可以接收 Service 已解析并封装进 typed `RunnerSpec.headers` 的 provider API key"与"其中 resolved headers / API key 只属于受信任 Host internal durable state，不能进入 public / LLM-facing / log projection"。全文搜索 `EventLog.*不能.*包含.*API`、`EventLog.*不能.*headers`、`Host.*不接收.*API key` 均零命中。旧"Host 不接收 API key 明文"与"EventLog 不能包含 headers / API key"冲突承诺已删除。
- `docs/ui/design.md` 第 66-71 行已写入完整的 local-trust / projection boundary 语句，与 host design 一致。搜索 `不写入.*Host.*durable`、`不.*进入.*Host.*durable` 零命中。
- `docs/engine/design.md` 经 Codex correction 核对无需修改，已确认 Engine observation 不包含 provider headers。
- 结论：用户裁决已准确写回 host/ui design，无残留冲突旧真源。

### Finding 2：trace/audit/public/LLM/log 零泄露结论有直接 owner 证据

- Severity：none
- 证据：
  - **Tool Trace**：`dayu/host/tool_trace.py` 的 `_CANONICAL_EVENT_TYPES` 不含 `USER_INPUT_ACCEPTED`；`_extract_canonical_trace` 只读取命名 tool/ref/digest/signal 字段，不复制 `effective_execution_config`。fresh Tool Trace output scan 为零。
  - **Audit**：`dayu/host/audit.py` 的 `build_audit_json_line` 只输出固定 metadata/ref/digest/summary 字段，不复制 `event.payload` 或 `payload_json`。fresh audit scan 为零。
  - **Public HostEvent/read**：`dayu/host/read_api.py` 的 `_host_event_from_row` 对非 terminal row 只构造 typed progress DTO；`_activity_from_row` 是显式 event-type allowlist，`USER_INPUT_ACCEPTED` 不产生 activity。fresh public output scan 为零。
  - **LLM-facing run input/memory/compact**：`dayu/host/run_input.py` 只读取 `display_text`、`system_prompt`、`operation_kind`；`dayu/host/memory.py` 的 `_user_visible_text` 只读取 `display_text`；`dayu/host/compact_material.py` 同样只读取 `display_text`。fresh LLM-facing scan 为零。
  - **Operator logs**：既有 `tests/host/test_logging.py` 与 `tests/engine/test_agent_phase2.py` / `tests/engine/runners/openai/test_diagnostic_payload.py` 已验证 prompt/authorization claim 不进入 Host/Engine logs。fresh log output scan 为零。
- 结论：每个 projection surface 都有唯一 owner 的直接代码证据和 fresh scan 佐证，不是按字段名猜测。

### Finding 3：五个 test-only path 是最小且非重复的

- Severity：none
- 证据：五个测试分别对应五个不同 projection owner 的独立代码路径：
  1. `test_audit_sink.py` → `build_audit_json_line` 审计行构建器
  2. `test_tool_trace_projection.py` → `ToolTraceProjectionConsumer` filter/extract
  3. `test_host_activity_event_projection.py` → `HostEvent` typed DTO 投影
  4. `test_run_input_builder.py` → LLM-facing `messages`、memory/compact material、runner-call observation
  5. `test_logging.py` → Host logger callsite
- 每个 owner 是不同模块的不同函数，有不同的 filter/extract/select 逻辑。若合并为单个测试，任一 surface 出现 leak 时，修复该 surface 的 diff 必须同时修改合并测试，增加了误改其它 surface 断言的风险。分离的测试路径也使 configured-secret scan 输出能精确按 surface 报告零/非零，提高了诊断精度。
- 同时，每个测试只验证一个 synthetic sentinel 值在一个 surface 的行为，不做过度测试。`test_run_input_builder.py` 的三路断言（messages、memory/compact、runner-call observation vs. Engine execution `RunnerSpec.headers`）是同一 owner 的三个消费边界，合理合并在同一文件。
- 结论：五个路径是最小分离，不重复，不可进一步合并而不损失 owner 边界清晰度。

### Finding 4：synthetic secret sentinel 验证设计正确

- Severity：none
- 证据：plan §4.1 第 4 项要求：
  1. 用 synthetic sentinel 构造含 resolved `RunnerSpec.headers` 的 `USER_INPUT_ACCEPTED.effective_execution_config`
  2. 先断言 internal durable round-trip 保留 exact value（证明测试没有把 accepted owner path 误清零）
  3. 再分别断言 Tool Trace、audit、HostEvent、run-input/memory/compact、logs 为零 sentinel
  4. 明确 `AgentRunRequest.runner_spec.headers` 是 Engine 执行所需的受信任 typed input，必须保留 sentinel，不得误判成 LLM projection
- 这同时验证了可信内部 retention 与各禁止投影为零。测试不使用字段名黑名单（不搜索 `Authorization`、`api_key` 等），只对 owner 级 filter/extract/select 的实际输出做 sentinel 匹配。
- 结论：设计正确，无字段名黑名单依赖。

### Finding 5：secret scan 分类精确、不宽泛

- Severity：none
- 证据：plan §6.7 定义两类：
  - `ACCEPTED_TRUSTED_INTERNAL`：只允许 ConfigLoader 管理的本地 Config source 和 Host internal SQLite/EventLog 中 `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers`。SQLite 物理命中必须做 logical row / JSON path 核对，logical other 必须为 0。
  - `ZERO_REQUIRED`：Tool Trace hot/cold/query、audit JSONL/query、public HostEvent/read/outbox、memory/compact/evidence/runner-call observation、operator logs、其它 smoke 输出、git diff、review artifacts。每类分别输出 0 match / 0 matched path。
- 分类不宽泛：不把"所有 output 零命中"作为单一规则；内部 match 做精确 event-type / JSON-path 核对；各 zero-required surface 独立报告。
- Codex correction artifact 的 fresh scan 结果验证了该分类：trusted internal = 3 次物理命中 / 1 path / 2 logical rows / 全部是 effective runner headers / logical other = 0；各 zero-required surface 均为 0。
- 结论：分类精确。

### Finding 6：严格三 slices，未偷带

- Severity：none
- 证据：plan 固定三个 slices（Slice 1: AR-F01/F03/F04/S1-SEC-F01 closure; Slice 2: AR-F02; Slice 3: AR-F05），production allowlist 精确列出（Slice 1/3 为空，Slice 2 只有 Fins owner 迁移相关 12 个路径），未引入 deferred issue（177/178/175/142/151 均保持各自 owner），未引入 secret type split、descriptor/resolver、secret manager 或统一 authorization framework。`S1-SEC-F01` 关闭为 no-code blocker，不增加 slice 或 production path。
- 结论：严格三 slices，无偷带。

### Finding 7：命令、路径、保护哈希、stop rule 可执行且正确

- Severity：none
- 证据：
  - 命令：每个 slice 有完整的 bash focused tests / coverage / pyright / Ruff / build / scans / real smoke 命令块。
  - 路径：production/test/validation-utility/README allowlists 与 protected zero-diff paths 精确列出。
  - 保护哈希：三个既有 Slice 1 test delta 的 SHA-256 在 plan §0 和 §7 中一致记录；`git diff --check`、`git diff --cached --name-status`、`git status --short` 作为门禁命令可直接执行。
  - Stop rule：§9 列出 10+ 个精确停止条件，每个都可由自动化命令或 Controller 直接验证触发。
- 结论：可执行且正确。

### Finding 8：完全避免 type split / descriptor / resolver / secret manager / auth framework

- Severity：none
- 证据：plan §0 明确"S1-SEC-F01 按 2026-07-19 用户产品裁决关闭为 no-code blocker"。§2.2.1 明确"不引入 Host-safe/Engine-only split、header descriptor、secret resolver callback、secret manager 或统一 tool authorization framework"。§6.7 no-code ledger 要求"Topic 9 不得引入统一 authorization 框架、capability token、policy DSL 或 role model"。用户裁决记录 §5 第 5 点明确"不引入 Host-safe/Engine-only 双类型、content-addressed header descriptor、secret resolver callback、通用 secret manager、permission schema 或统一 tool authorization framework"。
- 结论：完全避免。

## 4. 总结

全部八个 adversarial 审查维度均无 finding。用户裁决已准确写回 host/ui design、plan 与 control；trace/audit/public/LLM/log 零泄露结论有直接 owner 代码证据与 fresh scan 佐证；五个 test-only path 最小且不重复；synthetic sentinel 设计正确且无字段名黑名单；secret scan 分类精确；三 slices 结构未扩大；命令/路径/哈希/stop rule 可执行；完全避免 type split 等过度设计。

## 5. 结论

**PASS**

无 finding。
