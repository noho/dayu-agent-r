# WU-CLI-CONFORMANCE-F01-F07 — S8 post-fix integration/full-real evidence

## 1. Gate 结论

- Pull request：PR 190。
- exact target：`9fec164715bc6af7a4a7d7446cb45d49593ec64f`。
- verdict：`PASS`。
- completion marker：`READY-FOR-DUAL-S8-CODE-REVIEW`。
- 本轮没有修改 frozen oracle、scenario registry、CLI handbook、production 或 tests，也没有用 fake provider 替代 full-real。

新的唯一 evidence root：

```text
/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc
```

immutable bundle：

```text
/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle
```

bundle digest：

```text
7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72
```

## 2. Frozen inputs 与 evidence policy

以下 frozen digest 在 target 上与准入值完全一致：

| Input | SHA-256 |
|---|---|
| `docs/cli_ci_oracles.json` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` |
| `docs/cli_ci_scenarios.json` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` |
| `docs/cli_ci.md` | `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82` |

`metadata/input-artifact-manifest.json` 记录了 frozen docs、Host/Engine design 与全部
S1-S7、S3B-S3D、integration/corrective artifacts 的路径、大小和 SHA-256。deterministic
malformed candidate 只用于 owner tests；所有 provider 行为结论来自真实 Mimo
`mimo-v2.5-pro`、真实 CLI/PTY、真实 Host 与真实工具链。

## 3. F01-F07 结果

### F01 — remove global config

`PASS`。

- root/init/prompt/interactive help 的 `--config` occurrence 均为 0。
- recursive parser inventory 含 81 个 scoped actions，`config_option_occurrences=[]`。
- root-before、init before/after、prompt before/after、interactive before/after 共七条
  removed-option lane 均在 argparse boundary exit 2。
- active CLI/Service source scan 对 `--config`、旧 helper/export/request 字段零命中。
- 当前 README 与 frozen handbook 中的剩余文字只说明该参数不存在或被拒绝，不构成入口。

直接证据：`evidence/F01-remove-global-config/`、
`evidence/owner-matrices/f01-matrix.json`、`logs/f01-source-scan.log`。

### F02 — explicit invalid editor

`PASS`。

missing、non-executable、spawn failure 三个 fresh workspace 都保留原 draft、显示可操作
editor error、继续 REPL 后 exit 0，并恢复 terminal flags。SQLite/EventLog/Tool Trace owner
projection 逐 lane 交叉确认 Runs=0、Attempts=0、Tool Trace rows=0；没有用 CLI 自报替代
durable owner。

直接证据：`evidence/F02-explicit-invalid-editor/`、
`evidence/owner-projections/f02-*/`、`evidence/owner-matrices/f02-matrix.json`。

### F03 — cancel / escape / terminal

`PASS`。

- frozen prompt PS01/PS02/PS03 的 CSI/Home/Delete、Alt+X、bracketed paste 均成功 exit 0，
  不误判 standalone Escape，terminal flags 恢复。
- interactive CSI/Home/Delete、Alt+X same/cross chunk 与 bracketed paste 同样成功且无 cancel。
- pre-accept standalone Escape 的 0/10/20ms fresh lanes 各形成一次 graceful cancel，返回
  REPL 后 exit 0；pre-accept double Ctrl+C self-exit 130。
- provider wait、tool execution、closeout 三条 exact after-action +0.05s double POSIX SIGINT
  lane 全部由进程自身 exit 130，均只有一个 `CANCEL_REQUESTED` 和一个
  `RUN_CANCELLED`，没有 harness SIGTERM，terminal flags 全恢复。
- provider/closeout Attempt canonical terminal 为 `cancelled`；tool-await lane 的 Attempt
  既有真源是 `suspended`，等待态取消由唯一 `RUN_CANCELLED` 收口，因此不伪造第二个
  `ATTEMPT_CANCELLED`。
- single POSIX SIGINT 仍只产生一个 graceful cancel，返回 REPL 后正常 exit 0。
- 额外 prompt preaccept/provider/tool observations 全部保留在 bundle；其中 prompt 的
  download 请求因 prompt effective tools 不含该工具而直接成功，不被拿来替代 governing
  interactive tool-execution POSIX lane。

直接证据：`evidence/F03-graceful-cancel-and-escape-sequences/`、
`evidence/F03-interactive-completion/`、对应 owner projections 与
`evidence/owner-matrices/f03-matrix.json`。

