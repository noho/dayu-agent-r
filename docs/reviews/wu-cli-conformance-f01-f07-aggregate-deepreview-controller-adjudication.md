# WU-CLI-CONFORMANCE-F01-F07 — Aggregate Deepreview Controller Adjudication

## Scope

- Range: `cd6344c0..584ee394`
- MiMo review: `docs/reviews/wu-cli-conformance-f01-f07-aggregate-deepreview-mimo.md`
- DeepSeek review: `docs/reviews/wu-cli-conformance-f01-f07-aggregate-deepreview-ds.md`
- S8 evidence digest:
  `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`

Controller 逐项裁决两路报告，不以两路是否一致代替证据。

## Findings adjudication

### M-001 — `test_active_cancel_emits_public_cancel_event` 全量运行偶发失败

- Reviewer severity: low。
- Direct evidence: MiMo 的一次全量运行得到 6602 passed / 1 failed；该 node 单独运行通过，
  `tests/host/test_public_cancel_smoke.py` 整文件 5 tests 也通过。S8 exact implementation target
  的独立 full suite 此前为 6603 passed；本 work unit 对该 test file 没有 diff。
- Adjudication: `DEFER-WITH-OWNER — NON-BLOCKING`。
- Reason: 证据支持 test-order/environment flake，不支持把它归因到 F01-F07 production diff；
  在本 work unit 添加 isolation fixture 会用间接迹象猜 root cause，违反 root-cause/data 同源
  约束。由 Host public-smoke/test-runtime owner 在独立 work unit 复现并定位全局状态或 teardown
  泄漏。当前不改 production 或测试阈值。

### D-001 — `intent_type` / reference `reason` 应恢复旧闭集枚举

- Reviewer severity: medium。
- Adjudication: `REJECT-WITH-REASON`。
- Direct evidence: frozen v2 design 在 `docs/host/design.md` 的
  `CompactForwardIntentV2` 明确声明 `intent_type: str`；LLM-facing
  `conversation_compaction_user.md` 明确声明 `intent_type` 与 continuity `reason` 为非空字符串。
  只有 `status`、source kind 和 explicit drop reason 是闭集。当前 typed contract、strict parser、
  prompt 与 Memory projection均遵循这份新 v2 design truth。
- Reason: reviewer 从被替换的 vNext enum 反推新 v2 语义，等于擅自恢复旧 contract。按任务边界
  不得重新裁决或扩张 frozen schema，故不修改实现、design 或 oracle。

### D-002 — multi-pass `session_summary` 换行拼接不连贯

- Reviewer severity: low。
- Adjudication: `REJECT-WITH-REASON`。
- Direct evidence: reactive pass queue 是 disjoint material blocks；每个 pass candidate 先验收，
  aggregate 将所有 semantic sections 按 frozen pass order 合并，再由 root input 对 coverage、重复、
  矛盾、item/char caps 全量重验。多段 summary 以换行形成一个多段文本，不删除或重新解释业务
  语义。
- Reason: “可能不连贯”没有失败数据、稳定反例或 frozen coherence predicate；选择首段反而会丢失
  后续 pass coverage。额外 LLM summary/repair 会扩大产品语义和 provider 调用，不属于本 work unit。

### D-003 — VT100 reader thread 缺少 broad exception catch

- Reviewer severity: low。
- Adjudication: `REJECT-WITH-REASON`，保留为非阻塞维护观察。
- Direct evidence: `_read_loop` 已分别处理 terminal/select/read/strict UTF-8 的预期 I/O 失败；
  parser resolution collector 是同步 freeze 的内部 invariant，合法与畸形 VT100 输入由
  PromptToolkit parser 解析而不是异常分支；S8 覆盖 standalone Escape、CSI、Alt same/cross
  chunk 与 bracketed paste。事件循环关闭时 `call_soon_threadsafe` 的失败也不表示仍有一个合法
  `wait_next` owner。
- Reason: reviewer 建议的 `except Exception: break` 会掩盖 invariant/programming error，而且仍
  不会向等待方投递 typed terminal/error，不能修复其声称的“永久等待”。真正引入 reader failure
  channel 是新的 public/runtime failure语义，需要独立设计，不以猜测性防御分支进入 F03。

### D-004 — `_flush_submit_handoff_input` 的 `is_done` check/flush 竞态

- Reviewer severity: low。
- Adjudication: `REJECT-WITH-REASON`。
- Direct evidence: `application.is_done` 检查后直到 `flush_keys`、`feed_multiple` 与
  `process_keys` 完成之间没有 `await`；这些操作在同一 asyncio event-loop task 内同步执行，
  其它 coroutine 不能在所谓窗口中把 application 切换为 done。现有 handoff PTY/owner tests
  通过。
- Reason: reviewer 假设了不存在的 asyncio 调度点。重复检查不消除同步 callback 自身的语义，
  try/except 则会掩盖 PromptToolkit owner failure，因此不修改。

## Cross-review PASS items

Controller 接受两路对以下集成面的 PASS：CLI cancel/terminal coordination、post-cancel chord
revision owner、READ_ONLY close-before-open/stable mutation identity、VT100 complete-sequence
classification、Host compact v2 accept truth、multi-pass root revalidation、single canonical
terminal、Memory/RunInput/artifact 同源、F05 effective tool set、F06 trigger/outcome owner 分离、
frozen registry 不变量、README/design 职责与 pyright 0 errors。

## Residual risk and owner

- Host public cancel smoke 的 test-order flake：Host public-smoke/test-runtime owner；需独立稳定复现
  后定位，不在本 work unit 猜测修复。
- 真实 provider 非确定性：由 deterministic owner matrix 加真实 Mimo success/repair/exhaust/
  fallback conjunction 降低；不改变 frozen oracle。
- durable execution projection 保存 resolved Authorization：effective-execution durable projection
  owner；S8 bundle 已只保留脱敏 projection并删除本次 CI-owned raw carriers。

## Gate verdict

`AGGREGATE-DEEPREVIEW-PASS — READY-FOR-DRAFT-PR-CHAIN`

没有 production/test/docs corrective change；无需 aggregate rereview。两份 review 与本裁决应作为
accepted aggregate review commit 提交。
