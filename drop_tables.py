import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import connection

def drop_all_tables():
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        cursor.execute("SHOW TABLES;")
        tables = cursor.fetchall()
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS `{table[0]}`;")
            print(f"Dropped table: {table[0]}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    print("All tables dropped successfully.")

if __name__ == "__main__":
    drop_all_tables()
