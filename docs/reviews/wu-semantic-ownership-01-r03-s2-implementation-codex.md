# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 implementation handoff

## 0. Gate identity 与结论

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU：`R03`
- slice：`R03-S2`
- gate：implementation
- baseline HEAD：`fe497da395e8511c684945b9282894fe322a90df`
- accepted R03-S1 commit：`3e48f09e`，`git merge-base --is-ancestor 3e48f09e HEAD` 返回成功
- 开始状态：working tree clean
- 结束状态：仅保留本 slice allowlist diff 与本 artifact；未 commit、未进入 code review、S3 或 aggregate

结论：R03-S2 已按 accepted plan 的 owner boundary 完成。downstream 字段名 blacklist、`arguments_summary_unsafe` limited branch、Tool Trace readable redaction 与 `dayu.runtime.json_redaction` 已删除；没有新增 replacement normalization。canonical JSON、bounded text 与 digest 继续分别承担格式、展示上限和完整性职责。三个 schema 缺口只在各自 producer owner 修复，未改变工具名、参数名、enum、required、result 或 citation shape。

## 1. 第一性原理与 owner boundary

问题真实存在，且不是“多补几个敏感字段”即可解决：accepted arguments 已在 ToolRuntime accept boundary 形成 canonical JSON 与 digest，下游再按字段名判断 `path/token/password` 会把合法业务字段误当成 credential，并让 Memory、RunInput、Tool Trace 对同一事实产生不同语义。因此字段名分类没有业务真源，正确动作是删除，而不是扩充 blacklist。

本 slice 的 owner 判定如下：

1. accepted request/query fallback owner 是 `dayu/host/accepted_result_projection.py`；缺 semantic query 时机械投影已校验 canonical arguments。
2. Tool Trace readable request owner 是 `dayu/host/tool_trace.py`；只做 canonical/bounded 展示，不再改写字段值。descriptor ref/digest 不进入 readable summary，保留在 canonical/internal facts；descriptor strict resolution 属于 accepted S3，不在本 slice 实现。
3. `fetch_more` LLM-facing schema owner 是 Host framework tool producer `dayu/host/tool_runtime.py`。
4. `fetch_web_page.url` schema owner 是 `dayu/tools/web/web_tools.py`。
5. Fins read 的 `ticker/document_id` schema owner 是 `dayu/fins/tools/fins_tools.py`；两个模块级私有 helper 是唯一文案真源。
6. `dayu.runtime.json_redaction` 已失去合法调用方，删除模块及 runtime package 概览项；没有迁移、wrapper、re-export 或替代 helper。

## 2. 逐文件 implementation diff

| 文件 | actual diff / disposition | owner 证据 |
| --- | --- | --- |
| `dayu/host/accepted_result_projection.py` | 删除 `LIMITED_SIGNAL` query state、`_contains_unsafe_argument_key`、`_limited_query`、`arguments_summary_unsafe`；semantic query 缺失时始终输出 bounded canonical arguments | accepted-result 共享 query projection owner |
| `dayu/host/tool_trace.py` | 删除 runtime redaction import、`_redacted_json`、descriptor readable ref/digest placeholder；inline 与 accepted-result request summary 展示 exact args；readable map 不再携带 arguments descriptor ref/digest | Tool Trace readable projection owner；hot/cold internal diagnostic fields不作为 readable content |
| `dayu/host/payload_resolution.py` | audited no-diff；S1 strict atoms 已提供 exact canonical args/digest，未发现 S2 fallback/safe terminology | canonical request atom reader owner |
| `dayu/host/run_input.py` | audited no-diff；本 slice 不重复投影或重建参数 | RunInput 只消费共享 projection |
| `dayu/host/tool_runtime.py` | 仅更新 `fetch_more` tool description 与 `cursor/scope_token/limit` descriptions；required 与执行行为不变 | Host framework tool schema producer |
| `dayu/runtime/__init__.py` | 仅从模块 docstring 删除 JSON 字段脱敏能力及模块清单项 | runtime package capability inventory |
| `dayu/runtime/json_redaction.py` | 删除整个模块 | 唯一调用方已从 Tool Trace 删除；无合法层中立 owner |
| `dayu/tools/web/web_tools.py` | 仅补 `fetch_web_page.url` description | Web tool schema producer |
| `dayu/fins/tools/fins_tools.py` | 新增 `_ticker_parameter_schema` / `_document_id_parameter_schema`，九个 read definitions 复用 ticker，八个 document read definitions 复用 document_id | Fins read schema producer |
| `tests/host/test_accepted_result_projection.py` | 以合法 `file_path/scope_token/password_policy_name` exact canonical assertion 替换 blacklist fixture | owner contract test |
| `tests/host/test_run_input_builder.py` | audited no-diff；exact suite 保留 S1 strict consumer 回归 | consumer regression |
| `tests/host/test_memory_projection.py` | Memory 断言同一三个合法业务字段和值机械可见，不再断言 limited/隐藏 | shared projection propagation |
| `tests/host/test_tool_trace_projection.py` | request/result exact args、无 `<redacted>`；descriptor ref/digest 不进入 readable summary，normalized digest仍在 internal row | Tool Trace owner contract |
| `tests/host/test_tool_trace_queries.py` | audited no-diff；runner reconstruction `limited_signal` 是另一独立 typed diagnostic，不是 accepted arguments blacklist | internal query regression |
| `tests/host/test_toolruntime_truncation_fetch_more.py` | exact tool/parameter descriptions、required 与 `additional_properties` assertion | framework schema owner test |
| `tests/tools/web/test_web_tools_provider.py` | exact `url` description assertion | Web schema owner test |
| `tests/fins/test_fins_storage_provider.py` | 九个 ticker / 八个 document_id exact shared schema assertions；名称与治理字段 absence 保持 | Fins schema owner test |
| `dayu/host/README.md` | 将 Tool Trace “脱敏”陈述改为 exact canonical/bounded 与 descriptor internal/readable 分界 | 命中 Host README 职责 |
| `tests/README.md` | 更新 Memory/Tool Trace/schema owner 测试事实；保留其它现有测试说明 | 命中 tests README 职责 |
| 本文件 | implementation evidence/handoff | 用户明确要求的 review artifact |

