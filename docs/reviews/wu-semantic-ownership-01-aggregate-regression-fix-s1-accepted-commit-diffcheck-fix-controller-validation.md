# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Accepted-Commit Diff-Check Fix Controller Validation

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix continuation；不是新 WU。
- Finding：`S1-COMMIT-F01`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-accepted-commit-diffcheck-fix-codex.md`，SHA-256 `7d42a0fe4f42479b4bfb55bc99e60f1f54b7944ca6b4119348837120d72a5e43`。

## 2. Controller independent validation

Controller 完整读取 fix artifact并独立验证七个目标文件。每个文件均只删除一个 EOF LF byte，final SHA-256精确匹配 AgentCodex写入前计算的 expected-after hash：

| Artifact | Final SHA-256 | Trailing LF |
| --- | --- | ---: |
| local-trust plan-correction Controller validation | `bf3953a42f9149e7369d77d74d9677b4b11010720929ecafd56e948c26edfc52` | 1 |
| local-trust plan-review Controller adjudication | `7b195d596b1c00a9f6452c3b5f03756690d0a5f0e61d05bb41467d6692e3d54c` | 1 |
| provider-quota-stop Controller adjudication | `b41ef70a436657b9c74f62d6c0d6853ff5b0fb41f2ea483548b1afc874ce7a00` | 1 |
| local-trust resume Controller authorization | `03168041e59eb2d1efc3f9ea8af9a1f0bd4476de3bab7d0fae311aad44694e59` | 1 |
| quota-gate-separation Controller adjudication | `628d69e4d8e7eafbde6b9f33a6aaa5d0287c0998ca937f45fea7cdc6af6ccce4` | 1 |
| secret-finding user-decision Controller record | `af0a897c762765c9c6b56264bb47747c06c1f8ce86cdcb8ccd87355757f5eb84` | 1 |
| test-account-quota user-decision Controller record | `ac7383171afa417bf67a50495614ecfafd055c92670d533821ef55a6c82661b3` | 1 |

AgentCodex提供逐文件 before/prefix/after raw-byte proof：修复前均为 `prefix + LF + LF`，修复后均为相同 `prefix + LF`；prefix SHA不变，删除字节数均为 1。没有正文、行内空白、代码、测试、配置、design、plan、control、README或其它 artifact变化。

## 3. Immutable locks

- 八测试 ordered manifest仍为 `bcfc4088dfb2239236579159b71f6abc8e51a32201de240603f3a2eebd954c41`。
- Slice 1 implementation artifact仍为 `0e9d47aaba7a2cb0c7c2642ebb5163f2cdcec99a4a988a60d5a2fdd29753ea24`。
- Final MiMo/DS/Controller re-review hashes仍为 `4ab6b9d3...8c2ca`、`66bb3af1...6789e`、`2c831fb2...b34c9`。
- staged tree在 AgentCodex退出时为空；普通 `git diff --check`通过。
- 未运行或调用真实 provider，未修改 quota/config/model/key/retry/budget。

## 4. Decision

```text
PASS / S1-COMMIT-F01 CLOSED / READY_FOR_CONTROLLER_EXACT_SCOPE_RESTAGE
```

下一 gate 只授权 Controller重新暂存当前 exact 44-path Slice 1 scope，执行 `git diff --cached --check`、path scope/digest audit并创建 accepted local commit。若 staged gate仍有任何 error或额外path，必须再次停止；Slice 2仍未授权到 commit成功与 clean-tree验证完成。
