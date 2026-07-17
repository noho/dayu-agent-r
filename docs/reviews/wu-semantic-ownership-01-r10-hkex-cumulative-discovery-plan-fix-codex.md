# WU-SEMANTIC-OWNERSHIP-01 / R10 plan-review fix — AgentCodex

## 1. Gate、scope 与结论

- work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` 内部 R10；不是新 WU、issue 或 feature。
- work type：Controller adjudication 后的 plan-review fix；只修 plan/artifact，不做 implementation。
- timestamp：`2026-07-17T18:20:22+0800`，来自本机系统时钟。
- fixed target：`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`。
- fixed target lock：698 lines；SHA-256
  `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a`。
- verdict：`R10-PR-F01`、`R10-PR-F03` 已在 plan owner boundary 完整闭合；`R10-PR-F02` 维持
  `REJECTED-WITH-REASON` 且零 waiver。
- stop state：`READY_FOR_CONTROLLER_VALIDATION`。

本 artifact 采用用户指定的固定输出路径；未使用 `planreview` 默认 timestamp 文件名。用户的 exact-path 要求优先，
但审计 timestamp 仍按 skill 要求从系统时钟生成。

## 2. Immutable source locks

以下输入均在修改前完整读取并锁定：

| Source | Lines | SHA-256 | Result |
|---|---:|---|---|
| `AGENTS.md` | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | exact |
| R10 pre-fix plan | 605 | `5f8b1d3880fc5cf3fac370117edea441ffc1fc1c05574844fd0c0814e30db699` | exact |
| AgentMiMo review | 166 | `048c8e5998f6a9868fbc41b89127b26fec987a248d9a8aa89955b94d0634fe16` | exact |
| AgentDS review | 338 | `7bad9a391f19571724d3452c93797acc042c7e44ecedfb7f20c2e38697a956ce` | exact |
| Controller adjudication | 106 | `3659ef62964b195cda60d4c4d5e961214594076e75fc0a52adcda4f076493f4f` | exact |

baseline HEAD 仍为 `1c2585275f4134d8456a3fda2d84464e4e52c9d7`。pre-fix plan 的 SHA 是本次 fix
审计输入；fixed plan 已替换同一路径，因此不把旧 SHA 伪装成当前文件锁。

## 3. 第一性原理与 owner 裁决

动机成立，且两个 finding 都是 code-generation-readiness 缺口：

1. raw `Callable[[], bool]` 若跨进 provider，HKEX/CNInfo 就必须各自解释 bool、typed cancel 与 checker failure，
   造成多个 cancellation owner，或迫使 downloader 反向依赖/复制 workflow-private helper。
2. CNInfo 一次 discovery 按 fiscal period 发多个真实 POST；“方法前后”不能关闭 period 间的长取消窗口，也不能
   唯一生成实现。

最小正确边界是：workflow 用既有 `_raise_if_cancelled` 语义把 raw checker 绑定成 no-arg
`Callable[[], None] | None`；protocol 只运输；HKEX/CNInfo 只在各自真实 semantic request 前/成功响应后调用。
HKEX provider protocol/completeness owner 不变，CNInfo 也不获得 pagination 状态机。

## 4. Finding closure matrix

| Finding | Root cause | Fixed plan closure | Verification contract | Status |
|---|---|---|---|---|
| `R10-PR-F01` | raw bool checker 被运输到 provider，取消解释 owner 分裂；HKEX generic `RuntimeError` wrapper 可抹平 typed control flow | §1、§3.2、§4.1-4.2、§5.3、§6.2-6.3、§7、§8、§10、§14-15 全部改为 workflow-owned `cancellation_checkpoint: Callable[[], None] | None`；workflow 用 `functools.partial(_raise_if_cancelled, ...)` 构造；protocol/provider 不解释 bool；HKEX `CnDownloadCancelledError` 与 `HkexnewsProviderProtocolError` 均在 generic wrapper 前 passthrough | 正常返回、bool true mapping、caller typed cancel object identity、non-cancel direct/full cause chain、HKEX exception precedence、partial rows/candidates/HEAD zero-publication | **CLOSED** |
| `R10-PR-F03` | CNInfo “既有 discovery I/O 前后”可被解释为整个方法前后，未唯一指定多 period POST 粒度 | §3.2、§4.1-4.2、§6.3、§7、§8、§10、§14-15 明确 HKEX 每个 cumulative GET、CNInfo 每个 supported fiscal-period POST 前/成功响应后各调用一次同一 checkpoint；保留 workflow 原有 discovery 前后检查 | exact ordered traces：HKEX `CP1, GET(100), CP2, ...`；CNInfo `CP1, POST(p1), CP2, CP3, POST(p2), CP4`；任一 response 后取消均不发下一 provider request、无 partial publication | **CLOSED** |

## 5. Exception precedence 与 test closure

fixed plan 明确要求：

```text
except CnDownloadCancelledError:
    raise
