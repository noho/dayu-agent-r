# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1 Implementation

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Slice: `S1 Storage Identity, Commit Point, And Local Durability`
- Gate: `implementation`
- Implementer: `AgentCodex`
- Accepted plan commit: `7b24b070`
- Status: `pass`
- Artifact path: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-implementation-codex.md`
- Commit authorization: none；本轮未创建commit。

## Scope

本轮只实现accepted plan的S1 storage owner闭环：single-component/object-key identity、Source/Processed handle existence、filesystem batch commit/recovery、journal/rename durability和`LocalFileStore.put_object()`原子落盘。

未进入S2/S3；未修改upload/download workflow、CN/HK temp contract、Host/Service wait adapter、Engine、design/control docs或README。

## Changed Files

- `dayu/fins/storage/_fs_storage_utils.py`
  - 新增唯一single-component validator及filename/object-key wrapper。
  - ticker canonical/fallback、document id、entry name、filename复用同一组件真源。
  - local URI复用canonical object key并在resolve后校验`portfolio_root` containment。
  - `_write_json()`在既有same-directory unique temp、file fsync、atomic replace、parent-directory sync基础上补齐失败temp cleanup。
- `dayu/fins/storage/_fs_storage_infra.py`
  - 以`os.replace()` owner helper替换batch commit/recovery中的`shutil.move()`，每次关键rename刷新source/target parent。
  - `BACKED_UP_TARGET`在旧target不存在时也写入；`COMMITTED`是唯一commit point，backup cleanup移到其后。
  - pre-commit failure把new target移回staging并恢复backup；`SWAPPED_TARGET` orphan recovery明确撤回new target、恢复backup。
  - commit+rollback双失败保留原commit exception为primary、rollback exception为`__cause__`，给primary添加recovery-evidence note，并保留journal/backup/staging证据。
  - post-commit cleanup failure只记录diagnostic并保留orphan evidence，不把已提交状态报告为失败。
- `dayu/fins/storage/_fs_blob_core.py`
  - filename在key construction前只规范化一次。
  - Source/Processed handle统一读取meta确认存在，之后才构造key或调用FileStore。
- `dayu/fins/storage/local_file_store.py`
  - 所有public key入口复用canonical object-key owner和resolve containment。
  - `put_object()`使用same-directory UUID temp、flush/file fsync、`os.replace()`、parent-directory sync及finally temp cleanup。
- `dayu/fins/storage/repository_protocols.py`
  - 只补齐既有begin/commit/rollback方法的token ownership、commit point、异常与caller rollback docstring；未改变协议方法集合。
- `tests/fins/test_fins_storage_atomicity.py`
  - 新增71个owner-level测试用例。

`tests/fins/test_fins_storage_provider.py`未修改；既有47个测试直接作为S1 regression matrix继续通过。

## State And Error Contract

```text
STARTED
  -> BACKED_UP_TARGET
  -> SWAPPED_TARGET
  -> COMMITTED
  -> best-effort cleanup
```

- `COMMITTED`写入沿用`_write_json()`的atomic JSON + file fsync + parent-directory sync。
- `COMMITTED`前异常：new target从正式位置撤回到staging，存在backup时原子恢复为target，写`ROLLED_BACK`并清理成功rollback evidence。
- `COMMITTED`后：target是提交事实；backup/journal cleanup异常不改变成功返回。
- rollback本身失败：caller捕获原commit error；`commit_error.__cause__`是rollback error；note明确evidence retained；token仍由storage消费。
- orphan recovery：`STARTED/BACKED_UP_TARGET/SWAPPED_TARGET`恢复pre-state；只有`COMMITTED`保留new target并清理backup。

## Tests And Validation

### Required focused matrix

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q
```

结果：`118 passed, 3 warnings`。warnings均来自既有`edgar` deprecated modules，不属于S1 owner路径。

覆盖内容包括：

