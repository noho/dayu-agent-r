# WU-SEMANTIC-OWNERSHIP-01 / R11 plan entry Controller validation

## 1. Gate 与动机判断

- 当前是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU R11，
  不是新 WU、issue 或 feature。
- 用户已经确认整个 overdesign remediation continuation 的 goal；R10 completion commit
  `2b14b2fbc89654267e3d33daa2ae410ceff45e68` 成功后，依赖顺序允许进入 R11 独立 plan gate。
- 当前只授权 AgentCodex 产生 R11 code-generation-ready plan；不授权 implementation、R12、
  stage、commit、push 或 PR。

动机由 owner-side 直接证据确认成立：

1. `dayu/fins/upload_batch.py` 仍只有粗粒度 suffix/token 分类和 generic entries，没有已裁决的
   财期、material routing、同期优先级、dedup、caps 与 typed skip facts。
2. `dayu/cli/commands/fins.py` 仍把 batch plan 输出为公共 `schema_version=1` JSON argv，
   而不是用户可执行的 POSIX shell / Windows cmd script。
3. current direct upload runtime 已拥有 `auto`，但 CLI grammar 仍默认 `create`，batch 也缺
   `auto` 与 `--infer`。
4. `pyproject.toml`、`requirements.txt`、根 README、`dayu/README.md` 与 placeholder packages
   仍发布或承诺未实现的 Web/WeChat/render surface。
5. 当前 branch、default branch 与 GitHub Actions API 均无 workflow/run，因而真实 Windows
   `cmd.exe` evidence 没有既有 owner，必须在 R11 closed allowlist 内建立一个最小 release gate。

## 2. Owner 与 plan 硬边界

- Fins batch owner 唯一产生 scan/classification/priority/dedup/caps/recognized/material/skipped
  facts；CLI 不从 filename/raw fields 重算业务事实。
- CLI 只拥有 current grammar、single FMP resolve、typed-entry-to-argv projection、平台 renderer、
  safe publish 与 human summary。
- packaging 只删除 placeholder public surface；不实现真实 Web、WeChat 或 render capability，
  不创建重复 issue。
- Windows quoting 不能由 `subprocess.list2cmdline`、兼容 fallback 或 unit-only proof 代替；真实
  `cmd.exe` recorder 与真实 CLI/temp-storage smoke 是 release blocker。
- Issue 142、151、175、177、178、R12、Topic 8/9、统一 authorization framework 与所有 deferred
  tracker capability 均不授权。

## 3. Source locks

- branch：`phaseflow/host-issues-control`。
- HEAD：`2b14b2fbc89654267e3d33daa2ae410ceff45e68`。
- staged tree：empty。
- Controller-owned `docs/host/issues-implementation-control.md` 是唯一既有 tracked dirty 文件；
  Agent 不得修改、覆盖、stage 或提交。
- authority：`AGENTS.md`、Controller control、umbrella optimization control、Controller discussion
  Topic 7、Host/Engine/Tool/Fins/UI design、umbrella remediation plan R11、CURRENT code/tests/README，
  最后才是两个 OLD 文件的用户行为证据。

## 4. Authorized output

本 gate 只授权新增：

`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`

Plan 必须最多三个 dependency-ordered slices，给出 cumulative closed allowlist、typed owner contracts、
POSIX/Windows real smoke、wheel/public-surface closure、README/security/deferred scans、coverage/pyright/
Ruff/diffcheck 与 stop conditions。完成后必须停在 Controller plan validation，再进入 AgentMiMo /
AgentDS 并发完整 plan review。
