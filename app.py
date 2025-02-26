import requests
import socketio
import threading
import os
from dotenv import load_dotenv

load_dotenv()


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
        print(f"processing {len(track_data)} tracks.")
        track = track_data[0]
        closest_match_score = 0 if track['closeMatches'] is None else find_closest_match(track['closeMatches'])

        

        new_track = {"frameId": track["id"],"time_recognized": track["frameTimeStamp"], "imageQualityScore": track["landmarkScore"], "cameraTitle": track['camera']['title'], "cameraGroupId": track['camera']['cameraGroupId'], "closestScore": closest_match_score}
        print(new_track)

    @sio.on('recognition:created')
    def recognition_created(recognition_data):

        """
        Give group_id of camera of recognition check if it's from entrance group If not ignore.

        check if subject_id already exists in table if not insert recognition information

        SQL Job to run at 6am daily and COUNT * FROM recognitions table (should be all unique) prune table after

        Most stuff should be done by the UI or API calls
        """
        recognition = recognition_data[0]
        response = {"recognition_id": recognition["id"], "location_recognized": recognition["camera"]["title"], "relatedTrackId": recognition["relatedTrackId"], "subjectScore": recognition["subjectScore"], "matches": recognition["closeMatches"], "name": recognition["subject"]["name"]}

        print(f"{response["name"]} was recognized from {response['location_recognized']}, with a score of {response['subjectScore']} ")


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
