import requests
import socketio
import logging
import threading
import os
from dotenv import load_dotenv, dotenv_values

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

def get_groups():
    groups_url = f"{BASE_API_URL}/groups"
    response = requests.get(groups_url, headers=HEADERS, verify=False)
    return response.json()

def create_socket(token):

    #sio = socketio.Client(logger=True, engineio_logger=True, reconnection=True, ssl_verify=False) logging purposes

    sio = socketio.Client(reconnection=True, ssl_verify=False)

    @sio.on('connect')
    def connect():
        print("connected to socket")
    
    @sio.on('disconnect')
    def disconnect(reason):
        if reason == sio.reason.CLIENT_DISCONNECT:
            print('the client disconnected')
        elif reason == sio.reason.SERVER_DISCONNECT:
            print('the server disconnected the client')
        else:
            print('disconnect reason:', reason)
    
    @sio.on('connect_error')
    def connect_error(data):
        print("The connection failed!")
    
    @sio.on('track:created')
    def track_created(data):
        #print("Track created: ", data)
        data = data[0]
        response = {"track_id": data["id"], "location_tracked": data["camera"]["title"], "subject": data["subject"]}
        print(response)


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
    #logging.basicConfig(level=logging.DEBUG) IF YOU WANT TO LOG
    api_token = login()
    create_socket(api_token)
