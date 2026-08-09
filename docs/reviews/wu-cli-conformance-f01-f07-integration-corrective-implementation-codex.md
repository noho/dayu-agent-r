# WU CLI Conformance F01-F07 — Integration Corrective Implementation

## 1. Gate 与状态

- Gate：S5/S7 integration corrective implementation after S8 validation。
- Work unit：PR 190 / WU CLI Conformance F01-F07。
- Entry HEAD：`df99f858c6e01d3555eb5c16c3358160909a1f1a`。
- Branch：`codex/interactive-oracle`。
- 状态：`READY-FOR-CONTROLLER-REREVIEW`。
- Next entry：handoff 给总控进入 corrective re-review；本 artifact 不宣称 re-review 已通过。
- Artifact path：`docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md`。

本轮没有 stage、commit、push 或修改 PR。没有修改 production、frozen
`docs/cli_ci_oracles.json`、frozen `docs/cli_ci_scenarios.json`，也没有修改 S8 owner 的四份
README 或原 S8 implementation artifact。

## 2. 第一性原理与 owner 裁决

S8 稳定复现的 12 个 integration failure 都成立，但直接代码与数据证据表明它们不是
production defect：

1. init publication 的 schema/path/file-count/model owner 均正确，只有 S5/S7 已变 package
   文件的三个内容摘要仍是旧值；owner 是 checked-in publication manifest。
2. runtime smoke fake 仍输入旧 `trace_material` / `evidence_material` / `answer_material`，真实
   fake producer 只消费 fresh v2 `source_boundary`；owner 是该 consumer test fixture 与其
   candidate coverage assertion。
3. Service production 已分别从 scene system fragment 与 compactor user template 装配两个
   prompt；旧测试却要求 request 出现在 system prompt。v2 自足 request/schema owner 是 user
   prompt，system prompt 只拥有稳定任务规则。
4. `run_queue_promotion()` 已等待 scheduler-local pre-start sole flight，并可在返回后由后台
   dispatch consumer 先消费 pending record。第二次显式 `drain_once().dispatched == 1` 观察的是
   偶然时序，不是 public contract。正确证据是 public Run outcome 与 durable
   Run/Attempt/EventLog/dispatch record，再加 worker factory 创建次数。

因此最小修正只触及 publication manifest 与四个测试 consumer；没有兼容层、fallback、loose
parser、timing sleep 或 production 语义修改，也没有引入新抽象。

## 3. Changed files 与 exact changes

| 文件 | owner correction |
|---|---|
| `docs/cli_init_workspace_manifest_v1.json` | 只更新 interactive manifest 与两个 compaction prompt 的真实 package SHA-256；保持 5 directories、43 files、16 model owner pointers。 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 只更新 frozen publication manifest SHA-256 常量。 |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | fake input 改为 fresh v2 `schema/current_input/source_boundary`；candidate 断言改为 v2 schema、semantic labels 与 exact represented coverage。 |
| `tests/service/test_host_assembly.py` | 断言 system prompt 不携带 request placeholder/input-output schema，只携带稳定规则；user prompt 自足携带 placeholder、v2 input/output schema 与覆盖规则。 |
| `tests/host/test_phase5_local_execution_integration.py` | 六个场景删除 promotion 后第二次显式 drain 竞态断言；fake worker 暴露 event-stream started/closed lifecycle signal，不使用 sleep；新增 public Run + durable Run/Attempt/dispatch record/`ATTEMPT_RUNNING`/Attempt terminal/Run terminal + factory count exact-once helper。 |

本文件与后续 fix artifact 均是用户显式允许的 procedural artifact。

## 4. Publication identity

三个真实 package digest：

| path | SHA-256 |
|---|---|
| `config/prompts/manifests/interactive.json` | `69339ac8dbcdd3779b710140400037294458fff564048e80423b3474790426e7` |
| `config/prompts/scenes/conversation_compaction.md` | `4d107e1f66e9f4194d320e73a77a91e24ef2c9f2da5a1f4c3ba0178fc8c23f08` |
| `config/prompts/scenes/conversation_compaction_user.md` | `b5c1f2423b43e69302bdd861e108bf4e110cea3562ad9839b99ac8a9b46f7f3d` |

更新后的 publication manifest SHA-256 为
`c646c2a0c7b508f8cc07d7f446273fb37117a8b1d9e47da82bf09f32e9dfd65e`；JSON parse、fresh real
publication tree、OpenAI projected owner 与 Ollama dynamic owner tests 均通过。

