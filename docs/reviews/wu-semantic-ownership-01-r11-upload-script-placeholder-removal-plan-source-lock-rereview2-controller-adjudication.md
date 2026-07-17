# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan source-lock re-review 2 Controller adjudication

## 1. Gate 与裁决边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature、issue，
  也不是重新打开历史 sub-WU。
- gate：R11 dual complete final-plan re-review 2 Controller adjudication。
- immutable reviewed plan：
  `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，886 lines / 74,647 bytes /
  SHA-256 `817c9d2fde2112c244e14659e713041748e59d048b77e07be2f0b8def5175a92`。
- review inputs：
  - MiMo：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-source-lock-rereview2-mimo.md`，
    385 lines / 19,221 bytes / SHA-256
    `0ab884608d2b1b92fc0570ab3e69771e92ca00adf87326a9dc81493fc100c079`；
  - DS：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-source-lock-rereview2-ds.md`，
    405 lines / SHA-256 `a201385d7f3b4085451b31e7b65e829b77b54f34af729b313bb4d5bdc96362b7`。
- 本裁决不授权 implementation、stage、commit、R12、push 或 PR；只授权下述 plan-only owner fix。

## 2. 共同闭证

两路 review 均完整读取 886 行 plan，并独立确认：

- `R11-IMP-BF01` 已关闭：最终状态机只有 `R11-I1 atomic Fins+CLI cutover` 与
  `R11-I2 packaging/README/Windows gate` 两个 implementation slices；WP-A/WP-B 不是独立节点或 checkpoint；
- `R11-PR-BF-RR-F01` 已关闭：顺序编辑期间的 transient inconsistency 不是 gate truth，真实 blocker 的
  safety stop 也不构成 checkpoint、acceptance、commit、review 或 next-slice transition；
- `R11-PR-BF-FR-DS-F01`、`R11-PR-BF-FR-DS-F02`、`R11-PR-BF-FR-CV-F01` 均已关闭；
- activated `.venv` 的 Ruff 是 `0.15.11`，full baseline 为 144 findings / SHA-256
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；不存在 Ruff drift；
- full pyright zero、per-file line coverage `>=80.00%`、security/deferred/source scans、real POSIX smoke 与
  Windows `PENDING_RELEASE_BLOCKER` 均未弱化；
- product/test/README/design/CI 未被本 gate 修改，staged tree 为空。

以上五个 prior findings 最终状态保持 **CLOSED**。

## 3. 新 finding 裁决

### 3.1 `R11-PR-BF-RR2-DS-F01` — ACCEPTED-NARROW / plan-only

DS 观察到两个 OLD 文件不在当前 repo working tree 或 git history。其“OLD 文件不可达”前提不成立：用户已明确要求
对齐 `/Users/leo/workspace/dayu-agent`，Controller 直接验证以下外部只读真源存在且与 plan lock 精确匹配：

| Exact external source | Lines | SHA-256 |
|---|---:|---|
| `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` | 2267 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` |
| `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py` | 555 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` |

但 plan 只写 repo-relative descriptive OLD path，会让清屏后的 implementation agent 在错误仓库内查找，因此接受
“精确路由不可发现”这一窄 finding。修复必须同时在 §2.1 authority item 7 和 §2.2 两个 OLD source-lock row 写出上述
absolute external paths，并保持 lines/hash 不变。

不接受把 OLD 生产文件复制进当前 repo、tracked fixture 或引入兼容实现：那会复制历史实现、扩大当前产品/测试 surface，
与 OLD 仅作为工作流/分类证据的裁决冲突。

### 3.2 `R11-PR-BF-RR2-DS-F02` — ACCEPTED / plan-only

`umbrella remediation plan` 是描述性 label，且同目录另有不同的 umbrella plan。source-lock owner 必须可直接路由。
修复必须把 §2.1 authority item 4 与 §2.2 row 都改为 exact path：
`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`；保持 1269 lines / SHA-256
`30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` 不变。

### 3.3 `R11-PR-BF-RR2-DS-F03` — ACCEPTED-NARROW / plan-only

OLD 真源已给出唯一答案，不需重新做产品裁决：

- `_infer_fiscal_period_from_filename(filename)` 只检查完整 filename，不检查 ancestor/path；
- Q4 quarterly marker 是 exact literal substring `季报`，不是 `季度报告` alias，也不是宽松 pattern；
- `FY` / `annual` / `年度报告` / `年报` 在 Q1—Q4 前判定，因此 `2024Q4年报.pdf -> FY`；
- filename 自身不足、从 direct structured `20YYQ4` parent 回退时，仍只用 child filename 的 exact `季报`
  marker 决定 `Q4`，否则为 `FY`。

Plan §5.2 rule 4 必须明确这四点，不得扩大 OLD 业务语义。owner tests 必须至少锁定：

- `2024Q4季报.pdf -> Q4`；
- `2024Q4季度报告.pdf -> FY`；
- `2024Q4年报.pdf -> FY`；
- `2021Q4/季报.pdf -> Q4`；
- `2021Q4/季度报告.pdf -> FY`。

### 3.4 DS open questions / residual notes

- priority level 5 与 latest fiscal year periodic semantics 已由 plan §5.2 rules 8—9 给出 deterministic 行为，
  reviewer 未提供与 OLD 真源矛盾的直接证据，不另开 finding。
- renderer import-boundary 是 implementation validation 关注点；现有 no-reverse-dependency、full pyright、deferred diff
  与 closed allowlist gates 不因该 note 弱化，不扩大本轮 plan-only fix。
- Windows runner 仍是 R11 release blocker owner，不是本 plan fix 的 residual downgrade。

## 4. Exact fix allowlist 与禁止项

AgentCodex 只可修改：

1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`；
2. 新建一个对应 plan-fix evidence artifact 于 `docs/reviews/`。

必须只做：

- 两个 authority/source-lock exact path corrections；
- §5.2 Q4 OLD semantics clarification；
- 对应 owner-test matrix clarification；
- artifact 记录 before/after、direct OLD evidence、hash/lines/diffcheck。

禁止修改 product、tests、README、design、CI、control 或既有 artifact；禁止 stage/commit；禁止进入 implementation；禁止
引入 OLD fixture、兼容 seam、`Any`/dict bag、宽松 parsing、fallback、new WU、R12 或 deferred issue scope。

## 5. Gate verdict 与 ledger

**Verdict：PLAN FIX REQUIRED / READY_FOR_AGENTCODEX_EXACT_SOURCE_AND_Q4_PLAN_FIX**

| Finding | Final status at this gate |
|---|---|
| `R11-IMP-BF01` | CLOSED |
| `R11-PR-BF-RR-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F02` | CLOSED |
| `R11-PR-BF-FR-CV-F01` | CLOSED |
| `R11-PR-BF-RR2-DS-F01` | ACCEPTED / OPEN / narrow exact external path fix |
| `R11-PR-BF-RR2-DS-F02` | ACCEPTED / OPEN / exact umbrella path fix |
| `R11-PR-BF-RR2-DS-F03` | ACCEPTED / OPEN / exact OLD Q4 semantics fix |

- accepted/open：3；
- blocker：0；
- actual accepted residual：0；
- implementation authorization：无；
- next gate：AgentCodex plan-only fix -> Controller validation -> dual complete final-plan re-review 3。
