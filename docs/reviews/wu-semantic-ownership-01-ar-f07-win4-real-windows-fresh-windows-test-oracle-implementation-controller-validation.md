# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 One-test Implementation — Controller Validation

## Gate identity and verdict

- Timestamp：`2026-07-20T09:46:59+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本 gate 是最后一个内部 remediation sub-WU `AR-F07 WIN4-RW-RF01`，不是新 WU。
- Accepted corrected-plan commit：`e2c9a31b25fb6d87e6fb4d618bb4043f556a55b0`。
- Mechanical implementation base：`39926eb85aa25441f5209a128a3c971f451b5b25`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-implementation-codex.md`，`150` lines / SHA-256 `f9b36d4b58d4a81c845058790f6d99d8b7994b8a35410a79242aed606163f42e`。
- Verdict：`PASS / EXACT_ONE_TEST_BLOCK / PRODUCT_DIFF_ZERO / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / REMOTE_WINDOWS_PENDING`。

## Exact diff and owner validation

Controller逐行复核相对 mechanical base 的 tracked diff：只包含
`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 现有
snapshot assertion block，code diff SHA-256为
`fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。

实现删除 `snapshot.primary_filename == source_path.name`，并形成两个独立 fail-closed facts：

1. `snapshot.primary_filename` exact-name在 public descriptors中恰好命中一个；
2. `source_path.name` exact-name独立地恰好命中一个；
3. 唯一 raw-source descriptor的 public `sha256` 显式非空且等于同一 `fixture` bytes的 SHA-256。

primary与raw-source既未强制相等也未强制不同；没有硬编码 Docling filename/expected primary。新增断言只消费 public
descriptor `name/sha256`，没有读取 private meta/raw path或物化文件。原有 `rglob` 与 oracle JSON block零 diff，继续只承担
physical artifact integrity。

## Controller fresh validation

| Check | Result |
| --- | --- |
| Target test file | `20 passed, 2 skipped, 3 warnings` |
| Public repository owner nodes | `3 passed, 3 warnings` |
| Full CLI | `552 passed, 7 skipped, 3 warnings` |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff | `All checks passed!` |
| Code diff SHA | exact match `fcecb15c...f2169` |
| `git diff --check` | PASS / no output |
| Staged tree | empty |

AgentCodex另已 fresh通过 POSIX real smoke `1 passed`、plan aggregate `262 passed, 2 skipped`，并记录目标 Windows node在
macOS因 `requires real cmd.exe` 为 platform skip。Controller未把 skip误报为 closure；fresh R11/R12仍是后续唯一真实 Windows
destination。warning均来自未改动的 installed `edgar` deprecated imports。

## Boundary scans and README decision

- 相对 base 的 code path只有 target test；另只新增 AgentCodex implementation artifact。
- product、其它 tests、README、design、workflow与control零 implementation delta。
- 新增 `rglob`、private meta/get_source/materialize、Docling hardcode、primary/raw equality、import/helper/class/oracle field、
  display/stream oracle、fallback/`hasattr`/`getattr`扫描均为零。
- 本次只纠正既有 test node内部 public-contract assertion，不改变测试层级、运行方式或维护规则；按 `tests/README.md`
  更新边界判定 `NO UPDATE REQUIRED`。
- API key/header trusted-local与 Tool Trace/audit不泄露明文的既有安全裁决不变；没有统一 tool authorization framework，
  没有越界实施 Issue 142/151/175/177/178或 Web/WeChat/render trackers。

## Authorized next gate

只授权 AgentMiMo与AgentDS并发执行完整 immutable code review。review必须锁定 base、code diff SHA、artifact SHA和exact function
block，检查 duplicate descriptor、optional hash、primary/raw合法不相等反例、Fins owner不被test重定义、allowlist/security/deferred
边界与remote pending。不得 stage/commit/push/dispatch或进入 aggregate/PR/final closeout。
