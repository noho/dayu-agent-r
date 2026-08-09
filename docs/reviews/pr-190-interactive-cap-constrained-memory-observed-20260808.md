# PR 190 interactive cap-constrained memory replacement 观察报告

## 1. 报告身份

- 场景：`interactive.interactive.g06.cap-constrained-memory-replacement@1`
- 状态：真实行为已观察，等待用户裁决
- Target commit：`23097230861fe4acad730054e0ba9818ca42bd4f`
- Branch：`codex/interactive-oracle`
- 有效 evidence root：`/Users/leo/workspace/.dayu-cli-ci/interactive-cap-gap-r2-20260808-JdukC2`
- 被排除的无效尝试：`/Users/leo/workspace/.dayu-cli-ci/interactive-cap-gap-20260808-vQSiPE`
- 运行时间：2026-08-08 23:12:51–23:24:57 CST
- Production CLI：`/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli`
- CLI 文件 SHA-256：`ab7d7ba9f7ac8595296b8c53fb139a2af3267616cb0ce5088e3ce6f4a8071691`
- Python：3.11.15
- Provider / model：真实 MiMo / `mimo-v2.5-pro-plan`；公开 compactor identity 为 `mimo` / `mimo-v2.5-pro`
- Provider、tool：未使用 mock 或 fake

本报告只记录观察事实，不裁决行为正确性。

## 2. 运行前状态

从 fresh CI-owned root 创建 workspace，只复制：

- init 生成的 workspace `config/`，明确排除其中旧 `.dayu`；
- 真实 AAPL corpus 的 `portfolio/`。

装配前 workspace 不存在 `.dayu`、Host SQLite、EventLog、Memory、Session 或 Run。关键输入摘要：

- `config/models.json`：`dc924f842be81599c00606dae0cbe464d6f766147581d4bbb4167e83044e5f2b`
- AAPL processed manifest：`7e5512a11493e0177c8cd803526aab4060569efe37f8b2285b8a9c50ec3ebb74`
- 初始 cap profile：`00a3768c7bdfbdeb47f0d3bec5754634410bcf5cbb2e39e9f4c847ad8793d11d`

Memory policy 从 Session 创建到结束保持不变：

- `session_summary_char_cap=512`
- `evidence_fact_item_cap=2`，`evidence_fact_char_cap=1024`
- `answer_anchor_item_cap=1`，`answer_anchor_char_cap=512`
- `forward_intent_item_cap=1`，`forward_intent_char_cap=512`
- `reference_continuity_item_cap=1`，`reference_continuity_char_cap=512`
- `selected_recent_window_item_cap=32`
- `selected_recent_window_char_cap=131072`
- `selected_recent_window_turn_floor=4`

前 12 个 Runs 使用 `soft_threshold_context_ratio=0.65`。材料自然老化到 recent window 达到 32 项后，只把 soft threshold 改为 `0.001`、hard threshold 改为 `0.5`；Memory policy canonical JSON SHA-256 在修改前后均为 `ae056f93f2172bde2a7b48b04f3acf140026eeaabcea47c0314d23239a4f9c9e`。成功 compact 后恢复 0.65/0.82，Memory policy digest仍不变。

## 3. 精确调用与输入

三个进程段均使用相同生产入口：

```text
dayu-cli interactive
  --base /Users/leo/workspace/.dayu-cli-ci/interactive-cap-gap-r2-20260808-JdukC2/workspace
  --label cap-gap-final-r2
  --detail
  --no-thinking
  --model mimo-v2.5-pro-plan
  --log-level info
  --log-file /Users/leo/workspace/.dayu-cli-ci/interactive-cap-gap-r2-20260808-JdukC2/evidence/dayu.log
```

每个进程都通过 POSIX PTY 真实输入，最后在空 composer 连按两次 Ctrl+C；三个进程 exit code 均为 130。

### Segment 1：建立并老化真实材料

依次提交 12 个 Runs：

