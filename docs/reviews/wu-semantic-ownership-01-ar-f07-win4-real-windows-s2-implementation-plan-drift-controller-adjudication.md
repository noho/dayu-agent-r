# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S2 Implementation Plan-Drift Controller Adjudication

## Result

`PLAN_DRIFT_ACCEPTED / WIN4-RW-S2-PD-F01 / PRODUCT_OWNER_CORRECT / TEST_PROPAGATION_ALLOWLIST_INCOMPLETE / PLAN_ONLY_FIX_REQUIRED`

## Direct evidence

- Implementation entry：`3474254b5c9da44aff74c6589d3ccddd785c5e72`。
- Stopped protected payload paths仍只有：`README.md`、`dayu/cli/commands/init.py`、`tests/README.md`、
  `tests/cli/test_init_command.py`；staged tree empty。
- Stopped four-path binary diff SHA-256：
  `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669`。
- Fresh focused evidence：owner nodes `14 passed`；`test_init_command.py` `41 passed`；`test_init_smoke.py`
  `28 passed, 5 skipped`；three-file aggregate `89 passed, 7 skipped`；`init.py` line coverage `91%`；POSIX
  redirected smoke通过且value disclosure为0。
- Fresh full CLI regression稳定失败：
  `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config`。
  该node mock `getpass.getpass`，但未把production实际读取的`dayu.cli.commands.init.sys.stdin`设为TTY；pytest capture stdin
  的`isatty()`为false，正确进入redirected owner path，`readline()`由pytest capture stream抛`OSError`，CLI返回1。

## Root cause and ownership

`_read_secret_input()`按`sys.stdin.isatty()`在TTY hidden getpass与redirected logical-line读取之间分流，是accepted product owner
contract；让production识别pytest、mock identity、capture stream或在redirected失败后fallback到getpass都会违反语义所有权、
capability-only判断与禁止compat/test shim约束。

正确修复属于直接测试消费者迁移：`test_prompt_command_uses_init_generated_workspace_config`必须提供test-owned、严格typed TTY
stdin fake，`isatty()`恒为true且`readline()`被调用立即assertion failure；既有getpass mock继续只负责hidden value序列。不得mock
`_read_secret_input()`，不得改变production、prompt业务断言或runtime assembly行为。

## Plan finding

接受`WIN4-RW-S2-PD-F01`：accepted plan §13.4明确要求“所有受影响既有 getpass tests”迁移到strict TTY fake，但§13.3 S2
allowlist遗漏了direct consumer `tests/cli/test_prompt_command.py`，同时§13.6.4/§13.6.6 scoped Ruff与source scan也未包含该新增
allowed test path。`pytest tests/cli -q`把这一传播缺口作为mandatory broader gate直接暴露。

这不是设计真源矛盾、产品finding或新WU；它是当前umbrella WU / WIN4-RW-S2同一owner contract的plan allowlist不完整。

## Required plan-only correction

AgentCodex只允许修改现有accepted WIN4 plan与新增plan-fix artifact：

1. 在§13.3把`tests/cli/test_prompt_command.py`加入WIN4-RW-S2 allowed paths，ownership purpose只限该exact node的strict TTY
   fixture迁移。
2. 在§13.4明确只修改该node的stdin fixture，不抽共享compat helper、不移动业务断言、不修改其它prompt tests。
3. 在§13.6 scoped Ruff、ownership/forbidden scans、allowlist/README验证中加入该文件；保留full CLI regression mandatory。
4. 在§13.5 TTY矩阵明确这个direct integration consumer也必须证明TTY path不调用`readline()`。
5. 不改变product contract、四个已停止payload内容、README决定、remote closure、安全裁决、deferred边界或其它slice。

## Protected state and next gate

Plan-only修正期间必须保持上述四个payload内容SHA与aggregate diff SHA不变，`tests/cli/test_prompt_command.py`继续零diff，staged tree
empty。修正后由Controller验证，再由AgentMiMo/AgentDS并发完整plan review；accepted finding全部关闭并形成exact docs-only accepted plan
commit后，才可恢复S2 implementation并修改该一个新增test path。
