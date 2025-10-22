# database/db_manager.py
import os
import mysql.connector
from contextlib import contextmanager
from dotenv import load_dotenv

# локальний логер (не обов’язково, але зручно відслідковувати помилки SQL)
from utils.logger import log

load_dotenv()

DB_CONFIG: dict = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    user=os.getenv("DB_USER", "appuser"),
    password=os.getenv("DB_PASS", "20001202az"),
    database=os.getenv("DB_NAME", "mpi_agro_1_0"),
    charset="utf8mb4",
    autocommit=True,               # одразу комітимо всі запити
    collation="utf8mb4_0900_ai_ci",
)

# ──────────────────────────────────────────────────────────────
def connect_db():
    """Отримати «сире» з’єднання, якщо десь потрібно вручну."""
    return mysql.connector.connect(**DB_CONFIG)

@contextmanager
def db():
    """with db() as conn: … → автоматично закриє та відкотить у разі помилки."""
    conn = connect_db()
    try:
        yield conn
    except Exception as exc:
        log(f"ROLLBACK: {exc}", tag="db")
        conn.rollback()
        raise
    finally:
        conn.close()

# ──────────────────────────────────────────────────────────────
def db_fetch(sql: str, params: tuple | None = None) -> list[dict]:
    """
    Виконує SELECT та повертає list[dict].
    Використання:
        rows = db_fetch("SELECT * FROM table WHERE id=%s", (42,))
    """
    with db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        return rows

def db_exec(sql: str, params: tuple | None = None) -> int:
    """
    INSERT / UPDATE / DELETE.
    Повертає lastrowid (0, якщо не INSERT).
    """
    with db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        last_id = cur.lastrowid
        cur.close()
        return last_id
