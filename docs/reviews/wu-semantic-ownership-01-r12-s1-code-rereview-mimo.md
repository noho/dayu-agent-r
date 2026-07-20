# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Code Re-Review — AgentMiMo

## 1. Gate identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Internal remediation sub-WU：R12，`dayu-cli init` workflow。
- Slice：S1 — typed catalog、manifest projection 与 OS environment owner。
- Accepted-plan HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Immutable plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，
  608 lines，SHA-256
  `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`。
- AgentCodex completion artifact：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-implementation-codex.md`，
  248 lines / SHA-256
  `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed`。
- Controller validation：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-controller-validation.md`，
  SHA-256
  `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19`。
- Controller adjudication：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-controller-adjudication.md`，
  SHA-256
  `b3a9aca59a9f03bd1cf143bc6f4e5f30e35560d09054d1240f72d5dd5f441c19`。
- Fix controller validation：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-fix-controller-validation.md`，
  SHA-256
  `fd4afc8c6bc5bc52a56bf6552d8de84658a6922727a4f65fffc9658397105527`。
- Initial review (MiMo)：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-mimo.md`，
  SHA-256
  `4f27c186ac0ec9f439956f5eadf34458dd7f11455d5a8684f57e9d3dfcdc7492`。
- Initial review (DS)：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-ds.md`，
  SHA-256
  `06094e2704e6f8a42385f77e7d0e0fa56474be40272bfe511948b81958900652`。
- Codex fix artifact：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-fix-codex.md`，
  SHA-256
  `b9702a729a080b53d4585527f722b905777102bcf9f1288f2e0dbd49bd48fb44`。

本 artifact 是第一路独立完整 code re-review，在 Codex fix 后对 cumulative S1 tree
做独立验证与裁决。

## 2. Scope、hash 与完整阅读

Re-reviewer 完整逐行阅读了以下文件：

| Path | Lines | SHA-256 |
|---|---:|---|
| `dayu/cli/init_catalog.py` | 854 | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `dayu/cli/init_environment.py` | 584 | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` |
| `tests/cli/test_init_catalog.py` | 610 | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` |
| `tests/cli/test_init_environment.py` | 672 | `ae243050136d92e0c772caf3a51b3bdd999ff8efe3af096d73161f32473fd947` |

Hash 比对确认：

- `init_catalog.py` 和 `test_init_catalog.py` 的 SHA 与 Controller validation 中的
  记录一致——未被 Codex fix 修改。
- `init_environment.py` 和 `test_init_environment.py` 的 SHA 与 Codex fix artifact
  中的 post-fix hash 一致——fix 已正确应用。

## 3. HIGH R12-S1-CR-F01 裁决：marker-substring false rejection

### 3.1 Finding 回顾

Controller 在 validation 中发现：`_parse_managed_block()` 使用全文
`content.count(marker)` 检测嵌入 marker，导致合法 secret value 包含 marker 子串时
被错误拒绝。Codex fix 将检测逻辑改为逐行解析，只在非 export 行或 export 名称部分
检测 marker 子串，export 等号右侧的 value 部分被正确跳过。

### 3.2 独立验证

Re-reviewer 独立运行了以下对抗测试：

**合法 marker value × create/replace（6 cases）：**

| Case | marker fragment | profile state | 结果 |
|---|---|---|---|
| begin-only + absent | `# >>> dayu-cli init >>>` | absent | ✅ SUCCESS |
| end-only + absent | `# <<< dayu-cli init <<<` | absent | ✅ SUCCESS |
| both + absent | begin + end | absent | ✅ SUCCESS |
| begin-only + existing | `# >>> dayu-cli init >>>` | existing | ✅ SUCCESS |
| end-only + existing | `# <<< dayu-cli init <<<` | existing | ✅ SUCCESS |
| both + existing | begin + end | existing | ✅ SUCCESS |

所有 6 cases 均正确：profile 写入成功、marker 结构恰好一对、value 被保留、
进程环境注入、secret 不泄漏。

**Malformed marker 结构仍 fail closed（9 cases）：**