frozen CLI registry 保持：

- `docs/cli_ci_oracles.json`：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json`：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。

## 5. Formatter churn 收敛

曾误对四个测试整文件运行 `ruff format`。继续矩阵前已只用 `apply_patch` 恢复 Entry HEAD 的所有
未触及格式，再重施 semantic hunks；没有 checkout、reset 或脚本覆盖。

| 文件 | 收敛前 numstat | 收敛前 `-w` | 收敛后 numstat | 收敛后 `-w` |
|---|---:|---:|---:|---:|
| CLI provider matrix | `+148/-181` | `+101/-134` | `+1/-1` | `+1/-1` |
| Service Host assembly | `+25/-47` | 未单独冻结；总控确认存在 formatter churn | `+15/-3` | `+15/-3` |
| Runtime smoke assembly | `+38/-49` | 未单独冻结；总控确认存在 formatter churn | `+27/-13` | `+27/-13` |
| Phase5 integration | `+247/-146` | 未单独冻结；总控确认存在 formatter churn | `+247/-118` | `+247/-118` |

收敛后普通 numstat 与 `-w` numstat 完全一致，证明没有残留纯空白 formatter churn。Phase5 的较大
semantic diff 来自六场景 exact-once evidence、两个无 sleep lifecycle signal 与共享 owner helper。

## 6. Validation

全部命令均先 `source .venv/bin/activate`。

| Gate | Result |
|---|---|
| 四类 focused tests | `187 passed, 3 warnings` |
| Phase5 单文件 focused | `9 passed` |
| Accepted S7 15-file matrix | `711 passed, 1 skipped, 3 warnings`；skip 为既有 real-provider environment gate |
| S7 typed closure pyright | `0 errors, 0 warnings, 0 informations` |
| 完整 suite 首轮 | `2 failed, 6569 passed, 10 skipped, 6 deselected`；仅 watchdog duplicate observation 与 SIGKILL delayed recovery timeout |
| 两个 full-load failure 成对串行诊断 | 5/5 rounds passed；每轮两个 node 均通过 |
| 两个 full-load failure 三进程并发诊断 | 3/3 processes passed；每进程两个 node 均通过 |
| 完整 suite 最终复跑 | `6571 passed, 10 skipped, 6 deselected, 3 warnings in 219.51s` |
| Full repository pyright | `0 errors, 0 warnings, 0 informations` |
| Changed Python Ruff | `All checks passed!` |
| JSON parse | publication manifest 与两个 frozen registry 全部通过 |
| Fresh v1 symbol scan | active owner paths 零命中 |
| Reactive pass queue positive scan | producer、consumer 与 owner tests 均存在 |
| Stale Phase5 drain assertion scan | 零命中 |
| `git diff --check` | 通过 |
| Index | 空；未 stage |

三条 warning 均来自 `edgar` 依赖的 deprecation warning，不是当前改动。

### 6.1 Cancel-watchdog 诊断

修改前先执行目标 node 串行独立 10 次与五进程并发负载，合计 15/15 通过。完整 suite 首轮仍观察到
同线程 `request_cancel` 两次；随后把该 node 与 SIGKILL recovery node 成对串行 5 轮并以三个并发
pytest 进程执行，watchdog 再通过 8/8，完整 suite 复跑也通过。该现象只能在一次全仓负载中观察，
没有稳定 reproduction 或直接 root cause，因此本 corrective slice 不修改 cancel-watchdog test 或
production。

### 6.2 Recovery multiprocess 诊断

首轮完整 suite 的 SIGKILL immediate fresh attach 在 45 秒 delayed-recovery deadline 超时；同 node
随后串行 5/5、三进程并发 3/3、完整 suite 复跑全部通过。没有稳定 root cause，也没有证据把它归因
于本轮 test consumer 变更，因此不做 timing 放宽或 production 修改。

### 6.3 最终 validated working-tree fingerprint

总控接受 DS-02 后，先把 dispatch-record exact-once 查询收敛为同时绑定 `run_id` 与
`refs.attempt_id`，再在下列五个最终 corrective data/test 文件的精确内容上运行 Phase5 focused、
四类 corrective focused、完整 suite、changed Python Ruff、full repository pyright、JSON 与 diff
审计。本 implementation artifact 初版在原 implementation validation 后创建；本 fix loop 的全部
最终验证结束后才计算以下 SHA-256，随后才写入本 DS-08 补充并创建 fix artifact，因此 artifact 写入
不会反向改变这五个被验证文件的 fingerprint。

| validated working-tree file | SHA-256 |
|---|---|
| `docs/cli_init_workspace_manifest_v1.json` | `c646c2a0c7b508f8cc07d7f446273fb37117a8b1d9e47da82bf09f32e9dfd65e` |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | `cd6fe484080290a7ec66a70449697cb49e7fef7bb3c125fd0bb5240a4beaaad4` |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | `c2521212c5705b68cfcdd5bc59cc24fd22ff9be45f36b80a78c2098885c2c991` |
| `tests/service/test_host_assembly.py` | `80c2c399c9a84ab63d95d4ffbdb9220edf4dc3df04248fd260f25cadfd47c884` |
| `tests/host/test_phase5_local_execution_integration.py` | `8e84963898076b851496a51785d5c8038baf4546f448b0eb7f6bdb800fdcef83` |

§6 中 Accepted S7 15-file matrix、typed closure 与首轮偶发诊断保留为原 implementation pass 的历史
证据；本 DS-02 fix 后重新执行并绑定上述最终 fingerprint 的门禁，是 Phase5 focused、四类 corrective
focused、完整 suite、changed Python Ruff、full repository pyright、JSON/diff/hash/status 审计。

## 7. Docs 与 Ruff disposition

S8 owner 的 `README.md`、`dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md` 已在
入口工作树中按 accepted S8 plan 更新，本轮必须原样保留；其 SHA-256 分别保持：

- `ce5d0a9c850b6978da7393c789c378b353c2397c0b1c4a2c4b2c475aac5c6003`
- `3ba963ff0b9cc960c68a6464ec14ab33c1ad8374b3f9e6324b9a97759c7e7317`
- `0700d6709f7c239a499f6e221daefcedba32ea46c8f430484e56e02aa0310812`
- `b2b6e60e5525f888a28434661f6a2dbc2f328acdcf4d9579547fb933e0219c28`

原 S8 artifact SHA-256 也保持
`5c7b90314c489e84d7fcea7eb59ae2d1df408cf190a2626a3ae049963a411ebb`。本轮测试修改命中 README
trigger，但当前测试 owner 说明已由该 S8 README delta 覆盖，且用户明确禁止覆盖，因此不再写第二套
文档事实。

原 S8 artifact 把 full-repository Ruff 97 记为 readiness blocker，需要在此纠正：accepted plan §10–12
的最终完整验证没有 full-repository Ruff gate，97 项是既有跨仓 debt，且本轮没有 production 修改。
本 corrective slice 的适用门禁是 changed Python Ruff，已全绿。该纠正不声称 97 项 debt 已消失，也
不修改原 S8 artifact；它只防止把未授权的全仓 debt 错归为本 slice blocker。

## 8. Residual risks 与 uncovered areas

| Residual / uncovered area | Classification / owner |
|---|---|
| cancel-watchdog 仅在一次 full-suite load 观察 duplicate token request | `assigned to later S8 validation owner`；若后续可稳定重现，由 Host cancellation/watchdog owner 基于直接并发证据处理。本 slice 不规避。 |
| SIGKILL delayed recovery 仅在一次 full-suite load 超时 | `assigned to later S8 validation owner`；若稳定重现，由 Host recovery owner处理。本 slice 不放宽 timeout。 |
| full-repository Ruff 97 | `assigned to later work unit` 的 repository-wide quality debt；非 accepted plan gate，changed Python 已绿。 |
| frozen real CLI/provider/PTy/evidence bundle 尚未重跑 | `covered by later approved slice`：corrective code review通过后回到 S8 integration / real-evidence acquisition。 |
| 当前没有 production coverage delta | 无需当前 slice production coverage；所有改动均为 manifest/test/artifact。 |

没有 unclassified residual risk，没有 blocking open question，也没有发现稳定 production defect。

## 9. Completion signal

四类稳定 integration failure 已在真实语义 owner/test consumer 边界关闭；focused、S7 matrix、完整
6571+ suite、full pyright、changed Ruff、JSON/hash/diff/scans 均通过。DS-02/DS-08 fix gate 完成，
下一未完成 Gateflow entry 是 handoff 给总控进入 corrective re-review；全 work unit 仅 final closeout
停止，中间 gate 不停。
