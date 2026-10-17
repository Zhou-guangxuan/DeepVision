"""列类型工具。

SQLite 的 BIGINT 主键不会自增（只有 INTEGER PRIMARY KEY 才映射到 rowid），
因此用 with_variant 让 SQLite 使用 INTEGER，其他数据库使用 BIGINT。
"""

from sqlalchemy import BigInteger, Integer

IDType = BigInteger().with_variant(Integer, "sqlite")
