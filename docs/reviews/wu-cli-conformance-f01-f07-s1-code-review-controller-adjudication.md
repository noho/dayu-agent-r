# WU-CLI-CONFORMANCE-F01-F07 S1/F01 Code Review 总控裁决

## Gate 元数据

- Gate：`S1 implementation slice review`
- Base/HEAD：`4a3dca64466717ebbc1f8c36f4114207b8aed6de`
- Implementation artifact：`docs/reviews/wu-cli-conformance-f01-f07-s1-implementation-codex.md`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s1-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s1-code-review-ds.md`
- 裁决结论：`PASS — 无 accepted code finding，允许创建 S1 accepted slice commit`

## 独立证据裁决

两路 reviewer 都给出 PASS，但总控逐项回到 frozen F01、accepted plan §3、生产 diff 与 owner tests：

| 检查项 | 总控状态 | 直接证据 |
|---|---|---|
| parser/public CLI surface | `pass` | `ParsedCliArgs.config_dir`、runtime parent、`--config` action、二次 reject、namespace default 全部删除；17 个 parser scope 的 actions/help 零入口。 |
| helper/export/forwarding | `pass` | `CONFIG_DIR_OPTION_NAME`、`resolve_explicit_config_dir`、export、session/runtime forwarding 与两个 Service request 字段均删除；无 alias/wrapper/default/loose parsing。 |
| parse-before-side-effect | `pass` | prompt、interactive、session admin sentinel tests 令 Service preparation 被调用即失败；removed option 均在 parser usage error 2 结束，captured request 为空。 |
| split-value argparse behavior | `pass` | `--config=/tmp/x` 在各 scope 走 unrecognized argument；split `--config /tmp/x` 在部分 scope 因孤立 token 报 invalid subcommand，但均在有效 namespace/dispatch 前 exit 2。冻结语义要求“不接受”，不要求人为统一 argparse 文案；增加预扫描反而会重建 removed-option 特例。 |
| workspace/package config owner | `pass` | `EntrypointRuntimeRequest` 与 `ServiceHostAdminRequest` 不再承载显式 overlay；Service 直接使用既有 `resolve_runtime_locations(workspace_root, package_config_root)`。workspace config 存在则使用 `<workspace>/config`，不存在则 package fallback。 |
| lower-level runtime contract | `pass` | `RuntimeLocations.config_overlay_dir` 与 lower-level `explicit_config_overlay_dir` 未修改，仍由 `dayu.runtime.location` 独立拥有；Host assembly diagnostics 的同名字段是该合法投影，不是 CLI compatibility residue。 |
| typed construction sites/tests | `pass` | 全部 typed constructors 已机械移除旧 keyword；`dataclasses.fields()` 直接断言 request schema 无旧字段，CLI/Service tests 同时断言 workspace forwarding、fallback 和零下游调用。 |
| scope/type/doc/coverage | `pass` | 生产/测试 diff 恰好为 plan §3.1 的 15 文件；额外只有 implementation/review/controller artifacts。focused pyright 0 errors；六个修改生产文件覆盖率为 85%–99%；README 按 accepted plan 延迟 S8。 |

## Review findings 与 residual risk disposition

- MiMo：无 finding。
- DeepSeek：无 finding。
- DeepSeek residual 1（session resume/purge、tool_trace 的 split-value action scope未逐个参数化）：`covered by current owner invariant`。parser tree action inventory、equal-sign全 scope、split root/command/action代表路径以及 zero-dispatch sentinel 已共同证明删除 contract；不为穷举诊断文案扩张测试。
- DeepSeek residual 2（全仓回归）：`covered by later approved slice S8`，不阻塞 S1 focused acceptance。
- DeepSeek residual 3（diagnostics `config_overlay_dir` 易混淆）：`accepted as documented non-risk`；直接类型与 location owner 已核验，不删除独立投影。
- 当前没有未分类 residual risk，也没有需要 fix/re-review 的 finding。

## Validation snapshot

- Focused pytest：`692 passed`。
- Focused pyright：`0 errors, 0 warnings, 0 informations`。
- 修改生产文件覆盖率：`99% / 93% / 85% / 86% / 88% / 86%`。
- `git diff --check`：通过。
- 两个 registry `json.tool`：通过。
- Registry SHA-256：
  - `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
  - `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- Index：为空。

## Accepted slice commit boundary

下一步仅允许按显式路径 stage：plan §3.1 的 15 个生产/测试文件，加 S1 implementation artifact、两份独立 code-review artifact 与本 controller adjudication，共 19 个文件。不得混入 README、design、registry、Host/Engine/runtime 或其它文件；commit 后进入 S2，不在本 gate push。
