import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

SERVER = os.getenv("SERVER")
DATABASE = os.getenv("DATABASE")
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

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

query = """
BEGIN TRANSACTION;
INSERT INTO test2 (subject_id, time_entered)
SELECT subject_id, time_entered
FROM test1
WHERE time_entered < DATEADD(HOUR, 6, CAST(CAST(GETDATE() AS date) AS datetimeoffset));
DELETE FROM test1
WHERE time_entered < DATEADD(HOUR, 6, CAST(CAST(GETDATE() AS date) AS datetimeoffset));
COMMIT TRANSACTION;
"""

cursor.execute(query)
conn.commit()

cursor.close()
conn.close()