## 3. 37 个 prompt assets 最终人工 inventory

以下每个文件均在 implementation 后再次逐文件读取实际正文/manifest；不是以 `rg` 零命中代替。`git diff --name-only -- dayu/config/prompts` 为空。

| # | 文件 | actual evidence / disposition |
| ---: | --- | --- |
| 1 | `dayu/config/prompts/base/agents.md` | 人工读完整 16 行；只定义输出行为，无参数脱敏、opaque source 或 credential fallback；no-diff |
| 2 | `dayu/config/prompts/base/fact_rules.md` | 人工读完整 40 行；事实、数字、来源与 citation 规则自足；no-diff |
| 3 | `dayu/config/prompts/base/soul.md` | 人工读完整 10 行；角色与中文风格；no-diff |
| 4 | `dayu/config/prompts/base/tools.md` | 人工读完整 100 行；保留 R01 Doc navigation、fetch_more next_action、Fins ticker/document_id 工作流；no-diff |
| 5 | `dayu/config/prompts/scenes/audit.md` | 人工读完整 20 行；审计范围与禁用工具自足；no-diff |
| 6 | `dayu/config/prompts/scenes/confirm.md` | 人工读完整 20 行；只复核已有 evidence；no-diff |
| 7 | `dayu/config/prompts/scenes/conversation_compaction.md` | 人工读完整 16 行；label 明示仅为引用标签、非业务事实；no-diff |
| 8 | `dayu/config/prompts/scenes/conversation_compaction_user.md` | 人工读完整 108 行；字段、类型、必填、允许值和最小示例自足；no-diff |
| 9 | `dayu/config/prompts/scenes/decision.md` | 人工读完整 30 行；决策输入/输出与证据要求自足；no-diff |
| 10 | `dayu/config/prompts/scenes/fix.md` | 人工读完整 23 行；占位符修复边界自足；no-diff |
| 11 | `dayu/config/prompts/scenes/infer.md` | 人工读完整 25 行；业务标签判断边界自足；no-diff |
| 12 | `dayu/config/prompts/scenes/interactive.md` | 人工读完整 10 行；交互任务最小规则；no-diff |
| 13 | `dayu/config/prompts/scenes/overview.md` | 人工读完整 23 行；只压缩既有判断链；no-diff |
| 14 | `dayu/config/prompts/scenes/prompt.md` | 人工读完整 10 行；单轮问答规则；no-diff |
| 15 | `dayu/config/prompts/scenes/regenerate.md` | 人工读完整 24 行；整章重建与证据锚点规则；no-diff |
| 16 | `dayu/config/prompts/scenes/repair.md` | 人工读完整 20 行；局部修复、不扩展研究；no-diff |
| 17 | `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md` | 人工读完整 9 行；真实 memory smoke 场景且不披露运行时诊断；no-diff |
| 18 | `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md` | 人工读完整 10 行；scenario smoke，未确认事实不得编造；no-diff |
| 19 | `dayu/config/prompts/scenes/smoke_host_public_multiturn.md` | 人工读完整 10 行；multiturn smoke，不披露装配；no-diff |
| 20 | `dayu/config/prompts/scenes/wechat.md` | 人工读完整 8 行；WeChat 交互规则；no-diff |
| 21 | `dayu/config/prompts/scenes/write.md` | 人工读完整 24 行；章节写作与 citation owner 规则；no-diff |
| 22 | `dayu/config/prompts/manifests/audit.json` | 人工读完整 58 行；fragment/context assembly metadata，不另造业务语义；no-diff |
| 23 | `dayu/config/prompts/manifests/confirm.json` | 人工读完整 67 行；tool tags 与 fragments 只装配已审计文本；no-diff |
| 24 | `dayu/config/prompts/manifests/conversation_compaction.json` | 人工读完整 42 行；compactor fallback/continuation 文案与单轮 policy 自足；no-diff |
| 25 | `dayu/config/prompts/manifests/decision.json` | 人工读完整 73 行；scene fragment assembly；no-diff |
| 26 | `dayu/config/prompts/manifests/fix.json` | 人工读完整 73 行；scene fragment assembly；no-diff |
| 27 | `dayu/config/prompts/manifests/infer.json` | 人工读完整 61 行；scene fragment assembly；no-diff |
| 28 | `dayu/config/prompts/manifests/interactive.json` | 人工读完整 76 行；tool selection/fragments；no-diff |
| 29 | `dayu/config/prompts/manifests/overview.json` | 人工读完整 64 行；no-tool scene assembly；no-diff |
| 30 | `dayu/config/prompts/manifests/prompt.json` | 人工读完整 73 行；prompt scene/tool selection；no-diff |
| 31 | `dayu/config/prompts/manifests/regenerate.json` | 人工读完整 73 行；scene fragment assembly；no-diff |
| 32 | `dayu/config/prompts/manifests/repair.json` | 人工读完整 67 行；scene fragment assembly；no-diff |
| 33 | `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json` | 人工读完整 56 行；manual-smoke assembly；no-diff |
| 34 | `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json` | 人工读完整 56 行；scenario smoke assembly；no-diff |
| 35 | `dayu/config/prompts/manifests/smoke_host_public_multiturn.json` | 人工读完整 61 行；multiturn smoke assembly；no-diff |
| 36 | `dayu/config/prompts/manifests/wechat.json` | 人工读完整 71 行；WeChat fragments/tool selection；no-diff |
| 37 | `dayu/config/prompts/manifests/write.json` | 人工读完整 73 行；write fragments/tool selection；no-diff |

