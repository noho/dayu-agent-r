# Interactive Conversation Memory closure F09：code-review no-op fix audit

## Gate identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Gate：F09 code-review fix。
- 执行者：AgentCodex；本文是提交总控裁决前的独立实现者响应。
- 分支：`codex/interactive-oracle`。
- Implementation base / accepted F08 checkpoint：`47b6a2af`。
- Reviewed implementation：该 checkpoint 之后的 F09 当前未提交 diff。
- Review inputs：AgentMiMo 与 AgentDS 两份独立 F09 code review；结论均为 `PASS`。
- Artifact path：`docs/reviews/wu-interactive-memory-closure-f09-code-review-fix-codex.md`。
- 审计时间：2026-08-04 17:07:57 CST。
- Git 边界：本 gate 未 commit、未 push、未执行远端操作、未修改 resolver/projector/private
  SQLite owner 或 frozen baseline，也未运行五条正式 CLI scenarios。

## 输入完整性

| Durable input | SHA-256 |
|---|---|
| `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md` | `8b891e252788880f550f5c632f9f5a2144bcd2e30b65f53b50c645c891bf488e` |
| `docs/reviews/wu-interactive-memory-closure-f09-implementation-codex.md` | `69973dd4358b756755f800289dfe2d0e4bca70c56d308d78c702e64d8cc14e08` |
| `docs/reviews/wu-interactive-memory-closure-f09-code-review-mimo.md` | `e3e89d97b40ff6a342c40b1c1d6c516d42de678f4b9aaf67db054b5351637cd2` |
| `docs/reviews/wu-interactive-memory-closure-f09-code-review-ds.md` | `6d191661642d744777c131ba16238f7db503bc72b69cb558167f08227ab31acb` |

两份 review 均已完整读取，并与 accepted plan、implementation artifact、当前三文件
production/test diff 及只读 contract owner 交叉核对；本审计没有把两路一致的 `PASS` 本身当作
充分证据。

## 第一性原理与语义 owner 裁决

F09 的原问题真实存在：compactor proposal recorder 已在同一 transaction 中写出 canonical
manifest descriptor，hot payload 也携带该 manifest ref/digest，但 EventLog row descriptor
被 producer 显式写成 `None`。Tool Trace projector 只机械投影 canonical row，formal resolver
再严格比较 row/hot identity，因此 fail closed 是正确行为；根因属于
`DurableCompactorProposalManifestRecorder` 的 canonical manifest / EventLog producer
boundary，不属于 resolver、projector 或 private SQLite consumer。

当前 F09 production diff 在唯一 owner 完成闭环：projection descriptor、manifest body、
manifest descriptor、hot atoms 与 EventLog row 均从同一 transaction 内已写入的 descriptor
派生。没有下游 fallback、loose parsing、兼容 shim、重算或 identity check 放松。两路 review
没有给出可接受的 production、test-contract、stability 或 maintainability finding；因此为了
制造 fix diff 而修改 production/tests，反而会越过 owner boundary 或扩大 accepted F09 scope。

## AgentMiMo review：逐项响应

| Review 证据 | 独立复核与裁决 | 状态 |
|---|---|---|
| M1：EventLog row ref/digest 与 hot manifest identity 同源 | `payload_ref` 使用同一 `manifest_descriptor.payload_ref`；`payload_digest` 与 hot payload 均使用写 descriptor 时校验过的同一 `manifest_digest` | 无 finding / no-op |
| M2：manifest-level projection descriptor 必要且同源 | formal resolver 从 manifest JSON 读取 projection ref/digest；三元组来自同一个 `projection_descriptor`，没有把 manifest descriptor 当作 projection descriptor | 无 finding / no-op |
| M3：row/hot/manifest/projection/resolver identity 链完整 | manifest body 与 digest 各只构造一次；typed parser、hot/manifest identity validator 与 payload resolver继续 fail closed | 无 finding / no-op |
| M4：single success、repair-success、exhaust-fallback 均 formal reconstruct | 三条路径分别覆盖 1、2、全部失败 attempts；每个 call 都核对 EventLog、signal、manifest、projection、attempt 与 response identity | 无 finding / no-op |
| M5：测试不再依赖 private SQLite | helper 只调用 public Tool Trace catch-up、signal read 与 formal resolver；旧 `sqlite_payload_object` 路径已移除 | 无 finding / no-op |
| M6：row/hot mismatch 继续 fail closed | 反例保留严格 `HostDurableError("tool trace row and runner-call hot identity mismatch")`，resolver/projector 未修改 | 无 finding / no-op |
| M7：无 formatter/unrelated diff | 三个 tracked files 的 diff 均映射到 F09 producer 修复或获批测试；未发现 whitespace-only 扩散 | 无 finding / no-op |
| M8：README 与 frozen baseline 判定正确 | 本 slice 不改变稳定 Host contract、测试分层或用户工作流；baseline digest 已重新计算且完全一致 | 无 finding / no-op |
| Findings：无实质问题；Conclusion：`PASS` | 接受；每项均有当前代码、测试或 digest 直接证据 | `fix-pass` |

