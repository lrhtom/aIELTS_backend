from pathlib import Path

import pymysql
from dotenv import load_dotenv
import os

# Reuse backend runtime configuration so this script always follows current DB provider.
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / 'backend' / '.env'
load_dotenv(ENV_PATH)

HOST = os.environ.get('DB_HOST', 'localhost')
USER = os.environ.get('DB_USER', '')
PASSWORD = os.environ.get('DB_PASSWORD', '')
PORT = int(os.environ.get('DB_PORT', '3306'))
DB_NAME = os.environ.get('DB_NAME', 'aielts_db')
SSL_CA = os.environ.get('DB_SSL_CA', '')

# Resolve CA path from backend directory when a relative path is provided.
if SSL_CA and not Path(SSL_CA).is_absolute():
    SSL_CA = str((BASE_DIR / 'backend' / SSL_CA).resolve())

try:
    print(f"Connecting to {HOST} with SSL...")
    # Connect without a specific DB first to create one
    ssl_options = {'ca': SSL_CA} if SSL_CA else {}
    connection = pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        port=PORT,
        ssl=ssl_options,
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS
    )
    with connection.cursor() as cursor:
        print("Executing CREATE DATABASE...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        print(f"Database '{DB_NAME}' created or already exists.")
    connection.commit()
    connection.close()
    print("Done!")
except Exception as e:
    print(f"Error: {e}")
