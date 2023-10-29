#!/usr/bin/env python3
import os
import sys
import json
import toml
import asyncio
import aiohttp
import aioredis
import websockets

from urllib.parse import urljoin
from collections import namedtuple

CACHE_DIR = 'cache/'
JOIN_EVENT      = [0, 0, 'firehose', 'phx_join', {}]
HEARTBEAT_EVENT = [0, 0, 'phoenix', 'heartbeat', {}]

# ws = WebSocket URL, cdn = prefix prepended to image view URLs, root = prefix prepended to image ID
WsEndpoint = namedtuple('WsEndpoint', ('name', 'ws', 'cdn', 'root'))

WEBSOCKET_ENDPOINTS = [
    WsEndpoint(
        name='PonerPics',
        ws='wss://ponerpics.org/socket/websocket?vsn=2.0.0',
        cdn='https://ponerpics.org/',
        root='https://ponerpics.org/'
    ),
    WsEndpoint(
        name='Derpibooru',
        ws='wss://derpibooru.org/socket/websocket?vsn=2.0.0',
        cdn='',
        root='https://derpibooru.org/'
    )
]

pending_images = {}

with open('boorumon.toml', 'r') as fp:
    config = toml.load(fp)

# Enable verbose mode
if config['debug']:
    import logging
    logger = logging.getLogger('websockets')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

# Make cache directory if not available
if not os.path.exists(CACHE_DIR):
    os.mkdir(CACHE_DIR)

PROXY = config['proxy']

if PROXY and ('http_proxy' not in os.environ or 'https_proxy' not in os.environ):
    print(f"You should probably set http_proxy and https_proxy environment variables to {PROXY}...")
    sys.exit(1)

async def cache_image(image: dict, session: aiohttp.ClientSession, wsurl: WsEndpoint):
    ''' Save an image file and metadata for later, in case it gets deleted. '''
    response = await session.get(wsurl.cdn + image['representations']['full'], proxy=PROXY)
    content = await response.read()

    if response.status != 200:
        print(wsurl.name + ': Warning: Failed to get image ' + image['representations']['full'])
        return


    if not os.path.exists(os.path.join(CACHE_DIR, wsurl.name.lower())):
        os.mkdir(os.path.join(CACHE_DIR, wsurl.name.lower()))

    # save actual image
    with open(os.path.join(CACHE_DIR, wsurl.name.lower(), str(image['id']) + '.' + image['format']), 'wb') as fp:
        fp.write(content)

    # save API response
    with open(os.path.join(CACHE_DIR, wsurl.name.lower(), str(image['id']) + '.json'), 'w') as fp:
        json.dump(image, fp)

async def heartbeat(ws):
    ''' Send the Phoenix heartbeat event every 30 seconds. '''
    await ws.send(json.dumps(HEARTBEAT_EVENT))
    await asyncio.sleep(30)
    asyncio.get_event_loop().create_task(heartbeat(ws))

async def monbooru(session: aiohttp.ClientSession, wsurl: WsEndpoint):
    ''' Monitor image boorus for new uploads '''
    redis = aioredis.from_url('redis://localhost/')

    while True:
        async with websockets.connect(wsurl.ws) as ws:
            await ws.send(json.dumps(JOIN_EVENT))
            await heartbeat(ws)
    
            print(wsurl.name + ': Connected.')
    
            async for message in ws:
                joinRef, ref, topic, event, payload = json.loads(message)
                if event == 'image:create':
                    pending_images[payload['image']['id']] = payload['image']
                    await redis.publish('boorumon', urljoin(wsurl.root, '/images/' + str(payload['image']['id'])))
                    print(wsurl.name + ': ' + str(payload))
                elif event == 'image:process':
                    image_id = payload['image_id']
                    if image_id in pending_images:
                        await cache_image(pending_images[image_id], session, wsurl)
                        del pending_images[image_id]
        print(wsurl.name + ': Disconnected.')
        await asyncio.sleep(10)

async def main():
    session = aiohttp.ClientSession()
    await asyncio.gather(*[
        monbooru(session, endpoint) for endpoint in WEBSOCKET_ENDPOINTS
    ])

asyncio.run(main())