1. 强制通过真实财报工具读取 AAPL FY2025 10-K：FY2025/FY2024 net sales、operating income、net income，FY2025 iPhone/Services 销售变化及一项风险。
2. 确认 FY2025 为当前年度、FY2024 为历史比较。
3. 确认 FY2025 total net sales 416,161 million USD。
4. 确认 FY2025 operating income 133,050 million USD。
5. 确认 FY2025 net income 112,010 million USD。
6. 确认 FY2025 iPhone net sales 209,586 million USD、同比增长 4%。
7. 确认 FY2025 Services net sales 109,158 million USD、同比增长 14%。
8. 确认供应链集中、单一来源与关税是已披露风险。
9. 记录后续比较 FY2025/FY2024 利润率的待办。
10. 确认后续引用数值需保留期间、单位和 SEC 来源。
11. 确认材料只来自已加载的真实 AAPL SEC 财报，不使用 web。
12. 确认 AAPL 是唯一分析对象，下一步只整理既有材料。

Segment 1 结束时：12/12 canonical Runs 为 `RUN_SUCCEEDED`；最新 Memory snapshot 的 `selected_recent_window` 正好达到 32 项，最早保留项为 EventLog sequence 28，sequence 2–27 的完整早期材料已离开 recent window。

### Segment 2：两次真实 compaction operation

Run 13 输入：

```text
不要调用工具。整理并继续本会话已有的 AAPL 分析：回答当前年度三项合并指标、
iPhone 与 Services 变化、已披露风险和后续待办；只使用已有真实材料，不新增事实。
```

Run 14 输入：

```text
不要调用工具。再次整理现有会话记忆：只列出有真实 SEC 证据的两项最重要财务事实，
并保留当前年度、来源和后续利润率比较待办；不要添加其它内容。
```

### Segment 3：跨进程 reconnect

Run 15 输入：

```text
不要调用工具。重连后请回答：当前分析年度是什么，两项已保留的关键财务事实是什么，
SEC accession 是什么，后续待办是什么？
```

## 4. 屏幕观察

### 4.1 正常材料阶段

Run 1 屏幕逐项显示真实工具 request/response。最终工具统计为 10 个 call，均有 Host accepted result；模型给出：

- FY2025/FY2024 total net sales、operating income、net income；
- FY2025 iPhone 209,586、+4%；
- FY2025 Services 109,158、+14%；
- 供应链/单一来源/关税风险；
- SEC EDGAR Form 10-K accession `0000320193-25-000079`。

后续 11 个短 Runs 均能在不调用工具时复述对应既有事实。

### 4.2 第一次 compaction：repair exhaustion + fallback

屏幕依次显示：

```text
Activity: started 上下文压缩开始
Activity: failed 上下文压缩未接受 severity=warning   # 共 5 次
Activity: failed 上下文压缩失败 quality_check_rejected severity=error
Activity: info 上下文预算已评估
Activity: in_progress 运行已开始
```

五次 rejection 的日志诊断依次为：

1. `non_canonical_source_label_order` + `source_kind_mismatch`
2. `invalid_json`
3. `non_canonical_source_label_order`
4. `empty_semantic_output`
5. `empty_semantic_output`，`repairable=False`，下一步 `fail_compaction`

EventLog sequence 266 为唯一 `CONTEXT_COMPACTION_FAILED`：

- `attempt_count=5`
- `failure_reason=quality_check_rejected`
- `retry_repair_budget_exhausted=true`
- `fallback_policy_decision=deterministic_recent_window`
- `fallback_action=dispatch`
- fallback 估算 493 tokens，在 hard budget 内
- fallback selected 8 个 raw turns

RunInput manifest sequence 267：

- trigger=`context_governance_resolved`
- `context_fallback_decision_ref` 非空
- `compact_artifact_refs=[]`
- message count=10
- LLM-facing 普通消息只含最后 4 个 user/assistant turns 与当前输入，没有早期精确财务数据和风险工具证据。

普通 Run 随后成功并有 final answer，但回答行为是：

