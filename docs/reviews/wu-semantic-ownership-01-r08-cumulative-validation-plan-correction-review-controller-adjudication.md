# WU-SEMANTIC-OWNERSHIP-01 R08 Cumulative Validation Plan-Correction Review — Controller Adjudication

## 1. Gate 与 verdict

- umbrella / sub-WU：既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue。
- corrected plan SHA-256：`4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d`。
- protected S1 14-path diff SHA-256：`0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`。
- AgentMiMo：`PASS`，artifact `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-mimo.md`。
- AgentDS：`PASS-WITH-FINDINGS`，artifact `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-ds.md`。
- Controller verdict：`PLAN_FIX_REQUIRED / 5 SOURCE FINDINGS ACCEPTED INTO 3 FIX GROUPS / 3 REJECTED`。

两路均确认 product contracts、S1/S2 allowlists、R07 no-touch、Host truncation owner、retained security、deferred Issues、Topic 8-9 no-code 与两个受保护 hash 未漂移。Reviewer 的 PASS 不自行授权 S2；所有 accepted plan findings 必须先由 AgentCodex 修复并经两路完整 re-review。

## 2. Accepted fix groups

### R08-CVPF-01：精确 Python coverage manifest、自动阈值判定与路径 contract

合并接受：DS F1、DS F2、MiMo F4。

直接证据：§6.6 当前写 `git diff --name-only --diff-filter=ACMR -- dayu/fins`。S2 按 §6.8 会修改 `dayu/fins/README.md`，因此最终累计 tree 上该命令会包含非 Python path；MiMo 依据当前仅有 S1 代码 diff 得出“输出全部是 Python”的结论不能证明 S2 后的计划命令。Coverage JSON 的 `files` / `summary.percent_covered` contract 可用，但 plan 只有自然语言“逐项读取”，没有机械失败命令，也未固定 JSON key 与 git path 的 repo-relative exact-match contract。

AgentCodex 必须：

1. 用 Git pathspec 直接生成 production Python manifest，例如 `git diff --name-only --diff-filter=ACMR -- 'dayu/fins/*.py'`；不得先收集 README 再靠人工排除。
2. 在 §6.6 给出可复制执行的自动 checker 命令：读取 repo-root-relative manifest 与 `workspace/tmp/r08-cumulative-coverage.json`，对每个 manifest path 做 exact key match；manifest 为空、key 缺失、`percent_covered < 80.00` 任一情况都非零退出并打印逐文件 ledger。
3. 不得用 basename/suffix loose matching、absolute-path fallback、aggregate threshold、changed-line、pragma/omit、fake-only padding、skip/xfail 或豁免补救路径不一致；若 coverage JSON 不是 repo-root-relative exact key，修正 coverage invocation/working directory 后重跑。

### R08-CVPF-02：Ruff 必须消费实际 changed Python manifest

接受 MiMo F1。

`python -m ruff check <S1+S2全部实际修改的Python文件>` 是不可直接执行占位符，且可能遗漏 tests。Plan 必须给出机械命令，覆盖累计 tree 中 `dayu/fins` 与 `tests/fins` 的全部实际 changed `.py` 路径，例如 NUL-safe Git manifest 管道到 Ruff。只列入 allowlist 但零 diff 的文件不必伪跑；所有实际 changed production/test Python 必须纳入，空 manifest 必须失败而非静默成功。

### R08-CVPF-03：aggregate deepreview fix 后重跑唯一累计 validation

接受 DS F3。

§6.9 已对 code-review fix 明确要求新 hash + 完整 §6.6 revalidation，但 §7 对 aggregate deepreview accepted fix 只写 fix/re-review。AgentCodex 必须明确：任一 aggregate deepreview accepted finding 导致 reviewed tree 变化后，旧 validation/hash/deepreview 均失效；必须在新 hash 上重跑完整 §6.6/§6.7（focused/aggregate/full Fins、real smokes、逐文件 coverage、full pyright、scoped Ruff、全部 scans、diff check），然后两路 aggregate re-review，才可 Controller 关闭并授权 commit。

## 3. Rejected / no-fix findings

### DS F4：放宽 forced-truncation key-set equality — REJECTED

`set(post_value) == set(pre_value)` 不是偶然实现断言，而是原 accepted R08 plan 明确要求的公开组合证明：Host 只把 `facts` 替换为 cursor envelope，所有 Fins public siblings 原样保留，不凭空增加另一套顶层 public contract。Plan 已有 stop 回 Controller 的正确路径；未来 Host governance contract 演化必须经其 owner 与新的设计/测试裁决，不能在 R08 预先用 superset 断言放宽。不得修改 §6.4 该断言或 stop condition。

### MiMo F2：§6.6/§6.7 scans 两层描述混淆 — REJECTED

§6.6 明确把 §5.5、§6.7 scans 纳入同一累计 gate，§6.7 是具体命令/分类展开而非第二 validation truth。§7 又明确不得复制或缩减第二份矩阵。现有引用关系足够，无漏跑或双 owner 证据；不需要为低风险表述新增重复文字。

### MiMo F3：共享 test file “并发/行号偏移” — REJECTED

计划是同一 AgentCodex 在同一 tree 上严格顺序执行 S1→S2，不存在并发编辑或 Git merge。§5.1 以 symbol/node 名称而非行号定义边界，§6.1 明确 S2 基于 S1 protected tree；行号变化不是语义风险。不得加入 line-number compatibility、merge seam 或额外切片。

## 4. Findings ledger

| Reviewer finding | Controller decision | Fix group / disposition |
|---|---|---|
| DS F1 | ACCEPT | `R08-CVPF-01` |
| DS F2 | ACCEPT | `R08-CVPF-01` |
| DS F3 | ACCEPT | `R08-CVPF-03` |
| DS F4 | REJECT | strict Host/Fins public key-set proof retained |
| MiMo F1 | ACCEPT | `R08-CVPF-02` |
| MiMo F2 | REJECT | §6.7 is §6.6 detailed scan truth |
| MiMo F3 | REJECT | sequential symbol-based shared-file edit |
| MiMo F4 | ACCEPT | `R08-CVPF-01` |

Accepted source findings：5；合并 fix groups：3；rejected/no-fix：3；blocker：0。

## 5. 下一 gate

下一 gate 是 AgentCodex 同一 R08 plan-correction review fix：

- 只修改 corrected plan；新增一个 fix artifact；不得修改 product/tests/S1 artifact/control/controller/reviewer artifacts/README/design。
- 修复 `R08-CVPF-01..03`，不得实现 rejected findings。
- 重算 final plan SHA、受保护 14-path diff SHA、`git diff --check`、status 与 staged-empty。
- 完成后进入 MiMo/DS 对完整 final plan 的并发 re-review，不进入 S2。
