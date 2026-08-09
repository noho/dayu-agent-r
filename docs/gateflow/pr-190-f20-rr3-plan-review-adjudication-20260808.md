# PR 190 F20 RR3 Plan Review Adjudication

## Gate decision

- Reviewed plan SHA-256：`68a1a708ab2fc1cb86e3c6cc8f180794a88b182ab9509ba7ae0c4ff0b265d6a6`。
- AgentMiMo：`docs/reviews/plan-review-20260808-212457.md`，`FAIL`，SHA-256
  `e4c9edf6d1364b8077dfa2a8de4c1f80884eaf406fa98f03b4edaee452226516`。
- AgentDS：`docs/reviews/plan-review-20260808-212538.md`，`FAIL`，SHA-256
  `c6c79a55c5ceb213c449cb955a91ea57390d3314265fa6580b21d70fcf269480`。
- Controller verdict：`FAIL`；两类 finding均接受，进行一次最小 plan/control-doc同步后进入 RR4。
- 用户 RR2 后的最新明确裁决已同步到 binding goal；更新后的
  `docs/gateflow/pr-190-f20-goal-confirmation-20260808.md` SHA-256 为
  `14c18553cbb3b1ca0efb4c820476ac3bc913dd75c55ef2cc4d11f0bcdfd97c67`。

RR4 双 PASS 前禁止实现、provider、formal observation与accepted oracle/scenario/readiness变更。

## Controller direct verification

1. 旧 goal 的 pre-dispatch guard文本确实没有同步用户最新裁决；新计划的 stock production CLI + post-segment canonical evidence gate
   与最新用户指令一致。问题是 binding control doc SHA漂移，不应通过恢复不存在的 formal wrapper解决。
2. `InterruptibleProcessHandle`使用 `multiprocessing.get_context("spawn")`；业务 target作为 `_run_process_target`的参数经
   multiprocessing内部pickle/pipe传给 child，而不是 parent spawn argv字段。
3. `subprocess.Popen` audit event只拥有 executable/argv/cwd/env类信息；它不能产生 Fins target module/qualname/digest。实际 spawn
   还可能创建 `resource_tracker`与 `spawn_main` helper。把 target identity、helper process集合与 parent audit event强行做一个 exact
   allowlist没有单一 owner，违反语义所有权。
4. provider-free proof 的 no-network保证不依赖 child identity反推：冻结的 OS deny-network profile从 proof process启动前覆盖全部
   descendants，parent Python audit hook只补充parent outbound attempt ledger；spawned child negative probe直接证明OS policy继承。
5. Fins业务工具身份与结果已有独立 owner链：ToolDefinition的
   `ProcessBackedToolExecutionCapability.target_factory`构造typed target，Host tool request/result/EventLog与production storage owner
   证明具体工具业务。当前产品没有将该private target pickle identity公开成audit ledger；F20不得为观察临时新增产品字段，也不得从
   process argv、PID、顺序或pickle实现细节反推公共业务语义。

## Finding adjudication

### F20-RR3-PA-01 — Binding goal 未同步最新用户裁决

- 来源：`F20-RR3-MIMO-001`。
- 裁决：`accepted`，严重程度 `high`（gate consistency）。
- 修复：Controller已将 goal success signal更新为：proof分别注入deterministic ordinary factory与compactor port，并受process-tree
  deny-network约束；formal保持stock production CLI，不包装默认factory；actual sizing是post-segment canonical evidence acceptance
  predicate，不是pre-dispatch interception。计划与fix artifact必须绑定新goal SHA，删除旧SHA/旧guard残留。

### F20-RR3-PA-02 — Parent audit event被赋予不存在的child target语义

- 来源：`F20-RR3-MIMO-002`、`F20-RR3-DS-001`。
- 裁决：`accepted`，严重程度 `high`。
- 修复：
  1. Python audit hook唯一拥有proof parent的outbound socket/name-resolution attempt ledger；删除
     `subprocess.Popen`/`os.posix_spawn`到Fins target module/qualname/digest的映射、child exact union及未知child拒绝主张。
  2. OS deny-network profile继续是完整process-tree enforcement owner；冻结binary/profile/bootstrap identity，以parent TCP/DNS/UDP与
     spawned-child TCP/UDP negative tests证明在endpoint接触前拒绝。production Fins children、`resource_tracker`与`spawn_main`
     无需安装run-owned hook，也不被伪装成bootstrap children。
  3. actual proof要求parent outbound audit hits=0、OS policy identity/descendant coverage不变、全部production Fins tool calls按Host
     request/result/terminal ledger与storage owner exact闭合。任一tool child failure、tool terminal缺失或storage identity漂移仍使proof
     FAIL；不允许in-process/direct fallback。
  4. 不新增产品target ledger，不解析multiprocessing private pipe/pickle，不从argv/PID/order反推业务target identity。若实现发现OS
     deny不能覆盖实际descendant或production tool在sandbox内不能成功，则Slice 1诚实`setup-blocked`，不得调用provider。

## RR4 frozen requirements

1. plan与fix绑定新goal SHA `14c18553…c67`及本adjudication SHA。
2. formal stock CLI/post-segment evidence gate保持不退化。
3. proof双ports与Host ledgers保持，但parent audit hook不再拥有child process/target语义；OS sandbox独占process-tree network deny。
4. deadline allocation/activation、storage-only material、clean-seed隔离、R4 245 calls与publication exact union保持闭合。

完成最小修订后冻结plan/fix byte SHA，再由MiMo/DS独立RR4；未双PASS不得实现或调用provider。