- 把用户所说的“三项合并指标”理解成三项利润率，并全部写成“待计算”；
- iPhone/Services 精确金额与同比均回答为“待提取”；
- 输出供应链、竞争、国际运营、产品集中、隐私安全、知识产权、法律法规等风险；这些详细风险文本不在本次 runner input 的 10 条消息中；
- 进程未退出，REPL 可继续；该 Host Run 最终为 `RUN_SUCCEEDED`。

### 4.3 第二次 compaction：repair 后 accepted

屏幕依次显示：

```text
Activity: started 上下文压缩开始
Activity: failed 上下文压缩未接受 severity=warning
Activity: completed 上下文压缩完成
Activity: info 上下文预算已评估
Activity: in_progress 运行已开始
```

第一次 proposal 因 `invalid_json` 被拒绝并进入 `retry_semantic_repair`；第二次 proposal 被接受。普通 Run 最终回答：

- 当前年度 FY2025；
- Total net sales 416,161 million USD；
- Net income 112,010 million USD；
- SEC accession `0000320193-25-000079`；
- 后续比较 FY2025/FY2024 利润率。

### 4.4 reconnect

退出 Segment 2 后，以相同 label 启动 Segment 3。Run 15 未调用工具，屏幕回答完整复述：

- FY2025；
- 416,161 million USD；
- 112,010 million USD；
- accession `0000320193-25-000079`；
- 利润率比较待办。

## 5. Host / SQLite / Tool Trace 观察

### 5.1 Session 与 Run

