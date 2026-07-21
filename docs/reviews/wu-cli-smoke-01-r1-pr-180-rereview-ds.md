# WU-CLI-SMOKE-01-R1 Draft PR #180 Narrow Re-review (AgentDS)

## Scope

- Mode: Draft PR #180 narrow re-review，仅核验 PR180-F01 fix 结果与 metadata 保持。
- Reviewed head: `ff5d515a50d538415c0906b80ebdef594601c5c8`。
- 前置 artifacts:
  - `docs/reviews/wu-cli-smoke-01-r1-pr-180-review-controller-adjudication.md`（PR180-F01 accepted, blocking）。
  - `docs/reviews/wu-cli-smoke-01-r1-pr-review-fix-codex.md`（fix 执行记录）。
  - `docs/reviews/wu-cli-smoke-01-r1-pr-review-fix-controller-validation.md`（fix 后 controller validation）。
- 核验范围：仅以下 5 项，不扩展为完整 PR review。

## Direct Verification

### 1. PR180-F01：body 是否为真实 Markdown（无字面反斜杠-n）

- `gh pr view 180 --json body --jq '.body' | sed -n '1,30l'`：每行以真实换行终止（`$`），`## 摘要`、`## 验证`、`## 已接受边界` 为独立行标题；标题间有空行（仅 `$` 的行）；`- ` 列表项各自独立成行。
- `gh pr view 180 --json body --jq '.body' | grep -c '\\n'` → `0`：body 中不存在字面量反斜杠加 `n`。
- `gh pr view 180 --json body --jq '.body' | wc -l` → `26`：与 fix-codex 记录的 `lineCount=26` 一致。

**结论：FIXED。**

### 2. 无行首 Closes/Fixes/Resolves closing directive

- `gh pr view 180 --json body --jq '.body' | grep -c '^\(Closes\|Fixes\|Resolves\)'` → `0`。
- body 末行为说明句 "本 WU 是 PR #179 后的 residual remediation，没有独立 Issue owner，因此不添加 Closes footer。"，不构成 closing directive。

**结论：PASS。**

### 3. title、isDraft、reviewRequests、base、head branch、head OID 保持

- `gh pr view 180 --json title,isDraft,reviewRequests,baseRefName,headRefName,headRefOid`：
  - `title` = `WU-CLI-SMOKE-01-R1: move engine deltas to Host transient live stream`（未变）。
  - `isDraft` = `true`（保持）。
  - `reviewRequests` = `[]`（保持）。
  - `baseRefName` = `main`（保持）。
  - `headRefName` = `phaseflow/wu-cli-smoke-01-r1`（保持）。
  - `headRefOid` = `ff5d515a50d538415c0906b80ebdef594601c5c8`（与 fix 前一致，代码 diff 未变）。

**结论：PASS。**

### 4. 两项 CI checks pass

- `gh pr checks 180`：
  - `windows-init-transaction`：pass。
  - `windows-upload-script`：pass。

**结论：PASS。**

### 5. fix 未修改代码 diff 或引入新 material finding

- headRefOid `ff5d515a` 未变 → 代码 diff 未变。
- fix-codex 记录的外部修改仅限于 PR #180 body 换行格式；仓库侧仅新增 fix artifact 与 controller/validation artifacts。
- 本 re-review 对 body 内容、metadata、CI 与 head OID 的独立核验未发现新 material finding。

**结论：PASS。**

## Findings

未发现实质性问题。

## Decision

| 核验项 | 结果 |
|---|---|
| PR180-F01 body 真实 Markdown | **FIXED** |
| 无 Closes/Fixes/Resolves 指令 | **PASS** |
| metadata 保持（title/draft/requests/base/head/OID） | **PASS** |
| CI checks（2/2） | **PASS** |
| 无代码 diff 变更或新 material finding | **PASS** |

- **Overall：PASS。**
- **Blocking 数：0。**

## Open Questions

无。

## Residual Risk

- 本 re-review 是 narrow scope，仅核验 PR180-F01 fix 结果与 metadata 保持；未重新执行完整 adversarial failure pass、semantic ownership drift pass 或全量测试/coverage 验证——这些已在原始 AgentDS review（PASS, 0 finding）与 AgentMiMo review（PASS, 1 non-blocking low note）中覆盖，且代码 head 未变。
