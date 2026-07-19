# WU-SEMANTIC-OWNERSHIP-01 AR-F07 Windows fix Controller validation

## 结论

`PASS_LOCAL_FIX / READY_FOR_DUAL_IMMUTABLE_CODE_REVIEW / WINDOWS_RERUN_REQUIRED`

本记录验收 draft PR 179 首轮真实 Windows failure 的根因修复，不把 macOS skip 记作 Windows pass，也不关闭 AR-F07。

## 首轮远端证据与裁决

- R12 run `29690620412`、job `88202555076`、head `07db7af3855b7fc80a24d74a3214bef215752d8d`：真实 `windows-latest` / Python 3.11 locked environment，artifact 上传成功，job failure。
- R11 run `29690620419`、job `88202555102`、同一 head：真实 `windows-latest` / Python 3.11 locked environment，artifact 上传成功，job failure。
- `AR-F07-WIN-F01` accepted：CLI key monitor owner 在 Windows import 时无条件加载 `termios/tty`，阻断 init、upload 与 test collection。
- `AR-F07-WIN-F02` accepted：R11 workflow 错把 `cmd.exe /?` 的实际 exit 1 当作 execution capability failure。
- `AR-F07-WIN-F03` accepted：registry finally 仅以 `reg delete` return code 判断 cleanup，missing value 会产生二次错误并遮蔽原 failure。
- `AR-F07-WIN-F04` accepted：R12 JUnit 证明 fault injection 尚未安装时，Windows 已在 `os.fsync(O_RDONLY fd)` 报 `EBADF`；根因属于 transaction durability owner，不是 monkeypatch 误伤。

其余三个 init failure 和 R12 R11 collection error 均为 F01 传播，不拆成重复 finding。

## AgentCodex 修复验收

Agent artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-windows-fix-codex.md`，SHA-256 `0d1a8793d89072c1bb55687895cea3d42cb4becded04f4afbeba6a4af3ae43bf`。

- F01：平台 capability/factory 成为唯一 owner；非 POSIX 固定 no-op，POSIX Ctrl+T/Esc 与 terminal restore 保持。
- F02：真实 execution gate 改为 `cmd.exe /d /c ver` exit 0；help 输出与 0/1 exit 只作显式诊断分类，未知退出仍失败。
- F03：cleanup 以 exact value absent 加父 key 可访问共同证明；实际删除与原本 absent 均幂等，错误只投影变量名。
- F04：Windows staged regular file 用 `O_RDWR` 获得可 flush descriptor；POSIX 保持 `O_RDONLY | O_NOFOLLOW`，publication/swap/rollback、containment、symlink/reparse 与 cleanup state machine 未改。

README trigger 只命中并更新 `tests/README.md`；根 README、config/Fins/dayu README 的用户或架构 contract 未改变。

## Immutable implementation snapshot

- base HEAD：`07db7af3855b7fc80a24d74a3214bef215752d8d`
- tracked binary diff SHA-256：`18876f5b596a430588bdafa390d1e0cbbd19534864718fdfca9a271585dc00e5`
- sorted tracked path-list SHA-256：`b9f39d742e80f57b427d0632e12b8e24bf731d2a502b0247a74cec4706fb2001`
- tracked changed paths：8；implementation artifact：1；staged paths：0。

Exact content hashes：

| Path | SHA-256 |
|---|---|
| `.github/workflows/r11-upload-script-windows.yml` | `0897e4152c8a878bf2203b176072558cf7d6537f855762170f0804a10c6388b2` |
| `.github/workflows/r12-init-windows.yml` | `3a14172f84a338d40f12c4cd2e056dbe6dde255168e8366ac60b6a017f438da6` |
| `dayu/cli/init_workspace.py` | `355b7af3c84151de7926fdc93f9d833a814648b46036e82cdfb58336a9c88d26` |
| `dayu/cli/run_keys.py` | `e0f9f97c17dca9dc5f4b24329b96fdd8216cea193dd020e8382582d10bf53627` |
| `tests/README.md` | `0bd909af6ee2dcf6e99a281a9fa3ebc2c398805e84289580b972ceef409fe382` |
| `tests/cli/test_init_smoke.py` | `b5a82e8b2385d909070a3429a58fe4e67bcbead1b6c737ca841e8aafc4c06ec4` |
| `tests/cli/test_init_workspace.py` | `fefdc334dd7a07b1720cb6545b1473fe3b7482270974c8975d6e8647c74cb630` |
| `tests/cli/test_run_keys.py` | `2f4c746aa8c2fb34b59bec9994dc750b51cace64b61a2f90b9d6896ee9c020e9` |

## Controller 独立验证

Controller 在同一 unstaged snapshot 运行：

```text
pytest test_run_keys + init_smoke + init_workspace + upload_filings_from + arg_parsing
= 190 passed, 7 skipped, 3 existing edgar deprecation warnings
python -m pyright dayu/ tests/ utils/
= 0 errors, 0 warnings, 0 informations
scoped Ruff
= All checks passed
git diff --check
= pass
```

7 个 skip 均为当前 macOS 不可执行的 Windows-only nodes，未被计作 Windows pass。AgentCodex 另报告 full CLI `513 passed, 7 skipped`、`run_keys.py` 88.73% 与 `init_workspace.py` 87.27% 单文件覆盖率，均达到门槛。

## Gate

四项 accepted failure 已在唯一 owner 形成可 review 的本地修复；Gemini/test-account、deferred issues、统一 authorization no-code decision 与既有安全行为均未改变。当前进入 MiMo/DS 并发 immutable code review。只有 review/fix/re-review、accepted commit、push 后的两条真实 Windows rerun 与 artifacts 全部通过，AR-F07 才能关闭。
