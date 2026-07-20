# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Accepted-Commit Diff-Check Fix

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 1 continuation；不是新 WU。
- Finding：`S1-COMMIT-F01 = ACCEPTED / LOW / COMMIT_GATE_BLOCKING / semantic impact NONE`。
- 授权 owner：七个指定 Markdown artifact 的 EOF formatting。
- Verdict：`PASS / EXACT SEVEN-ARTIFACT MECHANICAL FIX COMPLETE / READY FOR CONTROLLER RESTAGE VALIDATION`。

## 2. Required inputs

AgentCodex 完整读取以下 gate inputs 至 EOF：

- `AGENTS.md`：128 行 / 10,036 bytes。
- `docs/host/issues-implementation-control.md`：2,322 行 / 586,628 bytes / SHA-256 `fd31fad0385b9f4e1d73f00e36d255beb34cb0894190f49ee5ad6449b403a764`。
- `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-accepted-commit-diffcheck-controller-adjudication.md`：47 行 / 2,985 bytes / SHA-256 `a46eafc02078aabab17863f5cb6dd97eef77f2a40391935221e3ccef978a0532`。
- Controller 指定的七个目标 artifact 全文。

直接证据确认问题真实存在：七个此前 untracked Markdown 均恰好以两个连续 LF bytes 结束；普通 unstaged `git diff --check` 不检查 untracked 输入，Controller 的 exact-scope staged gate 才首次暴露 `new blank line at EOF`。正确 owner 是 artifact 自身的 EOF formatting，不需要代码、测试、配置或下游补偿。

## 3. Semantic-byte proof

证明方法：对每个文件以 raw bytes 读取，令 `prefix` 为删除全部连续尾随 `0x0A` 后的字节串。修复前均满足 `before = prefix + 0x0A + 0x0A`；修复后均满足 `after = prefix + 0x0A`。逐文件 `prefix_sha` 前后相同，且 `after_sha` 精确等于修改前计算出的 expected after SHA，因此除最后一个多余 LF byte 外，全部 prefix bytes byte-identical。

| Path | Before bytes / SHA-256 | Prefix SHA-256 | After bytes / SHA-256 | 删除字节数 |
| --- | --- | --- | --- | --- |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-controller-validation.md` | 5,078 / `6fba19b2871f9553fc779d71ca33218bba102236fe3bf4d271526518a09dd7d2` | `4c824533fe88cc14b02bc79ffe06201209ac08d2aaedcd40798c083575b899d0` | 5,077 / `bf3953a42f9149e7369d77d74d9677b4b11010720929ecafd56e948c26edfc52` | 1 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-review-controller-adjudication.md` | 3,872 / `5abc0505e2ed7e47763557bfa53201afd5fd99f16d2c98115d04febdbcb3f59c` | `794a1e5c62a6033761a7e7973f492e09f52a7593ff83ea9d8d94713a373c1aac` | 3,871 / `7b195d596b1c00a9f6452c3b5f03756690d0a5f0e61d05bb41467d6692e3d54c` | 1 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-local-trust-provider-quota-stop-controller-adjudication.md` | 5,269 / `efefd473711e017fbf8fadfc6f056c1222d3dab3134e26a0c06e55b184da48fd` | `a4db99ff08f31045b90fc85e913e83a88001caf9ec81ef811a10435614ac4616` | 5,268 / `b41ef70a436657b9c74f62d6c0d6853ff5b0fb41f2ea483548b1afc874ce7a00` | 1 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-local-trust-resume-controller-authorization.md` | 5,897 / `32f172375d49b505e8dbeeb15034d650ee83eed6e38402e6b6002e3d13315f50` | `0c47e422e267118ff7c7a22eaeb66676c0feb549846bfe62ee10127665895308` | 5,896 / `03168041e59eb2d1efc3f9ea8af9a1f0bd4476de3bab7d0fae311aad44694e59` | 1 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-quota-gate-separation-controller-adjudication.md` | 4,136 / `aa6be1e35db8b3ec3528c28fcf60103ca0b54e0b33c954fca326381a92c921c5` | `61b8b9aefe971d9502e841f23623fa946747d18794deec7921b483b6d8cf54b2` | 4,135 / `628d69e4d8e7eafbde6b9f33a6aaa5d0287c0998ca937f45fea7cdc6af6ccce4` | 1 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-user-decision-controller-record.md` | 4,340 / `4a75899fbdb8244d93f1633b0be3f36e65d2ae211a3211f57f326289f6c3f12b` | `c3327524ad24c934d543b5405d420ae0c1f5234e3b39268e080b217d37f1380f` | 4,339 / `af0a897c762765c9c6b56264bb47747c06c1f8ce86cdcb8ccd87355757f5eb84` | 1 |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-test-account-quota-user-decision-controller-record.md` | 1,888 / `835361b10497beba061582855063be57d41d0e4ce1f416f275b06fff8997c02f` | `5f5b93465d2b03f4bb1bae3e7aabce1b6626274592d78a3fd7754eb036dc0a68` | 1,887 / `ac7383171afa417bf67a50495614ecfafd055c92670d533821ef55a6c82661b3` | 1 |

七个文件的 final raw-byte predicate 均为：`trailing_lf = 1`、`endswith newline = true`、`endswith double newline = false`。

## 4. Immutable locks

八测试逐文件 SHA-256 仍为：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
20f41229f4e0da48aa1f3904d3bd5c61f436f7a9a706dfe78e899a4d06dccda2  tests/host/test_audit_sink.py
4d9dbb9b5a215597182166b6a92c2d1d30447ae21539bf77602cc6b7c7869140  tests/host/test_tool_trace_projection.py
047b89fd099fdc3250bdcdc066487b05bcf70aeccc18b60228f3bb10cca90c77  tests/host/test_host_activity_event_projection.py
4ed1693ee6819caf99072883e850f2a11e0ccb11636a196b0af629205cd46190  tests/host/test_run_input_builder.py
e874e77e997039d7d1e907dc4df5e980edae876e3920ac4417e3836cabf5b180  tests/host/test_logging.py
```

