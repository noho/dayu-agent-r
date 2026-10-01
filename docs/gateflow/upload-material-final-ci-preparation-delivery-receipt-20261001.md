# 最终 upload_material CI 预备计划：总控交付核收

日期2026-10-01；workspace `/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`。artifact path：`docs/gateflow/upload-material-final-ci-preparation-delivery-receipt-20261001.md`。

## 结论与范围

接受 Sol13693 的**预备 proposal 交付**，不是 accepted final plan、完整 mandatory matrix、oracle/scenarios登记、readiness或真实CI pass。正式计划 `docs/gateflow/upload-material-final-ci-preparation-plan-20261001.md`，SHA `72c0205a1c2b9737c9cf235154d3dbc166cc0de776ea20760fbdd57db76dbd71` 已全文读取；36项裁决映射仍须后续独立审查与root最终核验，不能把候选predicate直接写正式registry。原件不改。

用户已明确授权全部修复后完整真实CI。此proposal只准备依赖、来源、场景族与取证步骤，没有实施原队列，真实CI均not-run。用户已有具体裁决仍为最高authority；未来parser/实现不得倒逼改oracle。F6在本任务输入时双审在途、当前已收两路并由Sol8619修A1/A2，是不同窗口，不是报告错报当前状态。

## 生命周期与必需证据

runtime=codex/provider=gpt-6-sol，label=`pr197-final-ci-preparation-sol-20261001-01`；独立output/stderr/last在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.hLsWbz/`。托管outer exit0；107行合法JSONL、明确turn.completed、47 completed命令均外层exit0、无error/failed item；stderr空。完整stream已核，实际model metadata缺失记unknown，canary逐字匹配。

root逐件重核41current+41originals、85交付artifact（含双流/command/exit/plan）hash全匹配；manifest SHA `c008c40064eae2b096cbd693e5d3679e4aa1393da744067dcec9cb537a44867b`。26额外源码首末窗口hash由原证据保持，当前25仍同；唯一CLI output已在任务完成后被获准F6 writer修改，其任务末hash与F6修复前独立original相同。root首次假定26当前均恒定的断言exit1；后按真实时间窗口与F6修复前copy恢复核验exit0，不回滚修复、不把原失败伪写通过。这不影响41冻结输入或85交付字节；正式最终计划必须重新绑定最终源码。

准备parser命令真实exit0/stderr空，14leaf；两个registry实际material条目仍0。root既有parser/registry/source观察及本次真实命令相符。实际仓库目前仅 `utils/cli_ci_run_observation.py` 匹配CLI CI工具检索，没有冒称已有一键完整campaign runner/readiness validator。报告早期仓储源码首读漏hash限制及后重读证据保留，不追认首次身份。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - model metadata缺失，unknown
  - test -e 内层exit1为新增目标不存在的预期检查，不是CI失败
  - 大读取输出窗口截断后相关关键段已独立重读，原双流保留
  - 首次仓储额外源码先读后hash的限制不追认，后身份绑定重读有效
  - root末核将已获准F6后续CLI改动误当历史窗口漂移，已按修复前copy恢复
evidence_gaps: []
retry_class: none
```

独立数据 `workspace/tmp/pr197-controller-collection-20261001/final-ci-preparation-delivery-receipt.json`。tool_trace完整只针对真实外部JSONL；准备命令中capture_output包装内层非零也按ledger解释，不以包装exit0冒称所有内层0。没有新持久Python脚本，产品/test/README/正式registry均未修改。

## 后续裁决边界与残余分类

- 正式最终CI plan/matrix/inventory/动态discover、全部36predicate的独立审查与最终authority重绑定：covered by later approved slice，owner=root最终CI收口；该proposal交付不是执行门禁。当前修复优先队列不因此转到CI执行。
- 真实市场/XBRL input来源、hash/version、受控依赖/taxonomy/部署OS：covered by later approved slice，owner=root corpus/Documents runtime。具体新来源当前未冻结是取证前置；用户已授权真实最终CI，不把它扩大成必须重新索取通用网络许可。后续先核既有公开来源和授权可读资产；只有确实缺少必须输入/新支持范围才提出具体问题。不得要求寻找已删除旧Raw，也不得用合成替代必要真实正样本。
- proposal关于空report_date/tombstone create/恢复/timeout等“待决”仅为候选边界：requiring new issue or explicit user decision **仅在最终in-scope且核所有既有approved contract后仍未定义时**；不能据此重开用户裁决或提前另造阻塞WU。root未接受这些候选为新的业务修复要求。
- 必要CI采集/验证harness：covered by later approved slice，owner=CLI CI工具/root。后续最小实现与实际type验证，不用mock或局部pytest替真实CLI；不得借证据工具新增产品fallback/public projection。
- F5 Q1：requiring explicit user decision，owner=用户具体业务选择/F5既有队列，当前未答。全部runtime/provider授权及继续任务不代选。
- 历史Raw删除：无法复核的历史证据限制，owner=证据/root新run lineage；新矩阵完整重建，旧160不当上限。
- 最终PR描述与同版PR review/closeout：covered by later approved slice，owner=root PR197收口；旧隔离worktree描述必须按当前唯一开发树更新，现有Closes #198及已完成证据保留，不merge/main。

下一入口：继续当前F6必要fix和同版双审；CI proposal后续按完整范围独立审查/最终重绑定。真实CI、正式material registry与readiness均未完成，不报告任务大目标完成。
