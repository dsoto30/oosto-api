import aiohttp
import socketio
from dotenv import load_dotenv
from datetime import datetime
import logging
import asyncio
import aioodbc

load_dotenv()

"""
COPY ENVIRONMENT VARIABLES FROM .env FILE TO THIS SCRIPT. HARDCODED VALUES FOR NOW
"""

log_file = "oosto_logs.log"
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", filemode="a")

def log_message(message):
    logging.info(message)
    print(message)

pool = None

async def create_db_pool():
    global pool
    conn_str = (
    'DRIVER={ODBC Driver 18 for SQL Server};'
    f'SERVER={DB_SERVER};'
    f'DATABASE={DB_NAME};'
    f'UID={DB_USER};'
    f'PWD={DB_PASSWORD};'
    'TrustServerCertificate=yes;')

    pool = await aioodbc.create_pool(dsn=conn_str)


async def close_db_pool():
    global pool
    if pool:
        pool.close()
        await pool.wait_closed()
        log_message("All database connections closed")

BASE_API_URL = f"https://{SERVER_IP}/bt/api"
HEADERS = {
        'accept': "application/json",
        'content-type': "application/json"
    }


async def login():

    login_url = f"{BASE_API_URL}/login"
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url=login_url, ssl=False, headers=HEADERS, json={'username': USERNAME, 'password': PASSWORD}) as response:
            response.raise_for_status()
            json_response = await response.json()
            token = json_response["token"]
            HEADERS["authorization"] = f"Bearer {token}"
            log_message(f"Got API TOKEN")
            return token

def find_closest_match(matches):
    return max([match['score'] for match in matches])

def construct_images(track):
    res = []
    for i, image in enumerate(track['images']):
        obj = {"isPrimary": i==2, "landmarkScore": track['landmarkScore'], "objectType": track['objectType'], "url": image['url'], "track": {
                    "camera": track['camera']['id'], "frameTimeStamp": track['frameTimeStamp'], "id": track['id']
                }}
        res.append(obj)
    return res

async def process_track(track):
    imageQualityThreshold = 75 # OOSTO RECOMMENDS 80 WE MIGHT NEED TO FIX CAMERA POSITIONING AT ENTRANCES TO CAPTURE GOOD SHOTS OF GUESTS
    closestMatchScoreThreshold = .45
    guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

    gender = "male" if track["metadata"]["attributes"]['gender'][0] == 1 else "female"

    closest_match_score = 0 if not track['closeMatches'] else find_closest_match(track['closeMatches'])
    if closest_match_score <= closestMatchScoreThreshold and track["landmarkScore"] >= imageQualityThreshold:
        body_request = {
            "name": "John Doe" if gender == "male" else "Mary Jane",
            "description": "",
            "groups": [guest_group_id],
            "sendToHq": False,
            "searchBackwards": [{
                "searchBackwardsThreshold": .6,
                "objectType": track["objectType"]
            }],
            "images": construct_images(track)     
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url=f"{BASE_API_URL}/subjects/from-track", json=body_request, headers=HEADERS, ssl=False) as response:
                if response.status == 201:
                    response_json = await response.json()
                    log_message(f"Added {response_json['name']}, id: {response_json["id"]} to Guest Group. Image quality score: {track['landmarkScore']}, closest match score: {closest_match_score} at {track['frameTimeStamp']}")
    else:
        track_id = track['id']
        collate_id = track["collateId"]
        frameQualityScore = track["landmarkScore"]
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    query = """
                            INSERT INTO tracks_missed (track_id, collate_id, frameQualityScore, closeMatchScore, time_missed)
                            SELECT ?, ?, ?, ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM tracks_missed WHERE track_id = ?
                            );
                            """
                    await cursor.execute(query, (track_id, collate_id, frameQualityScore , closest_match_score, track['frameTimeStamp'], track_id))
                    await conn.commit()
                    if cursor.rowcount > 0:
                        log_message(f"Dismissed track {track_id}, quality score: {frameQualityScore}, closest match score: {closest_match_score}, at {track['frameTimeStamp']}")
                except Exception as e:
                    log_message(f"Database error: {e}")

async def process_recognition(recognition):
    guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

    if recognition['subject']['groups'][0]['id'] == guest_group_id:
        subject_id = recognition['subject']['id']
        time_recognized = datetime.fromisoformat(recognition['frameTimeStamp'])

        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    query = """
                            INSERT INTO entrance_recognitions (subject_id, time_entered)
                            SELECT ?, ?
                            WHERE NOT EXISTS (
                                SELECT 1 FROM entrance_recognitions WHERE subject_id = ?
                            );
                            """
                    await cursor.execute(query, (subject_id, time_recognized, subject_id))
                    await conn.commit()
                    if cursor.rowcount > 0:
                        log_message(f"processed unique subject entrance recognition {recognition["subject"]["name"]}, id: {subject_id} at {time_recognized}")
                except Exception as e:
                    log_message(f"Database error: {e}")




sio = socketio.AsyncClient(reconnection=True, reconnection_delay=1, ssl_verify=False)

@sio.on('connect')
def connect():
    log_message("connected to socket")

@sio.on('disconnect')
def disconnect(reason):
    if reason == sio.reason.CLIENT_DISCONNECT:
        log_message('the client disconnected')
    elif reason == sio.reason.SERVER_DISCONNECT:
        log_message('the server disconnected the client')
    else:
        log_message('disconnect reason:', reason)


@sio.on('connect_error')
def connect_error(data):
    log_message(f"There was an error connecting: {data}")

@sio.on('track:created')
async def track_created(track_data):
    track = track_data[0]
    await process_track(track)
    
    

@sio.on('recognition:created')
async def recognition_created(recognition_data):
    recognition = recognition_data[0]
    await process_recognition(recognition)

async def create_socket(token):
    await sio.connect(url=f"https://{SERVER_IP}/?token={token}", socketio_path="/bt/api/socket.io")
    await sio.wait()


async def main():
    try:
        await create_db_pool()
        api_token =  await login()
        await create_socket(api_token)
    except asyncio.CancelledError:
        log_message("async task cancelled")
    finally:
        await close_db_pool()
        await sio.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
