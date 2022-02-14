#!/usr/bin/env python3

import os
import json
import toml
import asyncio
import aiohttp
import aioredis
import websockets

PONER_WS_URL    = 'wss://ponerpics.org/socket/websocket?vsn=2.0.0'
DERPI_WS_URL    = 'wss://derpibooru.org/socket/websocket?vsn=2.0.0'
JOIN_EVENT      = [0, 0, 'firehose', 'phx_join', {}]
HEARTBEAT_EVENT = [0, 0, 'phoenix', 'heartbeat', {}]

inDebugMode = False

# Enable verbose mode
if inDebugMode:
    import logging
    logger = logging.getLogger('websockets')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

pending_images = {}

with open('boorumon.toml', 'r') as fp:
    config = toml.load(fp)

# Make cache directory if not available
cachefp = './cache'
if (not os.path.exists(cachefp)):
    os.mkdir(cachefp)

PROXY = config['proxy']

async def cache_image(image: dict, session: aiohttp.ClientSession, wsurl: str):
    ''' Save an image file and metadata for later, in case it gets deleted. '''
    response = ''
    if (wsurl == PONER_WS_URL):
        response = await session.get(f"https://ponerpics.org/{image['representations']['full']}", proxy=PROXY)
    elif (wsurl == DERPI_WS_URL):
        response = await session.get(image['representations']['full'], proxy=PROXY)
    content = await response.read()

    if response.status != 200:
        print('Warning: Failed to get image ' + image['representations']['full'])
        return

    with open(f"cache/{image['id']}.{image['format']}", 'wb') as file:
        file.write(content)

    with open(f"cache/{image['id']}.json", 'w') as file:
        file.close()

async def heartbeat(ws: websockets.client.WebSocketClientProtocol):
    ''' Send the Phoenix heartbeat event every 30 seconds. '''
    await ws.send(json.dumps(HEARTBEAT_EVENT))
    await asyncio.sleep(30)
    asyncio.get_event_loop().create_task(heartbeat(ws))

async def monbooru(session: aiohttp.ClientSession, wsurl: str):
    ''' Monitor image boorus for new uploads '''
    redis = aioredis.from_url('redis://localhost/')

    async with websockets.connect(wsurl) as ws:
        await ws.send(json.dumps(JOIN_EVENT))
        await heartbeat(ws)

        async for message in ws:
            joinRef, ref, topic, event, payload = json.loads(message)
            if event == 'image:create':
                pending_images[payload['image']['id']] = payload['image']
                if (wsurl == DERPI_WS_URL):
                    await redis.publish('boorumon', f"https://derpibooru.org/images/{payload['image']['id']}")
                elif (wsurl == PONER_WS_URL):
                    await redis.publish('boorumon', f"https://ponerpics.org/images/{payload['image']['id']}")
                print(payload)
            elif event == 'image:process':
                image_id = payload['image_id']
                if image_id in pending_images:
                    await cache_image(pending_images[image_id], session, wsurl)
                    del pending_images[image_id]
async def main():
    session = aiohttp.ClientSession()
    await asyncio.gather(
        monbooru(session, DERPI_WS_URL),
        monbooru(session, PONER_WS_URL)
    )
asyncio.run(main())
