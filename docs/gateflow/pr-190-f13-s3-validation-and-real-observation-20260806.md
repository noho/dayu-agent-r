# PR 190 F13 S3 validation 与真实 CLI observation

## Gate 结论

本文件记录 implementation validation 与 post-fix observation，不执行 Oracle
formal scenario adjudication。三条 replacement scenarios 继续保持
`unadjudicated`。

当前实现的 owner tests、Host integration、完整 pyright 与静态校验通过；真实 MiMo
interactive CLI 观察到了首次 accepted compact、两次 rolling compact、previous
EvidenceFact 原子保留、canonical provenance 跨 compact 传递，以及最终 Memory、
artifact、EventLog、public Tool Trace 的 accepted EvidenceFact 同源。

本轮没有真实观察到 repair、repair exhaustion、failed compaction 或 stale/late
result：cap=1 的请求由模型首轮直接输出合法 `session_summary=null`；原计划用于诱发
无效输出的 workspace prompt 诊断变体没有使 provider 输出失败，第三次 compact 仍为
attempt 1 accepted。相关结论只能引用 owner tests，不能写成真实 CLI 行为通过。

## 目标提交与运行边界

- Git branch：`codex/interactive-oracle`
- observed commit：`e4c290c88e5ce853251e236e4422023889f6884a`
- observation root：
  `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX`
- run manifest：
  `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/run-manifest.json`
- execution index：
  `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/execution-index-f13-postfix.json`
- execution index SHA-256：
  `2c890d19dba720e316d0dca385dec57415c01130d294560083b7d4c1185ce003`
- execution index errata：
  `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/execution-index-f13-postfix.errata.json`；
  原 index 未修改。errata 明确把 F13O07 的三个 coverage intent 标签更正为实际
  observation：attempt 1 accepted，未触发 repair、exhaustion 或 fallback。
- captured harness：
  `/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/harness-source.py`
- harness SHA-256：
  `ce659ce272409017028ac26da5287d5a6eabb0b1f01b7290372ddd18ec3179cc`
- production CLI：
  `/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli`
- CLI SHA-256：
  `ab7d7ba9f7ac8595296b8c53fb139a2af3267616cb0ce5088e3ce6f4a8071691`
- provider：init choice `mimo-token-plan`，interactive 显式
  `--model mimo-v2.5-pro-plan`；terminal payload 与 public Tool Trace 观察到
  `effective_provider=mimo`、`effective_model=mimo-v2.5-pro`。
- corpus：
  `/Users/leo/workspace/.dayu-cli-ci/prompt-financial-20260731TqJFtTp/workspace/portfolio`
- tool path：production interactive scene 的 `fins-read` 工具；真实调用为
  `list_documents`、`get_financial_statement`、`query_xbrl_facts`、
  `get_document_sections`、`read_section`。
- mock/fake：本次真实 CLI observation 未使用 mock/fake provider 或 tool；owner
  tests/integration tests 中存在测试用 deterministic fake/mock，不能与真实 observation
  混写。

真实运行命令：

```bash
source .venv/bin/activate
python workspace/tmp/f13_postfix_real_cli_observation.py \
  --run-root /Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX \
  --repo-root /Users/leo/workspace/dayu-agent-r \
  --cli /Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli
```

结果：8 个 PTY process segment 均 `exit_code=0`、`timed_out=false`，
`harness_invalid_count=0`。这只表示 harness 完成，不能单独解释为业务 PASS。

## Tests 与静态验证

以下均为 test/static validation，不是真实 provider behavior：

