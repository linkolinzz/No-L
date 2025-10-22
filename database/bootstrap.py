# Ініціалізація/міграція схеми БД для Pre_Liz (MySQL/InnoDB)
# Створює таблиці, індекси, FK та виставляє коментарі українською.
from __future__ import annotations

import datetime as _dt
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from database.db_manager import connect_db

# Логер: використовуємо utils.logger.log, а якщо немає — простий принт
try:
    from utils.logger import log as _ext_log
    def log(msg: str, tag: str = "bootstrap"):
        _ext_log(msg, tag=tag)
except Exception:
    def log(msg: str, tag: str = "bootstrap"):
        now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{tag} {now}] {msg}")

# ───────────────────────────── helpers ─────────────────────────────

def esc(s: str) -> str:
    return s.replace("'", "''")

def qid(name: str) -> str:
    return f"`{name}`"

@contextmanager
def cnx_cur():
    cn = connect_db()
    try:
        cur = cn.cursor(dictionary=True, buffered=True)
        yield cn, cur
        cn.commit()
    except Exception as e:
        cn.rollback()
        log(f"Schema bootstrap ROLLBACK: {e}", tag="bootstrap")
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            cn.close()
        except Exception:
            pass

def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,),
    )
    return cur.fetchone() is not None

def column_info(cur, table: str, col: str) -> Optional[dict]:
    cur.execute(
        "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, col),
    )
    return cur.fetchone()

def table_columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (table,),
    )
    return {r["COLUMN_NAME"] for r in cur.fetchall()}

def index_exists(cur, table: str, index_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s",
        (table, index_name),
    )
    return cur.fetchone() is not None

def fk_exists(cur, table: str, fk_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME=%s "
        "AND CONSTRAINT_NAME=%s AND CONSTRAINT_TYPE='FOREIGN KEY'",
        (table, fk_name),
    )
    return cur.fetchone() is not None

def ensure_table_comment(cur, table: str, comment: str):
    cur.execute(f"ALTER TABLE {qid(table)} COMMENT='{esc(comment)}'")

def add_column(cur, table: str, col_def_sql: str, after: Optional[str] = None):
    sql = f"ALTER TABLE {qid(table)} ADD COLUMN {col_def_sql}"
    if after:
        sql += f" AFTER {qid(after)}"
    cur.execute(sql)

def modify_column_comment(cur, table: str, col: str, comment: str):
    import re
    info = column_info(cur, table, col)
    if not info:
        return
    col_type = info["COLUMN_TYPE"]
    is_null  = "NULL" if info["IS_NULLABLE"] == "YES" else "NOT NULL"

    default_sql = ""
    default = info["COLUMN_DEFAULT"]
    if default is not None:
        ds = str(default).strip()
        m = re.match(r"(?i)^current_timestamp(?:\((\d+)\))?\s*\(?\)?$", ds)
        if m:
            prec = m.group(1)
            default_sql = " DEFAULT CURRENT_TIMESTAMP" + (f"({prec})" if prec else "")
        else:
            default_sql = f" DEFAULT '{esc(ds)}'"

    extra = (info.get("EXTRA") or "").lower()
    extra_sql_parts = []
    if "on update current_timestamp" in extra:
        extra_sql_parts.append("ON UPDATE CURRENT_TIMESTAMP")
    if "auto_increment" in extra:
        extra_sql_parts.append("AUTO_INCREMENT")
    extra_sql = (" " + " ".join(extra_sql_parts)) if extra_sql_parts else ""

    sql = (
        f"ALTER TABLE {qid(table)} MODIFY COLUMN {qid(col)} "
        f"{col_type} {is_null}{default_sql}{extra_sql} COMMENT '{esc(comment)}'"
    )
    cur.execute(sql)

def ensure_index(cur, table: str, name: str, cols: List[str], unique: bool = False):
    if not index_exists(cur, table, name):
        cols_sql = ", ".join(qid(c) for c in cols)
        kind = "UNIQUE" if unique else "INDEX"
        cur.execute(f"ALTER TABLE {qid(table)} ADD {kind} {qid(name)} ({cols_sql})")

def ensure_fk(cur, table: str, fk_name: str, col: str,
              ref_table: str, ref_col: str = "id",
              on_delete: str = "CASCADE", on_update: str = "CASCADE"):
    if fk_exists(cur, table, fk_name):
        return
    ensure_index(cur, table, f"idx_{table}_{col}", [col])
    cur.execute(
        f"ALTER TABLE {qid(table)} "
        f"ADD CONSTRAINT {qid(fk_name)} FOREIGN KEY ({qid(col)}) "
        f"REFERENCES {qid(ref_table)} ({qid(ref_col)}) "
        f"ON DELETE {on_delete} ON UPDATE {on_update}"
    )

# ───────────────────────────── schema map ─────────────────────────────