## 4. 其它 LLM source / real fixture 人工 inventory

### 4.1 Production source owners

| 文件/来源 | actual disposition |
| --- | --- |
| `dayu/tools/doc_tools.py` | 人工复核五个 Doc definitions、params/errors/results；R01 final contract retained/no-diff |
| `dayu/tools/web/web_tools.py` | 仅 `fetch_web_page.url` description modify-at-owner；其它 Web policy/error/result no-diff |
| `dayu/tools/web/web_search_projection.py` | search success/next-action owner；no-diff |
| `dayu/tools/web/web_tool_projection_text.py` | failure/cancel/recovery text owner；no-diff |
| `dayu/tools/utils/provider.py` | time schema/enum/error/result；no-diff |
| `dayu/fins/tools/fins_tools.py` | 仅共用 ticker/document_id descriptions；其它九工具 contract retained |
| `dayu/fins/tools/read_runtime.py` | result/citation owner；no-diff |
| `dayu/fins/domain/tool_models.py` | Citation typed fields/serialization；no-diff |
| Fins `download_tools.py/preprocess_tools.py/upload_tools.py` | ingestion awaiting schemas；audited no-diff |
| `dayu/host/tool_runtime.py` | 仅 framework fetch_more schema descriptions；执行/result unchanged |
| `dayu/engine/agent.py` | ordinary ToolMessage typed projection；mechanical/no-diff |
| `dayu/engine/runners/openai/payload.py` | provider serializer；mechanical/no-diff |
| `dayu/host/run_input.py` | strict consumer；no-diff |
| `dayu/host/evidence.py` | four-line renderer；S3 owner/no-diff |
| `dayu/host/accepted_result_projection.py` | S2 query owner modified；S3 opaque source owner保留 |
| `dayu/host/memory.py` / `dayu/host/durable/memory.py` | shared projection consumers；S2 production no-diff |
| `dayu/host/compact_material.py` / `compact_pipeline.py` | compactor material consumers；S2 production no-diff |
| `dayu/host/llm_compaction.py` | typed compact input assembly；no-diff |
| `dayu/host/tool_trace.py` | S2 exact readable args/redaction deletion；S3 descriptor strict resolution未进入 |
| `dayu/host/durable/tool_trace.py` | internal diagnostic/query row owner；no-diff |
| `dayu/runtime/scene_prepare.py` | deterministic prompt assembly；no-diff |

### 4.2 真实 LLM prompt/schema fixtures

| 文件 | actual disposition |
| --- | --- |
| `tests/tools/test_doc_tools_provider.py` | R01 exact Doc schema/real input fixture；no-diff，第二 exact suite通过 |
| `tests/tools/test_combined_tools_acceptance.py` | combined provider/framework schema；no-diff，第二 exact suite通过 |
| `tests/tools/web/test_web_tools_provider.py` | URL description owner assertion modified |
| `tests/fins/test_fins_storage_provider.py` | shared ticker/document_id assertions modified |
| `tests/engine/runners/openai/test_payload_build.py` | provider serialization fixture；no-diff，第二 exact suite通过 |
| `tests/engine/test_agent_phase3_tool_call.py` | ToolMessage transport fixture；no-diff，第二 exact suite通过 |
| `tests/host/public_smoke_support.py` | deterministic public Host schemas/messages；no-diff |
| `tests/host/test_public_compact_smoke.py` | real compactor prompt assembly；S3 propagation owner/no-diff |
| 两个 runtime public smoke assembly tests | real prompt/tool assembly；no-diff |
| `utils/smoke_host_public_multiturn.py` | real provider/public Host smoke；no-diff |
| `utils/smoke_host_public_conversation_memory.py` | real memory smoke；no-diff |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | scenario/compactor smoke；no-diff |
| `utils/smoke_host_public_awaiting_entrypoint.py` | awaiting boundary smoke；no-diff |
| R03 semantic ownership smoke + assembly test | S3 future files，当前不存在且未创建 |

