# PR 190 F18 Plan Re-review Adjudication

## Gate decision

- Re-reviewed plan：`docs/gateflow/pr-190-f18-plan-20260808.md`。
- Reviews：
  - `docs/reviews/plan-review-20260808-152300.md`（AgentMiMo，`fail`）；
  - `docs/reviews/plan-review-20260808-152338.md`（AgentDS，`fail`）。
- Controller verdict：`fail`；返回 AgentCodex 做第二次 plan fix。provider gate继续关闭。

## Controller evidence corrections

两路 review 的主 blockers成立，但以下 owner细节由 Controller 直接裁清：

1. pre-dispatch material query 对 current input sequence 使用 exclusive end boundary；current input另作为 current anchor投影，
   不进入 selected recent completed-turn floor。因此 R13 时 floor=4保护 R9-R12，R9 unsupported material确实被排除；
   AgentMiMo 的结论成立。AgentDS 关于 current R13计入 floor、R9已eligible的细节不接受。
2. context window size 由 Service 从 effective model `context_window_tokens`装配，不由 `standard-256k` profile名字决定。当前
   MiMo plan model的值是 `1048576`，所以 ratio `0.001` 的 soft threshold是 `1048`，不是 `262`；AgentMiMo 的数值成立。
   两路关于 threshold远低于 `9048-26524` candidate、会提前反复触发 operation 的主 finding均接受。

## Accepted findings

### F18-RRA-01 — source-boundary/trigger cadence 不可执行

- 接受 MIMO-F18-RR-001、MIMO-F18-RR-002 与 F18-DS-RR-001 的主结论，严重程度 `high`。
- 现有 R1-R14 时序删除；不能通过把 target后移一轮修复，因为低 threshold仍会提前耗尽 operation。
- output caps与context trigger必须在同一首-opener profile中保持不同 owner语义：caps继续 constrained，soft ratio不得照搬
  Trial2 hot-switch值。新的 plan必须先用 production owner对 proposed fixed profile做 provider-independent可行性校准，再把真实
  模型差异交给 bounded stop，而不是预言 exact Run ordinal。

### F18-RRA-02 — provider/wall hard cap 不可由旧 sample保证

- 接受 MIMO-F18-RR-003 与 F18-DS-RR-002，严重程度 `high`。
- 历史 `29/28`只能是 expected cost，不是 hard cap。hard ordinary-call上界由
  `max ordinary Runs * AgentPolicy.max_iterations(24)`派生；每个 Run terminal后若超 expected budget立即seal，不启动下一 Run。
- chain hard wall deadline使用 monotonic remaining-time allocator：每次启动 segment前把 remaining传入冻结 harness；三条chain
  最多各 `540s`，另外预留 `180s` 给cleanup/publication/final scan，总计不超过registry `1800s`。到deadline可中止当前segment，
  原样记录失败，不得再启动 provider。

### F18-RRA-03 — B1 raw process outcome owner错配

- 接受 F18-DS-RR-003，严重程度 `medium`。
- B1 `exit_codes=[1]` 时 `execution_outcome`按raw process owner写 `error`；canonical ten Runs succeeded、evidence sufficient、
  gap none与accepted Oracle是独立字段，不得用业务成功改写process outcome。

### F18-RRA-04 — publication scan职责/文件名错配

- 接受 MIMO-F18-RR-004 与 F18-DS-RR-004，严重程度 `medium`。
- tracked finalizer只创建 `secret-scan.json`，不得改名。每条chain seal后先做incremental hygiene precheck，才能决定是否启动
  下一chain；它不是final publication verdict。最终所有writer完成后按handbook写digest并由tracked helper独占写
  `secret-scan.json`，之后零写入。

## Required second plan fix

最小可信的新 scenario设计如下；AgentCodex必须用代码/typed data核验后才可写入plan：

1. **Fixed profile**：保留 evidence/summary/anchor/intent/reference output caps `1 item / 160 chars`；把
   `selected_recent_window_turn_floor`改为合法的 `0`，避免为了旧 hot-switch脚本人为执行四轮aging。context soft ratio与output
   caps解耦，候选值 `0.02` 必须由 ConfigLoader/Service assembly确认对MiMo plan产生 `20971` token threshold。
2. **Provider-independent feasibility band**：现存 Trial2 owner data显示首个 FY2024 tool Run内最大 continuation candidate
   `20316 < 20971`，后续 ordinary candidate到 `20998` 时首次越线；这只证明 proposed profile存在可行band，不承诺fresh MiMo
   exact ordinal。首provider前必须保存这项typed校准、profile digest和selection policy。
3. **Phase A / accepted baseline**：fresh chain先执行一个真实 FY2024 tool Run，之后最多三个短no-tool retention Runs，直到首个
   compact operation。首operation若没有accepted且带canonical provenance的唯一FY2024 EvidenceFact，立即seal；不继续FY2025。
4. **Phase B / target**：accepted baseline后最多执行一个真实 FY2025 tool Run和一个no-tool target Run。FY2025 prompt与target
   current input都显式携带unsupported `21.7%/18.2%`作为待核验用户材料；因此无论target在tool Run的reactive boundary还是
   下一Run的pre-start boundary触发，initial input都必须直接证明previous atom、新FY2025 evidence material、unsupported current/
   trace material与真实caps共存。缺任一项立即seal，analyzer不得补足。
5. 每条chain最多 `6` ordinary Runs、`2` compact operations、每operation最多 `5` compactor calls；replacement accepted后最多
   第 `7` Run做一次fresh reconnect。expected ordinary calls可按历史 `10 + 3 + 7 + 1 (+1 reconnect)`记录为
   `21 (+1)`，hard上界分别是 `6*24=144` 与 `7*24=168`。它们是预算上界，不是要消耗的目标。
6. replacement链若自然覆盖reject->accept或5-reject->fallback，按已观察branch跳过独立repair/fallback链；最多三条chain，
   每条540秒，总provider observation预算1620秒，finalization reserve180秒。
7. no-tool Run出现任何tool request、unexpected compact operation、profile drift或再次`runner_candidate_invalid`，立即按既有全局
   stop/seal规则处理。
8. B1 process outcome与final scan按上节改正；B2裁决/readiness不变量保持。

新的 phase state machine仍是 conditional formal observation：真实MiMo可以在band内提前/延后触发；owner precondition不满足或
自然branch未出现时写`needs-more-evidence`。不得为了让plan“保证成功”新增hot-switch、output injection或无界重跑。

## Next gate

AgentCodex修订同一plan与plan-fix artifact；随后两路 reviewer再次独立re-review。通过前不得implementation、commit或真实provider。
