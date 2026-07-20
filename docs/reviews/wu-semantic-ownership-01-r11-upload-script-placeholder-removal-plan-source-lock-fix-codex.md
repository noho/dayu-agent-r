# WU-SEMANTIC-OWNERSHIP-01 / R11 plan source-lock exact fix evidence（AgentCodex）

## 1. Gate、授权与结论

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- gate：accepted finding `R11-PR-BF-FR-DS-F01` 的 exact plan-only source-lock fix。
- Controller 授权：仅把 plan §2.2 baseline source locks 表中 CURRENT `requirements.txt` 的错误 SHA-256 cell
  `7e8c14d6...79c93` 替换为 Controller 三路复测一致的完整 SHA-256
  `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a`，并新增本 evidence。
- write allowlist：
  1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
  2. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-source-lock-fix-codex.md`
- 结论：修复完成。plan 只改一个 table cell；其它字符、语义、marker、gate wording、owner、scope、slice、validation、
  Windows/deferred/security contract 均未改动。
- 本 gate 不授权且未执行 implementation、产品测试、pyright、coverage、Ruff、stage、commit、push、PR 或 R12。

## 2. 完整读取与输入锁

执行前完整读取了全部指定输入：

| Artifact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `AGENTS.md` | 128 | 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| plan（fix 前） | 886 | 74,523 | `c3c0616f7ec90cb8e62f68bf219e43b053a07db320c3b169f70159855ce1430c` |
| MiMo final re-review | 197 | 13,612 | `40d2d5d5f9c24436864fe66ff35493eeceab8f73850abfb1f3ec8fd6816537fe` |
| DS final re-review | 528 | 32,001 | `58e28d70c745f6d5b11de2d81e0a84f2476c9a8d9ddce92df827af054709fdbf` |
| Controller final re-review adjudication | 95 | 5,636 | `71549dc841a57f663f2e0f07fe46ea0a3535fae7c226e48978d5ecf6819d5095` |

Controller adjudication 接受该 finding 为 `LOW / PLAN-ONLY`，并判定 source-lock owner 是 plan §2.2；已知错误不能留给
implementation preflight 下游补偿。该直接证据与 AGENTS.md 的同源和 owner-boundary 约束一致，因此唯一正确修复就是在
source-lock owner 内替换该 cell，不重开任何已裁决产品问题。

## 3. 三路 `requirements.txt` hash 复测

三路均为 12 lines；SHA-256 完全一致：

| Source | Commit / tree | SHA-256 |
|---|---|---|
| working tree `requirements.txt` | 当前 working tree | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| accepted-plan `requirements.txt` | `f7b452f992b4797b32fea7c6f7212b5ec4345ec1` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| R10 completion baseline `requirements.txt` | `2b14b2fbc89654267e3d33daa2ae410ceff45e68` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |

复测命令与原始结果：

```text
$ shasum -a 256 requirements.txt
d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a  requirements.txt

$ git show f7b452f992b4797b32fea7c6f7212b5ec4345ec1:requirements.txt | shasum -a 256
d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a  -

$ git show 2b14b2fbc89654267e3d33daa2ae410ceff45e68:requirements.txt | shasum -a 256
d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a  -
```

因此不存在 `requirements.txt` 内容 drift；错误只在 plan 的 source-lock 测量值。

## 4. Before / final plan identity

| State | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| fix 前 | 886 | 74,523 | `c3c0616f7ec90cb8e62f68bf219e43b053a07db320c3b169f70159855ce1430c` |
| fix 后 | 886 | 74,571 | `59156239ff4d73bfeaa1cb78a593c2b75504804102a07e851b1239803a4de51f` |

- 行数差：`0`。
- bytes 差：`+48`，精确等于 16 字符缩写 `7e8c14d6...79c93` 替换为 64 字符完整 SHA-256 的长度差。
- fix 前旧值命中：精确 `1`，位于 plan line 71；完整目标值命中：`0`。
- fix 后旧值命中：`0`；完整目标值命中：精确 `1`，仍位于 plan line 71。
- plan 最后一行 marker 仍逐字为 `READY_FOR_CONTROLLER_PLAN_WORDING_FIX_VALIDATION`。

## 5. Exact one-cell diff

相对于本任务 fix 前的 plan identity `c3c0616f...1430c`，唯一 plan delta 是：

```diff
-| CURRENT `requirements.txt` | 12 | `7e8c14d6...79c93` |
+| CURRENT `requirements.txt` | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
```

工作树在本任务开始前已包含 Controller-owned control 改动、此前 accepted plan amendment 与既有 untracked gate artifacts；
这些均作为只读基线保留。相对 `HEAD` 的完整 plan diff 会同时显示此前 amendment，因此本次 one-cell delta 以 Controller
锁定的 fix 前 plan lines/bytes/SHA、旧值/新值唯一命中和上述 exact replacement 共同界定。

## 6. Boundary 与零 diff 证明

以下两个命令在 fix 后均无输出：

```text
$ git status --short -- dayu tests README.md pyproject.toml requirements.txt .github docs/host/design.md docs/engine/design.md docs/tool/design.md docs/fins/design.md docs/ui/design.md
<empty>

$ git diff --name-only -- dayu tests README.md pyproject.toml requirements.txt .github docs/host/design.md docs/engine/design.md docs/tool/design.md docs/fins/design.md docs/ui/design.md
<empty>
```

由此确认 product、test、README、design、CI 的 tracked/untracked diff 均为空。未修改 control、任何既有
review/auth/stop/adjudication artifact；未改 owner、scope、slice、validation、Windows/deferred/security contract。

README trigger：本次只修改 plan source-lock cell 并新增 review evidence，不改变任何代码、用户可见入口、命令、工作流、
分层或 README 职责，因此 README diff 正确保持为空。

## 7. Staged 与 whitespace validation

```text
$ git diff --cached --name-only
<empty>

$ git diff --check
<empty>
```

- staged tree 为空；未 stage、commit、push 或创建 PR。
- `git diff --check` 通过，无 whitespace error。
- 按 Controller 明示限制，未运行产品 tests、pyright、coverage 或 Ruff；这是 plan-only source-lock 修复，不是产品
  validation，也没有以未运行项冒充 pass。
- 两个授权写入均只通过 `apply_patch` 完成。

## 8. Finding closure 与 next gate

| Finding | Final status | Closure |
|---|---|---|
| `R11-PR-BF-FR-DS-F01` | **CLOSED** | plan §2.2 source-lock owner cell 已替换为三路一致的完整 SHA-256；虚假 drift signal 已消除 |

- accepted/open plan-only finding：`0`。
- product contract、owner、allowlist、实现可行性：未改变。
- `R11-IMP-BF01`：保持 CLOSED。
- `R11-PR-BF-RR-F01`：保持 CLOSED。
- actual accepted residual：`0`，未改变。
- Windows：仍为 `PENDING_RELEASE_BLOCKER`，未改变。
- next gate：Controller R11 final plan source-lock fix validation；随后按 Controller 裁决对完整 final plan 做双路 complete
  re-review，不得只审 one-cell delta。

READY_FOR_CONTROLLER_R11_FINAL_PLAN_SOURCE_LOCK_FIX_VALIDATION
