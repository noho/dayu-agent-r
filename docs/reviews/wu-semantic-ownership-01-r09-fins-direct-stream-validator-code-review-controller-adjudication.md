# WU-SEMANTIC-OWNERSHIP-01 R09 累积代码审查 Controller 裁决

## 1. 裁决对象

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- umbrella 内部 remediation sub-WU：`R09`
- gate：S1+S2 immutable cumulative code review
- accepted plan / HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`
- 12-path manifest SHA-256：
  `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`
- canonical cumulative binary diff SHA-256：
  `531ac9fa62112c8e9e69051b2bda9185d2f49fbdf8cc621eeaba2084065d85e8`
- implementation artifact：274 lines，SHA-256
  `3c16b65678e234f3f88379c01a371eb3059f5bb52ff68ac1db772a5c135d2d81`
- Controller implementation validation：104 lines，SHA-256
  `190a1e61f165446a3ad9ebccb3de53b1c954df7186076b1405ca2797721ba919`
- AgentMiMo code review：131 lines，SHA-256
  `ee79e2e19b794110becc72133ce1b1627827006c0be75050e45f0e07a9cb5df3`
- AgentDS code review：367 lines，SHA-256
  `0f1a46b3ca17a2c9b69d32f16ce028e0ef29c4f2829c9b47c7d8b6a900825363`

两路 reviewer 在开始与结束均匹配 HEAD、12 个 implementation path 的 content
locks 和 staged-empty。Controller 在两路 artifact 最终修正后再次核对：HEAD 未漂移、
staged 为空、implementation artifact 与 validation artifact hash 未漂移，且
`git diff --check` 通过。

## 2. 总结论

**REQUIRES CODE-REVIEW FIX**。

- accepted 独立 root findings：4；
- 同根 alias：1；
- rejected / no-current-fix observation：1；
- deferred finding：0；
- 设计真源冲突：0。

Fins validator 的 exactly-one-and-last 状态机、typed error、primary/cleanup cause、
raw-close-at-most-once、runtime/Service/CLI concrete signature cutover、PREPROCESS
provenance、CLI presentation、coverage、安全与 deferred/no-touch 边界均通过当前证据。
但 CLI 创建的 stream 在下游 render/log 异常时没有确定性关闭，测试以错误 concrete
`AsyncGenerator` cast 掩盖真实 generator cleanup，且 Fins README 三个 exact
signatures 仍陈旧。R09 不能进入 aggregate deepreview 或 accepted commit。

## 3. Accepted findings

### R09-CR-F01（HIGH）— CLI stream owner 未在所有退出路径关闭 raw source

#### 直接证据

`_run_fins_direct_command_async` 创建 `ValidatedFinsEventStream` 后直接等待
`_wait_for_terminal_handling_sigint`，没有 owner-level close boundary；
`_consume_fins_direct_events` 的 `async for` 循环体会调用同步 log/render，但也没有
`try/finally`。Python 不会为当前普通 `AsyncIterator` 类自动调用其自定义
`aclose()`。

Controller 使用 production `ValidatedFinsEventStream` 和真实 raw async generator
复现：consumer 在首个 progress 后抛出 `RuntimeError`，此时
`closed_after_consumer_error=False`；显式 `await stream.aclose()` 后才变为 `True`。
因此 raw bridge 的 `finally`、producer cancellation request 与 late-publication
fence 不能在下游失败时确定执行。

#### Root owner

- resource acquisition / lifecycle owner：
  `dayu/cli/commands/fins.py::_run_fins_direct_command_async`
- raw close/state owner：
  `dayu/fins/direct_stream.py::ValidatedFinsEventStream`
- raw producer cancellation side effect：
  `dayu/fins/ingestion_runtime.py::_run_direct_stream`

#### 必须修复

1. 在创建 stream 的 CLI owner boundary 对正常、异常、protocol error、外部取消和
   SIGINT/local-exit 的全部路径执行确定性 `aclose()`；不得依赖 GC、async-for
   finalization 或进程退出。
2. 不在 Service、runtime 或 validator 新增 consumer-specific fallback；不改变 public
   protocol/schema。
3. 下游异常已经存在而 close 又失败时，必须保持下游异常为 primary object，并把
   close failure 显式挂为 cause；不得让 cleanup failure 覆盖 root error。无既存
   primary 时才允许 close error 原样传播。
4. 新增真实 CLI owner 测试：log/render 失败后 raw generator 的 `finally` 已执行、
   close 至多一次、producer cancellation/无 late publication 的可观察信号成立，且
   原异常身份/cleanup cause 保持。
5. 正常完成、typed protocol error、business failure/cancel、SIGINT race 与 generic
   producer failure 的既有行为必须无回归。

### R09-CR-F02（MEDIUM）— owner tests 用不真实 cast 绕过 source 类型契约

`tests/fins/test_fins_direct_stream.py::_validated_stream` 把只实现
`AsyncIterator[FinsEvent]` 的 `_ControlledRawStream` cast 成 concrete
`AsyncGenerator[FinsEvent, None]`。该 fake 缺少真实 generator 的
`GeneratorExit`/`finally` 语义，且 `cast()` 使 pyright 无法验证 production
constructor 的 source contract。

必须删除错误 cast seam，使用真正的 `async def ... -> AsyncGenerator[...]` source
和独立 typed observation state。不得放宽 production constructor 为 loose iterator，
不得新增 `hasattr/getattr` 或兼容协议。

### R09-CR-F03（MEDIUM）— 未验证真实 generator close 的 cancellation/finally 因果链

当前 `_ControlledRawStream.aclose()` 只递增计数并可选抛错；它不能证明
`ValidatedFinsEventStream.aclose()` 对真实 `_run_direct_stream` 会注入
`GeneratorExit`、执行 `finally`、请求 operation cancellation 并清理 frame。

修复 R09-CR-F02 时必须增加非算法复制的真实-generator owner/integration tests，覆盖：

- consumer abort 后真实 generator `finally` 执行；
- close success/failure 与 repeated close 的 at-most-once 语义；
- raw bridge close 导致 cancellation request 的因果链；
- 测试不依赖 GC timing、fake-only private state 或错误 concrete cast。

### R09-CR-F04（LOW）— Fins README exact direct signatures 陈旧

`dayu/fins/README.md:192-194` 仍把 `download`、`preprocess`、`upload` 写成
`-> AsyncIterator[FinsEvent]`，而 production 已是 plain `def ->
ValidatedFinsEventStream`。这与同一 README 后文的 current contract、accepted plan
和真实代码矛盾。

必须更新三个 exact signatures，并扫描 Fins/Service/tests README 与当前 R09 scope 内
的代码说明，确保没有把 direct public return type 继续写成旧 loose iterator；不得借机
扩写 deferred lifecycle 或 Issue 175 能力。

## 4. Reviewer finding 裁决

| Reviewer finding | 裁决 | 理由 |
|---|---|---|
| MiMo 01 | ACCEPT -> R09-CR-F01 | Controller production reproduction 证实 consumer error 后 raw source 未关闭。 |
| MiMo 02 | ACCEPT -> R09-CR-F02/F03 | 错误 concrete cast 与真实 generator cleanup 缺口同源但分别需要类型与行为关闭。 |
| MiMo 03 | ACCEPT -> R09-CR-F04 | 三个 README exact signatures 与代码直接矛盾。 |
| DS F01 | ACCEPT -> R09-CR-F01 | 同一 deterministic cleanup root cause。 |
| DS F02 | ACCEPT -> R09-CR-F02 | strict typing 不能由 test-only cast 绕过。 |
| DS F03 | ACCEPT -> R09-CR-F03 | 真实 generator `finally` / cancellation 因果链缺少 owner-level test。 |
| DS F04 | ACCEPT AS ALIAS -> R09-CR-F01 | 与 F01 同一遗漏，只允许一处 owner-level lifecycle 修复。 |
| DS F06 | ACCEPT -> R09-CR-F04 | README 精确返回类型陈旧。 |
| DS 原 F05 / current observation §5.6 | REJECT / NO CURRENT FIX | `terminal_result` 在 clean exhaustion 后可用正是 validator public contract；CLI 读取该 property 不是从内部字段反推。若未来 contract 改变应在 owner gate 同步消费者，当前不加 fallback。 |

MiMo 初始 PASS 使用了错误的 async-for cleanup 前提；同任务证据 follow-up 后已修正为
FAIL/conditional。该过程不削弱其状态机、signature、presentation、安全与 no-deferred
PASS 证据。

## 5. 修复范围与验证门槛

AgentCodex 只修复上述 accepted findings。预期 owner paths 限于：

- `dayu/cli/commands/fins.py`
- `dayu/fins/README.md`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_direct_stream.py`
- 必要时用于真实 raw-bridge cancellation 因果链的
  `tests/fins/test_fins_ingestion_runtime.py`
