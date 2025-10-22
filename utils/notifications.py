# utils/notifications.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional, Dict, List, Tuple
from database.db_manager import connect_db


# -------------------- низькорівневі хелпери --------------------
def _fetchall(sql: str, params: tuple = ()):
    with connect_db() as cn:
        cur = cn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()


def _exec(sql: str, params: tuple = ()):
    with connect_db() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        cn.commit()
        return cur.rowcount


def _exec_lastrowid(sql: str, params: tuple = ()):
    with connect_db() as cn:
        cur = cn.cursor()
        cur.execute(sql, params)
        cn.commit()
        return cur.lastrowid


def _exec_many(sql: str, params_seq: List[Tuple]):
    if not params_seq:
        return 0
    with connect_db() as cn:
        cur = cn.cursor()
        cur.executemany(sql, params_seq)
        cn.commit()
        return cur.rowcount


def _current_db_name() -> str:
    rows = _fetchall("SELECT DATABASE() AS db")
    return rows[0]["db"] if rows and rows[0]["db"] else ""


def _table_exists(name: str) -> bool:
    db = _current_db_name()
    rows = _fetchall(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s LIMIT 1",
        (db, name),
    )
    return bool(rows)


def _notifications_id_coltype() -> Optional[str]:
    """
    Повертає точний COLUMN_TYPE колонки notifications.id (напр., 'int(11) unsigned').
    """
    db = _current_db_name()
    rows = _fetchall(
        """
        SELECT COLUMN_TYPE AS ct
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name='notifications' AND column_name='id'
        """,
        (db,),
    )
    if rows and rows[0].get("ct"):
        return rows[0]["ct"]
    return None