except HkexnewsProviderProtocolError:
    raise
except RuntimeError as exc:
    existing generic provider-context wrapper
```

- caller 主动抛出的 `CnDownloadCancelledError` 必须保持同一对象 identity。
- `HkexnewsProviderProtocolError` 必须保持 type/cause。
- raw checker 的非取消异常只由 workflow 既有语义包装；workflow seam 断言 direct cause，若 HKEX generic wrapper
  再加 provider context，则断言完整两层 cause chain。
- checkpoint 正常返回表示继续；provider 不读取返回值，不出现 `if checkpoint()`，不复制
  `_is_cancel_requested` / `_raise_if_cancelled`，不按异常消息字符串分支。
- HKEX response 后取消发生在 strict parse 前；CNInfo response 后取消发生在保存 period rows/selection 前；两路都
  断言无下一 request、无 partial candidates、无 HEAD。

## 6. F02 zero-waiver 与 forbidden-scope closure

`R10-PR-F02` 保持 Controller 的 `REJECTED-WITH-REASON`：

```text
dayu/fins/pipelines/cn_download_protocols.py  Stmts 40  Miss 0  Branch 0  Cover 100%
```

- 四个 modified production files 仍逐文件 `>=80%`。
- 不增加 N/A waiver、omit、pragma、test-only padding 或 coverage 兼容分支。
- 未加入 speculative range watchdog/warning/阈值、hard cap、日期 recursion、generic pagination、compatibility、
  deferred issue、R11/R12。

## 7. Plan-only diff

相对 605-line locked pre-fix plan，本轮 fixed plan 为 698 lines，净增 93 行。语义 diff 仅包含：

1. gate/authority/source-lock 记录与 `READY_FOR_CONTROLLER_VALIDATION` handoff；
2. owner map 从 raw bool transport 改为 workflow interpretation + no-arg checkpoint + protocol-only transport；
3. exact allowlist 描述与 protocol signature；
4. HKEX/CNInfo request-boundary state machine 与 exception precedence；
5. exact request sequence、identity、cause、partial-no-publication test matrix；
6. validation/coverage/source scan、completion report 与 completeness checklist。

本轮文件变更集合严格为：

- 修改 `docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`；
- 新增本 fix artifact。

未修改 control、MiMo/DS/Controller artifacts、代码、测试、README、design；未 stage、commit、push、创建 PR、
implementation 或进入 R11/R12。工作树中 Controller 自有 control 修改与既有未跟踪 review/validation artifacts 均为
本轮开始前已存在，已保留且未触碰。

## 8. Validation 与 gate state

- plan source lock：698 lines；SHA-256
  `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a`。
- `git diff --cached --name-only`：empty。
- `git diff --check`：PASS，stdout empty。
- tests / pyright / coverage：未运行；这是明确禁止代码/测试修改的 plan-only fix，运行 implementation gates 不会验证
  Markdown contract，且可能制造不必要的 workspace artifacts。
- README：未触发修改；本轮只修 plan/review artifact，不改变当前用户能力或已实现架构。
- residual risk：fixed plan 尚未由 Controller validation 与 AgentMiMo/AgentDS 双路 fixed-plan re-review 独立验证；
  这是下一 gate，不在本轮授权内。

最终状态：`READY_FOR_CONTROLLER_VALIDATION`。
