import csv
import mysql.connector

# Підставте свої параметри підключення
conn = mysql.connector.connect(
    host="127.0.0.1",      # адреса MySQL‑сервера
    user="appuser",      # ваш логін
    password="20001202az",  # ваш пароль
    database="MPI_AGRO_1_0",   # назва вашої БД
    charset="utf8mb4"
)

def export_table(table):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {table}")
    rows = cursor.fetchall()

    # якщо в таблиці є дані, зберігаємо їх у CSV‑файл
    if rows:
        with open(f"{table}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"Таблиця {table}: збережено {len(rows)} рядків.")
    else:
        print(f"Таблиця {table} порожня.")

for tbl in ["final_quality", "warehouse_moves", "product_base"]:
    export_table(tbl)

conn.close()