- `pytest -q tests/host tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - `2493 passed, 1 skipped, 6 deselected`
- `pytest -q tests/service/test_host_assembly.py`
  - 初次发现一个旧 prompt 自然语言短语断言；按 v4 owner contract 更新为断言
    `最终五类业务语义不能全部为空` 后，`88 passed`
- 完整 `pyright`
  - `0 errors, 0 warnings, 0 informations`
- changed Python `ruff check`
  - passed
- `python -m compileall -q dayu tests`
  - passed
- changed JSON file list为空；schema/template JSON validation 已由 owner tests覆盖
- `git diff --check`
  - passed

owner tests 覆盖但本次真实 CLI 没有直接观察的边界包括：typed reject、bounded
repair、repair exhaustion、deterministic fallback、failed candidate 非污染、stale/late
result 单 terminal、reconnect 只读 canonical accepted Memory。

## 真实 CLI immutable evidence

### 运行时序

场景名是 harness 意图标签，不是行为结论。文件变化证明实际 compact 时序为：

1. `F13O01`：真实工具与 corpus setup。
2. `F13O02`：未生成 compact artifact，因此不能称首次 compact。
3. `F13O03`：输入无工具证据的 21.7% 用户修正。
4. `F13O04`：生成首个 accepted artifact
   `d064f72a008ad60bf54d4bdcd98994da3a7db8135faabc91757c91d63e952d5f`。
5. `F13O05`：跨进程 reconnect 普通回答。
6. `F13O06`：生成 rolling/cap artifact
   `d7ff3e7f4c8f0b259c6590f9f4381e9ba33c7ae897d9902dbc42e63046d211ff`。
7. `F13O07`：生成第三个 rolling artifact
   `5fd4c26f940e6688f9e857aa53133af4bd79f581c84a79418600b0370d830480`；
   诊断变体未诱发失败，terminal 明确为 attempt 1 accepted。
8. `F13O08`：跨进程 reconnect，最终 Memory checkpoint 到 sequence 209。

EventLog 中 3 个 operation 分别只有一个 canonical terminal：

| operation | terminal sequence | terminal type |
|---|---:|---|
| `...baa9d36f...` | 133 | `CONTEXT_COMPACTED` |
| `...28b9032d...` | 165 | `CONTEXT_COMPACTED` |
| `...f63e56ea...` | 183 | `CONTEXT_COMPACTED` |

本 run 的 `CONTEXT_COMPACTED` 数为 3，`CONTEXT_COMPACTION_FAILED` 数为 0；因此
它不能作为 failed/stale/late terminal 的真实 observation。

### 首次真实 evidence material

首个 artifact schema version 为 5。其 proposal 使用 `E5`，Host 将 5 个新
EvidenceFact 投影为 5 个 `accepted_replacement.evidence_facts`；每项均携带同一非空
canonical ref：

`evidence:event-tool-result-accepted-2527bd9c73522f8ee606a3401041e5fe94f460567312aca2cf7371f1fdab867f`

SQLite EventLog 直接证明该 ref 对应 sequence 60 的 `TOOL_RESULT_ACCEPTED`，tool 为
`read_section`；artifact `E5` 的 immutable boundary material 含 SEC EDGAR 10-K
`CONSOLIDATED STATEMENTS OF OPERATIONS` 原文和 citation。

### rolling atomic retain

第二个 artifact 的 boundary 将第一份 accepted replacement 的 5 个事实投影为
`previous_evidence_fact` P2-P6；每个 boundary atom 同时带原 claim 与上面的 canonical
ref。模型 proposal 只返回：

```json
{
  "retained_previous_evidence_fact_labels": ["P2", "P3", "P4", "P5", "P6"],
  "evidence_facts": [],
  "session_summary": null
}
```

Host 的 accepted replacement 原样复制 5 个旧 claim 与其 canonical ref，selection
labels 分别为 P2-P6。第三个 artifact 再次以 P1-P5 原子保留同一组 claim/ref。

该数据直接证明 LLM 在 rolling 路径只拥有 keep/omit selector；旧 claim 与 provenance
由 Host atom 投影，未发生自由改写或 provenance laundering。

### 无证据修正与 durable Memory

所有 3 个 artifact 的 accepted EvidenceFact 均不含 `21.7` 或 `18.2`。最终 Memory
checkpoint 209：

- EvidenceFact 数为 5；
- empty `evidence_refs` 的 EvidenceFact 数为 0；
- claim 含 `21.7`/`18.2` 的 EvidenceFact 数为 0；
- 每项均指向第三个 accepted artifact `5fd4c26f...`、terminal event
  `event-context-compacted-742dcbd1fbde416f868b274ceec9ba50` 与同一 canonical
  `TOOL_RESULT_ACCEPTED/read_section` ref。

21.7% 仍存在于普通 recent user/assistant window，且 assistant 文本明确把它标为待核验、
无工具证据；它没有进入 `evidence_fact_memory.evidence_backed_facts`。这证明本 run 的
durable formal EvidenceFact 没有被用户修正污染，但存在一个限制：首个 artifact 的
immutable `source_boundary` 未选入该修正，故不能把本 observation 扩大解释为“模型已尝试
将它升级且被 Host typed reject”。该更强反例由 owner tests覆盖，formal scenario 仍需
Oracle 独立运行。

### Memory / artifact / EventLog / Tool Trace 同源

生产 public command：

```bash
dayu-cli tool_trace analyze \
  --base /Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/workspaces/chains/f13-postfix-provenance \
  --output-dir /Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/final-public-tool-trace \
  /Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/workspaces/chains/f13-postfix-provenance
