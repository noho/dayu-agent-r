# WU-SEMANTIC-OWNERSHIP-01 / R11 exact-source/Q4 plan fix Controller validation

## 1. Gate 与目标

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- gate：Controller validation of the exact-source/Q4 plan-only fix。
- Controller adjudication：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-source-lock-rereview2-controller-adjudication.md`，
  125 lines / 6,920 bytes / SHA-256
  `b6dc10a2561cc359f523d535aa126defa229ef9022910d48f16dd838e0e0f191`。
- AgentCodex evidence：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-exact-source-q4-fix-codex.md`，
  178 lines / 12,109 bytes / SHA-256
  `ccfc372f46acfa9e7957d6983c1bb773732195fc65517ab543ed666488cc5a8b`。
- after plan：892 lines / 75,434 bytes / SHA-256
  `35a15ae9acd3276d8fea95473d295cb01c9b39c591f1bac077ccc1b93029f571`。
- 本验证不授权 implementation、stage、commit、R12、push 或 PR。

## 2. Exact delta validation

Controller 完整读取 AgentCodex evidence，并核对其内嵌完整 unified diff。对 after plan 以该 diff 做 in-memory reverse
patch，得到 SHA-256：

```text
817c9d2fde2112c244e14659e713041748e59d048b77e07be2f0b8def5175a92
```

该值精确等于 dual complete final-plan re-review 2 的 immutable before plan。由此证明本轮增量只有 5 个 plan hunks：

1. §2.1 authority item 4 的 exact umbrella remediation plan path；
2. §2.1 authority item 7 的两个 exact external OLD paths；
3. §2.2 umbrella source-lock row 的 exact path；
4. §2.2 两个 OLD source-lock rows 的 exact external paths；
5. §5.2 rule 4 与 §5.3 owner-test matrix 的 Q4 semantic clarification。

本 delta 没有改变产品 scope、两个 implementation slices、closed allowlist、validation gates、Windows release blocker、
security/deferred/no-code decisions。

## 3. Source-lock validation

Controller 直接复测：

| Source | Lines | SHA-256 | Verdict |
|---|---:|---|---|
| `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` | 2267 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` | MATCH |
| `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py` | 555 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` | MATCH |
| `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` | MATCH |

Plan §2.1 与 §2.2 均使用这些 exact paths；旧 `umbrella remediation plan` descriptive row 与 repo-relative OLD row
不再存在。没有把 OLD 文件复制进当前 repo。

## 4. Q4 owner oracle validation

Controller 使用当前 `.venv/bin/python -B` 直接只读加载 external OLD
`/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py`，五个 oracle 精确通过：

```text
2024Q4季报.pdf -> Q4
2024Q4季度报告.pdf -> FY
2024Q4年报.pdf -> FY
2021Q4/季报.pdf -> (2021, 'Q4')
2021Q4/季度报告.pdf -> (2021, 'FY')
```

Plan 现明确：只检查 child 完整 filename；Q4 quarterly marker 只认 exact contiguous literal `季报`；
`FY`/annual/年度报告/年报在 Q1—Q4 前判定；direct `20YYQ4` parent fallback 仍只检查 child filename。
Owner-test matrix 包含全部五个 exact cases。没有引入 `季度报告` alias、宽松 regex 或 path/ancestor inference。

## 5. Hygiene 与 scope validation

- `git diff --check`：PASS；
- staged tree：empty；
- product/test/README/design/CI scoped status/diff：empty；
- plan 仍精确定义两个 implementation slices：
  `R11-I1 atomic Fins+CLI cutover -> R11-I2 packaging/README/Windows gate`；
- Issue 142、151、175、177、178、R12、真实 Web/WeChat/render 与 Topic 8/9 仍未进入；
- Windows 仍为 `PENDING_RELEASE_BLOCKER`，未误报 closed；
- 本 gate 只有文档变更，因此没有运行或虚报 product pytest、coverage、pyright、Ruff 或 implementation smoke。

## 6. Findings ledger

| Finding | Controller validation status |
|---|---|
| `R11-IMP-BF01` | CLOSED |
| `R11-PR-BF-RR-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F02` | CLOSED |
| `R11-PR-BF-FR-CV-F01` | CLOSED |
| `R11-PR-BF-RR2-DS-F01` | FIXED / CONTROLLER-VALIDATED |
| `R11-PR-BF-RR2-DS-F02` | FIXED / CONTROLLER-VALIDATED |
| `R11-PR-BF-RR2-DS-F03` | FIXED / CONTROLLER-VALIDATED |

- accepted/open before re-review：0；
- blocker：0；
- actual accepted residual：0。

## 7. Verdict

**PASS / READY_FOR_DUAL_COMPLETE_FINAL_PLAN_REREVIEW3**

两路 reviewer 必须完整读取全部 892 行 after plan，不得只审 delta；必须独立重测 exact external locks、五个 Q4 owner
oracles、全部八个 finding closure、two-slice state machine、validation/security/deferred/Windows gates。任一新 material
finding 仍回 Controller 裁决，不能由 reviewer verdict 直接授权 implementation。
