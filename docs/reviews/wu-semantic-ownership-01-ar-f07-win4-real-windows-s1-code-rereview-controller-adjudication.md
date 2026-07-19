# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S1 Code Re-Review Controller Adjudication

## Result

`PASS / ACCEPTED_OPEN=0 / NEW_FINDING=0 / BACKFLOW_FINDING=0 / BLOCKER=0 / S1_EXACT_SCOPE_COMMIT_AUTHORIZED / REAL_WINDOWS_PENDING`

## Locked target

- Entry：`8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`。
- Immutable payload：`tests/cli/test_upload_filings_from_command.py`，SHA-256
  `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d`。
- AgentMiMo re-review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-rereview-mimo.md`，352 lines / SHA-256
  `8d16c371c26d669b5cb712f465d9a8f7fb3ce70fab663e2d00b8f14f4fb25c80`。
- AgentDS re-review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-rereview-ds.md`，643 lines / SHA-256
  `98d8b461739fe21e08613763a7a4dd2d858ae018ecd80962cf7263de2f738f00`。

两路均从零完整读取unchanged payload、direct public Fins contracts、initial review、Controller adjudication、AgentCodex
zero-change artifact与Controller validation，并返回PASS / new finding 0 / backflow finding 0 / blocker 0。Controller接受该共同结论。

## Final adjudication

1. `WIN4-RW-F01`的本地owner修复成立：真实Windows smoke先验证process exit，再通过Fins public company/source repository与
   bounded snapshot读取published facts；stdout/stderr display grammar不再充当upload success真源。
2. Snapshot只在public `with`生命周期内读取，`materialize_files=False`；identity、source kind、primary filename与descriptor
   membership全部fail closed。`source_path.name`提供跨平台basename同源值。
3. 执行顺序锁定为exit → public storage facts → physical integrity → oracle write。Company-name pre-execution oracle与六字段
   oracle schema均未漂移。
4. Controller先前五项no-action裁决全部由两路复审核实：旧artifact路径引用、upload顺序文字错误、15/16计数、POSIX
   out-of-scope观察、filelock实现推测均不是current code finding，不得回流扩域。
5. Initial accepted code finding为0，AgentCodex zero-change处理正确；本轮无新finding、无backflow、无open question或设计冲突。

## Security, deferred and residual risk

- Config与Host internal SQLite/EventLog仍属于trusted-local domain；本slice未新增secret处理。Tool Trace、audit及
  public/LLM-facing/operator diagnostics继续禁止API key/header明文。
- 未引入统一tool authorization或secret infrastructure，未实施Issue 142、151、175、177、178或Web/WeChat/render能力。
- 同文件POSIX display assertion是pre-existing / out of current accepted scope，不由本slice改动或创建替代WU。
- Full Ruff 142项为已锁定pre-existing baseline；当前slice未新增、扩散或掩盖。
- 真实Windows R11与R12 embedded-R11 same-run evidence仍pending。它是后续remote closure gate，不能由本地skip或review
  PASS替代，也不阻止S1 exact-scope local commit和S2继续实施。

## Next gate

授权Controller只提交S1 exact scope：immutable test payload、完整implementation/validation/review/fix/re-review evidence与本
adjudication、control状态。提交前必须核对sorted path manifest、cached diff-check与无额外product/test/README/workflow/design
路径；提交后必须验证parent/tree/path/payload/working/staged并用artifact-only control commit授权WIN4-RW-S2。不得提前进入
aggregate、push、remote dispatch或PR review。
