# WU-SEMANTIC-OWNERSHIP-01 / R11 cumulative code review Controller 裁决

## 1. Review target 与输入

- immutable implementation HEAD：`7972c3c0ba8628173fc91c362b9394655f60678e`
- cumulative product tree：I1 `8` + I2 `15` - shared `1` = `22` unique paths
- stopped binary diff SHA-256：`6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`
- AgentCodex evidence：`57fb654d2f484da7e72340eadfba6f8edab37b8aefb90cb784a7dae7667aa3ba`
- Controller validation：`7023a71801a86f0f712ca320d25ea2cec06ef82d005458c352f280a6888902d1`
- AgentMiMo review：`docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-mimo.md`，46 lines / 6,814 bytes / SHA-256 `e28a5473b34e2bacb26800aef22eb6efc1b6f8de8bec8070a36a621a29cdf18d`
- AgentDS review：`docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-ds.md`，126 lines / 16,852 bytes / SHA-256 `df6e61c3e947fca3450163eed4b6b2315f3e3cdf09a4736d6d3321fb56b8ccbf`

Controller 完整读取两份 review、accepted plan对应 owner/allowlist、三个 finding的直接代码与测试/workflow证据。Reviewer verdict不独立授权修复或 acceptance。

## 2. Finding 裁决

### 2.1 `R11-DS-F01` — REJECTED / NO FIX

**Claim**：把 Fins source containment与 CLI publisher containment中三个相同 helper提取到 `dayu.runtime`。

**裁决**：拒绝。

直接真源：

- accepted plan §3 明确 `dayu/runtime/**` 是 R11 non-goal；§4 exact cumulative product allowlist没有 runtime path；
- semantic owner map分别把“source containment/symlink verdict”交给 `dayu.fins.upload_batch`，把“output target/containment/symlink/atomic publish”交给 `dayu.cli.upload_script`；
- 两者虽然当前使用相同 mechanical primitives，但产生不同业务 verdict、失败类型、外部承诺与未来 policy演进；共享同一 runtime helper会把两个独立 security policy owner耦合为一个事实 owner；
- 当前直接测试和两路 review都没有证明行为差异、security bypass、drift或调用者缺陷。

AGENTS 的公共 runtime要求禁止“语义不一致的重复 runtime helper”，不是授权把不同 owner 的 security policy抽成新的跨包 abstraction。当前实现保持 local policy owner更小、更符合 accepted plan，且不创建新的 runtime public surface。`R11-DS-F01` 因而是结构偏好，不是 accepted defect。

### 2.2 `R11-DS-F02` — ACCEPTED / OPEN

**Claim**：CLI `_single_batch_material_form` 复制了 Fins owner 的三个 material-form值。

**裁决**：接受，但修复路径不采用 reviewer建议的 public constant/alias。

直接证据：

- accepted plan §4/§5把 material routing与显式 override validation唯一交给 `dayu.fins.upload_batch`；CLI只机械投影 typed facts；
- `dayu/cli/commands/fins.py:1183-1187` 当前独立硬编码 `FINANCIAL_STATEMENTS` / `EARNINGS_CALL` / `EARNINGS_PRESENTATION`；
- Fins 已在 `_validated_material_form` 使用由 routing table派生的 `_MATERIAL_FORM_TYPES` 做最终 owner validation；
- CLI handler已经把 `UploadBatchPlanUsageError` 映射为 usage exit，因此没有第二套值域验证的必要。

要求 AgentCodex消除 CLI值域副本，使 raw normalized candidate进入 Fins request并仅由 Fins owner验证，同时保持严格类型、错误映射与现有 user contract。不得公开私有常量、增加 compatibility alias/wrapper、fallback或 loose downstream parsing。补 Fins owner invalid-value test与 CLI propagation test，证明唯一 owner。

### 2.3 `R11-DS-F03` — ACCEPTED / OPEN

