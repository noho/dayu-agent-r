# F4-S1 A1/A2 fix 交付核收

## 派发终态

Sol label `pr197-f4-s1-fix-sol-20261001-01`，托管22860真实outer exit0；完整76条JSONL逐行可解析且turn.completed，stderr空。run_dir `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.xQKcsM`，独立output/stderr/last。provider gpt-6-sol，actual model未有权威metadata，保持unknown，不用token推断。报告 `docs/gateflow/pr-197-r1-f4-s1-deep-json-fix-20261001.md` 本轮token与expected/实读文件字节匹配，全文noindexcheck exit1双流空。

## root 独立核验

51 original逐件SHA匹配、43 readonly保持；candidate-audit全部current实际SHA一致、problems空。八allowed完整真实差异逐份走读：生产唯一行为变化是storage read_source_meta_view删冗余递归deepcopy，包本次fresh JSON对象；其它协议/adapter/type仅文案。原getter独立parse和业务字典投影生命周期提供独立公开观察。guard/完整枚举/成功前缀/首个原异常/即时list错误/其它identity与workflow保持。测试只取消私有中间返回值突变，保留屏障/计数/异常原对象，补公开get独立与真实commit跨发布深dict/list8/300/600回归。原plan仅同goal技术假设/对应验证更新，无业务改裁。

实际最终激活venv九模块 `pytest-verified-coverage` exit0 **794 passed / 3既有edgar warnings**，43.12s；`pyright-verified`默认全量exit0 **0errors/0warnings**。root读独立完整exit/stdout/stderr与coverage-verified.json：八生产文件100/81.51/100/84.76/96.70/100/91.82/92.82%，均>=80。大目录63%不是八owner文件指标。无需重复整个矩阵来冒称root本人自跑；实际事件、终态及同版源码均已独立绑定。

## 所有非零事件与恢复

- item16/JSONL33：修前focused exit1两600层RecursionError是有效回归反例；focused修后/最终19passed及最终794恢复。
- item24/JSONL46：rg残留deepcopy相关文字无匹配exit1，预期空搜索，非缺失关键来源。
- item22/JSONL47：首次default pyright exit1四条新增测试Mapping setitem类型错误。作者删除非法setitem测试调用，保留真实只读容器与公开行为合同；未用Any/cast/ignore绕过。最终同版full type0恢复。
- item28/JSONL55：审计错误要求旧HEAD完全相等，在root合法87df docs checkpoint报git identity。后实际祖先+19docs paths核验、冻结source/original字节保持，audit-recovered及audit-final exit0恢复。原失败保留，不回滚root提交。
- 各noindex普通diff exit1有差异、全文check exit1零双流均预期，无真正空白损伤。版本升级提示不是类型diagnostic，不升级依赖。

## 裁决

交付 **accepted**，A1/A2为已修候选，正式修复状态和code-review gate须同版MiMo/Kimi re-review验证；本receipt不提前pass。下一入口re-review。F4-R01集合唯一性仍需另行goal/用户决定，R02总扫描成本及事件跨窗观察为later WU；其余队列按既有owner，不顺带实施。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - 预期修前红测试保留，修后恢复
  - 新测试四条类型错误已真正修复并全量重跑
  - 临时审计旧HEAD过强假设经docs祖先/路径与冻结字节恢复
  - rg空搜索及noindex差异exit1不当成整轮失败
  - 实际model不可核验保持unknown
evidence_gaps: []
retry_class: none
```