def _ensure_reads_table():
    """
    Створює notification_reads тільки коли вже існує notifications
    і підбирає ідентичний тип для notification_id.
    """
    if not _table_exists("notifications"):
        # schema ще не готова — спробуємо наступного разу при зверненні до API
        return

    # Якщо таблиця вже є — нічого не робимо
    if _table_exists("notification_reads"):
        return

    id_coltype = _notifications_id_coltype() or "BIGINT"

    # ВАЖЛИВО: використовуємо отриманий COLUMN_TYPE без змін
    # щоб збігався тип та unsigned із notifications.id
    create_sql = f"""
        CREATE TABLE IF NOT EXISTS notification_reads (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            notification_id {id_coltype} NOT NULL,
            user_key VARCHAR(191) NOT NULL,
            read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_nid_user (notification_id, user_key),
            KEY idx_user (user_key),
            CONSTRAINT fk_notification_reads_notifications
              FOREIGN KEY (notification_id) REFERENCES notifications(id)
              ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    _exec(create_sql)


def _columns_meta() -> Dict[str, Dict]:
    db = _current_db_name()
    rows = _fetchall(
        """
        SELECT COLUMN_NAME AS name, DATA_TYPE AS dt, EXTRA AS extra, IS_NULLABLE AS isnull
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='notifications'
        """,
        (db,),
    )
    meta: Dict[str, Dict] = {}
    for r in rows:
        name = r["name"]
        extra = (r.get("extra") or "").lower()
        meta[name] = {
            "data_type": (r.get("dt") or "").lower(),
            "extra": extra,
            "is_generated": "generated" in extra,
            "is_nullable": (r.get("isnull") or "").upper() == "YES",
        }
    return meta


def _has_writable_col(cols: Dict[str, Dict], name: str) -> bool:
    return name in cols and not cols[name]["is_generated"]


# -------------------- вибір полів під різні схеми --------------------
_MESSAGE_CANDIDATES = ["message", "text", "body", "payload", "raw", "content", "note", "details", "description", "msg"]
_TIME_CANDIDATES = ["created_at", "ts", "dt", "timestamp", "time", "created", "inserted_at"]
_LEVEL_CANDIDATES = ["level"]         # info|success|warning|error
_SRC_CANDIDATES = ["src", "source"]   # app|system|banner|...

_UNREAD_BOOL = ["is_read"]
_READ_AT = ["read_at"]


def _select_message_expr(cols: Dict[str, Dict]) -> str:
    present = [c for c in _MESSAGE_CANDIDATES if c in cols]
    if not present:
        return "''"
    return "COALESCE(" + ", ".join(present) + ")"


def _select_time_name(cols: Dict[str, Dict]) -> Optional[str]:
    for c in _TIME_CANDIDATES:
        if c in cols:
            return c
    return None


def _pick_first_writable(cols: Dict[str, Dict], names: List[str]) -> Optional[str]:
    for n in names:
        if _has_writable_col(cols, n):
            return n
    return None


# -------------------- публічні API: публікація --------------------
def push(msg: str, *, level: str = "info", src: str = "app") -> Optional[int]:
    _ensure_reads_table()

    cols = _columns_meta()

    msg_col = _pick_first_writable(cols, _MESSAGE_CANDIDATES)
    level_col = _pick_first_writable(cols, _LEVEL_CANDIDATES)
    src_col = _pick_first_writable(cols, _SRC_CANDIDATES)

    fields: List[str] = []
    ph: List[str] = []
    params: List = []

    if msg_col:
        fields.append(msg_col)
        ph.append("%s")
        params.append(msg)

    if level_col:
        fields.append(level_col)
        ph.append("%s")
        params.append(level)

    if src_col:
        fields.append(src_col)
        ph.append("%s")
        params.append(src)

    if not fields:
        try:
            return _exec_lastrowid("INSERT INTO notifications () VALUES ()")
        except Exception:
            return None

    sql = f"INSERT INTO notifications ({', '.join(fields)}) VALUES ({', '.join(ph)})"
    return _exec_lastrowid(sql, tuple(params))


# -------------------- публічні API: читання / статус --------------------
def latest_id() -> int:
    _ensure_reads_table()
    rows = _fetchall("SELECT MAX(id) AS max_id FROM notifications")
    val = rows[0]["max_id"] if rows else None
    return int(val or 0)


def unread_count(user_key: str) -> int:
    """
    К-сть нотифікацій, які користувач ще не бачив (один раз на користувача).
    """
    _ensure_reads_table()
    sql = """
        SELECT COUNT(*) AS c
        FROM notifications n
        LEFT JOIN notification_reads r
               ON r.notification_id = n.id AND r.user_key = %s
        WHERE r.id IS NULL
    """
    rows = _fetchall(sql, (user_key,))
    return int(rows[0]["c"] if rows else 0)


def recent(user_key: str, limit: int = 50, offset: int = 0) -> List[Dict]:
    """
    Останні нотифікації з прапорцем is_read для user_key.
    """
    _ensure_reads_table()
    cols = _columns_meta()
    tname = _select_time_name(cols)
    t_expr = tname if tname else "NULL"
    msg_expr = _select_message_expr(cols)

    level_name = next((n for n in _LEVEL_CANDIDATES if n in cols), None)
    src_name = next((n for n in _SRC_CANDIDATES if n in cols), None)

    sel_parts = [
        f"n.id",
        f"{msg_expr} AS msg",
        f"{t_expr} AS dt",
        (level_name or "NULL") + " AS level",
        (src_name or "NULL") + " AS src",
        "CASE WHEN r.id IS NULL THEN 0 ELSE 1 END AS is_read",
    ]

    sql = f"""
        SELECT {', '.join(sel_parts)}
        FROM notifications n
        LEFT JOIN notification_reads r
               ON r.notification_id=n.id AND r.user_key=%s
        ORDER BY n.id DESC
        LIMIT %s OFFSET %s
    """
    rows = _fetchall(sql, (user_key, int(limit), int(offset)))
    return rows


def history(user_key: str, q: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Dict]:
    """
    Повна історія з optional-пошуком по тексту (LIKE, case-insensitive).
    """
    _ensure_reads_table()
    cols = _columns_meta()
    tname = _select_time_name(cols)
    t_expr = tname if tname else "NULL"
    msg_expr = _select_message_expr(cols)

    level_name = next((n for n in _LEVEL_CANDIDATES if n in cols), None)
    src_name = next((n for n in _SRC_CANDIDATES if n in cols), None)

    sel_parts = [
        f"n.id",
        f"{msg_expr} AS msg",
        f"{t_expr} AS dt",
        (level_name or "NULL") + " AS level",
        (src_name or "NULL") + " AS src",
        "CASE WHEN r.id IS NULL THEN 0 ELSE 1 END AS is_read",
    ]

    base = f"""
        SELECT {', '.join(sel_parts)}
        FROM notifications n
        LEFT JOIN notification_reads r
               ON r.notification_id=n.id AND r.user_key=%s
    """

    params: List = [user_key]
    where = ""
    if q:
        where = f"WHERE LOWER({msg_expr}) LIKE %s"
        params.append(f"%{q.lower()}%")

    tail = " ORDER BY n.id DESC LIMIT %s OFFSET %s"
    params.extend([int(limit), int(offset)])

    rows = _fetchall(base + where + tail, tuple(params))
    return rows


def unread_of_source(user_key: str, src_value: str, limit: int = 1) -> List[Dict]:
    """
    Повертає непрочитані нотифікації певного джерела (наприклад, src='banner'),
    щоб показати банер 1 раз.
    """
    _ensure_reads_table()
    cols = _columns_meta()
    if not any(s in cols for s in _SRC_CANDIDATES):
        return []  # немає src-поля — пропускаємо

    tname = _select_time_name(cols)
    t_expr = tname if tname else "NULL"
    msg_expr = _select_message_expr(cols)

    # виберемо першу “src” колонку
    src_col = next((s for s in _SRC_CANDIDATES if s in cols), None)
    level_name = next((n for n in _LEVEL_CANDIDATES if n in cols), None)

    sel_parts = [
        "n.id",
        f"{msg_expr} AS msg",
        f"{t_expr} AS dt",
        (level_name or "NULL") + " AS level",
        f"{src_col} AS src",
    ]

    sql = f"""
        SELECT {', '.join(sel_parts)}
        FROM notifications n
        LEFT JOIN notification_reads r
               ON r.notification_id = n.id AND r.user_key = %s
        WHERE r.id IS NULL AND {src_col}=%s
        ORDER BY n.id ASC
        LIMIT %s
    """
    return _fetchall(sql, (user_key, src_value, int(limit)))


def mark_read(ids: List[int]) -> int:
    """
    Глобальна позначка (історичний API). Залишаємо як було.
    """
    _ensure_reads_table()
    if not ids:
        return 0
    cols = _columns_meta()
    if _pick_first_writable(cols, _UNREAD_BOOL):
        sql = f"UPDATE notifications SET is_read=1 WHERE id IN ({', '.join(['%s'] * len(ids))})"
        return _exec(sql, tuple(ids))
    if _pick_first_writable(cols, _READ_AT):
        sql = f"UPDATE notifications SET read_at=NOW() WHERE id IN ({', '.join(['%s'] * len(ids))})"
        return _exec(sql, tuple(ids))
    return 0


def mark_read_by_user(ids: List[int], user_key: str) -> int:
    """
    Позначає конкретні нотифікації прочитаними ДЛЯ КОРИСТУВАЧА (1 раз для цього user_key).
    Ідempotентно через INSERT IGNORE.
    """
    _ensure_reads_table()
    if not ids or not user_key:
        return 0
    params = [(int(i), user_key) for i in ids]
    sql = "INSERT IGNORE INTO notification_reads (notification_id, user_key) VALUES (%s, %s)"
    return _exec_many(sql, params)


# --------- додатковий хелпер під final_quality ---------
def request_closed(
    request_number: str | int,
    *,
    article_code: str | None = None,
    qty: int | None = None,
    stage: str | None = None,
    src: str = "final_quality",
) -> Optional[int]:
    """
    Публікує стандартне повідомлення про закриття/завершення заявки.
    Параметри гнучкі, щоб підходило під різні виклики у коді.
    """
    parts: List[str] = [f"Заявка {request_number} завершена"]
    tail: List[str] = []
    if article_code:
        tail.append(f"артикул {article_code}")
    if qty is not None:
        tail.append(f"{qty} шт")
    if stage:
        tail.append(f"етап: {stage}")
    if tail:
        parts.append(f"({', '.join(tail)})")
    msg = " ".join(parts)
    return push(msg, level="success", src=src)
