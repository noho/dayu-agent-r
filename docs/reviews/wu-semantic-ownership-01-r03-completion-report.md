# WU-SEMANTIC-OWNERSHIP-01 R03 Completion Report

## 1. Identity 与结论

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation sub-WU：R03 accepted-call evidence / LLM projection ownership。
- accepted plan commit：`8c6ae966`。
- accepted slice commits：S1=`3e48f09e`、S2=`4b4696e5`、S3=`3f777753`。
- aggregate accepted local commit：`f7006a80`（`gateflow: accept R03 aggregate projection closure`）。
- completion verdict：`R03 COMPLETE / UMBRELLA INCOMPLETE / ENTER R04 PLAN`。

R03 已完成独立 plan、双路 plan review/fix/re-review、三个 implementation slices、每 slice 双路 code review/fix/re-review、aggregate validation、真实 public smoke、双路 aggregate deepreview、zero-change fix、双路 complete re-review 与 accepted local commit。R03 不创建新 WU，也不关闭 umbrella。

## 2. 已关闭的产品语义

- ordinary 与 awaiting accepted tool call 复用唯一 canonical request atom writer；exact arguments/digest/identity 在 Host accepted boundary 同源。
- `TOOL_AWAITING` 只保存 governance metadata 与 strict request event link，不复制 accepted arguments 或 digest。
- wait-resolution result 使用 suspended source Attempt 的 attempt/execution identity，identity mismatch 在 durable mutation 前 fail closed。
- 删除 Host 下游 safe-arguments/normalized repair 与字段名 blacklist；内部 canonicalization 只服务 digest、幂等、audit、replay。
- shared accepted-result projection 是 result material、query、producer citation 与业务来源状态的唯一真源。
- RunInput、Durable Memory、Memory、Compact、LLM-ready Tool Trace 从同一 typed material 投影；缺 material 统一 fail closed。
- opaque/misspelled/internal refs 只保留 internal provenance/audit，不进入 LLM-readable business source。
- R03 aggregate findings `R03-AGG-CV-F01..F03` 已分别在 Compact exact renderer、hot/cold shared projection、typed canonical-fact smoke selection owner关闭。

## 3. 验证证据

- exact affected matrix：`933 passed, 2 skipped, 3 warnings`。
- complete Host frozen coverage matrix：`1962 passed, 1 skipped, 21 deselected`；changed production files均达到单文件 `>=80%`，范围为 80%-100%。
- full six-domain regression：`4235 passed, 3 skipped, 5 deselected, 2 failed, 3 warnings`；两项失败在 fresh process共同隔离为 `2 passed`，直接 owner 为既有 Web smoke global logging-state污染，不经过 R03 changed owner。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff、`git diff --check`、deleted-source/propagation/sentinel scans：PASS。
- Agent fresh hard-gate smoke 与 Controller independent fresh smoke 均完成 Doc、Web、Fins awaiting/list/read、observation 六轮，并得到 `requests=5 accepted_results=5 explicit_citations=1`。
- aggregate re-review：MiMo/DS 均 `PASS / 0 accepted findings / 0 blocking questions`。

## 4. Findings 状态

- R03 plan/code-review/fix/re-review findings：全部关闭。
- aggregate validation findings F01-F03：全部关闭。
- aggregate deepreview/re-review accepted findings：`0`。
- blocking open questions：`0`。
- 没有 accepted finding 留作后续优化。

## 5. 安全与 deferred 边界

R03 保留 DNS/peer、path containment、symlink、resource budget、atomic/process fencing、Host durable integrity 与 internal provenance。没有删除 allowed paths 或 Web/Fins 防御机制，没有引入统一 tool authorization framework、permission schema、BusinessSource abstraction、credential broker、compatibility shim 或旧 schema 兼容。

Issue 142、151、175、177、178 仍由原 owner 承接；R03 没有偷带 migration、assets/write、Docling isolation、Doc continuation wiring 或 Web storage-state lifecycle。

## 6. Residual owner / destination

| residual | owner / destination |
|---|---|
| Web smoke global logging-state顺序污染 | `utils/smoke_web_ci.py` / Web smoke test-harness owner；若 umbrella 最终 aggregate regression仍复现，进入最终 aggregate finding ledger并必须关闭。 |
| macOS coverage + NumPy/Pandas spawn instrumentation | validation harness/environment owner；未来 process-boundary 改动以 plain spawned-process tests取证。 |
| waiting helper DI/style 与 wait expiry文案 observations | Host waiting owner；当前分别为 `STYLE_OBSERVATION / NO_FIX`、`OWNER-CORRECT / NO_FIX`。 |
| future cold wait-result hypothetical | Host wait-result schema + RunInput/shared projection owner；只有 owner schema真正改变时重新验证。 |

## 7. 下一入口

下一 internal remediation sub-WU 是 R04 Awaiting provider resolution config 与 Host composition。R04 以前一 accepted code commit `f7006a80` 为代码基线，并按 umbrella plan §7.3/§11 重新核对真实文件、test nodes、slice 原子性、propagation/source/security scans，生成独立 code-generation-ready plan；umbrella baseline不能替代 R04 plan。

R04 不得实施 R05 observation-timeout 状态机、Issue 175 process isolation、统一 authorization、callback transport本体或其它 deferred owner能力。