## 5. executable constructor scan：114 路径逐文件实际 disposition

执行的 completion scan：

```bash
rg -l 'AgentRunRequest|SystemMessage|UserMessage|ToolFunctionSchema|ToolDefinition' \
  dayu tests utils --glob '*.py' | sort
```

结果为 **114 paths**。以下逐文件回看 actual constructor、literal、export 或调用目的；分类不是由零命中推断。

| # | path | actual direct evidence / final disposition |
| ---: | --- | --- |
| 1 | `dayu/contracts/__init__.py` | 只导出 ToolDefinition/ToolFunctionSchema contracts；not text owner/no-diff |
| 2 | `dayu/contracts/tool_declaration.py` | generic decorator/definition constructor，机械承接 producer 文案；no-diff |
| 3 | `dayu/contracts/tool_schema.py` | typed schema shape/validation，无具体业务文案；no-diff |
| 4 | `dayu/engine/__init__.py` | Engine request/message/schema re-export；no-diff |
| 5 | `dayu/engine/_default_runner.py` | AgentRunRequest 到 runner 装配；不读写消息语义；no-diff |
| 6 | `dayu/engine/agent.py` | pattern-match typed messages、构造 continuation UserMessage；Engine transport owner/no-diff |
| 7 | `dayu/engine/contracts/__init__.py` | contracts re-export；no-diff |
| 8 | `dayu/engine/contracts/agent_run.py` | request closed-union/non-empty validation；no-diff |
| 9 | `dayu/engine/contracts/messages.py` | System/User carrier dataclasses；content owner在上游；no-diff |
| 10 | `dayu/engine/runners/openai/_types.py` | provider wire TypedDict；no-diff |
| 11 | `dayu/engine/runners/openai/payload.py` | typed messages/tool schemas机械序列化；no-diff |
| 12 | `dayu/fins/tools/download_tools.py` | start_fins_download producer；ingestion schema audited/no-diff |
| 13 | `dayu/fins/tools/fins_tools.py` | 九个 read ToolDefinitions；只改共用 ticker/document_id helper |
| 14 | `dayu/fins/tools/preprocess_tools.py` | start_fins_preprocess producer；no-diff |
| 15 | `dayu/fins/tools/provider.py` | 聚合九个 read definitions；具体文案 owner在 fins_tools；no-diff |
| 16 | `dayu/fins/tools/upload_tools.py` | start_fins_upload producer；no-diff |
| 17 | `dayu/host/admission.py` | selected display snapshot/governance summary；not schema text owner/no-diff |
| 18 | `dayu/host/api.py` | public Host/worker protocol传递 typed request；no-diff |
| 19 | `dayu/host/compact_pipeline.py` | material kind到 System/User/Assistant messages 的既有投影；S3 owner/no-diff |
| 20 | `dayu/host/compaction_operation.py` | lifecycle state持有 AgentRunRequest；no-diff |
| 21 | `dayu/host/dispatch.py` | 从 RunInput 机械构造 AgentRunRequest；no-diff |
| 22 | `dayu/host/llm_compaction.py` | audited prompt assets + typed compact request assembly；no-diff |
| 23 | `dayu/host/local_proxy.py` | request transport到 Engine；no-diff |
| 24 | `dayu/host/run_input.py` | real Host LLM input owner；S1 strict atoms retained，S2 no-diff |
| 25 | `dayu/host/tool_runtime.py` | business/framework ToolDefinition owner；仅 fetch_more descriptions modified |
| 26 | `dayu/host/tool_runtime_schema_projection.py` | schema JSON/digest identity projection；no-diff |
| 27 | `dayu/runtime/tools_discovery.py` | definition aggregation/unique name/digest；no-diff |
| 28 | `dayu/service/host_assembly.py` | Fins producer assembly；no duplicated schema text/no-diff |
| 29 | `dayu/tools/__init__.py` | package overview mention；not LLM-facing/no-diff |
| 30 | `dayu/tools/doc_provider.py` | doc provider composition mention；actual ToolDefinition owner在 doc_tools/no-diff |
| 31 | `dayu/tools/doc_tools.py` | five real Doc schemas；R01 final retained/no-diff |
| 32 | `dayu/tools/utils/provider.py` | get_current_time real schema；audited/no-diff |
| 33 | `dayu/tools/web/provider.py` | Web definition discovery/validation；text owner在 web_tools/no-diff |
| 34 | `dayu/tools/web/web_tools.py` | two real Web definitions；仅 url description modified |
| 35 | `tests/contracts/test_package_exports.py` | package symbol surface fixture；no-diff |
| 36 | `tests/contracts/test_tool_declaration.py` | mismatched/empty definition contract samples；no-diff |
| 37 | `tests/engine/contracts/test_agent_run.py` | `hello` typed request validation；no-diff |
| 38 | `tests/engine/runners/openai/test_cancellation_boundaries.py` | `hi` runner cancellation checkpoints；no-diff |
| 39 | `tests/engine/runners/openai/test_cancellation_no_done_event.py` | `hi` cancelled terminal fixture；no-diff |
| 40 | `tests/engine/runners/openai/test_http_error_event.py` | HTTP failure runner fixture；no-diff |
| 41 | `tests/engine/runners/openai/test_http_unknown_status_runner.py` | unknown status transport fixture；no-diff |
| 42 | `tests/engine/runners/openai/test_payload_assistant_reasoning_content_preserved.py` | reasoning replay + `hi` user carrier；no-diff |
| 43 | `tests/engine/runners/openai/test_payload_build.py` | `sys/hi` + mock schema outbound serializer；no-diff |
| 44 | `tests/engine/runners/openai/test_request_identity.py` | request identity fixture；no-diff |
| 45 | `tests/engine/runners/openai/test_response_cleanup_race.py` | response close lifecycle fixture；no-diff |
| 46 | `tests/engine/runners/openai/test_retry_backoff.py` | `hi` retry/backoff fixture；no-diff |
| 47 | `tests/engine/runners/openai/test_runner_b3_extra.py` | provider extra/body fixture；no-diff |
| 48 | `tests/engine/runners/openai/test_runner_diagnostics.py` | diagnostics fixture；no-diff |
| 49 | `tests/engine/runners/openai/test_runner_only_emits_runner_event.py` | forbidden export symbol set；no-diff |
| 50 | `tests/engine/runners/openai/test_stream_idle.py` | idle/heartbeat fixture；no-diff |
| 51 | `tests/engine/runners/openai/test_stream_usage_capability_gating.py` | usage capability fixture；no-diff |
| 52 | `tests/engine/runners/openai/test_streaming_capability_and_content_type.py` | `hi` stream/content-type requests；no-diff |
| 53 | `tests/engine/test_agent_message_union.py` | `x` closed message union/role fixture；no-diff |
| 54 | `tests/engine/test_agent_phase2.py` | `hello` loop request + mock lookup schema；no-diff |
| 55 | `tests/engine/test_agent_phase3_tool_call.py` | `calculate` + add_numbers schema/outcome transport；no-diff |
| 56 | `tests/engine/test_import_boundary.py` | forbidden ToolDefinition symbol set；no-diff |
| 57 | `tests/engine/test_metadata_boundary.py` | metadata not entering protocol fixture；no-diff |
| 58 | `tests/engine/test_package_exports.py` | Engine export surface；no-diff |
| 59 | `tests/fins/test_fins_ingestion_tools.py` | real awaiting schema leak assertions；audited no-diff |
| 60 | `tests/fins/test_fins_storage_provider.py` | real nine Fins read definitions；shared descriptions modified |
| 61 | `tests/host/public_smoke_support.py` | deterministic public Host ordinary/awaiting schemas；no-diff |
| 62 | `tests/host/recovery_support.py` | fake proxy仅接收 typed request；no-diff |
| 63 | `tests/host/stress_support.py` | stress proxy typed request；no-diff |
| 64 | `tests/host/test_active_cancel_dispatch.py` | proxy accept request type/lifecycle；no-diff |
| 65 | `tests/host/test_compaction_cancellation_scope.py` | fake compactor observes typed request；no-diff |
| 66 | `tests/host/test_compaction_operation.py` | compaction lifecycle System/User request；no-diff |
| 67 | `tests/host/test_dispatch_scheduler.py` | scheduler/compaction state fixtures with mock schema；no-diff |
| 68 | `tests/host/test_effective_execution_config.py` | recording proxy saves request/config；no-diff |
| 69 | `tests/host/test_engine_ingest_mapping.py` | reactive system/user request fixture；no-diff |
| 70 | `tests/host/test_host_activity_event_projection.py` | mock schema activity projection；no-diff |
| 71 | `tests/host/test_import_boundary.py` | Host forbidden export symbol set；no-diff |
| 72 | `tests/host/test_llm_compaction.py` | captures real compactor AgentRunRequest；prompt owner audited/no-diff |
| 73 | `tests/host/test_local_proxy_engine_ingest.py` | Host/Engine proxy ingest `hello` request；no-diff |
| 74 | `tests/host/test_logging.py` | `_SECRET_PROMPT` only proves logs do not leak；security fixture/no-diff |
| 75 | `tests/host/test_open_host_runtime.py` | public runtime recording proxy；no-diff |
| 76 | `tests/host/test_per_run_tool_selection.py` | mock ToolDefinition selection；no-diff |
| 77 | `tests/host/test_phase5_local_execution_integration.py` | fake proxy receives request；no-diff |
| 78 | `tests/host/test_phase6_toolruntime_integration.py` | ordinary mock ToolDefinition accept integration；coverage-only/no-diff |
| 79 | `tests/host/test_phase7_waiting_integration.py` | awaiting ToolDefinition state fixture；coverage-only/no-diff |
| 80 | `tests/host/test_public_compact_smoke.py` | real compact prompt/public Host schema；S3 propagation/no-diff |
| 81 | `tests/host/test_public_lifecycle_smoke.py` | lifecycle fake proxy；no-diff |
| 82 | `tests/host/test_public_open_host_options.py` | public option assembly request；no-diff |
| 83 | `tests/host/test_public_retry_replay.py` | retry/replay request capture；no-diff |
| 84 | `tests/host/test_resolve_wait_command.py` | accepted S1 resume AgentRunRequest/UserMessage fixture；transition identity owner，不是新增 S2 source/no-diff |
| 85 | `tests/host/test_run_input_builder.py` | real Host messages/mock schema owner test；exact suite/no-diff |
| 86 | `tests/host/test_storage_maintenance.py` | no-op proxy typed request；no-diff |
| 87 | `tests/host/test_storage_usage_report.py` | no-op proxy typed request；no-diff |
| 88 | `tests/host/test_submit_followup_public_contract.py` | recording follow-up request；prompt owner在 RunInput/no-diff |
| 89 | `tests/host/test_tool_runtime_schema_projection.py` | mock schema transport/digest；no-diff |
| 90 | `tests/host/test_tool_trace_queries.py` | UserMessage only用于 internal runner-input reconstruction；S2 exact suite/no-diff |
| 91 | `tests/host/test_tooling_options.py` | mock ToolDefinition option assembly；no-diff |
| 92 | `tests/host/test_toolruntime_diagnostics.py` | mock definition diagnostics；coverage-only/no-diff |
| 93 | `tests/host/test_toolruntime_duplicate_governance.py` | mock duplicate decisions；coverage-only/no-diff |
| 94 | `tests/host/test_toolruntime_effective_bundle.py` | mock definition + framework injection；coverage-only/no-diff |
| 95 | `tests/host/test_toolruntime_executor.py` | mock execution boundary；coverage-only/no-diff |
| 96 | `tests/host/test_toolruntime_truncation_fetch_more.py` | real framework schema/behavior；description owner test modified |
| 97 | `tests/host/test_watch_session_events.py` | fake proxy event watch；no-diff |
| 98 | `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | real scenario prompts + conflict mock；no-diff |
| 99 | `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | real smoke assembly + conflict mock；no-diff |
| 100 | `tests/runtime/test_tools_discovery.py` | mock definition discovery；no-diff |
| 101 | `tests/runtime/test_tools_discovery_digest.py` | schema digest stability；no-diff |
| 102 | `tests/service/test_host_assembly.py` | Service mock ToolDefinition composition；no-diff |
| 103 | `tests/tools/test_combined_tools_acceptance.py` | current combined schemas/framework injection；no-diff |
| 104 | `tests/tools/test_doc_tools_provider.py` | real five Doc schemas/R01 smoke；no-diff |
| 105 | `tests/tools/web/test_diagnose_web_access.py` | diagnostic import/assembly mock schema；no-diff |
| 106 | `tests/tools/web/test_smoke_web_ci.py` | Web CI execution shell mock schema；no-diff |
| 107 | `tests/tools/web/test_web_tools_provider.py` | real Web definitions；url assertion modified |
| 108 | `utils/diagnose_web_access.py` | current provider取得/执行 ToolDefinition，operator diagnostic；no-diff |
| 109 | `utils/smoke_async_agent_providers.py` | real provider `_PROMPT` AgentRunRequest，业务中性；no-diff |
| 110 | `utils/smoke_host_public_awaiting_entrypoint.py` | public awaiting mock schema + finance prompt；no-diff |
| 111 | `utils/smoke_host_public_conversation_memory.py` | real provider/public Host finance memory schemas；no-diff |
| 112 | `utils/smoke_host_public_conversation_memory_scenarios.py` | scenario prompts/schema/compactor material；no-diff |
| 113 | `utils/smoke_host_public_multiturn.py` | real public Host/provider smoke facts；no-diff |
| 114 | `utils/smoke_web_ci.py` | real Service discovery ToolDefinition direct execution；no custom LLM schema/no-diff |

