import psycopg
from psycopg.rows import dict_row

from .config import DATABASE_URL


def get_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db() -> None:
    """Run schema.sql. Safe to call on every startup — every statement in
    it is idempotent (CREATE TABLE IF NOT EXISTS / ON CONFLICT DO NOTHING)."""
    import pathlib

    schema_path = pathlib.Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
