# WU-CLI-CONFORMANCE-F01-F07 — Final Closeout

## Work unit result

- Work unit: 修复 init/prompt/interactive 第一轮 oracle 收口后确认的 F01-F07 conformance findings。
- Branch: `codex/interactive-oracle`。
- Existing draft PR: PR 190，`https://github.com/noho/dayu-agent-r/pull/190`。
- Gateflow result: plan、dual plan review、S1-S8 implementation/review、corrective slices、aggregate
  deepreview、PR review/fix/re-review、accepted PR-review commit、final push 与 draft-PR-pass 均完成。
- Product exact-head evidence target: `58aeb7b377ef1857ad2a0a919c47556fdb3fa081`。
- Primary validation verdict: `full-real-pass`。

## F01-F07 final status and semantic owners

| Finding | Final status | What changed | Semantic owner |
|---|---|---|---|
| F01 global `--config` | `PASS / 已修复` | 删除 root action、help、typed args、CLI→Service forwarding、runtime request字段和公开产品入口；workspace 只从 `--base/-b/--workspace` 与 package fallback解析。 | CLI root parser/public surface；runtime location由 typed workspace request/Service config loader拥有。 |
| F02 explicit invalid editor | `PASS / 已修复` | 显式 missing、non-executable、spawn failure 返回 typed composer error，保留 draft与REPL，不创建 Run；未配置 EDITOR/VISUAL时仍允许系统 fallback。 | `dayu.cli.composer` external-editor selection/binding与draft lifecycle owner。 |
| F03 Escape/Ctrl+C | `PASS / 已修复` | 使用独立 VT100 ambiguity owner区分 standalone Escape、CSI、Alt与 bracketed paste；acceptance barrier前后保留 cancel/exit intent；double Ctrl+C等待同一 graceful closeout后 exit 130。 | CLI input/chord decoder只拥有 intent；Host继续唯一拥有 Run cancel、terminal与cleanup lifecycle。 |
| F04 READ_ONLY mutation | `PASS / 已修复` | READ_ONLY rejection不退出REPL、不ack composer draft；稳定 pending `client_request_id`；下一次 mutation执行 close-before-fresh-attach，不原地升级。 | interactive attachment controller与 `_InteractivePendingMutation` identity；Host attachment mode与single-writer contract不变。 |
| F05 preprocess registration | `PASS / 已修复` | 只从 interactive scene manifest effective tool set移除 `start_fins_preprocess`；保留实现及独立 process/preprocess能力。 | interactive scene manifest / Service assembly selection；Fins tool implementation未改。 |
| F06 trigger rename | `PASS / 已修复` | fresh contract全量改名为 `context_governance_resolved`，删除旧值，无 alias/parser fallback；success/failure exact outcome仍只由 canonical terminal/artifact/fallback refs表达。 | typed runner-call trigger contract、producer/reader/persistence；`CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 是唯一 exact outcome owner。 |
| F07 invalid compactor response | `PASS / 已修复` | fresh strict v2 input/candidate schema、exact/duplicate-key JSON、coverage/caps/duplicate/contradiction/low-information accept barrier、bounded whole-candidate repair、single terminal、fallback与 committed-truth-only Memory/RunInput/artifact projection全部收口；PR review又补齐 drop root order与 compact-input单 owner。 | Host Context Governance accept barrier构造唯一 `CompactAcceptedTruthV2`；`CompactionRequest.compact_input` 是唯一 input projector；terminal writer、artifact、Memory与RunInput只消费 committed truth。 |

## Accepted PR-review findings

- MiMo-01 reverse explicit-drop order: `已修复`，逆序 multi-drop 经 accept 与 committed payload
  parse round-trip后保持 root order。
- MiMo-02 delayed attachment join cleanup: `已修复`，join失败仍由 `finally` 调用 native
  `aclose()`，close成功时原 join failure传播。
- DS-D-001 duplicate strict-v2 projector: `已修复`，旧 projector、private helpers与 export
  删除，active Python inventory为零。
- 双路 PR re-review均未发现新 finding；Controller另行纠正 DeepSeek artifact对双异常
  `finally` 传播优先级的文字误述，没有扩张 frozen contract。

## Commits in this work unit

| Commit | Purpose |
|---|---|
| `4a3dca64` | accepted plan；提交用户冻结的 oracle/scenario baseline原字节 |
| `a41526ec` | S1 / F01 remove global config |
| `e5b572d4` | S2 / F02 explicit editor failures |
| `16c6ddc8` | S1 smoke runtime request closure |
| `fc1b4946` | S3 VT100 plan correction |
| `25400fba` | S3 / F03 graceful input cancellation |
| `c556df2b` | S4 / F04 READ_ONLY fresh-attachment retry |
| `64c581f1` | S5 / F05 interactive tool manifest |
| `b8f87e3b` | S6 / F06 trigger rename |
| `df99f858` | S7 / F07 strict compaction truth |
| `eae09be9` | integration owner-contract correction |
| `016d834a` | S3B pre-accept input ownership |
| `63fca270` | S3C interactive control intent |
| `9fec1647` | S3D post-cancel chord ownership |
| `584ee394` | S8 real evidence、README与accepted artifacts |
| `c69445c2` | accepted aggregate deepreview |
| `58aeb7b3` | accepted PR review、三项fix与双 re-review |
| `7480ab24` | exact-head evidence与draft-PR-pass adjudication |

本 closeout artifact 的 enclosing commit由 Controller在最终回复中报告；Controller只有在该 commit
push并从 PR readback确认后才会输出 final closeout pass。

## Verification

- Full-real provider/model: real Mimo / `mimo-v2.5-pro`；fake provider=false。
- F01-F07 mandatory matrix: 全 PASS，证据同时来自 Host/EventLog/Tool Trace/Memory/SQLite、
  runner-call manifest、compact artifact与真实 Fins生成物。
- PR fix focused owner: 2 passed；PR fix affected: 453 passed；full affected/owner union:
  1132 passed。
- Final full pytest: `6605 passed, 10 skipped, 6 deselected`。首轮已知 public-cancel
  flake为 1 failed / 6604 passed；隔离 1 passed；三份日志均保留。
- Full pyright: `0 errors, 0 warnings, 0 informations`。
- Coverage: CLI affected aggregate 87%；Host owner aggregate 84%，各实质 owner 82%-89%。
- Ruff、compileall、两份 JSON、frozen SHA-256、`git diff --check`: PASS。
- GitHub checks: zero/no checks；未声称 GitHub CI pass。

## Immutable evidence

- Bundle:
  `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-post-pr-fix-20260803T041030Z-58aeb7b377ef/bundle`
- Digest:
  `ab3f6ae5f4b5b76d768e0968d76ee83eca50d99fa8458b477e42d0c820a1e883`
- Controller独立 checksum: 743/743 PASS；bundle index 742 entries；writable paths=0。
- Final secret scan: 741 files、finding files=0、secret values persisted=false。
- 两个 init stdin 不完整 failed bundles与F07首次 no-compact observation均保留，未覆盖、未伪装为PASS。

## Design, prompts and README

- `docs/host/design.md`: 更新 F06 typed trigger / outcome owner与 F07 fresh strict-v2 accept、repair、
  terminal、Memory/RunInput/artifact同源设计。
- `docs/engine/design.md`: 不修改；本 work unit未改变 Engine lifecycle/provider selection语义。
- LLM-facing compactor prompts: 更新为自足 strict-v2 input/output、coverage/drop与 whole-candidate
  repair规则，不暴露不必要内部实现术语。
- Root `README.md`: 更新用户可见 CLI surface与真实工作流。
- `dayu/config/README.md`: 更新 interactive scene/effective tool与 compactor prompt职责。
- `dayu/host/README.md`: 更新 cancellation/attachment、Context Governance、single projector、
  canonical drop order与cleanup owner。
- `tests/README.md`: 更新 F01-F07 owner/integration/real-evidence测试职责。
- `dayu/README.md`、`dayu/engine/README.md`: 按各自职责检查后无需修改。

## Frozen oracle/scenario disposition

冻结内容没有被实现 Agent改写：

- `docs/cli_ci_oracles.json`:
  `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
