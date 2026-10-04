# PR197 F6 计划修订同版复审：总控裁决

当前范围：计划 SHA256 `57ab49b7648444629db3290b7d8ba54b397b63f1495fe70fd0e0d18c71d7f1b1`，冻结62current/62originals。MiMo37469尚未终态，不能接受计划。DS22262已outer0，root已核结构化输出、完整报告、stderr、canary及124件身份；以下是第一路证据裁决，不是完整 gate pass。

## DS 交付与证据限制

runtime/provider/model=claude/ds-flash/deepseek-flash[1m]（实际 modelUsage 元数据）。label=`pr197-f6-plan-fix-rereview-dsflash-20261001-01`；托管22262 outer0、JSON success/is_error=false/terminal completed、106turns。原JSON/独立stderr位于 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.9LvbwJ`。stderr精确 unrecognized_model 前缀仅warning。

正式报告 `docs/reviews/plan-review-20261001-124127.md`，SHA256 `c9baa40d2ad7ea9b3e0dbcf2117f121c54b03f4bb1a9e89ac473abd4ad578543`，报告token与expected字节匹配。默认Claude仅summary_only，无逐命令轨迹；报告末检双流/exit实际存在，root独立重算62current/62originals全匹配，并实读关键source/test/plan。首检错误相对路径和zsh复合echo错误由作者披露；summary-only不能证明所有中间失败均已观察，未伪造全轨迹。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: partial
warnings:
  - stderr 精确模型元数据 warning
  - 作者披露首次 originals 路径少一级，改绝对路径恢复；root124身份独立核查
  - 作者披露 zsh echo复合命令失败，重读恢复；无逐调用轨迹
  - T5 的SEC抛点reason对应错误，root以真实源码替代
  - HEAD123fad5d八文档并非全非冻结，其中两冻结文件已提交但字节未变
evidence_gaps: []
retry_class: none
```

partial 表示不采纳报告的全部叙述与通过标签；下面每项结论有 root 的直接证据，所需输入身份与关键取证完整。错误原报告不改写，不另派模型用票数纠正事实。

## Finding 裁决

**DS-PR2-N1：低，rejected-with-reason，非新增必修。** 真实 `test_direct_download_preserves_every_preflight_reason` 的6161行旧全集合断言在enum扩容后必须迁移，但最新计划E尾句已经明确“预检enum集合断言仅要求原确切四元素子集，增加两值后禁止旧全集合断言倒逼兼容”，且该test文件已列入原10文件范围。新增两值另有封闭分类测试；原map keys全集合与四个参数化投影断言保持。实施者不需要新的行为或owner选择就能按这一明确指令修改现成断言。仅补测试名字属于清单表达偏好，不是 code-generation-ready 的实际缺口；不得把已经规定的迁移再造为阻塞finding。实施任务仍点出真实node以方便执行，属于现成合同交接，不改变plan语义。

**报告T5 reason对应：拒绝该事实叙述。** root实读SEC single-filing238/275/383/505：238 PhaseA和505 PhaseB是UNSAFE_PUBLICATION；275 registry和383 6-K repair rejection是SELECTED_REJECTED_REPAIR_REQUIRED。报告“前两者unsafe/后两者selected”错误。当前计划D3四路径、原cause/reason保全和既定pair catch已正确，不需修改产品或plan来迎合报告。

**A1–A4：DS核证支持修复，最终状态待MiMo及root综合。** root重核显式cancelled/ok与日志归属、CN postrepair同try三类型、SEC四抛点和6-K/PhaseB迁移、CN PhaseB完整原断言保持；这些支持与此前直接核收一致。当前仍未接受plan，不实施产品，不以pass-with-risks代替门禁。

Residual：动态验收留后续F6-S1；job schema/durable reason、publication indeterminate、早期取消统计差异保持既有独立owner和destination；F5Q1待用户。最终真实CLI CI与oracle/scenarios/readiness未执行。

## 同版完整最终裁决（MiMo37469已终态）

MiMo label=`pr197-f6-plan-fix-rereview-mimo-20261001-01`，Claude/MiMo，actual modelUsage=mimo-v2.6-pro[1m]；托管37469 outer0，69turns，有效JSON success/is_error=false/terminal completed，result/report/expected token匹配。独立stderr只有精确unrecognized_model warning。原输出 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.VaP75y`。完整报告 `docs/reviews/plan-review-20261001-125754.md` 已全文读取；冻结124身份root再次重算全匹配，末检独立双流、PYEXIT=0实际核收。default Claude仍summary_only，未伪称逐事件轨迹。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - stderr 精确 unrecognized_model warning
  - 中间read仅汇总可见；root独立实读关键source/tests/plan并核124身份
evidence_gaps: []
retry_class: none
gate_decision: pass
plan_sha256: 57ab49b7648444629db3290b7d8ba54b397b63f1495fe70fd0e0d18c71d7f1b1
```

**总控 plan re-review pass；A1/A2/A3/A4均 accepted / 已修复（计划合同）。** root依据实际设计和独立源码/测试证据接受，不依据两路投票或通过标签。A1正常与abort status及日志归属闭合；A2三类型同try保前缀闭合；A3四真实抛点及6-K/PhaseB迁移守恒闭合；A4 CN PhaseB reason迁移及private/public owner边界闭合。DS列名建议维持rejected-with-reason；MiMo也直接核到6161迁移已被计划140行明确规定。全部原accepted计划finding已修，无新的阻塞业务/schema/owner问题。

MiMo六项近似候选按原合同收口：churn确认前缀布局和总计已定、日志取同次结果summary、JsonValue静态适配不逃边界、C.2封闭cause构造验证仍必须落实（不因D1未复述或测试少一个就删除合同）、旧合成行reason不顺带清理、E1输出示例由本轮新label独占目录覆盖。它们不是新增必修；owner=F6实施者按既定设计，超出既定行为的清理归既有待goal，不扩大slice。

下一入口：accepted plan commit→F6-S1 implementation。此pass只表示计划可实施，F6-P1与公共/工作流产品缺陷仍未修；动态pytest、逐8prod coverage≥80和非空fullpyright、四入口真实性必须由实施/审查核验。F3/F5和最终完整真实CLI CI未借此关闭。
