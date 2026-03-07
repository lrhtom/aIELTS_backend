import pymysql

# Azure MySQL Connection Info
HOST = 'aieltsmysql.mysql.database.azure.com'
USER = 'lrhtom'
PASSWORD = '20040502lr!'
PORT = 3306

try:
    print(f"Connecting to {HOST} with SSL...")
    # Connect without a specific DB first to create one
    connection = pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        port=PORT,
        ssl={'ca': ''},  # Minimal dict to negotiate SSL
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS
    )
    with connection.cursor() as cursor:
        print("Executing CREATE DATABASE...")
        cursor.execute("CREATE DATABASE IF NOT EXISTS aielts_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        print("Database 'aielts_db' created or already exists.")
    connection.commit()
    connection.close()
    print("Done!")
except Exception as e:
    print(f"Error: {e}")