| Case | 描述 | 结果 |
|---|---|---|
| missing-end | begin 无 end | ✅ rejected |
| missing-begin | end 无 begin | ✅ rejected |
| reverse-order | end 在 begin 前 | ✅ rejected |
| multiple-blocks | 两个完整 block | ✅ rejected |
| ordinary-text-embedded-marker | 普通文本含 marker | ✅ rejected |
| comment-embedded-marker | 注释含 marker | ✅ rejected |
| invalid-block-line | block 内非 export 行 | ✅ rejected |
| invalid-block-export-shape | export 缺 `=` | ✅ rejected |
| invalid-block-export-name-with-marker-value | 非法名 + marker value | ✅ rejected |

所有 9 cases 均正确拒绝，且拒绝发生在 profile 未被修改前（fail closed）。

**额外边界测试（re-reviewer 独立运行）：**

| Case | 输入 | 预期 | 实际 |
|---|---|---|---|
| marker in value, no block | `export MIMO_API_KEY="# >>> ..."` | None | ✅ None |
| marker in bare non-export | `random text # >>> ...` | reject | ✅ rejected |
| marker before `=` in export | `export # >>> ...>>=value` | None | ✅ None（注 1）|
| CRLF line endings | managed block with `\r\n` | parse | ✅ parsed |
| empty managed block | begin + end, no exports | parse | ✅ 0 names |
| export with tab | `export\tNAME=1` | reject | ✅ rejected |
| bare `=` in block | `=` | reject | ✅ rejected |
| `export=` no name | `export=1` | reject | ✅ rejected |
| value with multiple `=` | `export NAME="a=b=c"` | parse | ✅ parsed |
| empty value | `export NAME=` | parse | ✅ parsed |
| both markers in one value | begin+end in single value | parse | ✅ parsed |
| partial marker substring | `# >>> dayu-cli init >>` | None | ✅ None |

注 1：`export # >>> dayu-cli init >>=value` 中 marker 子串出现在 export 名称部分，
但因为 `export_head.startswith("export ")` 后 `export_head` 不含精确 marker 子串
（尾部少一个 `>`），所以 `marker_is_in_export_value` 为 True，被跳过。该行后续由
`_parse_export_name` 处理，变量名 `# >>> dayu-cli init >>` 不在 allowlist 中，
在实际 persist 流程中会被 `_validate_environment_name` 拒绝。这不是 parser 的
marker 检测缺陷，因为真正的防护在 name validation 层。

### 3.3 裁决

**R12-S1-CR-F01：CLOSED。**

Codex fix 正确解决了 Controller 发现的 marker-substring false rejection。修复策略
（逐行解析、只在非 export 行或 export 名称部分检测 marker 子串）合理且保守：

- 合法 value 含 marker 子串不再被错误拒绝。
- Malformed marker 结构（缺失、逆序、多块、嵌入、配对错误）仍然 fail closed。
- 不扩大 value reject 集合（空值、NUL、CR、LF 仍由 entry-level validation 处理）。
- 不泄漏 secret（`repr(result)` 不含 value）。
- 不改变 Windows contract（Windows 路径不受 POSIX parser 影响）。
- 不改变 catalog contract（`init_catalog.py` 未被修改）。

### 3.4 对抗检查补充

**Parser 是否把看似 export 的任意行错误放行？**

不会。`_parse_managed_block` 的 marker 检测逻辑要求行同时满足：
1. 不是 begin/end marker 行本身。
2. 是 `export NAME=VALUE` 格式（`partition("=")` 且 `startswith("export ")`）。
3. `export_head`（`=` 左侧）不含 marker 子串。

不满足以上条件的行如果包含 marker 子串，会被拒绝。block 内的行由
`_parse_export_name` 进一步校验：必须 `startswith("export ")`、含 `=`、
变量名在 allowlist 中。

**写后 state 是否一致？**

- POSIX：原子 `os.replace` 后 profile 内容恰好包含一个 begin/end pair 和
  shlex-quoted exports。`os.environ` 只在整个批次成功后注入。
- Windows：`setx` 逐个调用，首个失败停止，只报告 written/unwritten names。
  跨变量不可回滚是 accepted plan residual。

**Value-object equality no-fix 是否保持？**

`InitModelChoice` 是 `frozen=True` dataclass，自动生成的 `__eq__` 按值比较。
`replace(original)` 产生的 value-equal copy 通过 `in INIT_MODEL_CHOICES` 检查。
这是正确行为——`tuple.__contains__` 使用 `__eq__`，不要求 identity。不需要引入
registry/framework/identity shim。

## 4. Scans

### 4.1 Focused tests

