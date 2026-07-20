# WU-SEMANTIC-OWNERSHIP-01 / R09 code re-review finding fix Controller validation

## 1. Gate 与结论

- 当前仍是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R09 的 code re-review finding fix validation，
  不是新 WU、issue、feature 或历史 sub-WU reopen。
- authority：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-controller-adjudication.md`。
- accepted finding：仅 `R09-RR-F01`。
- Controller verdict：`PASS / READY_FOR_SECOND_DUAL_COMPLETE_CUMULATIVE_CODE_REREVIEW`。
- `R09-RR-F01` 已关闭：Fins 主要组件树仅补入 `direct_events.py` 与 `direct_stream.py` 两个
  R09 稳定 owner，没有扩成顶层文件流水账。

## 2. Scope 与 immutable locks

- branch：`phaseflow/host-issues-control`。
- HEAD：`9d36a115400fb59fd95475189810b43a09fda31b`。
- staged tree：empty。
- sorted newline-delimited 12-path manifest SHA-256：
  `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`。
- final canonical cumulative binary diff SHA-256：
  `60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e`。
- `dayu/fins/README.md`：791 lines，SHA-256
  `2f94d7b7efb880063cb75ed6c8e5a7740d117761ec66a969c73bd754a3d14d76`。
- AgentCodex fix artifact：
  `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-fix-codex.md`，
  145 lines，SHA-256
  `368b7f25019676c24cb0e87813d8feb04219377a90ef2e2f051910d98ccd9eaa`。

README 之外 11 个 target 的行数与 SHA-256 均与 fix authority entry locks 完全一致：

| Path | Lines | SHA-256 |
|---|---:|---|
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
| `dayu/fins/direct_events.py` | 496 | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` |
| `dayu/fins/direct_stream.py` | 261 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |
| `dayu/service/fins_direct.py` | 467 | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |
| `tests/cli/test_fins_commands.py` | 1803 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` |
| `tests/fins/test_fins_direct_stream.py` | 742 | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` |
| `tests/fins/test_fins_ingestion_runtime.py` | 4925 | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` |

因此本 finding fix 的唯一产品文档 drift 是获授权的 Fins README 两行；产品 Python、测试和其它
target README 均无 drift。

## 3. Controller 独立验证

所有 Python 验证均先执行 `source .venv/bin/activate`。

| Validation | Result |
|---|---|
| README exact owner projection | pass；主要组件树精确包含两个 R09 owner，未增加第三个条目 |
| R09 affected aggregate | `161 passed, 3 existing warnings` |
| full pyright：`python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff：9 个 changed Python files | `All checks passed!` |
| 12-path manifest / canonical diff / 12 个 content locks | pass；全部匹配上述 final locks |
| `git diff --check` | pass，零输出 |
| staged tree | empty |

## 4. 沿用的 immutable evidence

本轮只修改 README；11 个产品/测试/其它 target 内容锁无变化。因此沿用上一 Controller final
validation 已锁定且未被本轮重新解释的证据：

- R06 regression：`242 passed, 3 existing warnings`；
- R08 regression：`180 passed, 3 existing warnings`；
- full Fins：`873 passed, 1 existing skip, 3 existing warnings`；
- changed production file coverage：`92.21% / 97.78% / 90.44% / 90.16% / 88.56%`；
- retained security：16 个 exact parameter cases 全部通过；
- fresh real SEC download、Docling process、upload_filing smoke：三条均 exit 0。

这些证据只证明当前 immutable 产品/测试树；README-only fix 不承担也不改变其业务语义。

## 5. Findings、边界与 next gate

- `R09-RR-F01`：`fixed-and-controller-validated`。
- 当前 accepted/open code-review finding：0。
- 当前 blocker：0。
- Issue 142、151、175、177、178，Web/WeChat/render trackers，Topic 8/9 和统一 tool
  authorization framework 均未进入本 gate。
- 未 stage、commit、push 或创建 PR。
- next gate：AgentMiMo / AgentDS 对上述完整 12-path cumulative target 进行第二轮完整并发
  code re-review；必须同时复核全部代码和 `R09-RR-F01` 的精确 closure，不能只看 README diff。