集合 reconciliation：count 与 accepted baseline 同为 114。`dayu/host/compact_pipeline.py`、`dayu/tools/doc_provider.py` 是实际 scan path，分别已在 §8.2/§9 owner inventory 覆盖；`tests/host/test_resolve_wait_command.py` 的 constructor 命中来自 accepted S1 resume fixture。它们都不是 S2 新 semantic source。accepted plan 中列出的 future R03 smoke 两个路径仍不存在，未提前进入 S3。

## 6. R01 §11 mandatory handoff：30 行逐行 disposition

### 6.1 五个 descriptions

| # | R01 row | actual R03-S2 disposition |
| ---: | --- | --- |
| 1 | `list_files` description | retain/no-diff；`total/returned/scanned_entries` 与 navigation 语义不变；Doc exact suite通过 |
| 2 | `get_file_sections` description | retain/no-diff；大文件先定位章节仍是合法 output/navigation efficiency |
| 3 | `search_files` description | retain/no-diff；只保留 `result_limit` partial 语义 |
| 4 | `read_file` description | retain/no-diff；字符 output partial 合法 |
| 5 | `read_file_section` description | retain/no-diff；ref/navigation 与 output partial 合法 |

### 6.2 五组 parameters

| # | R01 row | actual R03-S2 disposition |
| ---: | --- | --- |
| 6 | list `directory/pattern/recursive/limit` | retain/no-diff；无 source input cap |
| 7 | sections `file_path/limit` | retain/no-diff；本 slice测试证明合法 `file_path` 不被字段名 blacklist |
| 8 | search `query/directory/include_types/limit` | retain/no-diff |
| 9 | read `file_path/start_line/end_line` | retain/no-diff；行范围仍是 output narrowing |
| 10 | read-section `file_path/ref` | retain/no-diff；ref 是必要业务导航标签且自解释 |