```
tests/cli/test_init_catalog.py: 31 passed
tests/cli/test_init_environment.py: 35 passed
Combined: 66 passed in 0.22s
```

### 4.2 Coverage

```
init_catalog.py: 276 statements / 27 miss / 90.22%
init_environment.py: 233 statements / 13 miss / 94.42%
```

两个 production 文件均满足 `>=80%` gate。

### 4.3 Full pyright

```
0 errors, 0 warnings, 0 informations
```

### 4.4 Scoped Ruff

```
dayu/cli/init_catalog.py: All checks passed!
dayu/cli/init_environment.py: All checks passed!
tests/cli/test_init_catalog.py: All checks passed!
tests/cli/test_init_environment.py: All checks passed!
```

### 4.5 Full Ruff baseline

```
Baseline: 144 findings, SHA-256 051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea
Current:  144 findings, SHA-256 051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea
Match: YES
```

### 4.6 Security scan (Ruff S rules)

```
S101 (assert): 137 hits — all in test files, expected
S106 (hardcoded-password-func-arg): 14 hits — all are env var names (e.g. "MIMO_PLAN_API_KEY"), not actual passwords
S603 (subprocess-without-shell-equals-true): 1 hit — Windows setx, by design (shell=False)
S607 (start-process-with-partial-path): 1 hit — same Windows setx call
```

No real security issues. `shell=True`、`text=True`、`print` 在 production 文件中均为零命中。
`hasattr`/`getattr` 在 production 文件中均为零命中。

## 5. Finding closure / new findings

### 5.1 R12-S1-CR-F01 (HIGH) — CLOSED

见 §3。Codex fix 正确解决。re-reviewer 独立验证通过。

### 5.2 新 findings

**未发现实质性问题。**

Re-reviewer 在独立逐行审查中未发现新的 correctness、security 或 architecture
defect。以下为已知 accepted residuals（非新 findings）：

- Windows `setx` 跨变量不可回滚：accepted plan residual，由 S3 real Windows gate 承担。
- `export # >>> ...>>=value` 类 edge case：marker 出现在 export 名称部分但因
  substring 不精确匹配被跳过——实际无害，因为变量名不在 allowlist 中，会在
  name validation 层被拒绝。

## 6. Open Questions

无。

## 7. Residual Risk

- Test coverage 未达 100%：`init_catalog.py` 90.22%、`init_environment.py` 94.42%。
  未覆盖行主要是 error-path guard 和 defensive checks，风险低。
- `_parse_managed_block` 的 marker-in-export-value 逻辑没有专门的 unit test
  覆盖 export 名称部分含 marker 子串但 substring 不精确匹配的 edge case
  （如 `export # >>> dayu-cli init >>=value`）。该路径在实际 persist 流程中
  会被 name validation 拦截，但 parser 本身的静默跳过行为值得在后续 round
  补充测试。

## 8. Authority hashes

| Artifact | SHA-256 |
|---|---|
| Accepted plan | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` |
| AgentCodex completion | `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed` |
| Controller validation | `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19` |
| Controller adjudication | `b3a9aca59a9f03bd1cf143bc6f4e5f30e35560d09054d1240f72d5dd5f441c19` |
| Fix controller validation | `fd4afc8c6bc5bc52a56bf6552d8de84658a6922727a4f65fffc9658397105527` |
| Initial review (MiMo) | `4f27c186ac0ec9f439956f5eadf34458dd7f11455d5a8684f57e9d3dfcdc7492` |
| Initial review (DS) | `06094e2704e6f8a42385f77e7d0e0fa56474be40272bfe511948b81958900652` |
| Codex fix | `b9702a729a080b53d4585527f722b905777102bcf9f1288f2e0dbd49bd48fb44` |
| init_catalog.py | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| init_environment.py | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` |
| test_init_catalog.py | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` |
| test_init_environment.py | `ae243050136d92e0c772caf3a51b3bdd999ff8efe3af096d73161f32473fd947` |
| Full Ruff baseline | `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` |

## 9. Final verdict

| Item | Status |
|---|---|
| R12-S1-CR-F01 (HIGH) | **CLOSED** — Codex fix verified |
| New findings | **0** |
| Accepted open | **0** |
| Blockers | **0** |
| Residual owner | S3 real Windows gate (accepted plan) |
| Ready for Controller adjudication | **YES** |
