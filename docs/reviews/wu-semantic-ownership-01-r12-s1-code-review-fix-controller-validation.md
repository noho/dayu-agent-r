# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Code Review Fix Controller 验证

## 1. Verdict

`PASS / R12-S1-CR-F01 FIX VALIDATED / READY_FOR_DUAL_COMPLETE_S1_REREVIEW`

这是现有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S1 fix validation，不是新
WU，不授权 S2、S3、stage、commit、aggregate、push 或 PR。

## 2. Authority 与锁

- HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Controller adjudication：97 lines / SHA-256
  `b3a9aca59a9f03bd1cf143bc6f4e5f30e35560d09054d1240f72d5dd5f441c19`。
- AgentCodex fix artifact：304 lines / 14,281 bytes / SHA-256
  `b9702a729a080b53d4585527f722b905777102bcf9f1288f2e0dbd49bd48fb44`。
- Accepted finding：HIGH `R12-S1-CR-F01`。

Controller 完整逐行读取：

- `dayu/cli/init_environment.py`：584 lines / 22,342 bytes / SHA-256
  `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f`；
- `tests/cli/test_init_environment.py`：672 lines / 24,469 bytes / SHA-256
  `ae243050136d92e0c772caf3a51b3bdd999ff8efe3af096d73161f32473fd947`；
- AgentCodex fix artifact 全文。

只读 S1 catalog locks 保持：

- `dayu/cli/init_catalog.py`：854 lines / SHA-256
  `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754`；
- `tests/cli/test_init_catalog.py`：610 lines / SHA-256
  `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4`。

## 3. Owner-level code validation

修复留在 `_parse_managed_block()` owner：

1. 独立、精确的 begin/end 行仍是唯一结构 marker 真源。
2. parser 只允许 marker 位于形如 `export <non-empty-left>=<value>` 的等号右侧；marker
   若出现在赋值左侧、普通文本或注释中仍拒绝。
3. block 内每个 export 仍继续进入同一个 `_parse_export_name()`，由固定 environment
   allowlist 拒绝非法 name；新分支没有成为 name-validation bypass。
4. 缺配对、逆序、多块和重复 name 的既有结构判断未改变。
5. entry value 拒绝集合仍只有 empty、NUL、CR、LF；没有 marker 黑名单、regex/parser
   framework、compat/fallback、downstream compensation 或 rollback 新协议。
6. environment 注入仍只发生在 whole-batch `result.succeeded` 后；Windows argv/flag、
   captured-output 与 partial-result 语义未改变。

## 4. Controller 独立行为复现

Controller 使用 production entry/plan/writer 和真实临时 profile 执行：

- begin、end、两者 marker value × absent/existing profile：`6/6` success；
- 每次磁盘独立 begin/end 行各一个，profile 含同一 secret，当前进程在写后校验成功后含
  同一值；命令只输出汇总，不输出 secret；
- 普通文本嵌入、注释嵌入、非法 allowlist export name 且 value 含 marker：`3/3`
  rejection，profile bytes 不变且进程未注入。

原始汇总：

```text
real_smoke_successes=6 malformed_rejections=3 secret_output=none
```

这直接关闭原先“profile 已 replace、调用报失败”的 accepted reproduction；没有用 fake
隐藏磁盘状态。

## 5. Controller 独立机械验证

在 `source .venv/bin/activate` 后：

- four-file focused：`66 passed`；
- environment owner coverage：`233 statements / 13 miss / 94.42%`；
- catalog owner coverage：`276 / 27 / 90.22%`，与只读基线一致；
- full pyright：`0 errors, 0 warnings, 0 informations`；
- four-file scoped Ruff：`All checks passed!`；
- full Ruff immutable result：raw exit `1`、count `144`、SHA-256
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`、
  baseline `cmp=0`；
- `git diff --check`：clean；staged name list：empty；
- weak typing、`content.count(marker)`、regex/parser framework、compat/fallback/shim/
  rollback、unsafe shell/text、logging/print、network/runtime assembly 与 tool authorization
  扫描无新增违规。

README 不在 S1 writable scope；本 fix 纠正内部 parser 对既有合法 value contract 的误判，
未改变 public CLI grammar/workflow，S3 的 README gate 不提前。

## 6. Finding 与 gate 状态

- `R12-S1-CR-F01`：`FIXED / CONTROLLER_VALIDATED / WAITING_DUAL_REREVIEW`。
- accepted/open before re-review：`0`。
- unclassified residual：`0`。
- design contradiction：`0`。
- local blocker：`0`。
- Windows `setx` 不可回滚与真实 runner：保持已分类 residual / umbrella release
  blocker；本修复没有冒充 Windows success。

下一 gate 仅为 AgentMiMo / AgentDS 对完整累计 S1 tree 的并发 re-review。两路必须完整
复核 `R12-S1-CR-F01` 关闭、malformed fail-closed、secret/state/security、catalog 不漂移及
所有 S1 contract；任何新 accepted finding 都返回 AgentCodex 修复。S2/S3 和 commit 仍未授权。