## AgentDS adversarial review：逐项响应

| DS evidence / attempted falsification | 独立复核与裁决 | 状态 |
|---|---|---|
| AC1：只修 row descriptor 后仍缺 manifest projection artifact | 成立。formal resolver 直接从 manifest JSON 读取 projection ref/digest；缺失时明确报错，producer 必须填充已有字段 | 无 finding / no-op |
| AC2：新增 projection fields 可能是 schema 扩张 | 已证伪；详见下节。字段集合、parser、pair validator、hot/manifest identity validator 都在 F09 前存在且未修改 | 无 finding / no-op |
| AC3：projection digest/size/ref 可能分裂 | 已证伪。三值直接取同一 `projection_descriptor`，写入时校验 payload digest，读取时再验证 descriptor/bytes digest 与 size | 无 finding / no-op |
| AC4：response identity 与 attempt mapping 可能错位 | 已证伪。signals 与 source events 由 event id 关联，`strict=True` zip 保证数量一致，循环序号与两个 canonical attempt 字段分别精确比较 | 无 finding / no-op |
| AC5：prepared inputs 数量可能掩盖漏掉的 attempt | 已证伪。attempt payloads 来自 canonical rejected/accepted events；三条路径同时比较 prepared inputs、signals、resolved calls 和 event attempt fields | 无 finding / no-op |
| AC6：private SQLite 仍可能是通过条件 | 已证伪。当前测试 import/call path 只使用 public formal Tool Trace contract | 无 finding / no-op |
| AC7：row/hot mismatch 可能静默跳过 | 已证伪。负例直接命中 strict equality check 并精确断言 `HostDurableError` | 无 finding / no-op |
| AC8：test helper 或 formatting 可能污染 scope | 已证伪。helpers 均有严格 typed signature、完整中文 docstring 和实际调用；diff 无无关格式化 | 无 finding / no-op |
| 结论：`PASS`，无 blocking finding / `NEEDS_FIX` | 接受；当前证据没有真实缺陷需要修复 | `fix-pass` |

## 为何 projection fields 不是 schema 扩张

F09 新填充的三个字段是：

- `runner_call_projection_artifact_ref`
- `runner_call_projection_artifact_digest`
- `runner_call_projection_artifact_size_bytes`

它们在 F09 前已经由 `dayu/host/_runner_call_manifest.py` 的同一 contract owner 定义：

1. `_RUNNER_CALL_HOT_FIELDS` 已包含三字段，`RunnerCallHotAtoms` 已将其声明为 optional
   ref/digest/size；F09 没有修改 frozen hot field set 或 dataclass。
2. `_RUNNER_CALL_MANIFEST_PROJECTION_FIELDS` 已包含完全相同的三字段；
   `_validate_manifest_fields` 已允许三字段整体缺失或整体出现，并拒绝 partial triple。
3. `_parse_manifest_projection_descriptor` 已把 non-null triple 解析为
   `RunnerCallProjectionDescriptor`，而 `_validate_manifest_hot_identity` 已比较 manifest 与
   hot projection triple。
4. formal resolver 已要求 manifest JSON 提供 projection ref/digest 才能读取独立 runner input
   projection；F09 没有新增 resolver 分支或公共 API。

所以本改动不是新增字段、放宽字段集合或改变 schema version，而是 compactor producer 首次把
既有 optional contract slot 填成同源 non-null descriptor。manifest descriptor 与 projection
descriptor 继续承担不同语义，没有混用。

## Low / informational findings 裁决

### DS finding 9（low）：`_required_json_int` 不校验正值

裁决：`rejected-with-reason`，不是 production 或 test coverage 缺陷，不修改 approved tests。

直接证据：

- `_required_json_int` 的职责是把 `JsonValue` 严格收窄为 `int` 且排除 Python 的 `bool`
  subclass；它是类型解析 helper，不拥有 attempt-number 值域语义。
- 当前仅有两个调用点，分别读取 canonical attempt event 与 resolved manifest 的
  `compaction_attempt_number`；两处都立即执行 `== attempt_number`。
- `attempt_number` 来自 `enumerate(..., start=1)`，因此预期值必定为正整数。实际值为负数、0、
  过大值或错序值都会在同一语句失败，不存在“helper 静默通过后测试仍通过”的反例。
- 为 helper 增加通用正值规则不会新增任何可观察 failure coverage，只会把字段语义塞进通用 JSON
  类型 helper；另加 helper 单元测试也只会重复 Python 类型/比较行为，不验证 production owner。

因此没有真实漏测。若未来该 helper 被用于允许 0 或负数的 JSON integer，强制正值还会产生错误
耦合；若未来出现新的正整数业务字段，应继续由对应调用点/contract owner 断言其具体值域。

### DS finding 10（informational）：diagnostic code 非 enum

