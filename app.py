import aiohttp
import asyncio
import socketio
import os 

async def login(username, password):
    connector = aiohttp.TCPConnector(ssl=False)  # Disable SSL verification if needed
    async with aiohttp.ClientSession(connector=connector) as session:
        payload = {'username': username, 'password': password}
        async with session.post(f"https://172.20.2.54/bt/api/login", json=payload) as response:
            if response.status != 200:
                print(f"Login failed: HTTP {response.status}")
                return

            data = await response.json()
            token = data.get('token')
            if token:
                print(f"Token: {token}")
                print("Login successful, connecting to socket...")
                await connect_to_socket(token)
            else:
                print("Login failed: No token received")

async def connect_to_socket(token):
    connector = aiohttp.TCPConnector(ssl=False)  # Disable SSL verification if needed
    http_session = aiohttp.ClientSession(connector=connector)

    sio = socketio.AsyncClient(http_session=http_session)
    

    @sio.event
    async def connect():
        print('Connected to socket')

    @sio.event
    async def disconnect():
        print('Disconnected from socket')

    try:
        await sio.connect(f'https://172.20.2.54/bt/api/socket.io/?token={token}')
        await sio.wait()
    except Exception as e:
        print(f"Socket connection failed: {e}")

async def main():

    username = os.environ.get('USERNAME')
    password = os.environ.get('PASSWORD')
    await login(username, password)

if __name__ == '__main__':
    asyncio.run(main())
