# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 wheel smoke plan-drift fix — AgentCodex

## 1. Gate 结论

本轮是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R11-I2 的 wheel smoke validation plan-drift
plan-only fix，不是新 WU、implementation/test continuation、packaging fix 或 release gate。

Controller 接受的唯一 finding `R11-I2-VAL-PD-F02` 已在 accepted plan 的验证 owner boundary 修复：

- wheel build 保持 `python -m pip wheel --no-deps --no-build-isolation`；
- METADATA、entry points、extracted paths 与 RECORD 四个 archive negative oracles完整保留；
- fresh venv 不再用 `--no-deps` 安装 runtime wheel；
- exact-one 选出的 built wheel 只执行一次使用
  `constraints/lock-macos-arm64-py311.txt` 的 normal constrained install；
- 安装后按顺序运行 `pip check`、两个真实 help 与 placeholder package importability oracle；
- §2.4、§7.3、§8.1、§10 和 Slice stop wording 已同步，dependency resolution/install、lock、`pip check`、
  help 或 importability failure 均是必须停止的真实 packaging gate failure。

本轮只修改 accepted plan 并新增本 artifact。未修改 Windows workflow、stopped implementation/test/README/
packaging、shared test contract、Controller control/artifacts；未运行 test、wheel、install、help、coverage、pyright、Ruff
或 workflow；未 stage、commit、push、创建 PR 或进入 R12。

## 2. 第一性原理与 semantic owner

修复动机成立，HIGH 严重度准确。直接证据链是：

1. `pyproject.toml` 声明 `aiohttp>=3.9.0` 等 runtime dependencies；
2. stopped smoke 用 `pip install --no-deps <built-wheel>` 明确禁止安装这些声明依赖；
3. 随后的 `python -m dayu.cli --help` 在真实 import graph 导入 `aiohttp` 时失败，符合 `--no-deps` 的预期语义；
4. wheel build/extract/no-deps install已经成功，因此该失败不证明 CLI、README、test 或 packaging implementation 有缺陷；
5. 正确 owner 是 accepted plan 的 packaging smoke contract：archive oracle证明 wheel 内容边界，fresh constrained
   install/runtime oracle证明声明依赖可解析、安装且 wheel 可运行，两者不能合并为互斥前提。

因此最佳最小修复是只改 validation plan。lazy import、fallback、fixture/sys.path shim、重复 install、修改 lock、回改
Windows workflow 或扩大 I2 production/test 范围都会把 plan defect 下沉给错误 owner，本轮明确禁止。

## 3. Authority 与 exact scope

完整读取并遵守：

- `AGENTS.md`：128/128 lines；
- before-fix accepted plan：925/925 lines，79,384 bytes，SHA-256
  `20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd`；
- Controller adjudication
  `docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-controller-adjudication.md`：75/75 lines，
  4,472 bytes，SHA-256 `cde7f5dd0900e6bbd8a0ebe61c2160f5583d68fae609783960deb3e5c4794ef5`；
- `docs/host/issues-implementation-control.md` 的完整 `## 当前状态`，实时 gate 为
  `R11-I2 wheel isolated-install validation plan-drift fix`。

本 turn authored paths 精确为：