### 6.3 五组 error/message/hint owners

| # | R01 row | actual R03-S2 disposition |
| ---: | --- | --- |
| 11 | argument validation `_DocBusinessFailure` | retain/no-diff |
| 12 | `_project_doc_paths` | retain/no-diff；路径是 Doc owner 的合法业务输入 |
| 13 | business exception projection | retain/no-diff |
| 14 | cancellation projection | retain/no-diff |
| 15 | former source budget failure/catch/hints | 继续 absent；未恢复、未转交 Issue #177 |

### 6.4 五组 result keys

| # | R01 row | actual R03-S2 disposition |
| ---: | --- | --- |
| 16 | list final keys | retain exact set/no-diff；Doc exact suite通过 |
| 17 | search final keys | retain exact set/reason/no-diff |
| 18 | read final keys | retain output partial fields/no-diff |
| 19 | sections final keys | retain/no-diff |
| 20 | read-section final keys | retain/no-diff |

### 6.5 十个其它 source rows

| # | R01 row | actual R03-S2 disposition |
| ---: | --- | --- |
| 21 | `dayu/config/prompts/base/tools.md` Doc workflow | 人工完整读取；保留“大文件先看 sections”；no-diff |
| 22 | `tests/tools/test_doc_tools_provider.py` exact descriptions | retain/no-diff；第二 exact suite通过 |
| 23 | 同文件 real complete-input smoke fixture | retain/no-diff；不冒充 R03 public-run smoke |
| 24 | 同文件 key/absence/source assertions | retain/no-diff |
| 25 | `tests/tools/test_combined_tools_acceptance.py` | retain/no-diff；未声称 Issue #177 完成 |
| 26 | `dayu/tools/doc_provider.py` | composition/operator source，not LLM business text owner；no-diff |
| 27 | `dayu/config/tool_discovery.json` | raw config，not LLM-facing；no-diff |
| 28 | `dayu/config/README.md` R01 text | development doc；no-diff |
| 29 | `tests/README.md` R01 text | 原 R01 内容保留；只更新 R03 S2 当前测试事实 |
| 30 | root `README.md` | 安装/CLI/user workflow 未变；README trigger判定 no-diff |