以上述固定顺序形成的 `shasum -a 256` manifest SHA-256 仍为 `bcfc4088dfb2239236579159b71f6abc8e51a32201de240603f3a2eebd954c41`。

其它 required locks：

- implementation artifact：`0e9d47aaba7a2cb0c7c2642ebb5163f2cdcec99a4a988a60d5a2fdd29753ea24`。
- final AgentMiMo rereview：`4ab6b9d36aece10030440bd8ea1da7e19c8ca5c4eb154cca730ca7beb1d8c2ca`。
- final AgentDS rereview：`66bb3af17ff4c07b52f28a0491619858698359f46e743c6228a700dd8566789e`。
- final rereview Controller adjudication：`2c831fb26d7c06d8b8666ffb3b281d0417a94de397b96bca3bc480f6ca3b34c9`。

## 5. Scope and gate validation

- 排除七个授权目标与本 fix artifact 后，改动前后 dirty-tree path/status/content manifest均为 35 paths / SHA-256 `ef55f2dc552df570a6ba955d0265ffc1423974642ef88b5b522cece5a58ebe1a`；授权范围外零漂移。
- `docs/host/issues-implementation-control.md` 与本 gate Controller adjudication hashes保持 `fd31fad0...a764`、`a46eafc0...0532`；未修改 control 或既有 adjudication。
- staged tree：`EMPTY`；AgentCodex未 stage、commit、push或创建 PR。
- `git diff --check`：`PASS`。
- 没有修改代码、测试、config、design、plan、control、README、implementation artifact、七个授权目标以外的 review artifacts或其它文件；七个目标只删除各 1 个 EOF LF byte，另只新增本固定 evidence artifact。
- 本 gate 未运行或调用任何真实 provider，未读取或输出 configured secret value/ref，未修改 provider quota、model、key、retry、budget或 config。
- 代码树与八测试/final evidence locks不变，因此既有 focused、pyright、Ruff 与 configured-value PASS仍对应同一代码树；本纯 artifact-byte gate不重复执行测试或 provider validation。

## 6. Final verdict

`PASS / S1-COMMIT-F01 CLOSED / READY FOR CONTROLLER RESTAGE VALIDATION`
