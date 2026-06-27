import os
import django
import sys
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import connection

ALLOWED_DATABASES = {'aielts_db', 'defaultdb'}


def _validate_safety_guards() -> None:
    db_name = connection.settings_dict.get('NAME') or ''

    # Guard 1: explicit opt-in env switch
    if os.environ.get('ALLOW_DROP_TABLES') != 'YES':
        raise RuntimeError('Refusing to drop tables: set ALLOW_DROP_TABLES=YES to continue.')

    # Guard 2: environment gate + allowlist
    allow_any_db = os.environ.get('DROP_TABLES_ALLOW_ANY_DB') == 'YES'
    if not allow_any_db and db_name not in ALLOWED_DATABASES:
        raise RuntimeError(f'Refusing to drop tables for DB={db_name!r}. Not in allowlist: {sorted(ALLOWED_DATABASES)}')
    if not settings.DEBUG and os.environ.get('DROP_TABLES_IN_PROD') != 'YES':
        raise RuntimeError('Refusing to drop tables while DEBUG=False. Set DROP_TABLES_IN_PROD=YES to override.')

    # Guard 3: typed confirmation phrase
    expected = f'DROP {db_name}'
    supplied = os.environ.get('DROP_TABLES_CONFIRM', '').strip()
    if not supplied and sys.stdin.isatty():
        supplied = input(f'Type "{expected}" to confirm dropping all tables: ').strip()
    if supplied != expected:
        raise RuntimeError('Confirmation phrase mismatch. Aborted.')

def drop_all_tables():
    _validate_safety_guards()
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
