import os
import asyncio
import argparse

from tgsync.config import appdata, config
from tgsync.logger import logger
from tgsync.core.get_client import get_client
from tgsync.core.list_chats import list_chats
from tgsync.core.sync_chat import sync_chat
from tgsync.core.save_media import save_all
from tgsync.core.link_media import link_media

from tgsync.db.session import engine
from tgsync.db.entities import Base


async def process(client, chat_id):
    logger.info(f'Processing chat {chat_id}')

    min_id, max_id = 0, 0
    if 'range' in config['tg']['chats'][chat_id]:
        min_id, max_id = config['tg']['chats'][chat_id]['range']

    logger.info('Syncing messages...')
    await sync_chat(client, int(chat_id), min_id, max_id)

    if (not 'media' in config['tg']['chats'][chat_id]) or (config['tg']['chats'][chat_id]['media']):
        logger.info(f'Saving media...')
        await save_all(client, int(chat_id), True)
        await save_all(client, int(chat_id), False)

    logger.info('Linking media to chat dir...')
    link_media()

    logger.info(f'Chat {chat_id} completed.')


async def main():
    Base.metadata.create_all(engine)

    parser = argparse.ArgumentParser(description='Telegram Sync Tool')
    parser.add_argument('-s', '--setup', action='store_true', help='Run setup')
    args = parser.parse_args()

    setup = not os.path.exists(appdata / config['tg']['session']) or args.setup
    if setup:
        logger.warning('No session file found. Please run the container in interactive mode to login.')

    client = await get_client()

    if setup:
        await list_chats(client)
        logger.info('You can now restart the container in detached mode.')
        return

    while True:
        for chat_id in config['tg']['chats']:
            await process(client, chat_id)

        logger.info('All chats completed.')
        logger.info('Waiting for 300 seconds before the next run...')
        await asyncio.sleep(300)


if __name__ == '__main__':
    asyncio.run(main())