裁决：`rejected-with-reason`，不是 F09 finding。`CompactCandidateDiagnosticV2.code` 的当前契约是
非空 `str`；`CompactValidationIssueCodeV2` 属于不同 parser-level 语义 owner。把
`"invalid-current-anchor"` 强塞进无关 enum，或在本 slice 统一 diagnostic namespace，都会造成
contract/schema 扩张与 goal drift。

### DS finding 11（verified）：Tool Trace catch-up 幂等

裁决：positive confirmation，无修复。helper 在每个独立测试 store 中调用 catch-up；projection
checkpoint 只消费新 events，不会制造重复 signals。

## No-op fix decision

本 gate 接受的 code-review finding 数为 0。没有 production finding、真实 test coverage gap、
docs finding、blocking open question 或 `needs-more-evidence` finding。最终 decision 是 no-op code
fix：

- 不修改 `dayu/host/compaction_operation.py`；
- 不修改 `tests/host/test_dispatch_scheduler.py` 或 `tests/host/test_tool_trace_queries.py`；
- 不修改 resolver、projector、private SQLite helper 或 frozen baseline；
- 不增加 schema、enum、兼容路径、通用正整数 helper 或重复 helper tests；
- 只新增本 durable fix audit artifact。

写 artifact 前，三个 production/test 文件当前 diff 的 SHA-256 指纹为
`cc49580c26c8fea3b8fb64532727056d435e0123c3e72a7e13ed05d4d9f926cd`；写入后复核必须保持一致。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

最小 F09 focused tests：

```text
pytest -q \
  tests/host/test_dispatch_scheduler.py::test_multi_turn_proactive_compact_feeds_subsequent_run_input \
  tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept \
  tests/host/test_dispatch_scheduler.py::test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback \
  tests/host/test_tool_trace_queries.py::test_runner_call_query_rejects_event_row_and_hot_manifest_identity_mismatch
```

结果：`4 passed in 0.46s`。四项分别覆盖 single success、invalid → repair → success、invalid
attempts 耗尽后 fallback，以及 row/hot identity mismatch fail closed；这是 accepted F09 test
matrix 的最小行为集合，没有运行正式 scenarios。

静态与边界验证：

- `python -m pyright dayu/host/compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_tool_trace_queries.py`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 三个 production/test 文件 diff 指纹：
  `cc49580c26c8fea3b8fb64532727056d435e0123c3e72a7e13ed05d4d9f926cd`。
- 未运行 full pytest、coverage 或正式 CLI scenarios；implementation 与两路 review 已有 focused +
  owner coverage/full pyright 证据，本 no-op gate 只重跑最小 accepted behavior set。

## Baseline digest 复核

### Frozen baseline

| 文件 | Accepted digest | 本 gate 重算 | 结果 |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` | 同左 | 未改变 |
| `docs/cli_ci_scenarios.json` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` | 同左 | 未改变 |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` | 同左 | 未改变 |

### Frozen evidence

| 文件 | SHA-256 | 结果 |
|---|---|---|
| `workspace/tmp/interactive-memory-observed-behavior.md` | `ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263` | 未改变 |
| `workspace/tmp/interactive-memory-report-freeze.json` | `7ba64926a22406f086a417ee269313a3b07dbc05b480463ff535007f72198f5b` | 未改变 |

## Docs decision

本 gate 只新增用户明确要求的 durable review artifact。没有修改 `dayu/host/README.md`、
`tests/README.md`、根 `README.md` 或设计文档：fix gate 没有新增生产行为、公共 contract、测试
分层、用户工作流或架构边界。

## Residual risks 与 uncovered areas

| Risk / uncovered area | Classification | Owner / destination |
|---|---|---|
| 真实 provider/model/response identity 的跨进程证据 | covered by later approved evidence stage | 后续 `interactive.g06.tool-trace-formal` readiness stage |
| 历史 null row descriptor 数据 | accepted non-goal / fresh current contract | 本 work unit 明确不做兼容读取或 migration |
| 五条正式 CLI scenarios 未在本 gate 运行 | covered by later approved evidence stage | 正式 readiness/evidence gate；本 gate 明确禁止运行 |
| no-op gate 未重复 full pytest/coverage | 已由 implementation 与两路 review 覆盖；当前 gate 无 production/test 新 diff | F09 accepted review chain；若 re-review 发现证据失效再重开 fix |

没有未分类 residual risk，没有 deferred production finding，没有 blocking open question。

## Completion status

- Fix gate conclusion：`fix-pass`。
- Finding 状态：两路 review 均为 `PASS`；accepted findings = 0；DS low 与 informational 均已
  `rejected-with-reason`；verified catch-up observation 为 positive confirmation。
- Changed files in this fix gate：仅本 durable artifact；production/tests 无新 diff。
- Next Gateflow entry point：F09 code-review re-review / controller adjudication。
- 本执行者不 commit、不 push、不修改 F10，也不运行正式 scenarios。