- `host_session_slots` 只有一个 `cli.agent.cap-gap-final-r2`，绑定 `session-0bb1006657f04c93982a0327eae40856`。
- `host_sessions` 只有该 Session，状态 `open`。
- 15 个 Runs 全部为 `succeeded`，terminal sequence 范围 3–312。
- Context terminal 计数：2 `CONTEXT_COMPACTION_REQUESTED`、6 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`、1 `CONTEXT_COMPACTION_FAILED`、1 `CONTEXT_COMPACTED`。

### 5.2 真实 compactor identity

公开 Tool Trace 共投影 7 个 compactor responses：

- operation 1：attempt 1–5 全部 `attempt_rejected`；
- operation 2：attempt 1 `attempt_rejected`，attempt 2 `accepted`；
- 7 次 effective provider/model 均为 `mimo` / `mimo-v2.5-pro`；
- 每次均有独立 runner run id、iteration id、proposal manifest ref/digest 和 terminal sequence；
- provider-native request id 在该 provider 路径为 `unavailable`，没有从其它字段猜测或补偿。

### 5.3 Accepted artifact 与 caps

唯一 accepted compact：

- EventLog sequence：286
- Artifact ref：`compact-artifact:fadba32fd0dc5962aabe5664e857ddee1b93589ea72699dd27e3e6423185bde6`
- Artifact 文件 SHA-256：`fadba32fd0dc5962aabe5664e857ddee1b93589ea72699dd27e3e6423185bde6`
- Artifact schema：5
- source boundary：28 labels
- represented：10 labels
- omitted：18 labels
- represented + omitted 是 source boundary 的无重复精确分区；missing/extra 均为 0。

Policy usage audit：

| Semantic Memory | actual | cap |
|---|---:|---:|
| session summary chars | 209 | 512 |
| evidence facts items | 2 | 2 |
| evidence facts chars | 157 | 1024 |
| answer anchors items | 1 | 1 |
| answer anchors chars | 117 | 512 |
| forward intents items | 1 | 1 |
| forward intents chars | 77 | 512 |
| reference continuity items | 1 | 1 |
| reference continuity chars | 60 | 512 |

Accepted replacement 包含：

- session summary：AAPL FY2025、416,161、112,010、accession 和利润率待办；
- 2 个 EvidenceFacts：FY2025 net sales 416,161 与 net income 112,010；
- 两个 EvidenceFacts 均绑定同一个非空 production `read_section` evidence ref；
- 1 个 answer anchor、1 个 forward intent、1 个 reference continuity；
- 没有把无 evidence ref 的内容升级为 EvidenceFact。

### 5.4 Artifact、Memory、RunInput、reconnect 同源

最新 durable Memory snapshot 中：

- 2 `evidence_backed_fact`
- 1 `answer_anchor`
- 1 `forward_intent`
- 1 `reference_continuity`
- 1 `session_summary`
- 18 `selected_recent_window`

上述五类 Semantic Memory 的文本、数量和 evidence ref 与 accepted artifact 一致。

RunInput manifest sequence 287（accepted 后同进程）和 sequence 301（重连进程）都：

- trigger=`context_governance_resolved`
- 引用同一 compact artifact ref 和 digest；
- system message 中投影相同的 Summary、两项 Verified EvidenceFacts、Answer Anchor、Forward Intent 和 Reference Continuity。

重连后的屏幕答案与这些投影一致。

## 6. Tool Trace 其它观察

公开 analyzer：

- 15 Runs
- 10 tool calls
- 7 compactor responses
- 0 invalid records
- 6 `host.context_compaction_attempt_rejected` warnings
- 1 `host.context_compaction_failed` error
- 10 `host.duplicate_governance` infos
- 1 `tool.truncation_not_followed` warning

后两类已分别由既有 Issue 192 和 Issue 191 追踪，不改变本报告中的 compaction 事实。

## 7. 文件、日志与敏感信息

创建了 workspace `.dayu/`，其中包括 Host SQLite、runtime lane SQLite、terminal cursor、Tool Trace cold JSONL、runner-input artifacts 和 compact artifact。未删除或修改 corpus。

主要 evidence：

- `evidence/segment-01.typescript`：`e3e52a00b6b3a4db8f697f95b710f990c371459903096c8b70073452eebd777c`
- `evidence/segment-02.typescript`：`6774aeaa21a6384d1073902a69ad8ccef8f9a11b687de6a11fa268a2f4ae4246`
- `evidence/segment-03.typescript`：`cd6a2563c06dad00897cbe7f22907ff3d873ac4ed7b986c9ca7538def0f2cbc9`
- `evidence/dayu.log`：`e8a2c899ecc8bc3fa34d798ce969ae8808b500193548b91142e1787e1557ad11`
- `evidence/tool-trace/tool-trace-analysis.json`：`9d5fc78538b324246fe3eeac7c9f2017b9af2aa8c57e5f911bc51334d037e234`
- `evidence/tool-trace/tool-trace-analysis.md`：`31a09ce0f620841101c6a2190f9dd55b7d3fa72d5f15322070e68ec46370a32d`

上述 6 个 evidence 文件以当前进程可用 credential exact values 和 Authorization/Bearer pattern 扫描，结果均为 0。Raw Host SQLite 保留在 CI workspace，不进入公开 evidence；Host SQLite 中允许存在 resolved credential 的既有用户裁决不变。

## 8. 被排除的第一次尝试

第一次 root `interactive-cap-gap-20260808-vQSiPE` 在已有 3 Runs 后才修改 Memory caps，导致 memory policy digest 改变。新 policy snapshot 只包含修改后的两项 recent material；普通阶段虽命中 `compact_soft_threshold`，但没有 `CONTEXT_COMPACTION_REQUESTED`，Tool Trace `compactor_responses=0`。该尝试的前置状态不符合“从 Session 创建起固定 caps”，因此不用于本场景裁决，也未被重标为成功。

## 9. 待用户裁决

1. 两个 compaction operation 的 Host 行为——可判定的非法/不合格 proposal 必须拒绝、bounded repair，耗尽后 deterministic fallback 并继续 REPL；后一次 repair 成功后 accepted——是否符合预期？
2. accepted replacement 严格满足 caps、represented/omitted 精确分区、EvidenceFact 必须绑定真实 evidence ref，是否符合预期？
3. accepted artifact、Memory、RunInput 和 reconnect 同源，是否符合预期？
4. 第一次 repair exhaustion 后的普通回答没有获得早期精确材料，却输出多项本次 runner input 中不存在的风险陈述；该用户可见回答是否可接受？
5. provider-native request id unavailable 是否仍作为 limitation，而不阻止本场景裁决？
