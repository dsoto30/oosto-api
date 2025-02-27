import requests
import socketio
import threading
import os
from dotenv import load_dotenv
import pyodbc
from datetime import datetime

load_dotenv()




DB_SERVER = os.getenv("DB_SERVER")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


conn_str = (
    'DRIVER={ODBC Driver 18 for SQL Server};'
    f'SERVER={DB_SERVER};'
    f'DATABASE={DB_NAME};'
    f'UID={DB_USER};'
    f'PWD={DB_PASSWORD};'
    'TrustServerCertificate=yes;'
)

conn = pyodbc.connect(conn_str)


SERVER_IP = os.getenv("SERVER_IP")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
BASE_API_URL = f"https://{SERVER_IP}/bt/api"
HEADERS = {
        'accept': "application/json",
        'content-type': "application/json"
    }

def login():

    login_url = f"{BASE_API_URL}/login"
    

    response = requests.post(login_url, headers=HEADERS, json={'username': USERNAME, 'password': PASSWORD}, verify=False)
    
    json_response = response.json()
    
    token = json_response["token"]
    HEADERS["authorization"] = f"Bearer {token}"
    return token


def create_socket(token):


    sio = socketio.Client(reconnection=True, ssl_verify=False)

    @sio.on('connect')
    def connect():
        print("connected to socket")

    @sio.on('disconnect')
    def disconnect():
        conn.close()

    
    @sio.on('connect_error')
    def connect_error(data):
        print("The connection failed!")

    def find_closest_match(matches):
        return max([match['score'] for match in matches])

    @sio.on('track:created')
    def track_created(track_data):
        """
        Check group_id of camera and check if from exit camera group

        check the closest matches array and check picture quality score

        if unknown create subject through OOSTO in guest group
        """
        
        imageQualityThreshold = 80
        closestMatchScoreThreshold = .45
        guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

        track = track_data[0]
        # print(track)

        if track["landmarkScore"] >= imageQualityThreshold:
            closest_match_score = 0 if not track['closeMatches'] else find_closest_match(track['closeMatches'])
            
            if closest_match_score <= closestMatchScoreThreshold:
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

                response = requests.post(f"{BASE_API_URL}/subjects/from-track", json=body_request, verify=False, headers=HEADERS)
                print("added unknown person to guest group!")




    @sio.on('recognition:created')
    def recognition_created(recognition_data):

        """
        Give group_id of camera of recognition check if it's from entrance group If not ignore.

        check if subject_id already exists in table if not insert recognition information also check if group_id matches guest group

        SQL Job to run at 6am daily and COUNT * FROM recognitions table (should be all unique) prune table after
        """
        recognition = recognition_data[0]
        guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

        if recognition['subject']['groups'][0]['id'] == guest_group_id:
            cursor = conn.cursor()

            subject_id = recognition['subject']['id']
            time_recognized = datetime.fromisoformat(recognition['frameTimeStamp'])

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

    def create_connection(token):
        try:
            sio.connect(url=f"https://{SERVER_IP}/?token={token}", socketio_path="/bt/api/socket.io")
            sio.wait()
        except Exception as e:
            print(e)
            sio.disconnect()
    
    thread = threading.Thread(target=create_connection(token))
    thread.start()
    thread.join()




if __name__ == '__main__':
    api_token = login()
    create_socket(api_token)
