# WU-SEMANTIC-OWNERSHIP-01 R07 complete-tree code-review Controller adjudication

## 1. Gate 与结论

- Review scope：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的累计 R07-S1+S2+S3 final tree；不是新 WU。
- AgentMiMo artifact：`docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-mimo.md`。
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-ds.md`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-r07-s3-controller-validation.md`。
- HEAD / transition base：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- accepted plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。

结论：**FIX REQUIRED / 3 accepted finding groups / 0 blocker**。

AgentDS 返回三项 material findings。AgentMiMo 初版 PASS 遗漏了 Controller 已提供的确定并发反例，并误写 process close error 会追加 note；Controller 要求同一 reviewer 就地纠正后，MiMo 最终也返回 `FIX REQUIRED / 3 findings / 0 blocker`。MiMo 修订版对第一项的具体 root cause 仍判错，因此本 artifact 只接受其最终 gate 结论，不接受错误根因；正确 owner fix 以下述 Controller 裁决为准。

## 2. Accepted findings

### R07-CR-F01 [HIGH] processor build 可在 runtime close 返回后发布 live cache entry

**来源**：AgentDS F-DS-01；Controller 独立发现与真实复现。AgentMiMo 最终的 cleanup concern 合并到本组，但其 `_close_retired_entry` 失败后无条件 discard 的说法被拒绝。

**直接证据**：Controller 使用现有 `tests/fins/test_processor_read_consistency.py` `_build_runtime`、真实 filesystem、`registry.before_return` 与 `threading.Event`（无 sleep）固定以下 interleaving：

```text
T1: _borrow_processor -> with creation lock -> _ensure_open() passes
T1: processor registry build blocks at existing before_return observation seam
T2: runtime.close() -> _closed=True -> cache.clear() -> returns
T1: build resumes -> created.try_acquire_borrow() -> cache.put(created) -> call completes
```

结果：

```text
cache_at_close=0
cache_after_join=1
result_count=1
errors=[]
roots_exist=[True]
```

这是 accepted plan §5.5/§7.3/§8.4 所禁止的 post-close live publication 与 temp-root leak。`_CachedProcessor` 自身状态机正确，但 `_ensure_open` 与 cache publication 不是对 `close()` 原子的。

**必须修复的 owner boundary**：

- 在 read-runtime lifecycle owner 内使 “closed check + cache publication” 与 `close()` 的 “set closed + clear” 具备确定顺序；不得持 publication guard 构建 processor，也不得靠下游调用者补偿。
- 若 close 已先发生，当前 build 必须以既有 close-state `RuntimeError` 结束，并完整 release/retire 已取得 borrow、created entry 与 full snapshot；不得在 cache 留 live/retired artifact。
- 若 publication 先发生，close 必须能 clear/retire 该 entry；当前 active borrow 可按既有 contract 完成，最后 release 删除 snapshot。
- 不新增 production test seam、sleep、fallback 或新公共状态机。

**测试要求**：把上述真实 Event/Barrier interleaving 固化为 owner test，断言 close 返回后的最终 cache 为空、thread 不悬挂、close-state结果明确、所有 full snapshot roots 已删除；再覆盖 publication-before-close 的 active-borrow 合法顺序，避免修复把正常 borrow 提前关闭。

### R07-CR-F02 [MEDIUM] per-document creation-lock registry 无界增长

**来源**：AgentDS F-DS-02、AgentMiMo MIMO-CR-F02、Controller 独立复现。

**直接证据**：对同一长生命周期 runtime 顺序调用 64 个不同 missing `document_id` 后：

```text
cache_size=0
creation_lock_count=64
```

`_get_creation_lock` 在 source snapshot read 之前为任意 key 创建永久 dict entry；不存在文档也会使表增长。它绕过 `processor_cache_max_entries`，与 accepted plan 的 long-lived bounded/resource-aware runtime 直接矛盾。MiMo 初版“每个 lock 小，因此 10,000 个也可忽略”的 no-action 理由不成立：输入空间无产品上限，且 `WeakValueDictionary` 或等价 owner-scoped lease 可以用小改动保持同-document serialization。

**必须修复的 owner boundary**：

- creation lock 必须仍保证重叠的同一 `ProcessorCacheKey` build 取得同一个强引用 lock；不同 key 不应被无必要地全局串行化。
- 不活跃、无 caller 强引用的 key 不得永久留在 runtime registry。优先使用最小 weak-value 或等价引用生命周期；不得用 `locked()` 猜测 waiter、定时 sweep、魔法阈值或 cache eviction 下游补偿。
- missing-ID 调用和超过 cache 容量的真实 document 访问均应保持 lock registry bounded/reclaimable。

**测试要求**：无 sleep 地证明两个重叠 same-key caller 共用一个 lock并只发布一个 processor；大量 sequential missing keys 与超过 cache 容量的 sequential valid keys 在调用结束/必要 GC 后不保留线性 lock 表，同时 cache contract不变。

