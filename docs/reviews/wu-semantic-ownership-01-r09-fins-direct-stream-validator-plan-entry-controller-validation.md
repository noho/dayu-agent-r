# WU-SEMANTIC-OWNERSHIP-01 R09 Plan Entry Controller Validation

## 1. Gate 与结论

- Active umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Internal remediation sub-WU：R09 Fins direct-stream terminal validator。
- Plan：`docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`。
- Plan SHA-256：`85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`。
- Plan lines：689。
- Entry verdict：**PASS / READY_FOR_DUAL_INDEPENDENT_PLAN_REVIEW**。
- 本结论只确认计划可审，不接受计划、不授权 implementation、stage、commit、R10-R12、deferred Issues、统一 authorization、push 或 PR。

## 2. Scope 与 current evidence 复核

Controller 完整读取计划并独立复核：

- current base 是 R08 completion accepted commit `a31ded764da0621b6e7a6c7c6a083b4bb6593d21`；
- 工作树只有 Controller 的 control transition 与 AgentCodex 新增 plan，staged tree 为空；
- plan-only `git diff --check` 通过；
- production allowlist 精确为 `dayu/fins/direct_events.py`、新增 `direct_stream.py`、`ingestion_runtime.py`、`dayu/service/fins_direct.py`、`dayu/cli/commands/fins.py`；
- test/README allowlist、R06/R08 no-regression、R10-R12/deferred/no-code/security boundaries 已显式记录；
- source locks 与 current tree、R08 completion artifacts 及 Controller transition 相符。

当前调用链直接证据支持 remediation 动机：

1. `FinsIngestionRuntime._run_direct_stream` 构造 missing/duplicate 并缓存 terminal；
2. Service `_ensure_result_event` 再次构造 missing/duplicate 并缓存 terminal；
3. CLI `_consume_fins_direct_events` 当前没有 duplicate checker，而是遇首个 result 即返回，并在正常耗尽时自行构造 missing；
4. runtime/Service 在首个 result 后仍接受 progress，重排后才 yield result，因此没有 `EVENT_AFTER_RESULT` 失败语义。

计划已按 actual evidence 修正 umbrella 对 CLI “scan again”的宽泛表述，没有为了匹配旧描述给 CLI 新增 duplicate checker。

## 3. Review 必须挑战的高风险点

两路 reviewer 除完整 `$planreview` / `/planreview` adversarial pass 外，必须分别给出以下问题的证据化结论：

1. **async API cutover**：current `download/preprocess/upload` 是 async-generator methods；计划是否精确规定改为普通 `def` 返回 concrete typed stream，并覆盖所有 protocol/call-site type propagation，避免 coroutine/iterator drift。
2. **exception/close precedence**：upstream exception/cancellation、duplicate/event-after 时 raw-source close、close 自身失败、consumer `aclose()` 的 object identity、资源释放与最终错误优先级是否唯一且可实现；不得只写互相冲突的“原样传播”和“先 close 再抛 protocol”。
3. **producer protocol-error channel**：current producer 没有 Fins protocol-error origin，唯一 validator 又应是三种 protocol error 唯一构造点；计划为 `_run_direct_stream_producer` 新增 protocol-error queue item 是否有直接证据，还是 speculative parallel origin/overdesign。
4. **mechanical consumer boundary**：Service/CLI 是否必须依赖 concrete `ValidatedFinsEventStream` 与 `terminal_result` property；该设计是否最小、类型自洽，且不让 CLI 重新拥有 terminal fact或形成不必要层耦合。
5. **public error/LLM/user projection**：CLI 展示 `reason.value` 是否是已裁决用户 contract，README trigger 是否正确；不得把内部治理 code 暴露为业务事实或无依据扩大用户行为。
6. **tests/smokes**：current nodes、新节点、real `dayu-cli` grammar、download/process/upload workspace handoff、Docling/network requirements、每文件 coverage 与 full validation 是否真实可执行且没有把 fake 称为 real。

任何 accepted finding 都必须由 AgentCodex 修复后对最终完整 plan 做双路 re-review；reviewer verdict 本身不授权 implementation。

## R09_PLAN_ENTRY_PASS / READY_FOR_DUAL_PLAN_REVIEW