```

exit code 为 0。public report 的 `compactor_responses` 有 3 个 accepted terminal；每个
均公开相同 5 个 claim 和相同非空 canonical ref，并分别指向 sequence 133、165、183。
这些 facts 与对应 artifact、EventLog terminal payload 和最终 Memory 完全相同。

public Tool Trace JSON：
`/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/final-public-tool-trace/tool-trace-analysis.json`

SHA-256：
`5c63586ed75ad395287452427d42b5c5d20c27d05a51a7f150fda95f820d6887`

CLI 退出后以 SQLite `.backup` 保存一致快照：
`/Users/leo/workspace/.dayu-cli-ci/f13-postfix-20260806T-W7W4JX/evidence/final-dayu-host.sqlite3`

SHA-256：
`d52c10a9a057f3b0d34da4a0ea9dc553d2518869ac2b8160b538def9ca580dd8`

### cap 与失败路径限制

- cap observation：`session_summary_char_cap=1`，provider 在 attempt 1 直接输出
  `session_summary=null`，Host 接受；没有 repair feedback 或第二次 attempt。
- “repair exhaustion”诊断：workspace-local prompt 变体虽被 harness 写入并在下一段恢复，
  但 durable terminal 显示 provider attempt 1 返回合法 retain proposal 并 accepted；没有
  `CONTEXT_COMPACTION_FAILED`。因此不能声称 repair exhaustion/fallback/non-pollution 已由
  真实 CLI 证明。

## README/design truth 检查

- `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md` 已在前序 slice 按职责
  更新。
- `docs/host/design.md` 与 `docs/engine/design.md` 的 owner/分层真相未被改变：Host 仍是
  compact acceptance、canonical provenance、durable projection 与 public response owner；
  Engine 只执行 LLM loop，不承担 provenance 判定。
- 本轮 S3 只新增 evidence artifact 与一个测试断言更新，不触发根 README 或
  `dayu/README.md` 用户工作流/分层更新。

## Oracle 下一步边界

Oracle 总控仍需在新的 run root 中独立补跑三条 formal replacement scenarios，至少覆盖：

1. unsupported correction 确实进入当前 immutable source boundary 后，不能生成
   EvidenceFact；
2. cap 导致 typed reject、bounded repair，并分别覆盖 repair success 与 exhaustion 后
   deterministic fallback；
3. stale/late compactor result、failed/rejected candidate 非污染、reconnect 只读最后一个
   canonical accepted Memory。

必须继续使用 production `dayu-cli interactive` PTY、真实 provider、production finance
tools 与真实 corpus；不得把本 observation、Host smoke 或 owner test 替代 formal
adjudication。