- `docs/cli_ci_scenarios.json`:
  `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- `docs/cli_ci.md`:
  `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`

两个 registry是前序总控冻结 baseline，在 accepted plan commit原字节提交；后续 slice、review、
evidence未重新发明、扩张或迁就实现修改 accepted behavior/scenario set。

## Remaining risks / owners

- Host public cancel test-order flake：Host public-smoke/test-runtime owner；需独立稳定复现根因，
  不在本 work unit猜 timing patch。
- G01-G07 overall registry calibration与最终 formal conformance裁决：用户/Oracle controller。
- renderer target pin / formal scenario promotion：Oracle renderer/calibration owner。
- durable resolved Authorization projection：effective-execution durable projection owner；本 bundle
  已只保留脱敏投影。
- real provider nondeterminism：provider/runtime owner；deterministic owner matrix、保留的 no-compact
  observation、真实 accepted compact与invalid-exhaust conjunction共同约束。
- GitHub zero checks：repository CI/config owner；本地 exact-head证据不能冒充不存在的 GitHub CI。

没有未分类或 blocking residual risk；未来 owner不得据此修改本轮 frozen oracle。

## PR and protected actions

- PR 190仍为 OPEN + draft；base/head正确，mergeable/CLEAN。
- 复用现有 PR 190，没有创建第二个 PR。
- 没有 mark ready、approve、merge、request reviewers、rebase、force-push、删除 branch或重写历史。

## Final marker and next entry point

`FINAL-CLOSEOUT-PASS`

Next entry point：由用户/Oracle 总控审阅本次 post-fix observation 与 immutable bundle，并决定
是否把当前实现判为 formal conformance pass；实现 Agent不代替用户作该裁决。
