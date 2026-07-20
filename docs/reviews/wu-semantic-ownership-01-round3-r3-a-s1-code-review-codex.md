# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: implementation diff 以 control-doc plan acceptance `41bd6ca9` 为基线；实现意图以 accepted plan `4a282850` 为基线
- Review time: `2026-07-12T13:41:10+08:00`（本机系统时钟）
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-codex.md`
- Included scope: R3-A S1 的 DR-006 runner-call hot payload、DR-010 durable descriptor/content integrity、effective execution snapshot、Tool Trace reconstruction、compact material request provenance、对应测试与 S1 文档更新
- Excluded scope: S2-S8 行为、schema DDL/migration、CLI/Config/Fins/Engine provider、control doc、commit/push/PR
- Parallel review coverage: 未使用 subagent。`wu-semantic-ownership-01-round3-r3-a-s1-code-review-mimo.md` 与 `wu-semantic-ownership-01-round3-r3-a-s1-code-review-ds.md` 仅在独立走读完成后作为结论对照；下列 findings 均由本 reviewer 回到真实代码路径复核。DS 关于 `compact_material.py` 其它 validation 调用越界的判断与 `41bd6ca9` 实际 diff 不符，未采纳；其 `iteration_index` 判断只依赖未来假设，未作为 material finding。
- Independent validation: focused S1 matrix `406 passed`；serial stress `5 passed`；`pyright dayu/host tests/host` 为 `0 errors`；完整 S1 矩阵下新增 owner 文件覆盖率为 `_runner_call_manifest.py 94%`、`durable/payload_resolution.py 84%`；`git diff --check` 通过

## Findings

### 1-未修复-[高]-严格 compact 路径把 durable payload 损坏降级成“没有 evidence”

- **入口/函数**: `build_pre_dispatch_compact_material_view()` → `_pre_dispatch_delta_material_blocks()` → `_accepted_tool_evidence_delta_blocks()`
- **文件(行号)**: `dayu/host/compact_material.py:2556-2558`；`dayu/host/accepted_result_projection.py:271-281`
- **输入场景**: 一个已接受且 descriptor-backed 的 `TOOL_RESULT_ACCEPTED` 进入 pre-dispatch compaction；其 descriptor、SQLite row、artifact 或 canonical bytes 任一 integrity atom 被损坏，因此本次新增的 shared `resolve_json_payload()` 正确抛出 `HostDurableError`。
- **实际分支**: `project_accepted_tool_result()` 在读取 event payload 时捕获该 `HostDurableError`，返回空 payload 加 `event_payload_unavailable` diagnostic；随后 `_accepted_tool_evidence_delta_blocks()` 观察到 `projection.envelope_available == False`，直接返回空 tuple。
- **预期行为**: compact material 是会进入后续 LLM proposal 和 durable compact truth 的严格消费者；shared integrity owner 报错后必须终止 material 构造并向上抛 `HostDurableError`，不得把“payload 已损坏”解释成“该 accepted evidence 不存在”。
- **实际行为**: compaction 继续执行，但损坏 row 对应的 accepted evidence 被静默省略。共享 resolver 虽然检测到了损坏，其错误语义却被下游 lenient projection 吞掉。
- **直接证据**: `accepted_result_projection.py:271-281` 明确把 `event_payload_object()` 的所有 `HostDurableError` 转成 `{}`；`compact_material.py:2556-2558` 在检查本次新增的 request ref / request identity 之前就按 `envelope_available=False` 返回。既有 `tests/host/test_accepted_result_projection.py:701-748` 还明确证明不可读 payload 会被降级为 `LOST` diagnostic；新增 compact fail-closed tests 只覆盖 missing/wrong request ref，没有覆盖 result descriptor/row/artifact tamper。该路径与 accepted plan 中“篡改时不得返回空值或旧字段”的 owner 边界相反。
- **影响**: 已接受的财报工具证据可从 compactor 输入中无声消失，后续 compact artifact、memory 与 LLM answer 可能基于不完整事实继续生成；外部表现不是明确的 integrity failure，而是难以审计的错误分析或事实遗漏。
- **建议改法和验证点**: 保留 `AcceptedToolResultProjection` 供 read/display 使用的 lenient contract，但在 compact strict owner 边界先调用 `event_payload_object()` 完整解析并校验 row，再把结果作为 `resolved_payload` 传给 `project_accepted_tool_result()`；resolver 异常必须原样向上收口。新增 compact integration tamper matrix，至少分别篡改 descriptor digest/size、SQLite row digest/size/content、artifact containment/bytes，并断言 material 构造抛错且不产生 compact proposal/material block。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 2-未修复-[中]-Tool Trace 只验证 manifest bytes 与六字段外形，未验证完整 manifest 语义图

- **入口/函数**: Engine continuation `_limited_runner_call_manifest_body()` / `_observed_runner_call_message_entry()`；Tool Trace `read_runner_call_reconstruction_signals_by_run()` → `_projector_metadata_summary_from_manifest()`
- **文件(行号)**: `dayu/host/engine_ingest.py:5620-5628,5656,5750-5767`；`dayu/host/durable/tool_trace.py:1044-1086`；`dayu/host/_runner_call_manifest.py:226-258`；`tests/host/test_engine_ingest_mapping.py:4409-4425`；`tests/host/test_tool_trace_queries.py:784-805`
- **输入场景**: 正常的 Engine continuation 携带四条 observed input messages 和 projection descriptor；随后 Tool Trace 按 Run 查询该 `RUNNER_CALL_INPUT_ASSEMBLED` signal。
- **实际分支**: 每条 message entry 写入 `projector:{message.index}:{message.role}`，但 manifest 只写一条 id 为 `projector:{iteration_index}:engine-observed` 的 metadata。Tool Trace 校验 descriptor ref/digest/row/bytes 后，只检查 `projector_metadata` 每项是否恰有六个字段、digest 格式及 id 唯一；它不验证 schema/identity/count、message entry 引用闭合、closed enum 或 hot signal 与 manifest identity 一致。
- **预期行为**: digest 验证只证明 bytes 未分裂，不能证明该 JSON 是语义有效且属于当前 signal 的 runner-call manifest。按 design contract，每个 message 的 `projector_metadata_id` 必须解析到 manifest 中的一项，`projector_id` / `purpose` 必须属于 closed enum，message count/index/identity/digest 必须由 manifest owner 一次性校验。
- **实际行为**: 当前真实 continuation manifest 的四个 message metadata ref 全部悬空，Tool Trace 仍返回一条看似有效的 metadata summary。测试还把只有 `{"projector_metadata": ...}`、没有 schema、identity、messages 或 counts 的 JSON 当作“verified manifest”并成功恢复 300 条 summary。
- **直接证据**: `engine_ingest.py:5656` 与 `:5750` 使用互不相同的 id 公式；当前 production test 在 `test_engine_ingest_mapping.py:4413-4415` 同时断言四条 message entries 与仅一条 metadata，却未断言引用闭合。`durable/tool_trace.py:1044-1086` 在 generic content integrity 之后只遍历 metadata list。`_runner_call_manifest.py:236-250` 对 `projector_id` / `purpose` 只做非空字符串检查；只读 probe 已确认任意非空的 `not-a-closed-projector` / `not-a-closed-purpose` 会被 owner 接受。`docs/host/design.md:2711-2723,2738,2748-2753` 明确要求 count/index、引用闭合及 closed enum。
- **影响**: Tool Trace / analyzer 无法把真实 continuation messages 关联到正确 projector contract，审计 provenance 会不完整或错误；任意内部 typo/非法 purpose 也能成为 durable semantic fact。descriptor digest 全绿会掩盖这一语义损坏。
- **建议改法和验证点**: 让 `dayu.host._runner_call_manifest` 同时拥有 typed full-manifest parser/validator，而不只拥有 hot serializer 和单项 metadata serializer；统一校验 schema、scope identity、message count/index、projection pair、metadata id 唯一/引用闭合、closed enums 与必要 digest。Engine continuation 应让所有 message entries 引用实际存在的 metadata（可共享一个正确 id，或按 message 生成对应 metadata）。Tool Trace 只能从该 owner 返回的 typed validated manifest 投影 summary。把 300-message 测试改成真实 producer manifest，并新增 incomplete manifest、悬空 id、unknown enum、hot/manifest identity mismatch 的 fail-closed 反例。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-[中]-shared hot owner 只约束写端，两个消费者仍为缺失 diagnostic 合成 complete

- **入口/函数**: Tool Trace `_runner_call_trace_summary()` → `_runner_call_diagnostic()`；Engine continuation resolution `_runner_call_payload_diagnostic()`
- **文件(行号)**: `dayu/host/tool_trace.py:735-764`；`dayu/host/engine_ingest.py:6597-6630`；`tests/host/test_tool_trace_projection.py:1616-1686`；`tests/host/test_tool_trace_queries.py:663-679`；`docs/host/design.md:1719,2676`
- **输入场景**: 一个 legacy、测试伪造或损坏的 `RUNNER_CALL_INPUT_ASSEMBLED` hot row 写有 `validation_status="complete"`，但 `diagnostic` 为 `None`、缺字段或与 message count / role digest 不一致；payload 还可能携带旧 `projector_metadata_summary` 数组。
- **实际分支**: Tool Trace 只看 sibling `validation_status`，在 complete 分支完全不读取 `diagnostic`，直接构造新的 complete diagnostic；Engine ingest 同样从 sibling count/digest 合成 complete。两条路径都绕过 shared owner 对 explicit diagnostic 的写端契约。
- **预期行为**: S1 frozen contract 要求 complete hot payload 也必须携带固定 shape、`status="complete"` 的 diagnostic，且不保留旧 hot payload compatibility。消费者应由同一 owner 解析并验证 exact shape、status/count/digest 跨字段一致性；缺失或冲突必须 fail closed。
- **实际行为**: malformed/legacy canonical row 被下游修补成 complete signal，Tool Trace cold/hot summary 与 Engine continuation diagnostic 因而显示“完整”，没有暴露 owner contract 已损坏。
- **直接证据**: `tool_trace.py:749-764` 和 `engine_ingest.py:6608-6630` 的 complete 分支均不要求 `diagnostic` 为 mapping。只读 probe 对 `diagnostic=None` 的 payload 调用两函数都返回 `complete`。修改后的 `test_tool_trace_projection.py:1616-1686` 明确注入旧 hot array 与 `diagnostic=None` 并断言投影成功；`test_tool_trace_queries.py:663-679` 也以 `diagnostic=None` 构造 complete signal。文档自身同时在 `design.md:1719` 允许 complete diagnostic 为 null、又在 `:2676` 要求 complete diagnostic 显式存在，形成两个互斥 contract。
- **影响**: canonical reconstruction corruption、旧 schema 数据或 producer 漂移会被隐藏，trace/audit 与 Engine validation 可能错误声称 complete；同一事实同时由 writer owner 和 consumer synthetic branch 产生，违反唯一语义 owner。
- **建议改法和验证点**: 在 `_runner_call_manifest` 增加 full hot payload typed parser/validator，并让 Tool Trace 与 Engine ingest 共同调用；complete 也必须读取 diagnostic，验证 exact fields、`reason/missing_*` 为空、observed/expected count 等于 `message_count`、observed/expected digest 等于 `role_sequence_digest`，再仅在展示投影中改写 consumer boundary。删除 legacy-array/null-diagnostic 成功夹具，新增 missing diagnostic、status mismatch、count/digest mismatch、旧 array 的 fail-closed tests，并统一 `docs/host/design.md` 两处契约。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

## Open Questions

- 无。

## Residual Risk

- generic durable JSON resolver 本身的 caller/descriptor/row/bytes/artifact/canonical-object 校验、effective execution config digest/ref 校验、compact request-event identity 校验、12-call stress oracle与 S1 scope audit未发现其它 material defect。
- `406 passed`、stress `5 passed` 与 pyright 全绿只能证明现有 oracle；其中多个新/修改测试正在明确接受不完整 manifest 或 null complete diagnostic，因此不能作为上述 findings 的反证。
- 本次未进入 S2-S8，也未评估那些 slice 的既有 accepted risks；workspace 中对应 production package 无 S1 越界 diff。

## Conclusion

`FAIL`：发现 1 项高严重度、2 项中严重度未修复 finding；当前 S1 不应进入 accepted commit / S2。
