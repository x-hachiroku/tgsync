from telethon import TelegramClient
from urllib.parse import urlparse

from tgsync.config import appdata, config
from tgsync.logger import logger


async def get_client():
    proxy_url = config['tg'].get('proxy')
    if proxy_url:
        components = urlparse(proxy_url)
        proxy = {
            'proxy_type': components.scheme,
            'addr': components.hostname,
            'port': components.port,
            'username': components.username,
            'password': components.password,
            'rdns': False,
        }
        if proxy['proxy_type'][-1] == 'h':
            proxy['proxy_type'] = proxy['proxy_type'][:-1]
            proxy['rdns'] = True
    else:
        proxy = None

    client = TelegramClient(
        appdata / config['tg']['session'],
        config['tg']['api_id'],
        config['tg']['api_hash'],
        proxy=proxy,
    )
    await client.start()
    logger.info('Logging successful.')
    return client


if __name__ == '__main__':
    import asyncio
    asyncio.run(get_client())