## 7. Tests、coverage 与静态验证

### 7.1 §10 exact pytest

```bash
source .venv/bin/activate
pytest \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_toolruntime_truncation_fetch_more.py \
  tests/tools/web/test_web_tools_provider.py \
  tests/fins/test_fins_storage_provider.py -q
```

结果：`519 passed, 1 skipped, 3 warnings in 19.61s`。skip 是既有环境条件；三条 warning 均来自 edgartools deprecated module。

```bash
pytest \
  tests/tools/test_doc_tools_provider.py \
  tests/tools/test_combined_tools_acceptance.py \
  tests/runtime/test_import_boundary.py \
  tests/runtime/test_scene_assets_migration.py \
  tests/engine/runners/openai/test_payload_build.py \
  tests/engine/test_agent_phase3_tool_call.py -q
```

结果：`171 passed, 3 warnings in 8.80s`。

### 7.2 coverage

先对 §10 第一组运行 coverage，再只追加既有 no-diff ToolRuntime owner regression（未编辑这些 tests）：

```bash
coverage run -a -m pytest \
  tests/host/test_accepted_tool_outcome_codec.py \
  tests/host/test_phase6_toolruntime_integration.py \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_public_contracts.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_toolruntime_diagnostics.py \
  tests/host/test_toolruntime_duplicate_governance.py \
  tests/host/test_toolruntime_effective_bundle.py \
  tests/host/test_toolruntime_executor.py \
  tests/tools/test_combined_tools_acceptance.py \
  tests/tools/test_doc_tools_provider.py -q
```

追加结果：`282 passed`。逐文件最终结果：

| production file | coverage | gate |
| --- | ---: | --- |
| `dayu/fins/tools/fins_tools.py` | 80% | pass；新增两个 helper 行均执行，达到新增 helper >=90% |
| `dayu/host/accepted_result_projection.py` | 94% | pass，>=90% |
| `dayu/host/tool_runtime.py` | 88% | pass |
| `dayu/host/tool_trace.py` | 88% | pass；redaction/descriptor placeholder branches已从源码删除 |
| `dayu/runtime/__init__.py` | 100% | pass |
| `dayu/tools/web/web_tools.py` | 81% | pass |
| `dayu/runtime/json_redaction.py` | N/A | deletion/source proof；未保留 dead module |

### 7.3 pyright、Ruff、diff

