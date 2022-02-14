#!/usr/bin/env python3
import json
import toml
import asyncio
import aiohttp
import aioredis
import websockets

DERPI_WS_URL = 'wss://derpibooru.org/socket/websocket?vsn=2.0.0'
JOIN_EVENT = [0, 0, 'firehose', 'phx_join', {}]
HEARTBEAT_EVENT = [0, 0, 'phoenix', 'heartbeat', {}]

pending_images = {}

with open('boorumon.toml', 'r') as fp:
    config = toml.load(fp)

PROXY = config['proxy']

# Save an image file and metadata for later, in case it gets deleted.
async def cache_image(image, session):
    async with session.get(image['representations']['full'], proxy=PROXY) as response:
        content = await response.read()

    if response.status != 200:
        print('Warning: Failed to get image ' + image['representations']['full'])
        return

    with open('cache/' + str(image['id']) + '.' + image['format'], 'wb') as fp:
        fp.write(content)

    with open('cache/' + str(image['id']) + '.json', 'w') as fp:
        json.dump(image, fp)

# Send the Phoenix heartbeat event every 30 seconds.
async def heartbeat(ws):
    await ws.send(json.dumps(HEARTBEAT_EVENT))
    await asyncio.sleep(30)
    asyncio.get_event_loop().create_task(heartbeat(ws))

async def derpimon(session):
    redis = aioredis.from_url('redis://localhost/')

    async with websockets.connect(DERPI_WS_URL) as ws:
        await ws.send(json.dumps(JOIN_EVENT))
        await heartbeat(ws)

        async for message in ws:
            joinRef, ref, topic, event, payload = json.loads(message)
            if event == 'image:create':
                pending_images[payload['image']['id']] = payload['image']
                await redis.publish('derpimon', f"https://derpibooru.org/images/{payload['image']['id']}")
                print(payload)
            elif event == 'image:process':
                image_id = payload['image_id']
                if image_id in pending_images:
                    await cache_image(pending_images[image_id], session)
                    del pending_images[image_id]
async def main():
    session = aiohttp.ClientSession()
    await derpimon(session)

asyncio.run(main())
