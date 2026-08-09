# WU-CLI-CONFORMANCE-F01-F07 S1/F01 Corrective Review 总控裁决

## Gate 元数据

- Gate：`S1 corrective fix review`
- Base/HEAD：`e5b572d44fa86beac8a23413007cc48805c9ba67`
- Implementation artifact：`docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-fix-codex.md`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s1-corrective-code-review-ds.md`
- 裁决结论：`PASS — 无 accepted finding，S1 cross-slice regression 已收口`

## 独立证据裁决

| 检查项 | 状态 | 总控直接证据 |
|---|---|---|
| root cause | `pass` | `EntrypointRuntimeRequest` owner 已由 S1 删除 `explicit_config_dir`；两个 utils typed constructor仍传旧 keyword，修复前各产生一个 `reportCallIssue`。 |
| fix boundary | `pass` | 两个 utils 文件各仅删除一行 `explicit_config_dir=None`，无其它代码变更；没有恢复字段、alias、wrapper、default、loose parsing 或下游补偿。 |
| constructor inventory | `pass` | 全部 13 个 `EntrypointRuntimeRequest(...)` 与 4 个 `ServiceHostAdminRequest(...)` call site 经两路独立扫描无旧 keyword；Python 源中唯一 `explicit_config_dir` 是 owner-level 字段不存在负向断言。 |
| lower-level owner | `pass` | `dayu.runtime.location` 的 `explicit_config_overlay_dir` 仍是独立公共 resolver contract，不是 CLI入口或兼容残留，不应删除。 |
| type/compile/import | `pass` | 两个 focused pyright、full pyright均为 `0 errors, 0 warnings, 0 informations`；两个脚本 `py_compile` 与 import 均 exit 0。 |
| docs/tests scope | `pass` | `utils/` 按 AGENTS 默认无 test/coverage要求；机械 typed-contract修复不改变用户行为或分层，不触发 README。真实 provider/Host smoke 归 S8最终 evidence，不在本 gate扩张。 |
| integrity | `pass` | `git diff --check`、两份 registry JSON解析、冻结 SHA-256均通过；registry无 diff，index为空。 |

## Review findings 与 residual disposition

- MiMo：无 finding。
- DeepSeek：无 finding。
- 未运行真实外部 provider/Host smoke：`covered by later approved slice S8`；该 residual 不阻塞当前机械 contract closure。
- 原 plan inventory 未含 `utils/`：`fixed by current corrective gate`；全仓 typed constructor与旧符号扫描已补足，不再有未分类残留。
- 当前无未分类 residual risk，无需 fix/re-review。

## Validation snapshot

- Focused pyright（两个 utils）：`0 errors, 0 warnings, 0 informations`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Compile/import：通过。
- `git diff --check`：通过。
- Registry SHA-256：
  - oracle：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
  - scenarios：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`

## Accepted corrective commit boundary

只允许按显式路径 stage 两个 utils 文件、corrective implementation artifact、两份独立 review artifact与本裁决，共六个文件。不得混入生产代码、tests、README、design、registry 或其它 artifacts；commit 后不 push，进入 S3/F03 implementation gate。
