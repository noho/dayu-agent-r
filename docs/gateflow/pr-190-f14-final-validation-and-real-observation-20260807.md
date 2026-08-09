# PR 190 / F14 final validation 与真实 CLI observation

## Gate verdict

F14 的确定性 root cause 已在 Host material owner boundary 修复。deterministic owner/integration tests、aggregate deepreview 与 fresh production CLI observation 均证明：accepted terminal 的 EventLog 位置不再被当作 coverage frontier；protected-but-unconsumed raw turns 能在离开 recent floor 后重新进入 canonical compactor boundary，并最终形成 durable accepted replacement。

本 gate 不改变 formal scenario 的 Oracle/registry 状态；`interactive.interactive.g06.rolling-correction-replacement` 仍为 `pending-user-adjudication`。

## Owner 与 contract

- 唯一 accepted consumption 真源：strict `ContextCompactedSemanticPayload.compacted_source_refs`，由 immutable source boundary 的 represented/omitted exact partition 机械派生。
- Host 读取当前 Session 的 accepted compact chain，累积 ordered-unique consumed refs；没有新增 durable cursor、双 projector 或第二 source truth。
- metadata stage 只在非空 `run_id`、唯一 canonical user anchor、anchor 已消费时建立 whole-group prefix proof；`run_id=None`、缺失/重复 anchor 保守进入 typed path。
- typed stage 复用 `_atomic_material_units`，要求 block all-in/none-in、Run group all-or-none、consumed prefix/unconsumed suffix；partial、split、gap、duplicate 或 reordering fail closed。
- material frontier 从最终首个 unconsumed canonical block 派生；`CONTEXT_COMPACTED.event_sequence` 只保留 terminal provenance 身份。
- schema、DB schema、public contract、LLM-facing prompt/tool schema、Engine contract 均未变化。

## Deterministic validation

以下是 test/static validation，不是真实 provider behavior：

- 旧实现 F14 regression red：accepted terminal 位于 protected suffix 后时，旧 frontier 返回 11，owner contract 期望 5；修复后通过。
- Controller adversarial red：`run_id=None` consumed user 未 fail closed，旧实现 `DID NOT RAISE HostDurableError`；修复后通过。
- finding-focused：`5 passed`。
- affected owner/integration union：`343 passed`。
- changed production file coverage：`190 passed`，`dayu/host/compact_material.py` line coverage `85%`。
- final full Pyright：`0 errors, 0 warnings, 0 informations`。
- changed-files focused Ruff：通过。
- `python -m compileall -q dayu tests utils`：通过。
- repository JSON `jq empty`：通过。
- `git diff --check b222b8b0..HEAD`：通过。
- final full pytest：`4 failed, 6766 passed, 10 skipped, 6 deselected, 3 warnings`；四个失败均位于 `tests/cli/test_smoke_cli_init_provider_matrix.py` 的 frozen publication manifest/config digest 校验。将同四个 nodeids 在 implementation 前 accepted-plan commit `b222b8b0` 的 detached worktree 精确重跑，结果同为 `4 failed`，因此是直接基线证据，不是 F14 回归。
- final full Ruff：89 个既有错误（44 F401、35 E402、7 F841、3 F541），均不在本 work unit changed production/test files；未自动修复或掩盖。

owner tests 覆盖 accepted、attempt rejected、repair accepted、repair exhausted、failed、cancelled、stale/late、fallback、restart/reconnect，及三轮以上 frontier monotonicity、canonical order、atomic Run group、exact-once、no-gap/no-duplicate、新旧 evidence ref 不借用/不重写、Memory/artifact/EventLog/RunInput/Tool Trace 同源。unit/integration tests 使用 deterministic fixture/fake/mock；不能冒充以下 real observation。

## Aggregate reviews

- Controller：`docs/reviews/code-review-20260807-001913.md` — `PASS`
- AgentMiMo：`docs/reviews/pr-190-f14-aggregate-deepreview-mimo-20260807.md` — `PASS`
- AgentDS：`docs/reviews/pr-190-f14-aggregate-deepreview-ds-20260807.md` — `PASS`
- acceptance：`docs/gateflow/pr-190-f14-aggregate-deepreview-acceptance-20260807.md`

三路 aggregate deepreview 无未解决 correctness、stability、maintainability、semantic ownership drift、over-coupling 或测试夹具真实性 finding。

## Fresh production CLI observation

### Run identity

- observed commit：`7dd84a4a888ad0dd7cbf4a5c542db63ca90884bb`
- evidence root：`/Users/leo/workspace/.dayu-cli-ci/f14-postfix-20260807-cAoxqy`
- fresh workspace：`workspaces/chains/rolling-correction-replacement`
- production CLI：`.venv/bin/dayu-cli`，SHA-256 `ab7d7ba9f7ac8595296b8c53fb139a2af3267616cb0ce5088e3ce6f4a8071691`
- harness：`evidence/harness-source.py`，SHA-256 `1de6956e6d1888387ea8fd75f37b35eb76a36849552edb9859d77f982153397c`
- provider：真实 MiMo plan；interactive 显式 `mimo-v2.5-pro-plan`；Tool Trace 显示 effective provider/model `mimo` / `mimo-v2.5-pro`
- tools/corpus：production 财报工具与真实 AAPL 2025 10-K corpus；真实工具包括 `list_documents`、`start_fins_download`、`get_financial_statement`、`query_xbrl_facts`、`get_document_sections`、`read_section`
- mock/fake provider/tool：未使用
- recent policy：production 默认 `selected_recent_window_item_cap=32`、`selected_recent_window_turn_floor=4`，未修改