**Claim**：Windows workflow递归扫描整个 `%TEMP%` 寻找 pytest artifacts，依赖 tmp-path实现并可能误取同名文件。

**裁决**：接受，且这是 accepted plan §7.2 的直接实现缺口。

直接证据：

- plan §7.2明确 `DAYU_R11_WINDOWS_ARTIFACT_DIR` 是唯一测试证据发布目录，并要求测试把 generated cmd、recorder oracle与 CLI evidence写入该目录；
- workflow当前 lines 82-84 对 `$env:TEMP` 做三次递归通用文件名搜索，随后复制结果；
- 两个 Windows tests只写 `tmp_path`，没有消费显式 artifact directory；
- 当前真实 Windows run尚未发生，因此这个不确定 locator不能留到 release blocker后再“视结果决定”。

要求 AgentCodex在现有 test/workflow owner内建立确定性 artifact locator，禁止扫描整个 `%TEMP%`。优先遵守 plan：Windows tests在显式 `DAYU_R11_WINDOWS_ARTIFACT_DIR` 存在时发布 exact evidence，workflow只从该目录读取/校验；无 env的普通本地 test仍使用 `tmp_path`，不能污染产品代码或改变 POSIX tests。不得用 broad glob、repo-local fallback、test-only production seam或跳过真实 `cmd.exe`。

## 3. Non-finding / observation 裁决

- AgentMiMo：zero material finding，接受其 PASS evidence；不产生 fix。
- AgentDS 对 `_optional_text` / `_optional_stripped_text` 的 open question：两者分别属于 Fins request field normalization与 CLI input boundary，没有 formal finding或当前 drift证据；`NO FIX`。
- 两项 Service baseline failure：保持 HEAD-existing分类，不属于 R11 fix scope，也不得宣称 repository full suite green。
- Windows real run：保持 `PENDING_RELEASE_BLOCKER`；本 fix只修 locator，不能关闭 release gate。

## 4. Fix scope 与 mandatory revalidation

只授权 AgentCodex修改以下现有 R11 allowlist paths：

1. `dayu/fins/upload_batch.py`
2. `dayu/cli/commands/fins.py`
3. `tests/fins/test_upload_batch.py`
4. `tests/cli/test_upload_filings_from_command.py`
5. `.github/workflows/r11-upload-script-windows.yml`
6. 若实际 user/test contract文字因 locator变化需要同步，最多 `tests/README.md`；没有触发则不得机械修改。

另允许唯一 fix evidence：`docs/reviews/wu-semantic-ownership-01-r11-cumulative-code-review-fix-codex.md`。

禁止修改 `dayu.runtime`、plan、Controller control、其它产品/test/README、既有 artifacts、constraints/lock、Service/Host/Engine、deferred Issue或 Topic 8/9。禁止 stage/commit/push/PR/R12。

修复后必须重跑：accepted plan全部 affected focused tests、Fins owner invalid-value contract、Windows local skip/grammar/workflow contract、three POSIX real smokes、fresh exact-wheel constrained install/runtime/archive gates、per-file coverage `>=80%`、full pyright zero、scoped/full-baseline Ruff、22-path allowlist/README/security/deferred scans、related/full suites与两项 baseline精确分类。任何新增 failure或 path expansion必须 stop。

## 5. Final ledger / next gate

| Finding | Status |
|---|---|
| `R11-DS-F01` | `REJECTED / NO FIX` |
| `R11-DS-F02` | `ACCEPTED / OPEN` |
| `R11-DS-F03` | `ACCEPTED / OPEN` |
| AgentMiMo material finding | `NONE` |

- accepted/open：`2`
- rejected：`1`
- blocker：`0` local fix blocker；Windows release blocker仍 pending
- next gate：AgentCodex bounded cumulative code-review fix → Controller validation → concurrent complete dual re-review

R11 implementation尚未接受；R12、stage/commit、push与 PR仍未授权。
