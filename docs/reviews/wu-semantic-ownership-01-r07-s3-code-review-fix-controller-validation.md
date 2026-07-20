# WU-SEMANTIC-OWNERSHIP-01 R07 complete-tree code-review fix Controller validation

## 1. Gate 与结论

- Active WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Internal remediation sub-WU：R07；checkpoint：累计 S1+S2+S3 complete-tree code-review fix。
- Accepted findings：`R07-CR-F01..03`。
- Controller finding 真源：`docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-controller-adjudication.md`，SHA-256 `f23602bd165a2ea11f028e6fc0a68fa0fcea07dbe0ecc02dce3f87256cc98673`。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-codex.md`，SHA-256 `ef0fe4fbc1c773962843b17a9288688e74d4b602ce9bf7e9819fe306abd98040`。
- Accepted plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`；HEAD 仍为独立 implementation transition `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- 结论：**PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_S1+S2+S3_CODE_RE-REVIEW**。
- 本结论只授权双路完整累积 re-review；不授权 R07 commit、R08-R12、deferred Issues、统一 authorization、push 或 PR。

## 2. Owner 与实现复核

### 2.1 `R07-CR-F01`：close / cache publication 线性化

Controller 逐段复核 `_borrow_processor(...)` 与 `close()`：

- processor 和 full snapshot 的长构建不持 lifecycle lock；只在最终 `_ensure_open()` 与 cache `put(...)` 时持有 `_lifecycle_lock`，没有扩大 storage publication guard 或构建临界区；
- close 先取得同一 owner lock时，build 在最终 closed-check 以既有关闭态 `RuntimeError` 结束，未向 cache 发布 entry，unowned snapshot 被删除；
- publication 先取得 owner lock时，close 随后 clear/retire entry，已接受的 active borrow 可继续完成，最后释放 snapshot；
- 没有按 MiMo 的错误根因修改 `_close_retired_entry`，既有 failed-cleanup retry authority 保持不变。

Controller validation 初读发现 Agent artifact 声称 close-first test 断言 cache/retired/pending 全空，但两条 lifecycle 集合断言误落在相邻 cancellation test。Controller 将该证据缺口退回同一 AgentCodex fix 任务；最终树只在准确的 close-first owner test 增加 `_retired_entries == set()` 与 `_pending_snapshots == []`，artifact 描述与测试事实重新一致。

### 2.2 `R07-CR-F02`：creation-lock registry 生命周期

- `_creation_locks` 改为严格类型 `WeakValueDictionary[ProcessorCacheKey, Lock]`；registry guard 仍唯一拥有 get/create 竞争。
- 每个 caller 在进入和持有 document creation lock期间保留局部强引用；重叠 same-key callers 因此共享同一 lock 与唯一构建。
- callers 离开后 registry 不再永久拥有历史 key；missing IDs 与被 cache 淘汰的 valid IDs 都不导致线性滞留。
- 没有 `locked()` waiter 猜测、sweep、magic threshold、striped global lock 或 cache consumer 补偿。

### 2.3 `R07-CR-F03`：process-target public cleanup retry authority

- 首次 `DefaultFinsRuntime.close()` 失败后只执行一次同一 public idempotent `close()` follow-up；helper 不访问 read runtime、retired entries、pending snapshots 或 storage private state。
- completed 首次 cleanup failure 仍投影 `execution_error`；typed business primary 与 unexpected primary outcome 均不被 secondary cleanup failure覆盖。
- follow-up 再失败只记录固定 `action`、exception `type` 与 `errno`；不记录 raw message、path、key、revision、cause 或 traceback。
- 真实 `FinsReadRuntime` pending snapshot cleanup 由第二次 public close删除 temp root；第三次 close保持幂等。
- 没有新增 envelope/schema/cancel 语义，也没有进入可配置或无限 retry policy。

## 3. Controller 独立验证

### 3.1 七个 exact owner nodes

Controller 在最终树独立运行七个 owner nodes，覆盖：

- same-key 并发唯一 lock / 唯一 build；
- close-first 拒绝事后 publication并清空 cache/retired/pending/temp root；
- missing 与超 cache 容量 valid key 的 lock registry 回收；
- publication-first active borrow在 close后合法完成；
- completed、typed business failed、unexpected failed 的首次 close failure / public follow-up / outcome priority；
- persistent follow-up failure 的 path-free diagnostic；
- 真实 snapshot cleanup 由第二次 public close重试成功。

最终结果：

```text
7 passed, 3 warnings in 1.11s
```

三条 warning 均为既有 `edgar` deprecated imports。测试使用真实 filesystem 与 `threading.Event` 协调；没有 sleep correctness oracle或 production test seam。

### 3.2 累计验证

AgentCodex 在最终生产树上完成并记录：

- 八个累计 test files：`494 passed, 3 warnings in 27.19s`；
- 20 个 R07 changed production owners逐文件 line coverage 全部 `>=80%`，范围 `80.00%`–`100.00%`；直接相关 `read_runtime.py=82.56%`、`fins_tools.py=85.80%`；
- formal directory full suite：`4883 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings`；三项 failure 与 accepted inherited ledger 的 node/type/location/text 精确一致，没有新增 failure。

Controller 独立静态验证：

- full `pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`；
- 本 fix 四文件 scoped Ruff：`All checks passed!`；Agent累计 20 production + 8 tests scoped Ruff同样通过；
- full Ruff 保持既有 `150` 项，未新增或扩散；
- `git diff --check`：通过；staged paths为空；
- accepted plan、Controller adjudication与 Agent fix artifact hashes匹配；
- 本 fix 没有新增 sleep、private runtime cleanup访问、旧 source revision grammar、filing-first source-kind probe、兼容/fallback 或 deferred scope。

## 4. Finding、风险与 next gate

| Finding | Severity | Controller status | Final evidence |
|---|---:|---|---|
| `R07-CR-F01` post-close publication/temp leak | HIGH | **implemented closed** | shared lifecycle linearization + close-first / publication-first exact owner tests |
| `R07-CR-F02` unbounded creation-lock registry | MEDIUM | **implemented closed** | weak-value owner lifecycle + same-key identity/build + missing/over-capacity reclamation tests |
| `R07-CR-F03` lost process cleanup retry authority | LOW | **implemented closed** | one public follow-up close + three outcome priorities + path-free persistent diagnostic + real cleanup retry |

最终 Controller fix ledger：`3 implemented closed / 0 open / 0 deferred / 0 blocker`。

连续两次 filesystem cleanup 都失败时，process target 按已裁决 bounded contract保留 primary outcome并记录 path-free diagnostic；这不是 open finding，也不授权第三次/无限/configurable retry。formal suite三项 inherited failure和 full Ruff 150项保留既有 owner/destination，不属于 R07。

下一 gate 是 AgentMiMo / AgentDS 并发完整累计 S1+S2+S3 code re-review。两路必须同时覆盖最终 complete tree、`R07-CR-F01..03` 的 root-cause closure、全部既有 S1/S2/S3 finding保持关闭、security / opaque identity / snapshot / citation / LLM non-leak组合行为，以及 deferred-scope边界。任何 accepted finding 都必须回到 AgentCodex fix、Controller validation和双路 re-review；不能留作后续优化。
