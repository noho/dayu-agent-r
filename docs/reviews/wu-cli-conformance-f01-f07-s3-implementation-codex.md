# WU-CLI-CONFORMANCE-F01-F07 S3/F03 Implementation Gate（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S3 / F03`
- Gate：`implementation`
- Entry HEAD：`16c6ddc8`
- 分支：`codex/interactive-oracle`
- 执行日期：2026-08-02（Asia/Shanghai）
- 状态：`BLOCKED — public Vt100Parser seam 与 accepted plan 不符`
- Artifact path：`docs/reviews/wu-cli-conformance-f01-f07-s3-implementation-codex.md`

## Scope 与 owner 边界

本次只核验 accepted plan §5 指定的 prompt key parser seam、Host acceptance/cancel/terminal public API，以及 S3 allowlist。没有重新裁决 frozen oracle，也没有修改 Host、Service、Engine、registry 或 evidence。

语义 owner 仍按 accepted plan 冻结：CLI input owner 负责把完整终端序列分类为 typed intent；Host 仍是 Run lifecycle、cancel 与 canonical terminal 的唯一 owner。CLI 不得伪造 `CANCELLED`。

## Blocking direct evidence

当前环境为 Python 3.11、`prompt_toolkit==3.0.52`。public import、构造和方法签名本身存在：

```text
prompt_toolkit.input.vt100_parser.Vt100Parser(callback)
Vt100Parser.feed(data: str)
Vt100Parser.flush()
```

但 Alt 序列的 callback 行为与 accepted plan §5.2(4)–(5) 的前提不一致。复验命令：

```bash
source .venv/bin/activate
python - <<'PY'
from prompt_toolkit.input.vt100_parser import Vt100Parser

for name, sequence in {
    "standalone-escape": "\x1b",
    "alt-x": "\x1bx",
}.items():
    observed = []
    parser = Vt100Parser(observed.append)
    parser.feed(sequence)
    parser.flush()
    print(name, [(repr(item.key), repr(item.data)) for item in observed])
PY
```

实际输出：

```text
standalone-escape [("<Keys.Escape: 'escape'>", "'\\x1b'")]
alt-x [("<Keys.Escape: 'escape'>", "'\\x1b'"), ("'x'", "'x'")]
```

`feed("\x1bx")` 即使一次收到完整 Alt+X bytes，也先回调与 standalone Escape 完全相同的 `KeyPress(Keys.Escape, "\x1b")`，随后才回调普通 `x`。跨 chunk feed 得到相同分类结果。因此，如果严格执行计划中“callback 看到 `key is Keys.Escape` 且 `data == "\x1b"` 就投递 `CANCEL_RUN`”，Alt+字符必然先触发取消，违反 frozen F03 oracle 的“Alt 完整序列不得误取消”。named ambiguity deadline 只能决定何时 `flush()`，不能改变 Alt 序列的上述 callback 形状。

Host 侧 seam 与计划一致：`on_run_accepted` 在 public acceptance barrier 完成后同步发布 exact accepted Run id；`cancel_entrypoint_run_and_wait` 通过 public Run precheck、graceful cancel 和 terminal waiter 返回 Host canonical terminal。Host API 不是 blocker。

## Decision 与变更

- 按用户指定 stop condition，在确认 parser 行为差异后停止 implementation。
- 没有引入第二套 byte parser、private prompt_toolkit API、`KeyProcessor`、callback 后置缓冲或其它未获批准的替代 seam。
- 已撤回核验期间产生的未完成生产代码改动；生产文件和测试文件保持 entry HEAD 内容。
- 本 gate 唯一变更是本 BLOCKED implementation artifact。

## Validation

- Preflight：分支 `codex/interactive-oracle`；entry HEAD `16c6ddc8`；进入实现前工作树与 index 均为空。
- Public seam：已核验 `Vt100Parser` 构造、`feed`、`flush` 签名及 standalone Escape / Alt+X callback 事实。
- Host API：已只读核验 acceptance callback 与 canonical cancel/terminal public call path。
- Implementation tests / coverage / full pyright：未进入；parser blocking open question 会改变实现策略与测试预期，按 Gateflow stop condition 禁止继续。
- Stage / commit / push / PR：均未执行。

## Docs decision

没有生产代码变更，因此不触发根 README、`dayu/README.md` 或分层 README 更新。本 artifact 是 implementation gate 的 durable blocking record。

## Residual risks 与 uncovered areas

- `requiring new issue or explicit user decision`：需要明确批准新的 public sequence-classification seam，才能同时满足 standalone Escape cancel 与 Alt 完整序列不取消。
- `covered by later approved slice`：真实 PTY 分块、terminal restoration、provider wait/tool execution/closeout double Ctrl+C 和完整 S3 coverage/pyright 尚未执行；只有 blocking seam 解除并完成 S3 implementation 后才能覆盖。
- 当前没有已接受但未修复的代码 finding；implementation 尚未形成可 review 的代码 diff。

## Blocking open question 与 next entry point

accepted plan 是否允许修订 §5.2 的 callback 处理：例如仍保留 reader thread 内唯一 public `Vt100Parser` 与 incremental decoder，但把 parser callback 产生的 Escape 暂存到当前 `feed`/`flush` 边界，只有确认没有同一 Alt continuation 后才投递 standalone Escape；或者由 plan 明确指定另一个 public prompt_toolkit seam？

在该问题被裁决并形成新的 accepted plan 前，next entry point 保持 `S3/F03 implementation blocked`，不能进入 code review、fix、commit 或后续 slice。