- ticker/document/entry/filename非法component矩阵及合法dot/hyphen输入；
- absolute/leading slash、backslash、empty/`.`/`..` object-key segment和local URI/symlink containment；
- Source/Processed missing handle时FileStore call count为0；
- 旧target存在/不存在下的backup rename、BACKED journal、staging rename、SWAPPED journal、COMMITTED journal phase failures；
- STARTED/BACKED/SWAPPED/COMMITTED真实orphan目录恢复；
- crash-between-swap-and-COMMITTED语义反转；
- commit+rollback双错误对象身份、note、`__cause__`及evidence；
- post-COMMITTED cleanup failure成功返回和后续orphan cleanup；
- critical directory rename parent sync及COMMITTED journal parent sync；
- LocalFileStore unique temp、file fsync -> replace -> directory sync顺序、失败保留旧object、temp cleanup、stat/list/delete/missing和symlink containment。

### Broader Fins regression

```bash
source .venv/bin/activate
pytest tests/fins -q
```

结果：`491 passed, 1 skipped, 3 warnings`。skip及warnings均为既有环境/依赖行为。

### Per-file coverage

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q \
  --cov=dayu/fins/storage --cov-report=term-missing
```

结果：`118 passed`；修改生产文件覆盖率：

| File | Coverage |
| --- | ---: |
| `_fs_storage_utils.py` | `88%` |
| `_fs_storage_infra.py` | `81%` |
| `_fs_blob_core.py` | `87%` |
| `local_file_store.py` | `99%` |
| `repository_protocols.py` | `100%` |

首次用多个module-name `--cov=`参数运行时，coverage instrumentation触发当前环境的NumPy重复加载错误；改用等价目录source `--cov=dayu/fins/storage`后通过。该问题只发生在coverage命令装载方式，不在普通focused/full Fins测试中复现，也不属于S1生产失败。

### Type check

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

### Whitespace check

```bash
git diff --check
```

结果：pass，无输出。

## README Decision

- `dayu/fins/README.md`: 本S1不更新。虽然`dayu/fins/`触发README检查，但accepted plan的`R3-C-PF-09`强制S1 -> S2 -> S3顺序，并明确README/current-fact同步只能在三个production slices全部land并通过各slice review后执行；S1单独同步会提前承诺尚未落地的S2/S3整体语义。
- `tests/README.md`: 本S1不更新。相同PF-09要求最终统一记录storage commit、ingestion atomicity、temp cleanup及wait-adapter测试迁移；当前新增测试仍属于README已有的Fins storage测试层级，没有新增测试目录、运行方式或维护规则。
- 根README及其它README：未触发用户可见安装、CLI、workflow或分层装配变化，不更新。

## Tool-Security Exclusion

本S1未实现、未测试承诺、未写README或LLM-facing文本投影以下任何工具安全项：

- upload allowlist / explicit user-file authority / symlink-safe upload source policy；
- URL / TLS / redirect / SSRF provenance policy；
- remote download byte-budget policy；
- LLM-facing upload/download security schema、prompt或tool schema变化。

storage object-key/local-URI containment只约束`dayu.fins.storage`自身产生和消费的filesystem identity，不是upload source authority或远端egress policy。

## Residual Risks And Uncovered Areas

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| rollback物理rename本身失败时正式目录可能暂时未恢复 | covered by current S1 recovery contract | journal/backup/staging证据保留，由`dayu.fins.storage.recover_orphan_batches()`重试；证据不可读时需要显式operator/user decision |
| directory fsync在不支持的平台继续采用既有best-effort策略 | assigned to later work unit | Fins filesystem backend portability WU；当前macOS验证已确认helper调用顺序 |
| upload/download caller token lifecycle与单document mutation | covered by later approved slice | mandatory next slice R3-C S2；本S1未修改caller |
| Fins -> Host reverse import relocation | covered by later approved slice | mandatory R3-C S3；本S1未修改Host/Service/Fins wait adapter |
| 四类tool-security finding | assigned to later work unit | 独立tool-security / remote-egress WU |

无未分类residual risk。

## Stop Status And Next Entry Point

- stop condition triggered: `no`
- blocking questions: `0`
- implementation status: `pass`
- next entry point: R3-C S1 code review
- 本artifact不授权commit；按用户要求停在implementation报告。