7 个独立 POSIX PTY process segment 全部 `exit_code=0`、`timed_out=false`、SQLite/Tool Trace 采集成功；累计 28 个 ordinary Run terminals，`harness_invalid_count=0`。精确 argv、环境键名、PTY bytes/trigger、屏幕、stdout/stderr、文件 diff、脱敏 SQLite before/after 与 Tool Trace 均已保存。exit 0 本身不承担业务 PASS 语义。

### Direct boundary proof

EventLog 仅有两个 canonical `CONTEXT_COMPACTED`：sequence 223 与 493。FY2025 correction raw material 位于 sequence 154–217，早于 first terminal 223；first artifact `0a8c93a2…` 的 boundary 只有 FY2024，故首 replacement 仍只有 FY2024 facts/current references。这直接重现 F14 的必要前提。

first accepted 后执行 18 个真实业务连续回合，使 correction 自然越过 production recent item cap。最终 Memory selected recent window 只含 sequence 432–519 的 12 items，不含 correction。

latest artifact `845fa417…` 的 48-label immutable boundary 重新包含 previous accepted compact、FY2025 correction `T2`–`T4`、production evidence `E1`/`E2`、FY2025 answers 与 canonical aging turns。FY2025 `read_section` evidence ref：

`evidence:event-tool-result-accepted-a07eff3b4bfac34ce760fa1362269e3965318bbe82a774f1b0ef6f1dce6897f1`

它对应真实 SEC EDGAR 2025 10-K accession `0000320193-25-000079`，包含 Total Net Sales 416,161 与 Operating Income 133,050。

### Durable business result

- latest replacement 新增 3 条 FY2025 EvidenceFact，全部只绑定上述新非空 production ref。
- FY2024 三条 EvidenceFact 继续保持旧 immutable provenance，只作为历史事实；其旧 current reference output 被新的 FY2025 reference continuity 替代。
- “当前年度”=FY2025；“当前销售额”=FY2025 Total Net Sales 416,161；FY2024 明确为历史对照，非当前结论。
- 21.7%/18.2% 进入真实 boundary，但没有进入任何 EvidenceFact，也没有 canonical evidence ref；只作为“待核验用户文本（无工具来源）”进入 anchor。
- source-label manual/audit：accepted sections 使用的 35 个 labels 全部解析到 48 个真实 boundary labels；FY2025 EvidenceFact 只选择真实 `E2`，没有无 label current input 虚假引用旧 `P` label。

### Projection/reconnect equality

`f14-owner-projection-audit.json` 19/19 checks 通过：latest artifact、EventLog terminal、Memory、public Tool Trace 的 6 条 EvidenceFact claim/ref tuples 完全相等。ordinary reconnect RunInput manifest 直接绑定 artifact `845fa417…`，system projection 含全部 durable facts 与 FY2025 current references。

reconnect 屏幕回答 FY2025、416,161、真实 SEC 10-K 来源；明确 21.7% 无工具证据、FY2024 已降为历史对照。correction raw 已不在 selected recent window，因此该回答可由正式 Memory/accepted replacement 证明。

## Evidence and secret boundary

- observed report：`evidence/f14-observed-behavior-report.md`，SHA-256 `6709366d0bf68a4061bfebc7692514b78da6f968dd5548d19d43577c7ca2c22a`
- execution index：`evidence/execution-index-f14-postfix.json`，SHA-256 `71bb9457f09f143b5a2cee4df42823bfd4381e3874e993a1e3b0e3b80d595aae`
- owner audit：`evidence/f14-owner-projection-audit.json`，SHA-256 `402449c5681c33aa5600f89128863c2bb1faee398387ea91a4876fc542b8fbfa`
- public Tool Trace：`evidence/public/rolling-correction-replacement/tool-trace-analysis.json`，SHA-256 `2e99014791fa09d429b8e65837058758fb9964a454d8d21dc5b24c4b406c85f2`
- distributable manifest：`evidence/evidence-manifest.json`，104 files，SHA-256 `84c2b93e32a58cd1f89a2ef9c331e420d600ebbc5e850b7939d333022cc1f4b6`
- exact-value secret scan：5 available credential values、104 files、0 finding、0 unreadable、未记录 secret 值；SHA-256 `ff3ecdef4d453cfd8604aa2a5c1dfb60faf9a7e7187f962b326ec3cd71332da3`
- raw Host SQLite 原件只在本机 fresh workspace 保留，SHA-256 `26656961928cb6c291c6522920beafe85c4fac894f9fcd5df00e440a0ce23dfe`；distributable evidence 无 `.sqlite/.sqlite3/.db` 文件，manifest 明确 `raw_sqlite_included=false`

## Documentation/registry boundary

- 更新 `docs/host/design.md` 与 `dayu/host/README.md`，明确 accepted source coverage、terminal provenance 与 frontier derivation；`docs/engine/design.md` 经检查无需改变，因为 Engine 仍不拥有 coverage/consumption。
- tests README、根 README、`dayu/README.md` 的职责/用户工作流未变化，无机械更新。
- Oracle 与 scenario predicate 未修改；registry 未标记 accepted/ready，也未覆盖 F13/F14 历史 evidence provenance。

## Residual risks

- accepted chain 与 material metadata scan 对 Session 历史为线性成本；这是保持唯一 durable truth 而接受的性能权衡，长会话压力未由本 work unit 建立独立 benchmark。
- MiMo/provider 输出非确定；本 run 保存了真实输入、输出与 Host accepted truth，但不能承诺未来 provider 文案完全一致。
- real observation 未触发 rejected/failed/cancelled/stale/late/repair/fallback；这些路径由 deterministic owner/integration tests 覆盖。
- formal scenario 仍需 Oracle/用户依据本 evidence 或 fresh rerun 独立裁决。