### F04 — READ_ONLY / fresh attachment

`PASS`。

两个真实 attachment 同连一个 Session。B 在 A 活跃时两次收到 typed READ_ONLY，两个时点
Run count 均为 0，B 保持存活并留在 REPL；A 完成并退出后，B 关闭旧 attachment、fresh attach
再提交并成功。最终恰好两个 succeeded Runs；两个 attachment 各自的
`turn-1:submit` request id 在本 attachment 内稳定且彼此不同，未原地升级 attachment。

直接证据：`evidence/F04-read-only-submit-keeps-repl/`、
`evidence/owner-projections/f04-two-attachments/`、
`evidence/owner-matrices/f04-matrix.json`。

### F05 — effective tools / real chain

`PASS`。

真实 Mimo `mimo-v2.5-pro` 完成三个 succeeded Runs。Host runner-input 与 SQLite selected
tool-schema snapshot 证明 effective set 不含 `start_fins_preprocess`；canonical
EventLog/Tool Trace 证明真实跨轮调用：

```text
start_fins_download -> list_documents -> get_document_sections -> read_section
```

MSFT 下载生成 165 个真实 portfolio 文件，路径、大小与 SHA-256 已写入
`evidence/generated-artifacts/f05-portfolio-manifest.json`；没有把 CLI 终端文案当作工具
成功真源。

直接证据：`evidence/F05-effective-tools-real-chain/`、
`evidence/owner-projections/f05-real-tool-chain/`、
`evidence/owner-matrices/f05-matrix.json`。

### F06 — dispatch manifest terminal ownership

`PASS`。

三个 accepted compact 与一个 failed-compaction fallback 后的首个 ordinary runner-call
manifest，`runner_call_trigger_reason` 都且只为
`context_governance_resolved`。该 trigger 只表达 dispatch permit；compact 结果由三个唯一
`CONTEXT_COMPACTED` 或一个唯一 `CONTEXT_COMPACTION_FAILED` canonical terminal 拥有，
没有把 outcome 复制到 manifest。

直接证据：success/failure EventLog、Host dispatch records，以及
`evidence/owner-matrices/f06-matrix.json`。

### F07 — strict v2 compaction / repair / continuity

`PASS`。

- accepted S7 deterministic owner matrix：`711 passed, 1 skipped`；覆盖 strict JSON、
  exact coverage/drop、caps、duplicate/contradiction、whole-candidate repair、aggregate-root
  revalidation、late/stale/cancel single terminal 与 committed-event-only propagation。
- 真实 Mimo invalid lane：attempt 1 rejected 后进入 bounded semantic repair；attempt 2
  再次 rejected 且 `repairable=false`；随后恰好一个
  `CONTEXT_COMPACTION_FAILED`，`retry_repair_budget_exhausted=true`，
  `fallback_action=dispatch`，普通用户 Run 最终 succeeded；没有
  `CONTEXT_COMPACTED` 或 partial accepted truth。
- 真实 success lane：三次非空 accepted candidate、三次非空 represented coverage、三份
  compact artifact；provider/model identity 全为 Mimo/`mimo-v2.5-pro`。第三次先有一个
  real invalid candidate，再由 attempt 2 repair 成功。
- 三个真实 compact artifact 已复制进 bundle 并逐文件摘要。
- compact 后第一轮同时保留 `OLD_AAPL_NET_SALES` 和新口径
  `NEW_SCOPE=OPERATING_MARGIN`；第二轮无工具复述旧事实
  `416,161`、单位、FY2025 期间和 SEC 来源；第三轮真实调用
  `list_documents`、`get_financial_statement`（模型额外调用 `read_section`），按新
  scope 得到 31.97%。
- EventLog、Host Run/Attempt、Tool Trace、Memory snapshot/items、SQLite payload projection
  与真实 compact artifacts 从同一 accepted truth 交叉核对。

直接证据：`evidence/F07-invalid-compactor-response/`、
`evidence/owner-projections/f07-compaction-{success,failure-cap}/`、
`evidence/generated-artifacts/f07-compact-artifacts/`、
`evidence/owner-matrices/f07-matrix.json`。

## 4. 完整验证

全部命令先激活仓库 `.venv`，并以 detached worktree 作为 `PYTHONPATH`：