- README trigger 命中时的 `tests/README.md`

不得修改 validator 状态机、Service pass-through、direct events public contract、
Fins storage/pipeline、R06/R08、design truth、其它 Topic/Issue 或 security controls。

修复后必须完整执行并报告：

1. accepted finding 精确 adversarial tests；
2. R09 affected aggregate、R06、R08、full Fins；
3. 五个 changed production Python files 的逐文件 coverage `>=80.00%`；
4. full pyright zero、changed Python Ruff、`git diff --check`；
5. stale-signature、fallback/compat/`hasattr|getattr`、deferred/no-touch、安全扫描；
6. 三个既有 real SEC/Docling smokes；若环境真源变化必须 STOP，不得伪造 pass。

## 6. 安全与 deferred 边界

- 必须保留 Fins storage containment、symlink 防护、atomic publication、operation
  cancellation、queue backpressure、late-publication fence、typed provenance/citation
  errors 与 R06 batch transaction authority。
- 本修复加强 consumer abort cleanup，不设计统一 tool authorization framework。
- 不实施 Issue 142、151、175、177、178，尤其不把 Issue 175 的 physical process
  isolation 偷带入本轮。
- 不修改 Topic 8/9 no-code decision，不进入 R10-R12。

## 7. Next gate

AgentCodex 执行 `R09-CR-F01..F04` cumulative code-review fix，产生 fix artifact 并完成
新树全量验证；Controller 随后独立锁定新 manifest/diff/content hashes、复核测试/coverage/
smokes，再由 AgentMiMo 与 AgentDS 对完整 S1+S2+fix 累积树并发 complete re-review。
aggregate deepreview、accepted implementation commit、R10-R12 与 umbrella closeout 均未获
授权。
