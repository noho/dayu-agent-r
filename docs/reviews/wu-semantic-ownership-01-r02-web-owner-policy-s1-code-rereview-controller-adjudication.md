# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 Code Re-Review Controller Adjudication

## 范围与真源

- 本裁决属于既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 overdesign remediation continuation，不是新 WU。
- 审查基线为 `70ffc917` 到最终工作树；R02-S1 只交付 Web config owner、typed policy snapshot、HTTP/Browser/Diagnostic resource budget owner split 及其直接类型传播。
- 产品裁决以 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 为最高真源；实现边界以 accepted R02 plan 为准。
- 第一路 re-review：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-rereview-mimo.md`，结论 `PASS`。
- 第二路 re-review：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-rereview-ds.md`，结论 `PASS`。

## 旧 Finding 最终状态

| Finding | Controller 最终状态 | 直接证据 |
|---|---|---|
| `R02-S1-CR-F01` 顶层 unknown key fail-fast | **closed** | raw JSON parser owner 使用精确 12-field 闭集，在读取字段前拒绝 unknown；合法 partial 和 ConfigLoader record-replace tests 通过。 |
| `R02-S1-CR-F02` added-definition/current-owner docstring closure | **closed** | added-definition 扫描 `89/issues=0`；无新增 loose callable。 |
| `R02-S1-CR-F03` 极小 diagnostic cap 截断标记 | **closed** | cap 1/14/15 分别得到有界且显式的 `…`、13 字符前缀加 `…`、1 字符前缀加 `...<truncated>`；未超限原样。 |
| `R02-S1-CR-CV-F01` signature-touched docstring closure | **closed** | 14 个 correction target 已补齐；最终扫描 `signature_touched=132/issues=0`，无行为修改。 |
| MiMo 初审 private-to-custom-port utility 临时投影 | **accepted observation / no S1 fix** | 这是保留既有 utility local/private 行为的 S1 过渡投影；S3 才从 typed config 同源读取两个独立字段。 |

## 新意见裁决

两路 re-review 均未提出新 material finding。Controller 对 observations 裁决如下：

1. 顶层 unknown key 只报告稳定的首个字段、nested resource group 报告全部字段：**no fix**。两处 owner 都执行正确的 fail-fast；产品 contract 未承诺诊断聚合形式，统一风格不是当前语义缺陷。
2. `_bool_default` 与 numeric parser 在存在性 guard 后分别使用下标和 `.get()`：**no fix**。类型与运行行为等价，属于无故障证据的风格意见。
3. 显式 JSON `null` 从旧的静默默认变为校验失败：**accepted intended behavior / no fix**。accepted plan 明确要求 present value 精确校验；`null` 不是缺失值，测试已覆盖。
4. 三个 owner 文件覆盖率接近 80% 下限、synthetic Playwright doubles 与顺序敏感测试：**accepted verification triggers for S2, not S1 defects**。S2 修改相同 owner 时必须重新执行逐文件覆盖率和行为矩阵，不要求为 S1 扩张代码或测试。
5. utility-local diagnostic `1_024`/`80` 与 private-to-custom-port 临时投影：**owned by R02-S3**。不得在 S1/S2 提前删除或形成第二套 config owner。
6. baseline test lambda：**out of scope / no fix**。不是本 slice 新增或修改的语义。

## Owner、边界与安全复核

- config raw JSON 的唯一 parser owner、typed immutable snapshot、三个 child resource budget owner 和 diagnostic projection owner 均已同源传播；未保留旧 `WebResourceBudget` 或下游 default/fallback。
- custom port 与 private network 在 typed policy 和业务消费者中独立；S1 没有提前修改 sender proxy/proof、browser/private coupling 或 storage-state lifecycle。
- DNS/redirect/peer proof、dangerous/mixed address fail-closed、filesystem containment、symlink 防护、challenge detection、resource budget 和 diagnostic redaction 均保留。
- 本 slice 没有设计或实施统一 tool authorization framework；Issue 178 storage lifecycle、R02-S2/S3、R03 以及其它 deferred Issue 均未偷带。

## 验证证据

- 最终允许三文件 suite：`249 passed, 1 skipped`。
- 九个修改 production 文件逐文件 coverage：`80%`-`100%`，总计 `84%`。
- pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- added-definition：`89/issues=0`；signature-touched：`132/issues=0`。
- legacy owner、owner propagation、deferred scope、retained security 与 loose-callable scans：通过。

## Verdict

**PASS**。

R02-S1 全部 accepted implementation/code-review/controller-validation findings 已关闭，无新 material finding、无 blocking question。允许 Controller 创建 accepted local R02-S1 commit；该 commit 仅授权随后按已接受 R02 plan 进入 R02-S2 implementation，不授权 S3、Issue 178、R03 或统一 tool authorization framework。