| Gate | Result |
|---|---|
| Full pytest | `6603 passed, 10 skipped, 6 deselected, 3 warnings in 235.28s` |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| Accepted S7 15-file matrix | `711 passed, 1 skipped, 3 warnings` |
| Affected coverage | composer 89%、run_keys 93%、session_execution 85%，aggregate 87% |
| Changed Python Ruff | `All checks passed!` |
| JSON tool | 两份 frozen registry 与 init manifest 全部通过 |
| Exact target diff check | 通过 |
| Controller dirty diff check | 通过 |
| Frozen hashes | 与第 2 节完全一致 |

S7 matrix 首次与 coverage 并发执行时，唯一失败是
`test_reactive_compact_request_uses_latest_previous_view` 的 0.01 秒 LLM lane acquire timeout。
该 node 随即串行通过，完整 15-file matrix 串行得到 711 passed，full suite 也通过。没有稳定
reproduction 或产品 owner 直接证据，因此本轮不修改 production、测试或 timeout。

三条 warning 均来自 `edgar` 依赖的既有 deprecation warning。

## 5. Secret、index 与 immutable seal

- 在删除 raw durable carriers 前，先把 Host/EventLog/Tool Trace/Memory/SQLite 的必要 owner
  projection、真实生成物摘要和 compact artifacts 复制进 evidence。
- raw inventory 扫描识别到本次 CI-owned SQLite 中存在真实 Mimo credential；projection
  已按 ref 脱敏，随后只删除本次新建 CI workspace 内的 SQLite/WAL/SHM、audit 与 cold trace
  raw carriers，没有删除仓库或用户数据。
- 最终 bundle secret scan：442 个 seal 前文件，exact credential=0、未脱敏 bearer=0、
  structured secret assignment=0，保留 41 个可审计 redaction placeholder。
- `bundle-index.json`：443 entries。
- `SHA256SUMS`：逐项 `sha256sum -c` 通过。
- `SHA256SUMS` digest 与 `bundle-digest.txt` 均为
  `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`。
- Python mode-bit 复核 bundle root、目录和文件：writable paths=0。

## 6. 三份历史失败 bundle

三份历史失败证据均保留、未覆盖，并在新 bundle 中记录路径、失败原因和 digest：

| Historical bundle | Digest | Historical failure |
|---|---|---|
| `pr190-wu-cli-conformance-f01-f07-s8-20260802T224352Z-016d834adba5/bundle` | `0b00b5dde036265e0538dfabbc3303d4566de4c61cdd2c2c18eb47e5e8bc2046` | F03 pre-accept Escape failure |
| `pr190-wu-cli-conformance-f01-f07-s8-20260803T000310Z-016d834adba5-r2/bundle` | `103d146f2ae223f45e5833f173150014f3bb2379617a8185db4de17b8f4ea581` | redacted supplemental failure evidence |
| `pr190-wu-cli-conformance-f01-f07-s8-20260803T005803Z-63fca270cc29/bundle` | `1baee636b99db8aec60d8af66ce86b81c7cce609e3851dbfd63f1e7146e1e050` | double POSIX SIGINT lacked self-exit 130 |

## 7. README 与工作区边界

- 已读取并按各 README 自身职责核对 `README.md`、`dayu/config/README.md`、
  `dayu/host/README.md`、`tests/README.md`。四份既有 dirty intended 内容准确覆盖用户入口、
  scene/effective tool、Host v2 compaction/dispatch owner 和测试职责，本轮原样保留，没有覆盖。
- `dayu/README.md` 不更新：目标未改变 UI/Service/Host/Engine 分层或装配边界。
- `dayu/engine/README.md` 不更新：本轮 target 没有需要同步的 Engine public contract 变化。
- `docs/reviews/code-review-20260803-075748.md` 与
  `docs/reviews/plan-review-20260803-064525.md` 是 excluded self-review artifacts，未修改。
- frozen docs、production 与 tests 未修改。
- 未 stage、未 commit、未 push，也未修改 PR 190 状态。

## 8. Residual risk 与 gate marker

真实 provider 输出仍具有通常的模型非确定性，但本轮同时具备 deterministic owner matrix、真实
invalid/exhaust、真实 accepted repair、真实 artifact/Memory/Tool follow-up 的完整 conjunction；
没有未分类或 blocking residual risk。

`READY-FOR-DUAL-S8-CODE-REVIEW`