```bash
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
ruff check <本 slice 修改 Python 文件> --ignore F401,F841
```

结果：`All checks passed!`。对 Web 以外的本 slice Python 文件单独执行
default Ruff 同样为 `All checks passed!`。随后对 Web 执行 default Ruff；唯一非零是
`dayu/tools/web/web_tools.py` 的 13 个 F401 与 1 个 F841。用下列 HEAD 对照复现相同 14 项：

```bash
git show HEAD:dayu/tools/web/web_tools.py \
  | ruff check --stdin-filename dayu/tools/web/web_tools.py --output-format concise -
```

HEAD 与当前均为相同符号的 `Found 14 errors`；本次只因 URL schema 插入四行导致后续 F841 行号从 1533 移到 1537。它们不是本 slice 新增或扩散；严格按 “Web 只改 URL description” scope 未借机删除 unrelated imports/exception binding。该 baseline lint debt 作为 residual owner 交 Controller，不伪报 default Ruff 零错误。

`git diff --check`：无输出，pass。本 artifact 尚是 untracked，另执行
`git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md`，
只返回表示存在新文件 diff 的 code 1，无 whitespace 诊断。

### 7.4 §10.3 source gates

1. `llm_safe_replay_arguments|arguments_summary_unsafe|unsafe_argument|safe_arguments|accepted_arguments_source_digest`
   - production 零命中；本 slice 八个 test 文件零命中。
   - 全仓唯一命中是 accepted S1 no-diff `tests/host/test_wait_awaiting_accept.py` 对 `accepted_arguments_source_digest` 的 **absence assertion**；不是生产 contract，也未在 S2 allowlist 内修改。
2. `redact_sensitive_json_fields|json_redaction|_SENSITIVE_KEY_FRAGMENTS|JSON_REDACTION_MARKER`
   - Host/runtime/tests 零命中，删除模块不存在。
   - 全仓余下 `_SENSITIVE_KEY_FRAGMENTS` 只在 `dayu/engine/runners/openai/diagnostic_payload.py`，owner 是 provider diagnostic security projection，不是 accepted arguments/Tool Trace readable normalization；Engine audited no-diff。
3. `_INTERNAL_SOURCE_REF_KINDS|_readable_ref_text`
   - 命中仍位于 `accepted_result_projection.py` 的 source projection；这是 accepted plan 明确放入 R03-S3 的 opaque source owner。本 slice不越界删除。
4. `api_key.*token.*secret.*password|password.*secret.*token.*api_key`
   - `dayu/host dayu/runtime tests/host` 零命中。单独出现的 `api_key_ref="test-key"` 属 runner/provider config fixture，不是字段名 blacklist或 LLM replay contract。

## 8. README trigger 与 no-diff proof

- `dayu/host/README.md`：Host Tool Trace 的稳定边界已改变，命中职责，按现有章节更新。
- `tests/README.md`：测试 owner contract 已改变，命中职责，更新 Memory/Tool Trace/Web/Fins schema 测试事实。
- 根 `README.md`：安装、CLI、输出通道、日志、workspace 与用户工作流均未变，no-diff。
- `dayu/README.md`：分层/装配关系未变，no-diff。
- `dayu/fins/README.md`：仅 LLM-facing parameter descriptions，不改变 Fins 存储/业务开发接口；按其职责无需更新。
- config/Engine/Doc/utils provider/Fins ingestion schema：`git diff --name-only --` 对这些路径为空。

## 9. Allowlist reconciliation 与 residual owners

结束时 implementation diff 路径为：

```text
dayu/fins/tools/fins_tools.py
dayu/host/README.md
dayu/host/accepted_result_projection.py
dayu/host/tool_runtime.py
dayu/host/tool_trace.py
dayu/runtime/__init__.py
dayu/runtime/json_redaction.py (deleted)
dayu/tools/web/web_tools.py
tests/README.md
tests/fins/test_fins_storage_provider.py
tests/host/test_accepted_result_projection.py
tests/host/test_memory_projection.py
tests/host/test_tool_trace_projection.py
tests/host/test_toolruntime_truncation_fetch_more.py
tests/tools/web/test_web_tools_provider.py
docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md
```

这是 §7.2 子集加用户明确要求的 implementation artifact。`payload_resolution.py`、`run_input.py`、`test_run_input_builder.py` 与 `test_tool_trace_queries.py` 经人工审计后无需 S2 diff；不为了“改满 allowlist”制造空重写。

Residual owners：

1. `accepted_result_projection.py` 的 opaque source kind/filter 与 `_readable_ref_text` 属 R03-S3；未处理。
2. `TOOL_CALL_REQUESTED` descriptor exact-args strict row resolution 属 R03-S3。S2 只保证 descriptor ref/digest 不进入 readable summary；accepted-result path 和 inline request path已显示 exact args。未新增 placeholder、fallback 或 loose resolver。
3. Web default Ruff 的 14 项是 HEAD 同源旧债；未在 schema-only S2 越界清理。
4. 未运行/创建 R03-S3 public smoke、未做 aggregate、未 commit、未发 review。

交回 Controller 时 working tree 保留上述未提交 diff。
