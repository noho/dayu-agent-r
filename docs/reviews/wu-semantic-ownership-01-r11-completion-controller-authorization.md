# WU-SEMANTIC-OWNERSHIP-01 / R11 completion handoff Controller authorization

## 1. Gate

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- gate：R11 accepted implementation commit后的artifact-only completion handoff。
- 不是新 WU、R12、aggregate deepreview、push或PR gate。

## 2. Immutable commit truth

- accepted implementation commit：`de4cf116c20c687f38cd3474b53949b0aedee5ab`
- parent：`7972c3c0ba8628173fc91c362b9394655f60678e`
- tree：`cf1d1aa6e205361c514a1c2522836459cb46a36a`
- message：`cli: accept R11 upload script remediation`
- exact commit path count：`39`
- cumulative product/test/README/packaging/workflow paths：`22`
- post-commit working tree：empty
- post-commit staged tree：empty

该commit只接受R11 implementation，不关闭R11/umbrella，不授权R12/push/PR。真实Windows run继续为
`PENDING_RELEASE_BLOCKER`。

## 3. AgentCodex writable scope

只允许新增：

`docs/reviews/wu-semantic-ownership-01-r11-completion-codex.md`

禁止修改任何production、tests、README、packaging、workflow、plan、control、既有review artifact、constraints、
design或其它文档；禁止stage/commit/push/PR/R12。

## 4. Mandatory completion ledger

AgentCodex必须基于accepted commit tree与全部最终artifacts形成self-contained handoff，至少记录：

1. accepted plan链及最终plan SHA；
2. accepted implementation commit的SHA/parent/tree/path count与exact 22-path product manifest；
3. R11全部plan/implementation/review findings的最终状态，尤其：
   - `R11-DS-F01` rejected/no-fix；
   - `R11-DS-F02/F03` closed；
   - re-review new material finding = 0；
4. tests、三项POSIX real smoke、fresh exact-wheel、coverage、pyright、Ruff、diff/scans的最终证据；
5. 两项HEAD-existing Service baseline failure的精确分类，不冒充full suite green；
6. README/packaging/placeholder closure；
7. 保留/修改过的安全相关行为：source/output containment、symlink、atomic replace/rollback、argv injection、
   secret non-persistence；明确未实现统一tool authorization、workspace trust或shell sandbox；
8. deferred Issue 142/151/175/177/178、Topic 8/9、真实Web/WeChat/render与R12未偷带；
9. residual ledger与owner/destination；
10. Windows `PENDING_RELEASE_BLOCKER`的触发方式、required artifacts/oracles、失败回到R11 owner fix/review的规则；
11. 明确R11 local completion可验证但不等于cross-platform/release closure，也不关闭umbrella。

## 5. Validation 与 stop

至少复核commit元数据、39-path manifest、22-path product subset、artifact hashes、working/staged empty、
`git diff --check HEAD^ HEAD`、deferred/security边界和final finding counts。若commit tree/path或finding ledger不一致，立即
stop；不得修改历史artifact来“对齐”。

完成后停在Controller checkpoint；下一gate只能是Controller completion validation，之后才可能做artifact-only completion
accepted local commit。
