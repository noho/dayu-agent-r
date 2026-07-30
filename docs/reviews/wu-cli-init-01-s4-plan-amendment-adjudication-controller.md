# WU-CLI-INIT-01 S4 Plan Amendment Adjudication

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- Slice：`S4 — Managed whole-tree modes 与 repair`
- Gate：plan gap amendment / review / fix / rereview
- Controller：AgentController
- Base：`06ea49e0`
- 日期：2026-07-30

## Motivation verdict

Plan gap 成立。S2 把
`execution_profiles.json` 的静态 no-follow stat 到 ConfigLoader pathname read
之间的 TOCTOU 交给 S4，但原 S4 白名单没有真实 read owner
`dayu/cli/commands/init.py`、parse owner `dayu/runtime/config_loader.py` 及其测试。

只改 transaction/staging 下游无法撤销首个 model prompt 前已经发生的外部路径读取，
也不能阻止基于错误 profile minimum 的交互。因此本 gate 返回 planning 并扩展 S4
allowed files，符合 Gateflow 的 owner/scope stop discipline。

## Accepted owner split

- `dayu.cli.commands.init`：locked root identity、mode、逐层 fd-relative/no-follow
  open、descriptor snapshot read。
- `dayu.runtime.config_loader`：typed filename manifest、JSON decode、layering、
  schema 与 typed projection。
- `dayu.cli.init_workspace`：managed-root snapshot drift、staging、publication、
  rollback。

ConfigLoader 只接收 `bytes | None`，不接收 init mode、workspace identity 或路径
治理；CLI 不复制 JSON parser/schema。

## Review adjudication

### Accepted

- MiMo R002：原 amendment 未把 deterministic race test 的具体注入机制写到
  code-generation-ready。现已固定 pytest monkeypatch、original syscall delegate、
  `threading.Event` / `threading.Barrier`、bounded waits，并逐项指定
  `os.open` / `os.read` / `os.fstat` / ConfigLoader boundary。
- DS-002/003/004：明确 init-owned chunk 常量、逆序 close 与 primary-error
  precedence、`typing.NamedTuple` 的 tuple 兼容语义。
- DS OQ-001/002：只有 config/final fd-relative open 的 `FileNotFoundError`
  映射 absent；root fd 只比较 device/inode/mode。
- DS-001 采用保守选项：`st_nlink` / `st_ctime_ns` 漂移也要求 rerun，并记录
  metadata-only 误报 tradeoff。

### Rejected

MiMo R001 声称 Darwin 上含 `O_NONBLOCK` 的 ordinary file 在 EOF 返回
`EAGAIN`。Controller 与 MiMo rereview 均在当前 Darwin/Python 3.11 真实执行：

```text
non-empty ordinary file -> b'profile-bytes'
empty ordinary file     -> b''
read after EOF           -> b''
```

该前提被直接证据否定。S4 保留 `O_NONBLOCK`，以免 FIFO 占位让 open 阻塞；
若 regular-file `fstat` 后仍出现 `BlockingIOError`，按 `OSError` fail closed，
不 retry、不伪装 EOF。

## Review results

- MiMo initial：`pass-with-risks`，两个 findings 均已裁决。
- DS initial：`PASS`，四个低严重度规格项均已处理。
- MiMo rereview：`PASS`，R001/R002 已关闭，无新 material finding。
- DS rereview：`PASS`，全部 findings/open questions 已关闭，无新 owner/scope。

## Accepted S4 file scope

原范围：

- `dayu/cli/init_workspace.py`
- `tests/cli/test_init_workspace.py`
- `tests/cli/test_init_smoke.py`

新增必要 owner 范围：

- `dayu/cli/commands/init.py`
- `tests/cli/test_init_command.py`
- `dayu/runtime/config_loader.py`
- `tests/runtime/test_config_loader.py`

## Final verdict

`PASS`

`docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md` 与原 accepted plan 共同
构成 S4 的 code-generation contract。实现若命中 amendment 第 8 节 stop
conditions，必须停止并返回 planning，不得用 path fallback、临时文件、兼容 shim
或下游补偿继续。
