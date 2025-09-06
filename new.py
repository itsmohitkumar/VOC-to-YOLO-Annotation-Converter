from utils.env_vars import *
import pymssql
import sys

# Database Creds
db_server = DATABASE_SERVER
db_user = DATABASE_USERNAME
db_pass = DATABASE_PASSWORD
db_name = DATABASE_NAME

table = "agentic_campaign_images"  # or "dbo.agentic_campaign_images"

conn = None
cursor = None

try:
    conn = pymssql.connect(
        server=db_server,
        user=db_user,
        password=db_pass,
        database=db_name,
    )
    cursor = conn.cursor(as_dict=True)
    print("Connected to SQL server")
except Exception as e:
    print("Connection failed:", e)
    sys.exit(1)

# Split schema and table if provided as "schema.table"
if "." in table:
    owner, table_name = table.split(".", 1)
else:
    owner, table_name = "dbo", table

try:
    # Create the table if it doesn't exist
    create_table_query = f"""
    IF OBJECT_ID('{owner}.{table_name}', 'U') IS NULL
    BEGIN
        CREATE TABLE {owner}.{table_name} (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username NVARCHAR(255) NOT NULL,
            campaign_name NVARCHAR(255) NOT NULL,
            post_id NVARCHAR(255) NOT NULL,
            image_base64 NVARCHAR(MAX) NULL,
            image_s3_key NVARCHAR(MAX) NULL,
            prompt_used NVARCHAR(MAX) NULL,
            generation_model NVARCHAR(255) NULL,
            created_at DATETIME DEFAULT GETDATE()
        );
    END
    """
    cursor.execute(create_table_query)
    conn.commit()
    print(f"Table {owner}.{table_name} created or already exists.")

    # Parameterized call to avoid quoting issues
    cursor.execute(
        "EXEC sp_columns @table_name=%s, @table_owner=%s",
        (table_name, owner),
    )
    columns = cursor.fetchall()

    if not columns:
        print(f"No columns found in table {owner}.{table_name}")
    else:
        print(f"\nColumns in table {owner}.{table_name}:")
        for col in columns:
            column_name = col.get("COLUMN_NAME")
            data_type = col.get("TYPE_NAME")
            print(f"- {column_name} ({data_type})")

except Exception as e:
    print("Failed to create table or retrieve columns:", e)
finally:
    try:
        if cursor is not None:
            cursor.close()
    finally:
        if conn is not None:
            conn.close()
