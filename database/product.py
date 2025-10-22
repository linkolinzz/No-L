from database.db_manager import connect_db

def all():
    with connect_db() as conn:
        cur = conn.cursor(dictionary=True)
        # Вибираємо всі поля, включаючи вагу виробу
        cur.execute(
            """
            SELECT id,
                   article_code,
                   name,
                   weight_g,
                   drying_needed,
                   trimming_needed,
                   cutting_needed,
                   cleaning_needed
            FROM product_base
            ORDER BY id DESC
            """
        )
        return cur.fetchall()

def save_or_update(
    code: str,
    name: str,
    weight: int | None,
    drying: int,
    trimming: int,
    cutting: int,
    cleaning: int,
) -> None:
    """
    Вставляє або оновлює запис у таблиці product_base.

    Параметри:
      code    – артикул виробу (унікальний ключ)
      name    – назва виробу
      weight  – вага виробу в грамах (або None, якщо невідома)
      drying  – чи потрібна сушка (0/1)
      trimming– чи потрібна обрізка (0/1)
      cutting – чи потрібна різка (0/1)
      cleaning– чи потрібна зачистка (0/1)

    Якщо запис з таким артикулом вже існує, оновлюються ім'я, необхідні етапи
    та вага (якщо weight не None).  Якщо weight дорівнює None, існуюче значення
    weight_g не змінюється.
    """
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM product_base WHERE article_code = %s", (code,))
        exists = cur.fetchone() is not None
        if exists:
            if weight is not None:
                cur.execute(
                    """
                    UPDATE product_base
                       SET name=%s,
                           weight_g=%s,
                           drying_needed=%s,
                           trimming_needed=%s,
                           cutting_needed=%s,
                           cleaning_needed=%s
                     WHERE article_code=%s
                    """,
                    (name, weight, drying, trimming, cutting, cleaning, code),
                )
            else:
                cur.execute(
                    """
                    UPDATE product_base
                       SET name=%s,
                           drying_needed=%s,
                           trimming_needed=%s,
                           cutting_needed=%s,
                           cleaning_needed=%s
                     WHERE article_code=%s
                    """,
                    (name, drying, trimming, cutting, cleaning, code),
                )
        else:
            cur.execute(
                """
                INSERT INTO product_base
                    (article_code,
                     name,
                     weight_g,
                     drying_needed,
                     trimming_needed,
                     cutting_needed,
                     cleaning_needed)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (code, name, weight, drying, trimming, cutting, cleaning),
            )
        conn.commit()

def delete(article_code: str):
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM product_base WHERE article_code = %s", (article_code,))
        conn.commit()