### R07-CR-F03 [LOW] process target 在已有 primary failure 时吞掉 close failure 并丢失公开 retry authority

**来源**：AgentDS F-DS-03、AgentMiMo MIMO-CR-F03；Controller 修正两份 artifact 的不精确部分后接受。

**直接代码证据**：`_FinsReadProcessTarget.__call__` 的 `finally` 只调用一次 `runtime.close()`。当该调用抛异常且 `primary_failed=True` 时，分支不 log、不加安全诊断、不再次调用幂等 public close；原 outcome 保留，但 `FinsReadRuntime` 内 pending snapshot/retired entry 的 retry authority 随短命子进程退出而消失。

普通 `tempfile.mkdtemp` 目录不会因 Python 子进程退出自动删除；AgentDS 关于 OS 会最终回收的表述被拒绝。只增加日志也不能关闭本 finding，因为根因是 public retry authority 未被 composition owner 消费。

**必须修复的 owner boundary**：

- 继续保持原业务/执行 primary outcome，不得让 cleanup secondary 覆盖它。
- process target 只能通过 `DefaultFinsRuntime.close()` 公共幂等 owner contract 消费 retry authority，不得访问 `_read_runtime`、`_pending_snapshots` 或其它 private state。
- 首次 close 失败后，必须执行一次结构化 follow-up close 来消费已经登记的 pending cleanup；这不是 product retry policy，也不得形成可配置/无限 loop。
- 若 follow-up 仍失败，保留原 primary outcome，并只记录不含 raw message/path/key/revision/cause/traceback 的稳定 action/type/errno diagnostic。成功业务路径继续保持既有“cleanup failure -> execution_error”投影，不新增 envelope/schema 字段。

**测试要求**：

- owner-level test 证明 snapshot cleanup 首次失败、public close follow-up 成功时 temp root 最终删除且 pending authority 清空；
- process-target completed、typed/business failed、unexpected execution failed 三路均覆盖 transient close failure，证明 follow-up public close 被调用、原有 outcome priority 不漂移；
- follow-up 仍失败时只留下 path-free diagnostic，不泄漏 locator/error message；不增加 cancellation envelope 或 Host/process-isolation scope。

## 3. Rejected、deduplicated 与 no-action observations

- **拒绝 MiMo MIMO-CR-F01 的具体根因**：`_close_retired_entry` 并非在 close failure 后无条件 discard。异常分支在 `finish_close(succeeded=False)` 后 return/raise，只有成功路径才 discard；现有 retry test已证明该 owner contract。Controller 复现的 root cause 是 build publish 与 runtime close 的 race，已由 `R07-CR-F01` 精确承接。
- **拒绝 MiMo 初版 PASS / ready-commit 结论**：与确定复现冲突，已被同一 artifact 的最终 `FIX REQUIRED` 覆盖。
- **拒绝 DS F-DS-03 的 “OS 回收 ordinary temp tree” 与 log-only fix**：均不能满足 cleanup owner contract；正确 fix 见 `R07-CR-F03`。
- **DS OBS-DS-01/02/05/06/07/08**：接受为 no-action 设计确认或 inherited ledger；不形成当前 finding。
- **DS OBS-DS-03**：evidence-invalid。`_get_cached_processor_borrow_for_diagnosis` 已捕获 light snapshot read/compare/close failure并返回 `None`，不会按该 observation 所述直接替换原始参数错误。
- **DS OBS-DS-04**：`Exception` vs `BaseException` 不单独立项；R07 cleanup 的生产异常属于 `Exception`，Host cancellation 由父进程治理。不得借 F03 扩大为捕获 `SystemExit`/`KeyboardInterrupt`。
- **MiMo OBS-2 / DS 对 list/alias/cross-document 的其余观察**：accepted plan 已明确 bounded cached diagnosis、typed list/meta projection 和 alias 0/1/2边界；无新增 action。
- 两路 reviewer 对 opaque identity、stable snapshot、static corruption、same-snapshot processor/meta/provenance/citation/result、containment/symlink/atomic/recovery、LLM non-leak、no compatibility、no R08+/deferred Issue/unified authorization 越界的 PASS 结论均接受。

## 4. Final ledger 与 handoff

| Finding | Severity | Status |
|---|---:|---|
| `R07-CR-F01` post-close processor publication/temp leak | HIGH | ACCEPTED / OPEN |
| `R07-CR-F02` unbounded creation-lock registry | MEDIUM | ACCEPTED / OPEN |
| `R07-CR-F03` process-target cleanup retry authority lost | LOW | ACCEPTED / OPEN |

最终 ledger：`3 accepted open / 0 deferred / 0 blocker`。

下一 gate 是 AgentCodex 在当前 S3 allowlist 内修复全部三组 finding、补 owner-level tests并更新一个 fix artifact。Controller 完整复核后，AgentMiMo 与 AgentDS 必须并发 re-review 完整累计 S1+S2+S3 final tree；任何 accepted finding 未关闭前不得创建 R07 accepted implementation commit、进入 R08 或实现 deferred scope。
