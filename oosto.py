import requests
import socketio
import threading
import os
from dotenv import load_dotenv
import pyodbc
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue

load_dotenv()


DB_SERVER = os.getenv("DB_SERVER")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


DETECTION_MISSED = 0
CREATED_GUESTS = 0


conn_str = (
    'DRIVER={ODBC Driver 18 for SQL Server};'
    f'SERVER={DB_SERVER};'
    f'DATABASE={DB_NAME};'
    f'UID={DB_USER};'
    f'PWD={DB_PASSWORD};'
    'TrustServerCertificate=yes;'
)

connection_pool = queue.Queue(maxsize=20)
for _ in range(20):
    connection_pool.put(pyodbc.connect(conn_str))


SERVER_IP = os.getenv("SERVER_IP")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
BASE_API_URL = f"https://{SERVER_IP}/bt/api"
HEADERS = {
        'accept': "application/json",
        'content-type': "application/json"
    }

executor = ThreadPoolExecutor(max_workers=25)

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

        conn = connection_pool.get()

        try:
            cursor = conn.cursor()
            query = """
                    MERGE INTO entrance_recognitions AS target
                    USING (SELECT ? AS subject_id, ? AS time_entered) AS source
                    ON target.subject_id = source.subject_id
                    WHEN NOT MATCHED THEN 
                        INSERT (subject_id, time_entered) VALUES (source.subject_id, source.time_entered);
                    """
            cursor.execute(query, (subject_id, time_recognized))
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"Database error: {e}")
        finally:
            connection_pool.put(conn)



def create_socket(token):


    sio = socketio.Client(reconnection=True, ssl_verify=False)

    @sio.on('connect')
    def connect():
        print("connected to socket")

    @sio.on('disconnect')
    def disconnect():
        print("Disconnected from socket. Closing database connections...")

        # Close all database connections in the pool
        while not connection_pool.empty():
            conn = connection_pool.get()
            conn.close()
        
        print("All database connections closed.")

    
    @sio.on('connect_error')
    def connect_error(data):
        print("The connection failed!")

    def find_closest_match(matches):
        return max([match['score'] for match in matches])

    @sio.on('track:created')
    def track_created(track_data):
        global DETECTION_MISSED
        global CREATED_GUESTS
        
        imageQualityThreshold = 80
        closestMatchScoreThreshold = .45
        guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

        track = track_data[0]
        # print(track)
        closest_match_score = 0 if not track['closeMatches'] else find_closest_match(track['closeMatches'])
        if closest_match_score <= closestMatchScoreThreshold:
            if track["landmarkScore"] >= imageQualityThreshold:
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
                print("added unknown person to guest group!")
                CREATED_GUESTS += 1
            else:
                DETECTION_MISSED += 1 # missed that we believe are unknown

        print(f"Created Guests = {CREATED_GUESTS}, Guests miss hits = {DETECTION_MISSED}")

    @sio.on('recognition:created')
    def recognition_created(recognition_data):

        recognition = recognition_data[0]
        executor.submit(process_recognition, recognition)

    def create_connection(token):
        try:
            sio.connect(url=f"https://{SERVER_IP}/?token={token}", socketio_path="/bt/api/socket.io")
            sio.wait()
        except Exception as e:
            print(f"Socket connection error: {e}")
            sio.disconnect()
    
    thread = threading.Thread(target=create_connection(token), daemon=True)
    thread.start()




if __name__ == '__main__':
    api_token = login()
    create_socket(api_token)
