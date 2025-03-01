import requests
import socketio
from dotenv import load_dotenv
import pyodbc
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue
import logging
import threading

load_dotenv()


"""
COPY ENVIRONMENT VARIABLES FROM .env FILE TO THIS SCRIPT. HARDCODED VALUES FOR NOW
"""


log_file = "oosto_logs.log"
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", filemode="a")


def log_message(message):
    logging.info(message)
    print(message)

conn_str = (
    'DRIVER={ODBC Driver 18 for SQL Server};'
    f'SERVER={DB_SERVER};'
    f'DATABASE={DB_NAME};'
    f'UID={DB_USER};'
    f'PWD={DB_PASSWORD};'
    'TrustServerCertificate=yes;'
)

connection_pool = queue.Queue(maxsize=8)
executor = ThreadPoolExecutor(max_workers=12)

for _ in range(8):
    connection_pool.put(pyodbc.connect(conn_str))


BASE_API_URL = f"https://{SERVER_IP}/bt/api"
HEADERS = {
        'accept': "application/json",
        'content-type': "application/json"
    }


def login():

    login_url = f"{BASE_API_URL}/login"
    

    response = requests.post(login_url, headers=HEADERS, json={'username': USERNAME, 'password': PASSWORD}, verify=False)
    response.raise_for_status()
    json_response = response.json()
    
    token = json_response["token"]
    HEADERS["authorization"] = f"Bearer {token}"
    return token


def process_recognition(recognition):
    guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

    if recognition['subject']['groups'][0]['id'] == guest_group_id:
        subject_id = recognition['subject']['id']
        time_recognized = datetime.fromisoformat(recognition['frameTimeStamp'])

        if connection_pool.empty():
            log_message("connection pool is empty!")

        conn = connection_pool.get()
        cursor = conn.cursor()
        try:
            
            query = """
                    MERGE INTO entrance_recognitions AS target
                    USING (SELECT ? AS subject_id, ? AS time_entered) AS source
                    ON target.subject_id = source.subject_id
                    WHEN NOT MATCHED THEN 
                        INSERT (subject_id, time_entered) VALUES (source.subject_id, source.time_entered);
                    """
            cursor.execute(query, (subject_id, time_recognized))
            
            if cursor.rowcount > 0:
                log_message(f"processed subject {recognition["subject"]["name"]}, id: {subject_id} at {time_recognized}")
            conn.commit()
            
        except Exception as e:
            log_message(f"Database error: {e}")
        finally:
            cursor.close()
            connection_pool.put(conn)



def create_socket(token):


    sio = socketio.Client(reconnection=True, ssl_verify=False)

    @sio.on('connect')
    def connect():
        log_message("connected to socket")

    @sio.on('disconnect')
    def disconnect():
        log_message("Disconnected from socket. Closing database connections...")

        # Close all database connections in the pool
        while not connection_pool.empty():
            conn = connection_pool.get()
            conn.close()
        
        log_message("All database connections closed.")

    
    @sio.on('connect_error')
    def connect_error(data):
        log_message("The connection failed!")

    def find_closest_match(matches):
        return max([match['score'] for match in matches])

    @sio.on('track:created')
    def track_created(track_data):
        
        imageQualityThreshold = 80
        closestMatchScoreThreshold = .45
        guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

        track = track_data[0]
        # print(track)
        closest_match_score = 0 if not track['closeMatches'] else find_closest_match(track['closeMatches'])
        if closest_match_score <= closestMatchScoreThreshold and track["landmarkScore"] >= imageQualityThreshold:
            body_request = {
                "name": "John Doe",
                "description": "",
                "groups": [guest_group_id],
                "sendToHq": False,
                "searchBackwards": [{
                    "searchBackwardsThreshold": .6,
                    "objectType": track["objectType"]
                }],
                "images": [
                    {"isPrimary": True, "landmarkScore": track['landmarkScore'], "objectType": track['objectType'], "url": track['images'][0]['url'], "track": {
                        "camera": track['camera']['id'], "frameTimeStamp": track['frameTimeStamp'], "id": track['id']
                    }}
                    ]
                
            }

            executor.submit(requests.post, f"{BASE_API_URL}/subjects/from-track", json=body_request, verify=False, headers=HEADERS)
            log_message(f"Added unkown to Guest Group image quality score was {track["landmarkScore"]} and closest match score was {closest_match_score}")
        else:
            track_id = track['id']
            collate_id = track["collateId"]
            frameQualityScore = track["landmarkScore"]

            if connection_pool.empty():
                log_message("connection pool is empty!")

            conn = connection_pool.get()
            cursor = conn.cursor()
            try:
                
                query = """
                    MERGE INTO tracks_missed AS target
                    USING (SELECT ? AS track_id, ? AS collate_id, ? AS frameQualityScore, ? AS closeMatchScore) AS source
                    ON target.track_id = source.track_id
                    WHEN NOT MATCHED THEN
                        INSERT (track_id, collate_id, frameQualityScore, closeMatchScore)
                        VALUES (source.track_id, source.collate_id, source.frameQualityScore, source.closeMatchScore);
                    """
                cursor.execute(query, (track_id, collate_id, frameQualityScore , closest_match_score))
                
                if cursor.rowcount > 0:
                    log_message(f"Dismissed track {track_id}, quality score: {frameQualityScore}, closest match score: {closest_match_score}")
                conn.commit()
                
            except Exception as e:
                log_message(f"Database error: {e}")
            finally:
                cursor.close()
                connection_pool.put(conn)

    @sio.on('recognition:created')
    def recognition_created(recognition_data):

        recognition = recognition_data[0]
        executor.submit(process_recognition, recognition)

    def create_connection(token):
        try:
            sio.connect(url=f"https://{SERVER_IP}/?token={token}", socketio_path="/bt/api/socket.io")
            sio.wait()  # This will block and allow socket.io to listen for events
        except KeyboardInterrupt:
            sio.disconnect()

    socket_thread = threading.Thread(target=create_connection, args=(token,))
    socket_thread.start()
    socket_thread.join()
    


def main():
    api_token = login()
    create_socket(api_token)

if __name__ == "__main__":
    main()