1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-fix-codex.md`

## 4. Exact before / after commands

### 4.1 Before-fix runtime sequence

```bash
python -m venv workspace/tmp/r11-wheel-venv
python -c "from pathlib import Path; import subprocess; wheels=tuple(Path('workspace/tmp/r11-dist').glob('dayu_agent-*.whl')); assert len(wheels) == 1, f'expected exactly one wheel, got: {wheels}'; subprocess.run(('workspace/tmp/r11-wheel-venv/bin/python', '-m', 'pip', 'install', '--no-deps', str(wheels[0])), check=True)"
workspace/tmp/r11-wheel-venv/bin/python -m dayu.cli --help
workspace/tmp/r11-wheel-venv/bin/python -m dayu.cli upload_filings_from --help
workspace/tmp/r11-wheel-venv/bin/python -c "import importlib.util; assert all(importlib.util.find_spec(name) is None for name in ('dayu.web', 'dayu.wechat', 'dayu.render'))"
```

该序列把“禁止安装声明依赖”与“运行完整 CLI import graph”组合为互斥 oracle；不得继续使用。

### 4.2 After-fix runtime sequence

```bash
python -m venv workspace/tmp/r11-wheel-venv
python -c "from pathlib import Path; import subprocess; wheels=tuple(Path('workspace/tmp/r11-dist').glob('dayu_agent-*.whl')); assert len(wheels) == 1, f'expected exactly one wheel, got: {wheels}'; subprocess.run(('workspace/tmp/r11-wheel-venv/bin/python', '-m', 'pip', 'install', '--constraint', 'constraints/lock-macos-arm64-py311.txt', str(wheels[0])), check=True)"
workspace/tmp/r11-wheel-venv/bin/python -m pip check
workspace/tmp/r11-wheel-venv/bin/python -m dayu.cli --help
workspace/tmp/r11-wheel-venv/bin/python -m dayu.cli upload_filings_from --help
workspace/tmp/r11-wheel-venv/bin/python -c "import importlib.util; assert all(importlib.util.find_spec(name) is None for name in ('dayu.web', 'dayu.wechat', 'dayu.render'))"
```

exact-one assertion 是 built wheel path 的唯一选择真源；fresh venv 对该 wheel 只做一次 normal constrained install。
`pip check` 与 runtime oracles只在该安装之后运行，不先装 `--no-deps`，不重复安装同版本 wheel。

### 4.3 Unchanged build/archive sequence

下列 plan contract保持不变：

- `python -m pip wheel --no-deps --no-build-isolation --wheel-dir workspace/tmp/r11-dist .`；
- exact-one wheel extract；
- METADATA 中无 `Provides-Extra: web` / Streamlit requirement；
- entry points 中无 `dayu-web` / `dayu-wechat` / `dayu-render`；
- extracted archive 与 RECORD 中无 `dayu/web`、`dayu/wechat`、`dayu/render`；
- 四个 negative oracle 的 exact stdout 与非零失败语义。

## 5. Plan wording closure

| Plan owner | 修复结果 |
|---|---|
| §2.4 baseline mapping | 明确 build/archive 与 fresh constrained runtime 两类证据分离 |
| §7.3 command | 删除 fresh venv runtime install 的 `--no-deps`；增加 exact wheel + macOS arm64/Python 3.11 lock 的一次 normal install及 `pip check` |
| §7.3 oracle text | 固定声明依赖安装、`pip check`、两个 help、importability顺序，禁止先 no-deps / 重复 install |
| §7.3 Slice stop | dependency resolution/install、lock、pip check、help/importability任一失败均为真实 packaging gate failure |
| §8.1 final cumulative validation | 同步两类 oracle、一次 install、failure/stop semantics，并明确 Windows workflow command不变 |
| §10 checklist | 增加完整 build/archive/constrained install/pip check/help/importability acceptance oracle |

未改 §7.2 Windows workflow、`22/8/15` counts、shared test node contract、review/commit sequence、deferred owner、
security boundary 或 R12 boundary。

## 6. Protected stopped-tree locks

stopped tracked product diff 的 exact proof command保持：

```bash
git diff --binary HEAD -- README.md dayu tests pyproject.toml requirements.txt .github | shasum -a 256
```

| Lock | Before plan fix | After plan fix | 结果 |
|---|---|---|---|
| HEAD | `de476c452411e9d325d43b608de22b7236edfedb` | same | unchanged |
| accepted plan | `20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd` | `f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd` | authorized plan-only delta |
| plan size | 925 lines / 79,384 bytes | 942 lines / 81,592 bytes | authorized |
| stopped product/test/README/packaging diff | `6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6` | same | unchanged |
| shared `tests/cli/test_arg_parsing.py` | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` | same | unchanged |
| `tests/README.md` | `478efffcbf5d3e4f172ec5a7373e49996cf62f3b85a485fdcd60af7623f1c4c1` | same | unchanged |
| untracked renderer | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` | same | unchanged |
| untracked Windows workflow | `4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953` | same | unchanged |
| Controller adjudication | `cde7f5dd0900e6bbd8a0ebe61c2160f5583d68fae609783960deb3e5c4794ef5` | same | read-only |
| staged set | empty | empty | unchanged |

Controller control 只读 current-state hash 为
`b1de37a62bba4ce6624e6611cf31184385bebd396bec57c155775c389b2c67d3`；它不属于稳定 stopped product diff lock，
本 turn 未修改或 stage。

## 7. Validation、docs decision 与 no-continuation proof

- accepted 925-line plan 完整读取：PASS。
- Controller adjudication完整读取：PASS。
- 总控完整 `## 当前状态` 读取：PASS。
- `git diff --check -- docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`：PASS。
- plan after-fix：942 lines / 81,592 bytes / SHA-256 `f1c95c3b...b2ffd`。
- stopped tracked product diff、shared test、tests README、renderer、workflow、adjudication hashes：全部 MATCH。
- `git diff --cached --name-only`：空。
- tests / wheel build / install / `pip check` / help / importability / coverage / pyright / Ruff / Windows workflow：未运行。
- README decision：不更新。当前只修 accepted plan 与新增 review artifact，不改变 stopped 用户可见实现或 README truth。
- stage / commit / push / PR / R12：均未执行，仍未授权。

## 8. Finding、residual risk 与 next entry point

| ID | Gate status | 当前状态 |
|---|---|---|
| `R11-I2-VAL-PD-F02` | plan fix | `FIXED_IN_PLAN / PENDING_DUAL_COMPLETE_WHEEL_SMOKE_PLAN_REVIEW` |

- blocking open question：`0`。
- unclassified residual risk：`0`。
- Windows real-run release blocker：保持既有状态，本轮未关闭、修改或降级。
- stopped implementation validation evidence：保持历史事实，本轮未重跑、未冒充 green。
- next entry point：Controller validation与双路 complete wheel smoke plan review；在新 plan acceptance和 exact
  continuation authorization 前，R11-I2 implementation/test/README/packaging/workflow保持 stopped。

READY_FOR_DUAL_COMPLETE_WHEEL_SMOKE_PLAN_REVIEW
