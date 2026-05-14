"""Host durable foundation 内部包。

本包承载 Host 层内部的 SQLite durable store 基础设施，包括 schema
bootstrap、连接装配、事务 runner、codec helper 与结构化错误类型。它不
属于 ``dayu.host`` 包根公共导出面，也不承载 EventLog append、Host command
path、Engine dispatch、projection、memory 或 recovery 行为。
"""
