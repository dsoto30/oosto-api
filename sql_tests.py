import pyodbc
import datetime
import os
from dotenv import load_dotenv, dotenv_values

load_dotenv()

SERVER = os.getenv("SERVER")
DATABASE  = os.getenv("DATABASE")
UID = os.getenv("UID")
PWD = os.getenv("PWD")

conn_str = (
    'DRIVER={ODBC Driver 18 for SQL Server};'
    f'SERVER={SERVER};'
    f'DATABASE={DATABASE};'
    f'UID={UID};'
    f'PWD={PWD};'
    'TrustServerCertificate=yes;'
)

# connect using your server info
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# SQL INSERT statement with placeholders
insert_query = "INSERT INTO entrance_recognitions (subject_id, time_entered) VALUES (?, ?)"

# Create a timezone-aware datetime (e.g., using UTC)
now = datetime.datetime.now(datetime.timezone.utc)

# Define the values to insert (subject_id is a string, time_entered is a datetimeoffset)
values = ("user_id", now)
# send the values
cursor.execute(insert_query, values)
conn.commit()

print("Row inserted successfully!")

# close the connection
cursor.close()
conn.close()
