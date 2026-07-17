# WU-SEMANTIC-OWNERSHIP-01 / R09 cumulative implementation Controller validation

## 1. Decision

`PASS / READY_FOR_DUAL_COMPLETE_IMMUTABLE_CUMULATIVE_CODE_REVIEW`。

本结论只授权对同一 immutable R09 cumulative implementation target 做 AgentMiMo / AgentDS 双路完整 code review；不代表代码已接受，不授权 commit、aggregate deepreview、R10、push 或 PR。

R09 仍是现有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 overdesign remediation continuation 内部 sub-WU，不是新 WU、feature/issue 或重开旧 sub-WU。

## 2. Immutable target locks

- implementation base / current HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`；
- base tree：`4112761a35ed2a6b806caaaedd5654e93acfee9e`；
- fixed plan SHA-256：`a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`；
- implementation authorization SHA-256：`c9341d7b6c0c1eaa62578d68f7f34ed973ab63d67e3da6c4c1442d988d3a49e4`；
- AgentCodex implementation artifact：`docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-implementation-codex.md`，274 lines，SHA-256 `3c16b65678e234f3f88379c01a371eb3059f5bb52ff68ac1db772a5c135d2d81`；
- sorted 12-path product/test/README manifest SHA-256：`ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`；
- canonical cumulative binary diff SHA-256：`531ac9fa62112c8e9e69051b2bda9185d2f49fbdf8cc621eeaba2084065d85e8`；
- coverage JSON SHA-256：`8ba9abf67272ad157d807234731a9907f320624b1e30c97bb6593cd9571becef`；
- staged tree：empty。

Controller 独立重算了 manifest、全部 12 个 content SHA 与 canonical binary diff，均与 implementation artifact 一致。

## 3. Exact reviewed path manifest

1. `dayu/cli/commands/fins.py` — `c60e5152fa7e7db7d5795ce7845f7f285f3c52d9392df9140d66ef078a9b7e59`
2. `dayu/fins/README.md` — `81f788b1e935bb06293bb866f47be3dd907424dc86cb65fded18aaf0ba388252`
3. `dayu/fins/direct_events.py` — `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a`
4. `dayu/fins/direct_stream.py` — `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53`
5. `dayu/fins/ingestion_runtime.py` — `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580`
6. `dayu/service/README.md` — `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d`
7. `dayu/service/fins_direct.py` — `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac`
8. `tests/README.md` — `3355e9652e7e373e4526ce1862ae6e270924487fa8e6a2d3a123ee02e7755d7e`
9. `tests/cli/test_fins_commands.py` — `d425cf29aa909014c09ea92069cf3e41539a7720385f69fa64b6f7ae6a957f4c`
10. `tests/fins/test_fins_direct_stream.py` — `7607a6ff790031ad15b6fc66478dfad3d0d2db15dfc3cf65d30f1856d8ee6ceb`
11. `tests/fins/test_fins_ingestion_runtime.py` — `8fd5f5a95333da40df5ffb4b2dc1178c3c6e874d468c7659198fb6d820826f02`
12. `tests/service/test_fins_direct.py` — `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162`

Controller-owned modified control doc、untracked authorization 与本 validation artifact不是 implementation diff；reviewer 可以读取为 gate evidence，但不得把它们计入 code target或修改共享 tree。

## 4. Direct code and contract validation

Controller 完整读取 implementation artifact、新 `direct_stream.py`、production diff、测试迁移和三份 README，并复核：

- `ValidatedFinsEventStream` 是 missing/duplicate/event-after、buffer-until-clean-EOF、terminal availability 与 raw close lifecycle 的唯一 production decision owner；
- runtime `download/preprocess/upload` 是 plain `def`，直接以 raw `AsyncGenerator` 构造 validator；raw bridge 不再 import/构造 protocol error；
- Service protocol/public/private methods 直接返回同一个 validator，不 await/iterate/wrap/rebuild；
- CLI 删除 `_direct_operation_kind` 与 missing fallback，完整消费 validator 后读取 `terminal_result`；既有 prefix/message/exit、business result 与 SIGINT路径保留；
- process filing/material 的 validator provenance 是 runtime `PREPROCESS`，Service command alias 只用于日志；
- `FinsDirectStreamProtocolErrorKind.EVENT_AFTER_RESULT` 是唯一新增 code；没有 alias、兼容 parser、第二 error schema或 speculative producer channel；
- Fins/Service/tests README只同步当前已实施职责，root/dayu README 与 design truth no-touch；
- retained leakage/cancellation/backpressure/containment/symlink/atomic/process/security行为未删除或放宽。

本 gate 没有裁决 code finding；所有 correctness、lifecycle、typing/test-seam 或 maintainability疑点必须由双路 reviewer给出带代码证据的 finding，再由 Controller裁决。

## 5. Independent Controller validation

Controller 在 immutable tree 上独立执行并取得：

| Validation | Result |
|---|---|
| affected complete-tree suite | `155 passed, 3 existing warnings` |
| R06 storage regression | `242 passed, 3 existing warnings` |
| R08 financial/XBRL regression | `180 passed, 3 existing warnings` |
| full Fins | `874 passed, 1 existing skip, 3 existing warnings` |
| full pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff, all 9 changed Python files | `All checks passed!` |
| `git diff --check` | pass |
| staged tree | empty |

Controller 对同一 coverage data 独立执行五次 `--fail-under=80`：

- `direct_events.py` 92%；
- `direct_stream.py` 97%；
- `ingestion_runtime.py` 90%；
- `service/fins_direct.py` 90%；
- `cli/commands/fins.py` 88%。

Controller 还在两个 fresh controller workspace 独立重跑真实 success smokes：

- SEC AAPL 10-K download：exit 0，`discovered=1/downloaded=1/written=1`；
- process / Docling：exit 0，`selected=1/processed=1`；
- upload_filing / Docling：exit 0，`uploaded_files=1`。

Source/propagation scans确认 Service/CLI旧 checker/fallback、Service/CLI enum/reason ownership、runtime/Service protocol-error import均为零；三个 reason literal只在 `direct_events.py`定义和`direct_stream.py` decision中；weak-type/compat新增行扫描为零。

## 6. Mandatory dual-review questions

两路 reviewer 必须完整、独立回答，不能只复述测试通过：

1. 状态机是否在 clean EOF、buffered result、duplicate、event-after、result-then-error、upstream error/cancel、显式/repeated close 和 close failure全部保持 exactly-one-and-last、primary identity/cause 与 raw close-at-most-once；是否存在并发/中止路径让 terminal success提前或晚发布。
2. 当 CLI consumer 在两次 `__anext__` 之间因 rendering/logging/其它下游异常退出时，当前 concrete iterator与 caller cleanup是否保证 raw source及时 close、取消 producer并阻止 late publication；若不保证，必须给出可复现路径和 owner-level最小修复，不得加 fallback。
3. owner tests把 `_ControlledRawStream` cast为 concrete `AsyncGenerator` 是否会掩盖真实 async-generator `aclose`/exception行为或违反项目 strict typing；若是，给出不复制 production算法的真实-generator测试边界。
4. runtime/Service/CLI exact signature cutover是否遗漏任何 production caller、await/async-generator假设、Protocol实现或 fake；`process_filing/material`是否始终保留 runtime PREPROCESS provenance。
5. CLI presentation、SIGINT race、business failure/cancel terminal和 generic producer exception映射是否保持，且 typed reason不成为新 public输出协议。
6. README、coverage、test migration、安全/no-deferred/no-touch是否真实覆盖当前 diff；删除的三项 runtime checker tests是否由 owner tests完整承接而无 fixture算法漂移。

## 7. Next gate

对上述同一锁定 target并发执行 AgentMiMo / AgentDS 双路完整 code review。任一 target content、manifest、diff或implementation artifact变化会使两路 review失效。reviewer只能新增各自 review artifact，不得修改 implementation、tests、README、control或prior artifacts。

review verdict不自动接受实现。所有 finding由 Controller逐项裁决；全部 accepted findings必须交AgentCodex修复并完整 revalidation、双路完整 re-review。即使零 accepted finding，也仍需 durable adjudication、zero-change closure/re-review和后续 aggregate deepreview；当前不得 commit或进入R10。
