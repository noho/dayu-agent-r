# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Controller Validation

## 1. Gate 与裁决

- Work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- Slice：既有 `R03-S1 — ordinary/awaiting shared request atom + durable replay identity`。
- 输入：accepted plan correction `f5a28f9e`、implementation transition `6e11d916`、
  `docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md` 与当前未提交实现 diff。
- Controller verdict：**REQUIRES_IMPLEMENTATION_FIX**。
- accepted finding：`R03-S1-CV-F01`。
- 本裁决不是新 WU、新 slice 或 plan reopening；不得进入 code review、S2/S3 或 aggregate。

## 2. 第一性原理与 owner 复核

实现动机成立，owner 边界总体正确：ordinary/awaiting 共用 canonical request writer；
`TOOL_AWAITING` 只保存治理字段和真实 request row link；request atom reader 严格校验
storage/shape/digest；accepted-result、resume、Memory、Compact 与 Tool Trace 不再用
missing-request fallback；wait-resolution result identity 由 suspended source `AttemptRow` 唯一拥有，
transition 在写入前校验 `WaitRecord.execution_id == source_attempt.execution_id`。

Controller 直接检查当前 production/test/README diff，未发现 S2/S3、Issue 177/178、统一授权框架、
兼容 reader、下游 normalization 或设计真源之外的生产语义扩张。此前 Controller follow-up 的
governance-only fixture、descriptor 冷热互斥、strict request/result execution equality、
public producer identity 与 direct mismatch 五表 no-mutation 均已落地。

## 3. 独立验证结果

| 验证 | Controller 结果 |
|---|---|
| corrected 9-file matrix | `387 passed` |
| full Host | `1950 passed, 2 skipped, 5 deselected` |
| full per-file coverage matrix | `1934 passed, 2 skipped, 21 deselected`；8 个 production file 为 `86%`–`98%`，`run_transition.py` 为 `93%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| ruff exact changed Python allowlist | PASS |
| `git diff --check` + untracked writer whitespace check | PASS |
| corrected allowlist / S2-S3 no-diff / old-helper deletion scans | PASS |

coverage 插桩矩阵排除 21 个 macOS multiprocessing/spawn 用例；无插桩 full Host 已包含并通过这些
路径，因此这不是产品行为 finding。

## 4. Accepted finding

### R03-S1-CV-F01 — accepted correction 指定的 transition owner suite 未达到单文件门槛

直接执行 accepted plan §6.5 的精确命令：

```bash
source .venv/bin/activate
pytest \
  tests/host/test_resolve_wait_command.py \
  tests/host/test_run_attempt_transitions.py \
  --cov=dayu.host.durable.run_transition \
  --cov-report=term-missing -q
```

得到 `75 passed`，但 `dayu/host/durable/run_transition.py` 只有 `79%`；accepted correction 对该
文件的门槛是 `>=80%`，并明确指定以上 owner test + no-diff transition regression suite 作为
证据。更宽的 full Host coverage 虽然得到 `93%`，但不能替代这条已接受的精确 owner-suite gate。

修复要求：

1. 只在 corrected allowlist 内补最小、业务相关的 durable transition owner test；优先覆盖
   waiting-resolution 写前 NOT_FOUND / no-partial-mutation 等真实 precondition contract，不得增加
   无语义的 coverage-only assertion、mock seam、production branch、`pragma` 或降阈值。
2. 精确命令必须达到 `run_transition.py >=80%`，同时保留 execution mismatch resume/terminal
   `INVALID_STATE` 与五表 no-mutation 证据。
3. 更新 implementation artifact 的 test/coverage/closure ledger，并重跑 corrected 9-file matrix、
   full Host、full per-file coverage、pyright、ruff、diff/allowlist/source scans。
4. 不修改 production、accepted plan、control 以外的 Controller 状态、S2/S3 或 deferred scope；
   若最小 owner test 无法闭合门槛，停止回 Controller。

## 5. 下一入口

下一入口仅为 AgentCodex 在同一 R03-S1 implementation task 内修复 `R03-S1-CV-F01`。修复与
Controller re-validation 通过前，不发送 MiMo/DS code review，不创建 accepted commit。
