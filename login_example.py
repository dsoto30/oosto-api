import requests
import socketio
import json
import threading

domain = "https://172.20.2.54"
base_url = "/bt/api"
login_url = domain + base_url + "/login"
headers = {
    'accept': "application/json",
    'content-type': "application/json"
}
headers_dumps = json.dumps(headers)
# add  verify=False this when running without certificate
response = requests.request("POST", login_url, headers=headers,
                            json={'username': 'Administrator', 'password': 'pa$$word!'}, verify=False)
# token = 'Bearer' + response.json()['token'] # token for rest requests
token = response.json()['token']
print(f'token: {token}')
querystring = {"offset": "0", "sortOrder": "desc", "limit": "10"}
headers = {'accept': 'application/json', 'authorization': 'Bearer ' + token}
response = requests.request("GET", f'{domain}{base_url}/roles', headers=headers, params=querystring, verify=False)
print(response.text)
sio = socketio.Client(ssl_verify=False, logger=True, reconnection=True, engineio_logger=True)


@sio.on("connect")
def connect():
    print('connection established')

@sio.on("track:created")
def onTrakCreated(data):
    print(data)

@sio.on("disconnect")
def disconnect():
    print('disconnected from server')


def connect_to_socket_and_wait(token):
    try:
        sio.connect(url=f'hhttps://172.20.2.54/?token={token}', socketio_path='/bt/api/socket.io')
        sio.wait()
    except:
        pass


# Socket Thread Runs as a Thread
socket_thread = threading.Thread(target=connect_to_socket_and_wait(token=token))
socket_thread.start()
# Main Thread Should be Running
while True:
    pass