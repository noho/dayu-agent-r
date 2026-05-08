"""Host P6 HostStorage / HostStorageTransaction 行为测试。"""

from __future__ import annotations

import asyncio

import pytest

from dayu.host._host_storage_transaction import HostStorage


@pytest.mark.asyncio
async def test_transaction_commit_runs_post_commit_hooks() -> None:
    """COMMIT 成功后 post-commit hook 必须按注册顺序触发。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    async with storage.transaction() as tx:
        tx.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    triggered: list[str] = []
    async with storage.transaction() as tx:
        tx.execute("INSERT INTO t (id) VALUES (1)")
        tx.add_post_commit_hook(lambda: triggered.append("a"))
        tx.add_post_commit_hook(lambda: triggered.append("b"))
    assert triggered == ["a", "b"]
    rows = storage.execute_read("SELECT id FROM t")
    assert [row[0] for row in rows] == [1]
    storage.close()


@pytest.mark.asyncio
async def test_transaction_rollback_skips_post_commit_hooks() -> None:
    """事务体抛异常时回滚，hook 不触发。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    async with storage.transaction() as tx:
        tx.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    triggered: list[str] = []

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        async with storage.transaction() as tx:
            tx.execute("INSERT INTO t (id) VALUES (1)")
            tx.add_post_commit_hook(lambda: triggered.append("a"))
            raise _Boom()
    assert triggered == []
    rows = storage.execute_read("SELECT id FROM t")
    assert rows == []
    storage.close()


@pytest.mark.asyncio
async def test_transaction_serializes_concurrent_writers() -> None:
    """并发 transaction 通过 asyncio.Lock 串行化。"""

    storage = HostStorage(database_path=":memory:")
    storage.open()
    async with storage.transaction() as tx:
        tx.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    order: list[int] = []

    async def _writer(value: int) -> None:
        async with storage.transaction() as tx:
            tx.execute("INSERT INTO t (id) VALUES (?)", (value,))
            order.append(value)

    await asyncio.gather(*(_writer(i) for i in range(5)))
    rows = storage.execute_read("SELECT id FROM t ORDER BY id")
    assert [row[0] for row in rows] == [0, 1, 2, 3, 4]
    assert sorted(order) == order
    storage.close()
