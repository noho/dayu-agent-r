# PR 190 Compactor 输出业务语义 S1 implementation

## Gate metadata

- Gate：`implementation`
- Work unit：补齐 Compactor LLM-facing 输出 schema 的核心字段与显式丢弃原因业务语义
- Slice：`S1 — Compactor output business semantics`
- Branch：`codex/interactive-oracle`
- Plan source：`docs/gateflow/pr-190-compactor-output-business-semantics-plan-20260803.md`
- Acceptance source：`docs/gateflow/pr-190-compactor-output-business-semantics-plan-review-acceptance-20260803-215810.md`
- Decision：`pass`
- Completion status：`implementation-pass`
- Current gate after this artifact：`code review`
- Next entry point：对本 slice 的五个实现文件与本 artifact 执行 evidence-based code review
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-compactor-output-business-semantics-s1-implementation-20260803.md`

implementation 在 code review 接受前未 stage/commit/push；接受后由 accepted slice checkpoint 只处理 intended files，并按 Gateflow 自动推进。

## First-principles and owner decision

该 work unit 的动机成立：现有 strict parser 只能校验字段 shape、source kind 与闭集枚举，不能替无状态模型推断摘要、事实、回答锚点与 drop reason 的业务边界。唯一正确修复位置是直接投给模型的 user prompt owner；若在 Host parser、Context Governance、Memory 投影或下游消费者补偿，会造成语义所有权漂移。

- 唯一 LLM-facing 语义 owner：`dayu/config/prompts/scenes/conversation_compaction_user.md`。
- typed schema、strict parser、accept barrier、repair feedback owner 与 Memory 完整 replacement 投影均保持不变。
- publication manifest 与冻结 manifest digest 只记录最终 prompt bytes 的派生真值，不拥有业务语义。
- 没有新增 schema、enum、状态机、semantic verifier、fallback、loose parsing、默认值或兼容分支。

## Changed files

| File | Change |
|---|---|
| `dayu/config/prompts/scenes/conversation_compaction_user.md` | 在现有 output schema 字段旁补齐 `session_summary`、`evidence_facts`、`answer_anchors` 与四种 drop reason 的业务语义 |
| `tests/host/test_llm_compaction.py` | 扩充 packaged prompt owner test，逐字段与逐 reason 锁定 accepted semantics |
| `tests/host/test_public_compact_smoke.py` | 在默认真实装配路径添加最小语义哨兵，保留既有 example parse/accept 证明 |
| `docs/cli_init_workspace_manifest_v1.json` | 只更新 `conversation_compaction_user.md` 条目的真实 content SHA-256 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 只更新最终 manifest bytes 对应的 `FROZEN_MANIFEST_SHA256` |
| `docs/gateflow/pr-190-compactor-output-business-semantics-s1-implementation-20260803.md` | 新增本 durable implementation artifact |

除上表外没有文件变化。实现未修改 Host、schema、system prompt、README、design、oracle、scenario 或 `docs/cli_ci.md`，也未实现 deferred `forward_intents.status` / `reference_continuity.reason`。

## Implemented semantics

- `session_summary` 保存整体任务背景、已完成进展、当前状态与关键约束；`text` 只能概括 cited material，`source_labels` 是直接来源引用标签。
- `session_summary: null` 表示本次完整 replacement 不含摘要；candidate 被接受后当前摘要变为空，包括清除先前已接受摘要，且不影响同一 candidate 中其它四类业务语义项。
- `evidence_facts.claim` 必须由 `support_labels` 指向的 accepted `evidence_material` 或 `previous_evidence_fact` 直接支持；`context_labels` 只提供背景、限定或既有回答上下文，不能支持 claim 或弥补 support 不足。
- `answer_anchors` 只保存既有回答、判断或结论；`title` 标识主题，`detail` 保留已表达结论及必要条件、边界或不确定性，`source_labels` 只引用 `answer_material` 或 `previous_answer_anchor`。
- `superseded` 只表示旧内容已被更新、更完整或更权威内容替代，继续保留会过时、冲突或误导。
- `redundant` 只表示内容仍有效但必要信息已完整表达，丢弃不损失独立业务信息；不能掩盖冲突或遗漏。
- `out_of_scope` 只表示内容与当前输入、会话任务及可预见后续无关；不能因难分类、冲突或依据不足而使用。
- `policy_limit` 只在 source 仍相关且原本应保留、当前 repair feedback 明示具体 cap、并且为了让完整 replacement 满足该 cap 必须 drop 时使用；首次请求、无 repair feedback 或无具体 cap 时禁止猜测或使用。
- 四种 reason 是对 source 实际业务关系的互斥解释，不是固定优先级状态机。

## Digests and frozen-file checks

### Updated publication truth

- `dayu/config/prompts/scenes/conversation_compaction_user.md`：`sha256:a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce`
- `docs/cli_init_workspace_manifest_v1.json`：`sha256:fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c`
- `tests/cli/test_smoke_cli_init_provider_matrix.py::FROZEN_MANIFEST_SHA256` 已同步为后一 digest。

### Durable inputs preserved

- `docs/reviews/pr-190-review-20260803-203709.md`：`sha256:e7add55e6c95c783ca8d92c8f8d15b223836851e70cfd73a902f15207d0d9841`
- `docs/reviews/plan-review-20260803-212134.md`：`sha256:1d592ae41f6ed42b8b0c2e30fe37ebfa96751347859d2b0bf8ddb07aad46ae02`
- accepted plan：`sha256:23b8951e787cecbee520490988a7e69c229c7426249ac9796379e917bf11510a`

### Frozen files preserved

- `dayu/host/compaction.py`：`sha256:9c14b0294e1177f38e96cfa85d8c57a7a0aef31d7f338ed3f58b97ac6d7a7868`
- `dayu/host/context_governance.py`：`sha256:ffbd24282737e316a70102229cbf9628f33b80154394c45b1404aedb77b6df3e`
- `dayu/host/memory.py`：`sha256:42a56de0c2af9fb07fcaea2667a216d854d7225f4766f91902b289fc987026f8`
- `dayu/config/prompts/scenes/conversation_compaction.md`：`sha256:4bd476db45f17bebaa7eb951c8354d10189df1faadb9c1c530619d9f3352f60a`
- `dayu/config/prompts/manifests/conversation_compaction.json`：`sha256:a3ad3ec2b30bc9037b5a4aa7b288d8a2462870d5bac77217a6aa708d58aa52db`
- `dayu/config/execution_profiles.json`：`sha256:3fd7e6940e337f0668bbac315f6b99254e3eb3309473a2161efc91cfc1b2e1f5`
- `docs/cli_ci_oracles.json`：`sha256:f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
- `docs/cli_ci_scenarios.json`：`sha256:7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- `docs/cli_ci.md`：`sha256:a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`

## Validation

全部命令均在 `source .venv/bin/activate` 后运行。

| Command | Result |
|---|---|
| `pytest tests/host/test_llm_compaction.py -q` | `24 passed` |
| `pytest tests/host/test_public_compact_smoke.py -q -k 'default_compactor_prompt_is_llm_facing_and_self_contained'` | `1 passed, 30 deselected`；完整示例继续通过 production parser 与 accept barrier |
| `pytest tests/host/test_memory_projection.py -q -k 'accepted_compact_without_summary_clears_prior_session_summary'` | `1 passed, 62 deselected`；锁定 accepted `null` 清空既有摘要 |
| `pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_config_loader.py tests/cli/test_smoke_cli_init_provider_matrix.py tests/service/test_host_assembly.py -q` | `287 passed, 3 warnings`；warnings 均为第三方 `edgar` deprecated API 提示 |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | pass，无输出 |
| `git status --short` | 只有五个 allowed implementation files；新增本 artifact 后预期再包含本路径 |
| durable input SHA-256 check | 两份 durable review input 与 accepted plan 均和冻结记录一致 |
| frozen-file SHA-256 check | Host/system prompt/scene manifest/execution profile/oracle/scenario/`cli_ci.md` 均与实现前基线一致 |

## Docs decision

- `dayu/config/README.md`：已读取 prompts 目录职责与 LLM-facing prompt 自足约束。本 slice 只兑现现有职责，不改变目录职责、装配、配置 schema 或用户工作流；`no-change`。
- `tests/README.md`：已读取 README 更新边界。本 slice 只强化既有 Compactor conformance tests，不新增测试层级、运行方式或维护规则；`no-change`。
- `dayu/host/README.md`、`docs/host/design.md`：Host typed contract、accept barrier、repair projection 与 Memory state transition 未变；`no-change`。
- 根 `README.md`：安装、初始化、CLI/Web/WeChat 入口、参数、输出、日志位置与用户工作流未变；`no-change`。
- `dayu/README.md` 与其它 design：分层、依赖、装配、public contract shape、schema 与状态机未变；`no-change`。

## Residual risks and uncovered areas

- `fixed in current slice`：`session_summary: null` replacement 语义、previous evidence 直接支持、无具体 cap 时禁止 `policy_limit`、两级 publication hash 漂移均由 prompt owner 与 deterministic tests 固定。
- `assigned to later work unit`：真实 provider 对字段分类、drop reason 与 repair cap 的稳定遵循度；owner 为 real Compactor conformance evidence work unit。
- `assigned to later work unit`：frozen oracle/scenario 的 current-head readiness refresh；owner 为独立 readiness refresh work unit。
- `assigned to later work unit`：`forward_intents.status` 与 `reference_continuity.reason` 的 LLM-facing 业务语义；owner 为后续独立 LLM-facing schema work unit。

没有未分类 residual risk，没有 blocking open question。第三方 `edgar` deprecation warnings 与本 slice 无关，不影响通过结论。

## Completion decision

`implementation-pass`

单一 slice 的五个实现文件与本 durable artifact 已形成完整 intended diff；focused tests、publication tests、完整 pyright、diff check、digest 与冻结文件检查均通过。README/design 判定为 no-change。下一未完成 gate 是 `code review`；implementation 在 code review 接受前未 stage/commit/push，接受后由 accepted slice checkpoint 只处理 intended files，并按 Gateflow 自动推进。
