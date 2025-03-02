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

    pool = await aioodbc.create_pool(dsn=conn_str, minsize=1, maxsize=10)


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
            return token

async def process_track(track):
    imageQualityThreshold = 80
    closestMatchScoreThreshold = .45
    guest_group_id = "ee87c48a-146c-4a0d-820a-df4c0cacb41d"

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

        async with aiohttp.ClientSession() as session:
            async with session.post(url=f"{BASE_API_URL}/subjects/from-track", json=body_request, headers=HEADERS, ssl=False) as response:
                if response.status == 201:
                    response_json = await response.json()
                    log_message(f"Added unknown {response_json["id"]} to Guest Group. Image quality score: {track['landmarkScore']}, closest match score: {closest_match_score} at {track['frameTimeStamp']}")


    else:
        track_id = track['id']
        collate_id = track["collateId"]
        frameQualityScore = track["landmarkScore"]
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    query = """
                        MERGE INTO tracks_missed AS target
                        USING (SELECT ? AS track_id, ? AS collate_id, ? AS frameQualityScore, ? AS closeMatchScore) AS source
                        ON target.track_id = source.track_id
                        WHEN NOT MATCHED THEN
                            INSERT (track_id, collate_id, frameQualityScore, closeMatchScore)
                            VALUES (source.track_id, source.collate_id, source.frameQualityScore, source.closeMatchScore);
                        """
                    await cursor.execute(query, (track_id, collate_id, frameQualityScore , closest_match_score))
                    
                    if cursor.rowcount > 0:
                        log_message(f"Dismissed track {track_id}, quality score: {frameQualityScore}, closest match score: {closest_match_score}, at {track['landmarkScore']}")
                    await conn.commit()
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
                            MERGE INTO entrance_recognitions AS target
                            USING (SELECT ? AS subject_id, ? AS time_entered) AS source
                            ON target.subject_id = source.subject_id
                            WHEN NOT MATCHED THEN 
                                INSERT (subject_id, time_entered) VALUES (source.subject_id, source.time_entered);
                            """
                    await cursor.execute(query, (subject_id, time_recognized))
                    
                    if cursor.rowcount > 0:
                        log_message(f"processed subject recognition {recognition["subject"]["name"]}, id: {subject_id} at {time_recognized}")
                    await conn.commit()
                except Exception as e:
                    log_message(f"Database error: {e}")




sio = socketio.AsyncClient(reconnection=True, ssl_verify=False)

@sio.on('connect')
async def connect():
    log_message("connected to socket")

@sio.on('disconnect')
async def disconnect():
    log_message("Disconnected from socket. Closing database connections...")
    pool.close()
    await pool.wait_closed()
    log_message("All database connections closed")

@sio.on('connect_error')
def connect_error(data):
    log_message("The connection failed!")

def find_closest_match(matches):
    return max([match['score'] for match in matches])

@sio.on('track:created')
async def track_created(track_data):
    track = track_data[0]
    await process_track(track)
    
    

@sio.on('recognition:created')
async def recognition_created(recognition_data):
    recognition = recognition_data[0]
    await process_recognition(recognition)

async def create_socket(token):
    try: 
        await sio.connect(url=f"https://{SERVER_IP}/?token={token}", socketio_path="/bt/api/socket.io")
        await sio.wait()
    except Exception as e:
        log_message(str(e))
        await sio.disconnect()


async def main():
    try:
        await create_db_pool()
        api_token =  await login()
        await create_socket(api_token)
    except KeyboardInterrupt:
        await disconnect()

if __name__ == "__main__":
    asyncio.run(main())
