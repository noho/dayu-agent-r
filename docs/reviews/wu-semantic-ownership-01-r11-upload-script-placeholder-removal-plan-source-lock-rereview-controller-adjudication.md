# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan source-lock re-review Controller adjudication

## 1. Gate 与 reviewed target

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- gate：dual complete final-plan re-review Controller adjudication。
- reviewed target：886 lines / 74,571 bytes / SHA-256
  `59156239ff4d73bfeaa1cb78a593c2b75504804102a07e851b1239803a4de51f`。
- AgentMiMo artifact：236 lines / 15,062 bytes / SHA-256
  `973775da67b11190e70a3c6f108d7605d9993786617f078ecc1e63493c1a5a00`。
- AgentDS artifact：508 lines / 27,710 bytes / SHA-256
  `f9eedd8e6277d57ce03f9e0406227cd2197e042696d481415a7ce041071ba972`。
- Controller 完整读取两份 artifact，并独立重测完整 §2.2 source-lock table 的当前/accepted-plan/R10 baseline
  输入，而不是只依赖 reviewer finding label。
- 本裁决不授权 implementation、stage、commit、push、PR 或 R12。

## 2. Findings that remain closed

两路一致证明，Controller 接受：

| Finding | Status |
|---|---|
| `R11-IMP-BF01` | CLOSED；精确两个 slices，无 producer-only gate truth |
| `R11-PR-BF-RR-F01` | CLOSED；sequential edit 与 transient gate truth/safety stop 边界完整 |
| `R11-PR-BF-FR-DS-F01` | CLOSED；`requirements.txt` full SHA 三路一致，旧值零残留 |

Two-slice state machine、Fins correction loop、combined revalidation、full pyright `0 errors`、Ruff/coverage/
security/deferred/Windows gates 均未弱化；没有重开已裁决产品问题。

## 3. Accepted new findings

### `R11-PR-BF-FR-DS-F02` — ACCEPTED / LOW / PLAN-ONLY

Plan §2.2 使用描述性 label `CURRENT FMP resolver`，而 exact file 是
`dayu/fins/resolver/fmp_company_info.py`。Hash 与 394 lines 正确，产品 contract 不受影响；但该表承担 implementation
preflight source-lock 路由，描述性 label 会让 Agent 猜路径或先命中不存在的相邻名字。其余 production source rows 使用
exact path，本行应同样自足。

Accepted fix：只把 label cell 改为 `CURRENT dayu/fins/resolver/fmp_company_info.py`（path 以 code span 表示）；
lines/hash cell 不变，不修改 resolver、owner、allowlist、slice 或 validation。

### `R11-PR-BF-FR-CV-F01` — ACCEPTED / LOW / PLAN-ONLY

MiMo artifact §3.2/§8 直接记录 plan 的 `dayu/README.md` lock 为 `111 lines / 1534bcfd...d9a74`，当前为
`265 lines / 16bbdc87...5367`，但错误地把它归为 Controller-owned expected drift。Controller 独立复测：

| Source | Lines | SHA-256 |
|---|---:|---|
| working tree `dayu/README.md` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| accepted-plan `f7b452f9:dayu/README.md` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| R10 baseline `2b14b2fb:dayu/README.md` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |

`dayu/README.md` 不是 Controller-owned artifact；它是 R11-I2 exact product allowlist 与 README trigger 的输入。三路完全
一致证明没有 source drift，只有 plan 创建时的 measurement/copy error。把错误值留到 implementation preflight 会制造与
`requirements.txt` finding 相同的虚假 drift signal，违反 exact execution truth 与 owner-boundary 修复约束。

Accepted fix：只在 grouped README row 把 lines 从 `348 / 111 / 793 / 293` 改为
`348 / 265 / 793 / 293`，并把第二个 hash 从 `1534bcfd...d9a74` 改为 full SHA
`16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367`。其它三个 README cells 不变。

## 4. Rejected reviewer observations

### Ruff version drift — REJECTED AS CURRENT FINDING / RESIDUAL

MiMo 与 DS 都在未激活 `.venv` 时运行 `python -m ruff --version`，得到全局 `ruff 0.15.9`，再把它记录为
implementation preflight residual。AGENTS 与 plan 的命令都要求先 `source .venv/bin/activate`。Controller 按权威环境重跑：

```text
$ source .venv/bin/activate && python -m ruff --version
ruff 0.15.11

$ source .venv/bin/activate && python -m ruff check dayu tests utils --output-format json | shasum -a 256
051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea  -
```

版本 oracle、144-finding baseline content hash 与 plan 完全一致；没有 drift、finding 或 residual，也无需重锁。

### Controller control live drift — NO-FIX EXPECTED STATE

Control 是当前 gate truth owner，随每个 gate 合法变化；plan 已明确允许。它不属于上述 product source-lock 错误，不需要
固定回旧 hash。

## 5. Exact fix boundary 与 next gate

AgentCodex 仅获授权修改 plan §2.2 的两个 label/measurement cells，并新增 fix evidence；不得修改其它 plan 语义、
product/test/README/design/CI、control、既有 review/auth/stop/adjudication artifact。不得运行产品 tests/pyright/coverage/
Ruff，不得 stage/commit/push/PR。

修复后 Controller 必须重放 two-cell delta 与三路 source truth，再并发对完整最终 plan 做双路 complete re-review；不能只审
delta。若没有新 finding，才可接受 plan amendment commit 并进入 `R11-I1` authorization。

| Item | Count |
|---|---:|
| prior findings closed | 3 |
| accepted/open new findings | 2 |
| blocker | 0 |
| actual accepted residual | 0 |

Windows 仍为 `PENDING_RELEASE_BLOCKER`；R12、deferred Issue 与统一 authorization framework 未进入。

READY_FOR_AGENTCODEX_R11_FINAL_PLAN_SOURCE_LOCK_FIX2