TABLES: Dict[str, Dict[str, Any]] = {
    # === КОРИСТУВАЧІ ДЛЯ ЛАУНЧЕРА ===
    "users": {
        "comment": "Облікові записи для входу в застосунок",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`first_name` VARCHAR(100) NOT NULL",                            "Ім'я користувача", "id"),
            ("`last_name`  VARCHAR(100) NOT NULL",                            "Прізвище користувача", "first_name"),
            ("`login`      VARCHAR(100) NOT NULL",                            "Логін (унікальний)", "last_name"),
            ("`password_hash` VARCHAR(255) NOT NULL",                         "SHA256-хеш пароля", "login"),
            ("`role`       VARCHAR(50)  NOT NULL",                            "Роль (Адміністратор/Робітник)", "password_hash"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",     "Створено", "role"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [("uq_users_login", ["login"])],
        "indexes": [],
        "fks": [],
    },

    # === ОСНОВНА БАЗА ВИРОБІВ ===
    "product_base": {
        "comment": "Довідник виробів (артикул і назва) та прапорці потрібних етапів",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code` VARCHAR(64) NOT NULL",                           "Артикул виробу (унікальний)", "id"),
            ("`name` VARCHAR(255) NOT NULL",                                  "Найменування виробу", "article_code"),
            # Значення ваги виробу в грамах. Може бути NULL, якщо вага невідома.
            ("`weight_g` DECIMAL(10,3) NULL",                                 "Вага (г)", "name"),
            ("`drying_needed`   TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Сушка»", "name"),
            ("`trimming_needed` TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Обрізка ливників»", "drying_needed"),
            ("`cutting_needed`  TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Різка»", "trimming_needed"),
            ("`cleaning_needed` TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Зачистка»", "cutting_needed"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",     "Створено", "cleaning_needed"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [("uq_product_article", ["article_code"])],
        "indexes": [],
        "fks": [],
    },

    # === OLD: тимчасова таблиця для імпорту/перенесення ===
    "product_base_old": {
        "comment": "Тимчасова база виробів (OLD) для імпорту з Excel і перенесення в основну",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "PK", None),
            ("`article_code` VARCHAR(64) NOT NULL",                           "Артикул (унікальний)", "id"),
            ("`name` VARCHAR(255) NOT NULL",                                  "Найменування", "article_code"),
            # Значення ваги виробу у грамах (може бути NULL).
            ("`weight_g` DECIMAL(10,3) NULL",                                 "Вага (г)", "name"),
            ("`drying_needed`   TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Сушка»", "name"),
            ("`trimming_needed` TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Обрізка ливників»", "drying_needed"),
            ("`cutting_needed`  TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Різка»", "trimming_needed"),
            ("`cleaning_needed` TINYINT(1) NOT NULL DEFAULT 0",               "Потрібно етап «Зачистка»", "cutting_needed"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",     "Створено", "cleaning_needed"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [("uq_product_old_article", ["article_code"])],
        "indexes": [],
        "fks": [],
    },

    "casting_requests": {
        "comment": "Заявки на виробництво (позиції: артикул/кількість/клієнт/дата/етап)",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number` VARCHAR(30) NOT NULL",                         "Номер заявки", "id"),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "request_number"),
            ("`quantity`       INT NOT NULL",                                 "Потрібна кількість (шт.)", "article_code"),
            ("`stage`          VARCHAR(40) NOT NULL",                         "Початковий етап (для навігації)", "quantity"),
            ("`request_date`   DATE NOT NULL",                                "Дата створення заявки", "stage"),
            ("`client`         VARCHAR(120) NOT NULL",                        "Клієнт/замовник", "request_date"),
            ("`reason`         VARCHAR(255) NOT NULL",                        "Примітка/причина", "client"),
            ("`is_closed` TINYINT(1) NOT NULL DEFAULT 0",                    "Прапорець: 1 – заявка закрита, 0 – активна", "reason"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "reason"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [("uq_castreq_req_art", ["request_number", "article_code"])],
        "indexes": [
            ("idx_castreq_req", ["request_number"]),
            ("idx_castreq_req_art", ["request_number", "article_code"]),
        ],
        "fks": [],
    },

    "casting": {
        "comment": "Етап «Лиття»: журнальні записи по виробленим партіям",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number` VARCHAR(30) NOT NULL",                         "Номер заявки", "id"),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "request_number"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`quantity`       INT NOT NULL",                                 "Кількість (циклів/виливків)", "product_name"),
            ("`defect_quantity` INT NULL",                                    "Брак (шт.)", "quantity"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "defect_quantity"),
            ("`machine_number` VARCHAR(60) NULL",                             "Станок/форма", "operator_name"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "machine_number"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_casting_req", ["request_number"]),
            ("idx_casting_art", ["article_code"]),
        ],
        "fks": [],
    },

    "drying": {
        "comment": "Етап «Сушка»: результат по партії лиття, таймінг запуску/завершення",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number` VARCHAR(30) NOT NULL",                         "Номер заявки", "id"),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "request_number"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість після лиття (добра)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника (сушка)", "qty"),
            ("`casting_id`     INT NOT NULL",                                 "Посилання на партію лиття (casting.id)", "operator_name"),
            ("`start_time`     DATETIME NULL",                                "Час старту сушіння", "casting_id"),
            ("`end_time`       DATETIME NULL",                                "Час завершення сушіння", "start_time"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "end_time"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [("uq_drying_casting", ["casting_id"])],
        "indexes": [
            ("idx_drying_req", ["request_number"]),
            ("idx_drying_art", ["article_code"]),
        ],
        "fks": [
            ("fk_drying_casting", "casting_id", "casting", "id", "CASCADE", "CASCADE"),
        ],
    },

    "casting_quality": {
        "comment": "Проміжний контроль якості після лиття/сушки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number`   VARCHAR(30) NOT NULL",                       "Номер заявки", "id"),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "request_number"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`controller_name`  VARCHAR(120) NULL",                          "ПІБ контролера", "product_name"),
            ("`checked_quantity` INT NOT NULL",                               "Перевірено (шт.)", "controller_name"),
            ("`accepted_quantity` INT NOT NULL",                              "Прийнято (шт.)", "checked_quantity"),
            ("`defect_quantity`  INT NULL",                                   "Брак (шт.)", "accepted_quantity"),
            ("`reason`           VARCHAR(255) NULL",                          "Опис/причина браку", "defect_quantity"),
            ("`drying_id`        INT NULL",                                   "Зв'язок із сушінням (drying.id)", "reason"),
            ("`casting_id`       INT NULL",                                   "Зв'язок із литтям (casting.id)", "drying_id"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP","Створено", "casting_id"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cq_req", ["request_number"]),
            ("idx_cq_art", ["article_code"]),
            ("idx_cq_cast", ["casting_id"]),
            ("idx_cq_dry",  ["drying_id"]),
        ],
        "fks": [
            ("fk_cq_casting", "casting_id", "casting", "id", "SET NULL", "CASCADE"),
            ("fk_cq_drying",  "drying_id",  "drying",  "id", "SET NULL", "CASCADE"),
        ],
    },

    "trimming": {
        "comment": "Етап «Обрізка ливників»: оброблені/дефектні кількості по артикулу",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number`   VARCHAR(30) NOT NULL",                       "Номер заявки", "id"),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "request_number"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`operator_name`    VARCHAR(120) NULL",                          "ПІБ робітника", "product_name"),
            ("`processed_quantity` INT NOT NULL",                             "Оброблено (шт.)", "operator_name"),
            ("`defect_quantity`    INT NULL",                                 "Брак (шт.)", "processed_quantity"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP","Створено", "defect_quantity"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_trim_req", ["request_number"]),
            ("idx_trim_art", ["article_code"]),
        ],
        "fks": [],
    },

    "cutting": {
        "comment": "Етап «Різка»: оброблені/дефектні кількості, зв'язок із литтям",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number`   VARCHAR(30) NOT NULL",                       "Номер заявки", "id"),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "request_number"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`operator_name`    VARCHAR(120) NULL",                          "ПІБ робітника", "product_name"),
            ("`processed_quantity` INT NOT NULL",                             "Оброблено (шт.)", "operator_name"),
            ("`defect_quantity`    INT NULL",                                 "Брак (шт.)", "processed_quantity"),
            ("`casting_id`       INT NULL",                                   "Посилання на партію лиття (casting.id)", "defect_quantity"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP","Створено", "casting_id"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cut_req", ["request_number"]),
            ("idx_cut_art", ["article_code"]),
            ("idx_cut_cast", ["casting_id"]),
        ],
        "fks": [
            ("fk_cut_cast", "casting_id", "casting", "id", "SET NULL", "CASCADE"),
        ],
    },

    "cleaning": {
        "comment": "Етап «Зачистка»: оброблені/дефектні кількості, зв'язок із різкою",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number`   VARCHAR(30) NOT NULL",                       "Номер заявки", "id"),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "request_number"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`operator_name`    VARCHAR(120) NULL",                          "ПІБ робітника", "product_name"),
            ("`processed_quantity` INT NOT NULL",                             "Оброблено (шт.)", "operator_name"),
            ("`defect_quantity`    INT NULL",                                 "Брак (шт.)", "processed_quantity"),
            ("`cutting_id`       INT NULL",                                   "Посилання на партію різки (cutting.id)", "defect_quantity"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP","Створено", "cutting_id"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_clean_req", ["request_number"]),
            ("idx_clean_art", ["article_code"]),
            ("idx_clean_cut", ["cutting_id"]),
        ],
        "fks": [
            ("fk_clean_cut", "cutting_id", "cutting", "id", "SET NULL", "CASCADE"),
        ],
    },

    "final_quality": {
        "comment": "Фінальний контроль якості по партіях етапів",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`request_number`   VARCHAR(30) NOT NULL",                       "Номер заявки", "id"),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "request_number"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`inspector_name`   VARCHAR(120) NULL",                          "ПІБ інспектора", "product_name"),
            ("`checked_quantity` INT NOT NULL",                               "Перевірено (шт.)", "inspector_name"),
            ("`accepted_quantity` INT NOT NULL",                              "Прийнято (шт.)", "checked_quantity"),
            ("`drying_id`        INT NULL",                                   "Зв'язок із сушінням (drying.id)", "accepted_quantity"),
            ("`trimming_id`      INT NULL",                                   "Зв'язок із обрізкою (trimming.id)", "drying_id"),
            ("`cutting_id`       INT NULL",                                   "Зв'язок із різкою (cutting.id)", "trimming_id"),
            ("`cleaning_id`      INT NULL",                                   "Зв'язок із зачисткою (cleaning.id)", "cutting_id"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP","Створено", "cleaning_id"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_fq_req", ["request_number"]),
            ("idx_fq_art", ["article_code"]),
            ("idx_fq_dry", ["drying_id"]),
            ("idx_fq_trim", ["trimming_id"]),
            ("idx_fq_cut", ["cutting_id"]),
            ("idx_fq_clean", ["cleaning_id"]),
        ],
        "fks": [
            ("fk_fq_dry",   "drying_id",   "drying",  "id", "SET NULL", "CASCADE"),
            ("fk_fq_trim",  "trimming_id", "trimming","id", "SET NULL", "CASCADE"),
            ("fk_fq_cut",   "cutting_id",  "cutting", "id", "SET NULL", "CASCADE"),
            ("fk_fq_clean", "cleaning_id", "cleaning","id", "SET NULL", "CASCADE"),
        ],
    },

    # ─────────── СКЛАД ───────────
    "warehouse_moves": {
        "comment": "Рухи складу: + прийом, - відвантаження, ± коригування",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "PK", None),
            ("`move_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",       "Час руху", "id"),
            ("`request_number` VARCHAR(30) NULL",                             "Номер заявки (якщо є)", "move_time"),
            ("`article_code` VARCHAR(64) NOT NULL",                           "Артикул", "request_number"),
            ("`product_name` VARCHAR(255) NOT NULL",                          "Найменування", "article_code"),
            ("`qty` INT NOT NULL",                                            "Кількість (+ прийом, - відвантаження)", "product_name"),
            ("`reason` VARCHAR(255) NULL",                                    "Причина/коментар", "qty"),
            ("`operator_name` VARCHAR(120) NULL",                             "ПІБ робітника (склад)", "reason"),
            ("`location` VARCHAR(60) NULL",                                   "Локація/осередок", "operator_name"),
            ("`source_table` VARCHAR(40) NULL",                               "Джерело (наприклад final_quality)", "location"),
            ("`source_id` INT NULL",                                          "ID запису у джерелі", "source_table"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",     "Створено", "source_id"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_wh_art", ["article_code"]),
            ("idx_wh_src", ["source_table", "source_id"]),
            ("idx_wh_time", ["move_time"]),
        ],
        "fks": [],
    },

    "notifications": {
        "comment": "Черга сповіщень для інтерфейсу (банер повідомлень)",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`message` VARCHAR(255) NOT NULL",                               "Текст сповіщення", "id"),
            ("`is_read` TINYINT(1) NOT NULL DEFAULT 0",                       "Позначка «прочитано»", "message"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",     "Створено", "is_read"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [],
        "fks": [],
    },

    # === Лиття без заявки ===
    "casting_no_request": {
        "comment": "Етап «Лиття без заявки»: журнальні записи по виробленим партіям без прив'язки до заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`quantity`       INT NOT NULL",                                 "Кількість (циклів/виливків)", "product_name"),
            ("`defect_quantity` INT NULL",                                    "Брак (шт.)", "quantity"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "defect_quantity"),
            ("`machine_number` VARCHAR(60) NULL",                             "Станок/форма", "operator_name"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "machine_number"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_casting_no_request_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Сушка без заявки ===
    "drying_no_request": {
        "comment": "Етап «Сушка без заявки»: записи сушіння для партій без прив'язки до заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "Первинний ключ", None),
            ("`casting_id` INT NULL", "Посилання на партію лиття без заявки", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "casting_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`qty` INT NOT NULL", "Кількість після лиття (добра)", "product_name"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника (сушка)", "qty"),
            ("`start_time` DATETIME NULL", "Час старту сушіння", "operator_name"),
            ("`end_time` DATETIME NULL", "Час завершення сушіння", "start_time"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "end_time"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_drying_no_request_art", ["article_code"]),
        ],
        "fks": [
            ("fk_drying_no_request_cast", "casting_id", "casting_no_request", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Сушка (випробування) ===
    "drying_test": {
        "comment": "Етап «Сушка (випробування)»: записи сушіння для тестових виливків без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "Первинний ключ", None),
            ("`casting_id` INT NULL", "Посилання на тестову партію лиття", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "casting_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`qty` INT NOT NULL", "Кількість після лиття (добра)", "product_name"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника (сушка)", "qty"),
            ("`start_time` DATETIME NULL", "Час старту сушіння", "operator_name"),
            ("`end_time` DATETIME NULL", "Час завершення сушіння", "start_time"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "end_time"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_drying_test_art", ["article_code"]),
        ],
        "fks": [
            ("fk_drying_test_cast", "casting_id", "casting_test", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Проміжний КЯ без заявки ===
    "casting_quality_no_request": {
        "comment": "Етап «К/Я Лиття без заявки»: записи контролю якості для партій без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`casting_id` INT NULL", "Посилання на партію лиття без заявки", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "casting_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`controller_name` VARCHAR(120) NULL", "ПІБ контролера", "product_name"),
            ("`checked_quantity` INT NOT NULL", "Перевірено (шт.)", "controller_name"),
            ("`accepted_quantity` INT NOT NULL", "Прийнято (шт.)", "checked_quantity"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "accepted_quantity"),
            ("`reason` VARCHAR(255) NULL", "Опис/причина браку", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "reason"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cq_no_request_art", ["article_code"]),
        ],
        "fks": [
            ("fk_cq_no_request_cast", "casting_id", "casting_no_request", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Проміжний КЯ (випробування) ===
    "casting_quality_test": {
        "comment": "Етап «К/Я Лиття (випробування)»: записи контролю якості для тестових партій",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`casting_id` INT NULL", "Посилання на тестову партію лиття", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "casting_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`controller_name` VARCHAR(120) NULL", "ПІБ контролера", "product_name"),
            ("`checked_quantity` INT NOT NULL", "Перевірено (шт.)", "controller_name"),
            ("`accepted_quantity` INT NOT NULL", "Прийнято (шт.)", "checked_quantity"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "accepted_quantity"),
            ("`reason` VARCHAR(255) NULL", "Опис/причина браку", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "reason"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cq_test_art", ["article_code"]),
        ],
        "fks": [
            ("fk_cq_test_cast", "casting_id", "casting_test", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Обрізка без заявки ===
    "trimming_no_request": {
        "comment": "Етап «Обрізка без заявки»: записи обрізки ливників для партій без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`drying_id` INT NULL", "Посилання на сушку без заявки", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "drying_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`processed_quantity` INT NOT NULL", "Оброблено (шт.)", "product_name"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "processed_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_trim_no_request_art", ["article_code"]),
        ],
        "fks": [
            ("fk_trim_no_request_drying", "drying_id", "drying_no_request", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Обрізка (випробування) ===
    "trimming_test": {
        "comment": "Етап «Обрізка (випробування)»: записи обрізки для тестових партій без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`drying_id` INT NULL", "Посилання на тестову сушку", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "drying_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`processed_quantity` INT NOT NULL", "Оброблено (шт.)", "product_name"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "processed_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_trim_test_art", ["article_code"]),
        ],
        "fks": [
            ("fk_trim_test_drying", "drying_id", "drying_test", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Різка без заявки ===
    "cutting_no_request": {
        "comment": "Етап «Різка без заявки»: записи різки для партій без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`trimming_id` INT NULL", "Посилання на обрізку без заявки", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "trimming_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`processed_quantity` INT NOT NULL", "Оброблено (шт.)", "product_name"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "processed_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cut_no_request_art", ["article_code"]),
        ],
        "fks": [
            ("fk_cut_no_request_trim", "trimming_id", "trimming_no_request", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Різка (випробування) ===
    "cutting_test": {
        "comment": "Етап «Різка (випробування)»: записи різки для тестових партій без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`trimming_id` INT NULL", "Посилання на обрізку (тест)", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "trimming_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`processed_quantity` INT NOT NULL", "Оброблено (шт.)", "product_name"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "processed_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cut_test_art", ["article_code"]),
        ],
        "fks": [
            ("fk_cut_test_trim", "trimming_id", "trimming_test", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Зачистка без заявки ===
    "cleaning_no_request": {
        "comment": "Етап «Зачистка без заявки»: записи зачистки для партій без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`cutting_id` INT NULL", "Посилання на різку без заявки", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "cutting_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`processed_quantity` INT NOT NULL", "Оброблено (шт.)", "product_name"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "processed_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_clean_no_request_art", ["article_code"]),
        ],
        "fks": [
            ("fk_clean_no_request_cut", "cutting_id", "cutting_no_request", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Зачистка (випробування) ===
    "cleaning_test": {
        "comment": "Етап «Зачистка (випробування)»: записи зачистки для тестових партій",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`cutting_id` INT NULL", "Посилання на різку (тест)", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "cutting_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`processed_quantity` INT NOT NULL", "Оброблено (шт.)", "product_name"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "processed_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ робітника", "defect_quantity"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_clean_test_art", ["article_code"]),
        ],
        "fks": [
            ("fk_clean_test_cut", "cutting_id", "cutting_test", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Фінальний КЯ без заявки ===
    "final_quality_no_request": {
        "comment": "Етап «Фінальний К/Я без заявки»: фінальний контроль якості для партій без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`cleaning_id` INT NULL", "Посилання на зачистку без заявки", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "cleaning_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`checked_quantity` INT NOT NULL", "Перевірено (шт.)", "product_name"),
            ("`accepted_quantity` INT NOT NULL", "Прийнято (шт.)", "checked_quantity"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "accepted_quantity"),
            ("`reason` VARCHAR(255) NULL", "Опис/причина браку", "defect_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ контролера", "reason"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_final_no_request_art", ["article_code"]),
        ],
        "fks": [
            ("fk_final_no_request_clean", "cleaning_id", "cleaning_no_request", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Фінальний КЯ (випробування) ===
    "final_quality_test": {
        "comment": "Етап «Фінальний К/Я (випробування)»: фінальний контроль для тестових партій",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT", "PK", None),
            ("`cleaning_id` INT NULL", "Посилання на зачистку (тест)", "id"),
            ("`article_code` VARCHAR(64) NOT NULL", "Артикул виробу", "cleaning_id"),
            ("`product_name` VARCHAR(255) NOT NULL", "Найменування виробу", "article_code"),
            ("`checked_quantity` INT NOT NULL", "Перевірено (шт.)", "product_name"),
            ("`accepted_quantity` INT NOT NULL", "Прийнято (шт.)", "checked_quantity"),
            ("`defect_quantity` INT NULL", "Брак (шт.)", "accepted_quantity"),
            ("`reason` VARCHAR(255) NULL", "Опис/причина браку", "defect_quantity"),
            ("`operator_name` VARCHAR(120) NULL", "ПІБ контролера", "reason"),
            ("`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_final_test_art", ["article_code"]),
        ],
        "fks": [
            ("fk_final_test_clean", "cleaning_id", "cleaning_test", "id", "CASCADE", "CASCADE"),
        ],
    },

    # === Лиття (випробування) ===
    "casting_test": {
        "comment": "Етап «Лиття (випробування)»: тестові записи по виливках без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`quantity`       INT NOT NULL",                                 "Кількість (циклів/виливків)", "product_name"),
            ("`defect_quantity` INT NULL",                                    "Брак (шт.)", "quantity"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "defect_quantity"),
            ("`machine_number` VARCHAR(60) NULL",                             "Станок/форма", "operator_name"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "machine_number"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_casting_test_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Сушка без заявки ===
    "drying_no_request": {
        "comment": "Етап «Сушка без заявки»: записи сушіння без прив'язки до литтєвої заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_drying_no_req_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Сушка (випробування) ===
    "drying_test": {
        "comment": "Етап «Сушка (випробування)»: тестові записи сушіння без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_drying_test_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Контроль якості лиття/сушки без заявки ===
    "casting_quality_no_request": {
        "comment": "Етап «Контроль якості (без заявки)»: записи перевірок без прив'язки до заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "id"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`controller_name`  VARCHAR(120) NULL",                          "ПІБ контролера", "product_name"),
            ("`checked_quantity` INT NOT NULL",                               "Перевірено (шт.)", "controller_name"),
            ("`accepted_quantity` INT NOT NULL",                              "Прийнято (шт.)", "checked_quantity"),
            ("`defect_quantity`  INT NULL",                                   "Брак (шт.)", "accepted_quantity"),
            ("`reason`           VARCHAR(255) NULL",                          "Причина браку", "defect_quantity"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "reason"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_castqual_no_req_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Контроль якості лиття/сушки (випробування) ===
    "casting_quality_test": {
        "comment": "Етап «Контроль якості (випробування)»: тестові записи перевірок без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "id"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`controller_name`  VARCHAR(120) NULL",                          "ПІБ контролера", "product_name"),
            ("`checked_quantity` INT NOT NULL",                               "Перевірено (шт.)", "controller_name"),
            ("`accepted_quantity` INT NOT NULL",                              "Прийнято (шт.)", "checked_quantity"),
            ("`defect_quantity`  INT NULL",                                   "Брак (шт.)", "accepted_quantity"),
            ("`reason`           VARCHAR(255) NULL",                          "Причина браку", "defect_quantity"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "reason"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_castqual_test_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Обрізка без заявки ===
    "trimming_no_request": {
        "comment": "Етап «Обрізка без заявки»: записи обрізки ливників без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_trimming_no_req_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Обрізка (випробування) ===
    "trimming_test": {
        "comment": "Етап «Обрізка (випробування)»: тестові записи обрізки ливників без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_trimming_test_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Різка без заявки ===
    "cutting_no_request": {
        "comment": "Етап «Різка без заявки»: записи різки без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cutting_no_req_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Різка (випробування) ===
    "cutting_test": {
        "comment": "Етап «Різка (випробування)»: тестові записи різки без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cutting_test_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Зачистка без заявки ===
    "cleaning_no_request": {
        "comment": "Етап «Зачистка без заявки»: записи зачистки без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cleaning_no_req_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Зачистка (випробування) ===
    "cleaning_test": {
        "comment": "Етап «Зачистка (випробування)»: тестові записи зачистки без заявки",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`   VARCHAR(64) NOT NULL",                         "Артикул виробу", "id"),
            ("`product_name`   VARCHAR(255) NOT NULL",                        "Найменування виробу", "article_code"),
            ("`qty`            INT NOT NULL",                                 "Кількість (шт.)", "product_name"),
            ("`operator_name`  VARCHAR(120) NULL",                            "ПІБ робітника", "qty"),
            ("`created_at`     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "operator_name"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_cleaning_test_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Фінальний контроль якості без заявки ===
    "final_quality_no_request": {
        "comment": "Етап «Фінальний контроль якості без заявки»",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "id"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`controller_name`  VARCHAR(120) NULL",                          "ПІБ контролера", "product_name"),
            ("`accepted_quantity` INT NOT NULL",                              "Прийнято (шт.)", "controller_name"),
            ("`defect_quantity`  INT NULL",                                   "Брак (шт.)", "accepted_quantity"),
            ("`reason`           VARCHAR(255) NULL",                          "Причина браку", "defect_quantity"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "reason"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_finalqual_no_req_art", ["article_code"]),
        ],
        "fks": [],
    },

    # === Фінальний контроль якості (випробування) ===
    "final_quality_test": {
        "comment": "Етап «Фінальний контроль якості (випробування)»",
        "columns": [
            ("`id` INT NOT NULL AUTO_INCREMENT",                              "Первинний ключ", None),
            ("`article_code`     VARCHAR(64) NOT NULL",                       "Артикул виробу", "id"),
            ("`product_name`     VARCHAR(255) NOT NULL",                      "Найменування виробу", "article_code"),
            ("`controller_name`  VARCHAR(120) NULL",                          "ПІБ контролера", "product_name"),
            ("`accepted_quantity` INT NOT NULL",                              "Прийнято (шт.)", "controller_name"),
            ("`defect_quantity`  INT NULL",                                   "Брак (шт.)", "accepted_quantity"),
            ("`reason`           VARCHAR(255) NULL",                          "Причина браку", "defect_quantity"),
            ("`created_at`       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP", "Створено", "reason"),
            ("PRIMARY KEY (`id`)", "", None),
        ],
        "unique": [],
        "indexes": [
            ("idx_finalqual_test_art", ["article_code"]),
        ],
        "fks": [],
    },
}

# ─────────────────────────── core builders ───────────────────────────

def create_table(cur, name: str, spec: Dict[str, Any]):
    cols_sql = []
    for ddl, comment, _after in spec["columns"]:
        if ddl.upper().startswith("PRIMARY KEY"):
            cols_sql.append(ddl)
        else:
            if comment:
                ddl = f"{ddl} COMMENT '{esc(comment)}'"
            cols_sql.append(ddl)

    create = (
        f"CREATE TABLE {qid(name)} (\n  " + ",\n  ".join(cols_sql) + "\n)"
        " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        f" COMMENT='{esc(spec.get('comment',''))}'"
    )
    cur.execute(create)

    for idx_name, cols in spec.get("indexes", []):
        ensure_index(cur, name, idx_name, cols, unique=False)
    for uq_name, cols in spec.get("unique", []):
        ensure_index(cur, name, uq_name, cols, unique=True)
    for fk_name, col, ref_t, ref_c, od, ou in spec.get("fks", []):
        ensure_fk(cur, name, fk_name, col, ref_t, ref_c, od, ou)

def ensure_columns_and_comments(cur, name: str, spec: Dict[str, Any]):
    prev = None
    for ddl, comment, after in spec["columns"]:
        if ddl.upper().startswith("PRIMARY KEY"):
            continue
        col = ddl.split()[0].strip("`")
        info = column_info(cur, name, col)
        if not info:
            add_column(cur, name, f"{ddl} COMMENT '{esc(comment)}'", after=after or prev)
        else:
            if (info.get("COLUMN_COMMENT") or "") != (comment or ""):
                modify_column_comment(cur, name, col, comment or "")
        prev = col

    ensure_table_comment(cur, name, spec.get("comment", ""))

    for idx_name, cols in spec.get("indexes", []):
        ensure_index(cur, name, idx_name, cols, unique=False)
    for uq_name, cols in spec.get("unique", []):
        ensure_index(cur, name, uq_name, cols, unique=True)
    for fk_name, col, ref_t, ref_c, od, ou in spec.get("fks", []):
        ensure_fk(cur, name, fk_name, col, ref_t, ref_c, od, ou)

# ───────────────────────────── migrations ─────────────────────────────

def migrate_product_base_flags(cur):
    renames = [
        ("drying",   "drying_needed",   "Потрібно етап «Сушка»"),
        ("trimming", "trimming_needed", "Потрібно етап «Обрізка ливників»"),
        ("cutting",  "cutting_needed",  "Потрібно етап «Різка»"),
        ("cleaning", "cleaning_needed", "Потрібно етап «Зачистка»"),
    ]
    for old, new, comment in renames:
        cur.execute(
            "SELECT 1 FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME='product_base' AND COLUMN_NAME=%s",
            (old,),
        )
        has_old = cur.fetchone() is not None
        if has_old and not column_info(cur, "product_base", new):
            cur.execute(
                f"ALTER TABLE `product_base` CHANGE COLUMN `{old}` `{new}` "
                f"TINYINT(1) NOT NULL DEFAULT 0 COMMENT '{esc(comment)}'"
            )

def migrate_missing_article_code_in_casting_requests(cur):
    if not column_info(cur, "casting_requests", "article_code"):
        add_column(
            cur,
            "casting_requests",
            "`article_code` VARCHAR(64) NOT NULL COMMENT 'Артикул виробу'",
            after="request_number",
        )

def migrate_final_quality_ids(cur):
    for col, cmt in [
        ("drying_id",   "Зв'язок із сушінням (drying.id)"),
        ("trimming_id", "Зв'язок із обрізкою (trimming.id)"),
        ("cutting_id",  "Зв'язок із різкою (cutting.id)"),
        ("cleaning_id", "Зв'язок із зачисткою (cleaning.id)"),
    ]:
        if not column_info(cur, "final_quality", col):
            add_column(cur, "final_quality", f"`{col}` INT NULL COMMENT '{esc(cmt)}'")
    ensure_index(cur, "final_quality", "idx_fq_dry",   ["drying_id"])
    ensure_index(cur, "final_quality", "idx_fq_trim",  ["trimming_id"])
    ensure_index(cur, "final_quality", "idx_fq_cut",   ["cutting_id"])
    ensure_index(cur, "final_quality", "idx_fq_clean", ["cleaning_id"])

# ───────────────────────────── міграція ваги ─────────────────────────────

def migrate_weight_g_column(cur):
    """
    Ensure that the weight_g column is stored as a DECIMAL with three fractional
    digits instead of INT.  If the column exists and is defined as an integer,
    change its type to DECIMAL(10,3) and keep the comment.
    """
    for table in ("product_base", "product_base_old"):
        info = column_info(cur, table, "weight_g")
        if not info:
            continue
        # DATA_TYPE may be 'int' and COLUMN_TYPE may be 'int' or 'int(11)' etc
        dt = (info.get("DATA_TYPE") or "").lower()
        if dt and dt.startswith("int"):
            # Change column type preserving the NULLability and comment
            cur.execute(
                f"ALTER TABLE `{table}` MODIFY COLUMN `weight_g` DECIMAL(10,3) NULL COMMENT 'Вага (г)'"
            )
    ensure_fk(cur, "final_quality", "fk_fq_dry",   "drying_id",   "drying",  "id", "SET NULL", "CASCADE")
    ensure_fk(cur, "final_quality", "fk_fq_trim",  "trimming_id", "trimming","id", "SET NULL", "CASCADE")
    ensure_fk(cur, "final_quality", "fk_fq_cut",   "cutting_id",  "cutting", "id", "SET NULL", "CASCADE")
    ensure_fk(cur, "final_quality", "fk_fq_clean","cleaning_id", "cleaning","id","SET NULL","CASCADE")

def ensure_notifications_compat(cur):
    cols = table_columns(cur, "notifications")

    if "msg" in cols and "message" not in cols:
        cur.execute(
            "ALTER TABLE `notifications` CHANGE COLUMN `msg` `message` "
            "VARCHAR(255) NOT NULL COMMENT 'Текст сповіщення'"
        )
        cols.remove("msg")
        cols.add("message")

    if "msg" in cols and "message" in cols:
        info = column_info(cur, "notifications", "msg")
        extra = (info.get("EXTRA") or "").upper()
        if "GENERATED" not in extra:
            cur.execute(
                "UPDATE `notifications` "
                "SET `message` = COALESCE(NULLIF(`message`, ''), `msg`) "
                "WHERE `msg` IS NOT NULL AND `msg` <> ''"
            )
            cur.execute("ALTER TABLE `notifications` DROP COLUMN `msg`")
            cols.remove("msg")

    if "msg" not in cols:
        cur.execute(
            "ALTER TABLE `notifications` "
            "ADD COLUMN `msg` VARCHAR(255) GENERATED ALWAYS AS (`message`) VIRTUAL"
        )
        cols.add("msg")

    if not index_exists(cur, "notifications", "idx_notifications_isread_created"):
        cur.execute(
            "CREATE INDEX `idx_notifications_isread_created` "
            "ON `notifications`(`is_read`, `created_at`)"
        )

def migrate_final_quality_warehouse_link(cur):
    if not column_info(cur, "final_quality", "warehouse_in_id"):
        add_column(
            cur,
            "final_quality",
            "`warehouse_in_id` INT NULL COMMENT 'Рух складу (прийом з виробництва)'",
            after="cleaning_id",
        )
    ensure_index(cur, "final_quality", "idx_fq_whin", ["warehouse_in_id"])
    try:
        ensure_fk(cur, "final_quality", "fk_fq_whin", "warehouse_in_id", "warehouse_moves", "id", "SET NULL", "CASCADE")
    except Exception:
        pass

def migrate_wh_operator_column(cur):
    cols = table_columns(cur, "warehouse_moves") if table_exists(cur, "warehouse_moves") else set()
    has_worker = "worker_name" in cols
    has_operator = "operator_name" in cols
    if has_worker and not has_operator:
        cur.execute(
            "ALTER TABLE `warehouse_moves` "
            "CHANGE COLUMN `worker_name` `operator_name` VARCHAR(120) NULL "
            "COMMENT 'ПІБ робітника (склад)'"
        )
    elif not has_operator:
        add_column(
            cur,
            "warehouse_moves",
            "`operator_name` VARCHAR(120) NULL COMMENT 'ПІБ робітника (склад)'",
            after="reason",
        )

def migrate_casting_requests_unique(cur):
    """
    Деякі БД мали помилковий UNIQUE на `request_number` (без article_code),
    що забороняє додавати кілька позицій у одну заявку.
    Тут ми його прибираємо і вводимо коректний унікальний ключ по парі.
    """
    cur.execute(
        """
        SELECT DISTINCT s.INDEX_NAME
          FROM information_schema.STATISTICS s
         WHERE s.TABLE_SCHEMA = DATABASE()
           AND s.TABLE_NAME = 'casting_requests'
           AND s.NON_UNIQUE = 0
           AND s.COLUMN_NAME = 'request_number'
           AND NOT EXISTS (
               SELECT 1
                 FROM information_schema.STATISTICS t
                WHERE t.TABLE_SCHEMA = s.TABLE_SCHEMA
                  AND t.TABLE_NAME   = s.TABLE_NAME
                  AND t.INDEX_NAME   = s.INDEX_NAME
                  AND t.SEQ_IN_INDEX > 1
           )
           AND s.INDEX_NAME <> 'PRIMARY'
        """
    )
    to_drop = [r["INDEX_NAME"] for r in cur.fetchall()]
    for idx in to_drop:
        log(f"Dropping wrong UNIQUE index {idx} on casting_requests.request_number", tag="bootstrap")
        cur.execute(f"ALTER TABLE `casting_requests` DROP INDEX `{idx}`")

    ensure_index(cur, "casting_requests", "idx_castreq_req", ["request_number"])
    ensure_index(cur, "casting_requests", "uq_castreq_req_art", ["request_number", "article_code"], unique=True)

# --- New migration: add is_closed column to casting_requests ---
def migrate_casting_requests_closed(cur):
    """
    Adds the `is_closed` flag to casting_requests if it does not exist.

    The column is a tinyint(1) with default 0, indicating whether the request is closed.
    It is added after the `reason` column.
    """
    try:
        if not column_info(cur, "casting_requests", "is_closed"):
            # Insert the new column after `reason`
            add_column(cur, "casting_requests", "`is_closed` TINYINT(1) NOT NULL DEFAULT 0", after="reason")
    except Exception as e:
        log(f"Failed to add is_closed column: {e}", tag="bootstrap")

# ───────────────────────────── entry point ─────────────────────────────

def ensure_schema():
    with cnx_cur() as (_cn, cur):
        log("Schema bootstrap started", tag="bootstrap")

        # створити відсутні таблиці
        for tname, spec in TABLES.items():
            if not table_exists(cur, tname):
                log(f"Creating table {tname}", tag="bootstrap")
                create_table(cur, tname, spec)

        # додати/оновити відсутні колонки, коментарі, індекси, FK
        for tname, spec in TABLES.items():
            ensure_columns_and_comments(cur, tname, spec)

        # міграції/узгодження
        migrate_product_base_flags(cur)
        migrate_missing_article_code_in_casting_requests(cur)
        migrate_final_quality_ids(cur)
        migrate_final_quality_warehouse_link(cur)
        # Ensure weight columns use DECIMAL instead of INT
        migrate_weight_g_column(cur)
        ensure_notifications_compat(cur)
        migrate_wh_operator_column(cur)
        migrate_casting_requests_unique(cur)

        # ensure casting_requests has is_closed flag
        migrate_casting_requests_closed(cur)

        log("Schema bootstrap finished", tag="bootstrap")

# ——— ЗВОРОТНА СУМІСНІСТЬ ———
def ensure_stage_tables():
    return ensure_schema()
