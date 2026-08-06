# PR 190 F13 final closeout

## Metadata

- work unit：PR 190 F13 Compaction rolling EvidenceFact provenance
- branch：`codex/interactive-oracle`
- base：`main@113ea34d47b95812d79aa31705949bbb46bc6061`
- reused draft PR：[#190](https://github.com/noho/dayu-agent-r/pull/190)
- PR state before closeout artifact：`OPEN`、`draft=true`、`mergeStateStatus=CLEAN`
- accepted final-review head：`57b553a2b916223568f83edb690a2b66d6ceb505`
- decision：`final-closeout-pass`
- formal replacement scenarios：`unadjudicated`
- blocking questions：None

## 1. F13 是否从 root cause 修复

是。修复位于 Host semantic owner，不是下游展示补偿：

- previous compacted EvidenceFact 不再只投影 previous compact event/ref；每个 fact 从上一
  `CONTEXT_COMPACTED.accepted_replacement.evidence_facts[*]` 携带原 claim 与逐 fact
  `canonical_evidence_refs` 进入下一轮 immutable source boundary。
- LLM proposal 与 Host accepted replacement 分离。LLM 对旧事实只输出 keep/omit label；Host
  从 boundary atom 原子复制 claim/ref，模型没有改写旧 claim 后借 provenance 的路径。
- 新 EvidenceFact 只能选择当前 `evidence_material`；Host 根据选中 material 计算逐 fact
  canonical refs。`CompactAcceptedEvidenceFactV4` 与 durable parser 均强制 refs 非空。
- accepted replacement 在 durable write 前接受完整 boundary binding、source kind、唯一
  membership、caps、coverage、aggregate/subset 与 root replay 校验。
- Memory、artifact、EventLog、Tool Trace、reconnect/next-round input 从同一个 accepted
  replacement 投影；failed/rejected/stale/late 路径没有第二 accepted materialization owner。

Mandatory owner tests覆盖 previous fact 原子保留、claim rewrite 消除、不相关 previous fact
laundering 阻断、empty refs reject、无工具证据用户/assistant 文本不升级、新 evidence 接受、
rolling/cap repair、repair exhaustion/fallback 非污染、stale/late single terminal、六端同源与
reconnect canonical-only。

## 2. Schema / prompt 是否变化及原因

有变化，按全新 schema 处理，无 compatibility layer：

- compactor input/output：v3 → v4；
- compact durable artifact：schema version 4 → 5；
- output proposal 新增必填 `retained_previous_evidence_fact_labels: string[]`；
- durable terminal 新增并严格要求 `accepted_replacement`；
- 每个 accepted EvidenceFact 自带非空 `canonical_evidence_refs`。

原因：旧 schema 让模型重写 previous EvidenceFact 正文，再由 Host 根据 label 猜 provenance；
该结构无法同时保证 claim 与旧 provenance 同源。v4 把旧事实职责降为 keep/omit selector，
Host 成为 claim/provenance atom 的唯一 owner。

LLM-facing prompt 已自足说明七个必填字段、类型、允许 source kind、keep/omit 语义、五类业务
内容、caps 与最小 JSON 示例；没有向模型暴露 canonical refs、event id、digest 或 Host
治理责任。prompt 不是唯一防线，所有强约束均由 Host typed barrier 实现。

## 3. Previous EvidenceFact provenance 如何保持

链路如下：

1. durable accepted terminal 保存 `accepted_replacement.evidence_facts`；每项包含 claim 与
   canonical refs。
2. 下一轮 `compact_material` 只从该 accepted replacement 机械投影
   `previous_evidence_fact` boundary atom，并携带原 claim/ref。
3. LLM 只能在 `retained_previous_evidence_fact_labels` 中选择 atom label。
4. `derive_compact_accepted_replacement_v4` 按 immutable boundary 顺序复制 atom 的原
   `readable_text` 与 `canonical_evidence_refs`；不读取模型重写正文。
5. durable parser 重新计算 proposal + boundary → replacement，并要求与 terminal payload、
   aggregate refs、artifact 完全相等。
6. Memory、Tool Trace、reconnect 与再下一轮 compaction 消费这个 replacement。

真实 MiMo observation 中，5 个 AAPL facts 在三次 accepted terminal、三个 artifact、最终
Memory 与 public Tool Trace 始终指向同一
`evidence:event-tool-result-accepted-2527bd9c73522f8ee606a3401041e5fe94f460567312aca2cf7371f1fdab867f`
（EventLog sequence 60，production `read_section`）。

## 4. 验证分层

### Test / static validation

- Host owner/integration：`2493 passed, 1 skipped, 6 deselected`
- Service assembly：`88 passed`
- final review focused tests：`267 passed`
- full pyright：`0 errors, 0 warnings, 0 informations`
- changed-file Ruff、compileall、JSON validation、`git diff --check`：passed

这些是 test/static evidence；其中 deterministic fake/mock 不是真实 provider 行为。

### Host observation

没有把 direct Host smoke 作为独立 scenario evidence。本 work unit 的 Host integration 由
owner/integration tests验证；真实 durable Host 状态则通过下面 production CLI run 的
EventLog、Memory、SQLite、artifact 与 Tool Trace 观察，归类为真实 CLI observation，而非
伪装成 interactive 的 Host smoke。

### 真实 CLI observation

- root：`/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX`
- production POSIX PTY `dayu-cli interactive`
- real provider：MiMo plan；terminal/public trace 为 `effective_provider=mimo`、
  `effective_model=mimo-v2.5-pro`
- production finance tools：`list_documents`、`get_financial_statement`、
  `query_xbrl_facts`、`get_document_sections`、`read_section`
- real corpus：冻结 AAPL 2025 10-K corpus
- 8 个 process segments，0 harness invalid；实际产生 3 个 attempt-1 accepted compact。

真实观察支持首次 evidence material、rolling atom provenance、最终 empty-ref fact=0、
21.7/18.2 EvidenceFact=0、Memory/artifact/EventLog/public Tool Trace 同源和 reconnect。

真实观察不支持 typed reject、repair、repair exhaustion、failed/fallback、stale/late 行为结论：
cap=1 时模型首轮合法输出 `session_summary=null`；无效 prompt 诊断也未诱发失败。原始
execution-index 的意图标签未修改，并由
`evidence/execution-index-f13-postfix.errata.json` 更正为实际 attempt-1 accepted 观察。

## 5. 是否使用 mock/fake provider 或 tool

- owner/integration tests：是，使用测试用 deterministic fake/mock；只作为 test evidence。
- 真实 CLI observation：否。provider、CLI、Host、finance tools 与 corpus 均为 production/
  real 路径。
- 未把 fake/mock test、Host smoke 或 diagnostic prompt 变体写成 formal CLI PASS。

## 6. 三条 formal replacement scenarios 状态

仍为 `unadjudicated`。本 work unit 没有修改 accepted Oracle、没有替用户裁决，也没有把
post-fix observation 升级为 formal acceptance。

Oracle 仍需独立证明：

1. unsupported correction 进入当前 immutable compact boundary 后不能升级成 EvidenceFact；
2. cap typed reject → bounded repair success，以及 repair exhaustion → deterministic fallback
   的 failed/rejected candidate 非污染；
3. stale/late result 单 terminal、public/canonical response identity、reconnect 只读最后一个
   canonical accepted Memory。

## 7. Oracle 下一步精确命令与证据入口

### 7.1 复跑当前 post-fix observation（不是 formal acceptance）

```bash
source /Users/leo/workspace/dayu-agent-r/.venv/bin/activate
OBS_ROOT=$(mktemp -d /Users/leo/workspace/.dayu-cli-ci/f13-postfix-rerun-XXXXXX)
PYTHONPATH=/Users/leo/workspace/dayu-agent-r/workspace/tmp \
  python /Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/harness-source.py \
  --run-root "$OBS_ROOT" \
  --repo-root /Users/leo/workspace/dayu-agent-r \
  --cli /Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli
```

该命令只复现本 closeout 的 observation matrix；其 F13O07 已知不会证明 exhaustion，不能
替代下面三条 formal scenario。

### 7.2 新 formal run 的 production CLI 入口

每条 replacement scenario 必须使用独立 fresh root/workspace；不要复用本轮 DB/session：

```bash
FORMAL_ROOT=$(mktemp -d /Users/leo/workspace/.dayu-cli-ci/f13-oracle-formal-XXXXXX)
WS="$FORMAL_ROOT/workspace"
CLI=/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli
"$CLI" init --base "$WS"
```

在真实 TTY 中对 init 输入 `mimo-token-plan`、Enter、Enter；然后复制已冻结的真实 corpus
到 fresh workspace（不得复制旧 `.dayu`、SQLite 或 Session）：

```bash
cp -R /Users/leo/workspace/.dayu-cli-ci/prompt-financial-20260731TqJFtTp/workspace/portfolio "$WS/portfolio"
"$CLI" interactive \
  --base "$WS" \
  --label f13-oracle-formal \
  --detail \
  --no-thinking \
  --model mimo-v2.5-pro-plan
```

Oracle 的 PTY harness 必须记录每个输入按键和 Host terminal trigger，并按 §6 的三组义务使用
独立 chain。若 MiMo 失败，保留整个失败 `FORMAL_ROOT`，再创建另一个 fresh root 使用
`deepseek-flash` init choice；不得覆盖或复用失败 workspace。

### 7.3 公开与 durable evidence 入口

每个 fresh chain 退出后执行：

```bash
"$CLI" tool_trace analyze \
  --base "$WS" \
  --output-dir "$FORMAL_ROOT/evidence/public-tool-trace" \
  "$WS"
sqlite3 "$WS/.dayu/host/dayu_host.sqlite3" \
  ".backup '$FORMAL_ROOT/evidence/dayu_host.sqlite3'"
shasum -a 256 \
  "$FORMAL_ROOT/evidence/dayu_host.sqlite3" \
  "$FORMAL_ROOT/evidence/public-tool-trace/tool-trace-analysis.json"
```

必须交付的入口：

- PTY `command.json`、actions/timeline、stdout/stderr/exit/timeout；
- `filesystem-before/after/diff.json`；
- SQLite backup 与只读 EventLog/Memory 查询；
- `.dayu/artifacts/compaction/sha256/*/*`；
- public `tool-trace-analysis.json/.md`；
- corpus/config/provider/model/CLI/harness SHA-256 manifest；
- 原始 execution index 与只增不改的 errata（如需）；
- 每个 operation 的 terminal-count 等式、逐 fact claim/ref 四端等式和 reconnect snapshot。

本轮可参考但不可 adjudicate 的证据入口：

- `docs/gateflow/pr-190-f13-s3-validation-and-real-observation-20260806.md`
- `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/run-manifest.json`
- `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/execution-index-f13-postfix.json`
- `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/execution-index-f13-postfix.errata.json`
- `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/final-dayu-host.sqlite3`
- `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/final-public-tool-trace/tool-trace-analysis.json`

## Residual risks

1. Oracle formal replacement scenarios 未裁决；若独立 run 发现偏差，应以新 evidence 开新
   Gateflow work unit，不篡改本轮证据。
2. public Tool Trace strict terminal identity resolution 当前为 bounded O(n) scan；这是已接受
   non-blocking performance residual，不影响 correctness。
3. provider request id 在 MiMo observation 中不可用；runner/client correlation identity 与
   terminal/event/artifact digest 仍完整。该限制已在 public report 标明。

## External action boundary

已执行：在当前 branch 提交 F13 code/tests/docs；普通 non-force push 到既有 PR190。

未执行：创建新 PR、merge、mark ready、approve、request reviewers、rebase、force-push、删除
branch、修改 Oracle acceptance 或覆盖失败 evidence。

## Final decision

`final-closeout-pass`。F13 implementation 与 Gateflow validation/review 已完成；PR190 继续保持
draft，三条 formal replacement scenarios 交回 Oracle 总控独立运行与用户裁决。
