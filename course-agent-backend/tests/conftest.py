from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles


@compiles(LONGTEXT, "sqlite")
def compile_longtext_for_sqlite(_type, _compiler, **_kwargs):
    """Allow isolated SQLite tests to create models that use MySQL LONGTEXT."""

    return "TEXT"
