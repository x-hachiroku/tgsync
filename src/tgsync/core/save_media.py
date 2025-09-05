import os
import shutil
import asyncio
import traceback
from time import time
from mimetypes import guess_extension
from tabulate import tabulate

from sqlalchemy import select, bindparam

from tgsync.config import config
from tgsync.logger import logger
from tgsync.core.get_client import get_client
from tgsync.db.session import session_generator
from tgsync.db.entities import MessageEntity, PhotoEntity, DocumentEntity


class ProgressSummary:
    def __init__(self):
        self.report_time = time()
        self.tasks = [{
            'chat_msg_id': None,
            'media_id': None,
            'name': None,
            'total': 0,
            'received': 0,
            'start_time': 0,
            'speed': 0,
        } for _ in range(config['download']['concurrent'])]

    def init_task(self, seq, msg):
        self.tasks[seq]['chat_msg_id'] = f'{msg.chat_id}/{msg.id}'
        if msg.photo:
            self.tasks[seq]['media_id'] = msg.photo.id
            return f'photo: {self.tasks[seq]["chat_msg_id"]} | {msg.photo.id}'
        else:
            self.tasks[seq]['media_id'] = msg.document.id
            self.tasks[seq]['name'] = msg.file.name
            self.tasks[seq]['total'] = msg.document.size
            self.tasks[seq]['speed'] = 0
            self.tasks[seq]['received'] = 0
            self.tasks[seq]['started'] = time()
            media_str = f'document: {self.tasks[seq]["chat_msg_id"]} | {msg.document.id} | {msg.file.name}'
            return media_str

    def make_progress_callback(self, seq):
        def progress_callback(received):
            self.tasks[seq]['received'] = received
            self.tasks[seq]['speed'] = received / (time() - self.tasks[seq]['started'])
            self.log_progress()
        return progress_callback

    def log_progress(self):
        def format_bytes(b):
            for unit in ['B', 'KiB', 'MiB', 'GiB']:
                if b < 1024:
                    return f'{b:.2f}{unit}'
                b /= 1024

        if time() - self.report_time < config['download']['summary_interval']:
            return
        self.report_time = time()

        task_table = []
        total_speed = 0
        for i, task in enumerate(self.tasks):
            if task['chat_msg_id'] is None:
                continue

            total_speed += task['speed']

            name = task['name']
            if name and len(name) > 32:
                name = name[:20] + '...' + name[-10:]

            task_table.append([
                f'#{i}',
                task['chat_msg_id'],
                task['media_id'],
                name,
                f'{format_bytes(task["received"])}/{format_bytes(task["total"])}',
                f'{100*task["received"] / task["total"]:.1f}%',
                f'{format_bytes(task["speed"])}/s',
            ])

        task_table.append(['', 'Total:'] + ['']*4 +  [f'{format_bytes(total_speed)}/s'])

        logger.info('\n'+tabulate(task_table))


async def download_with_timeout(client, msg, file, progress_callback, timeout):
    received = 0

    iter_download = client.iter_download(msg.media)
    with open(file, 'wb') as f:
        while True:
            try:
                chunk = await asyncio.wait_for(anext(iter_download), timeout)
                f.write(chunk)
                received += len(chunk)
                progress_callback(received)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError:
                logger.error(f'Timeout occurred while downloading {msg.chat_id}/{msg.id}.')
                raise


async def save_worker(seq, queue, progress_summary, client):
    logger.debug(f'Worker {seq} started')
    progress_callback = progress_summary.make_progress_callback(seq)

    while True:
        try:
            logger.debug(f'Worker {seq} fetching next message, queue size: {queue.qsize()}')
            msg = await queue.get()
            media_str = progress_summary.init_task(seq, msg)
            logger.info(f'Worker {seq} starting download {media_str}')

            if msg.photo:
                tempfile = config['download']['incomplete'] / 'photos-by-id' / f'{msg.photo.id}.jpg'
                file = config['download']['media'] / 'photos-by-id' / f'{msg.photo.id}.jpg'

                await asyncio.wait_for(
                    client.download_media(message=msg, file=tempfile),
                    timeout=config['download']['timeout']
                )

                shutil.move(tempfile, file)

                with session_generator() as session:
                    entity = session.get(PhotoEntity, msg.photo.id)
                    entity.saved = True

            elif msg.document:
                ext = guess_extension(msg.document.mime_type)
                if ext is None:
                    ext = '.bin'
                tempfile = config['download']['incomplete'] / 'documents-by-id' / f'{msg.document.id}{ext}'
                file = config['download']['media'] / 'documents-by-id' / f'{msg.document.id}{ext}'

                if not (msg.file.name and msg.file.name.endswith('apk')):
                    await download_with_timeout(client, msg, tempfile,
                                                progress_callback,
                                                config['download']['timeout'])

                    shutil.move(tempfile, file)

                with session_generator() as session:
                    entity = session.get(DocumentEntity, msg.document.id)
                    entity.saved = True

            else:
                raise ValueError('Message does not contain a photo or document')

            logger.info(f'Worker {seq} download finished {media_str}')

        except Exception:
            logger.error(f'Exception in worker {seq}: {traceback.format_exc()}')
            os.remove(tempfile)

        finally:
            progress_summary.tasks[seq]['name'] = None
            queue.task_done()


async def save_all(client, chat_id, photo):
    (config['download']['incomplete'] / 'photos-by-id').mkdir(parents=True, exist_ok=True)
    (config['download']['incomplete'] / 'documents-by-id').mkdir(parents=True, exist_ok=True)
    (config['download']['media'] / 'photos-by-id').mkdir(parents=True, exist_ok=True)
    (config['download']['media'] / 'documents-by-id').mkdir(parents=True, exist_ok=True)

    if photo:
        logger.info(f'Downloading photos from {chat_id}')
        target_id = MessageEntity.photo_id
        target_entity = PhotoEntity
        target_col = PhotoEntity.id
        saved_col = PhotoEntity.saved
        limit = config['tg']['message_limit']
    else:
        logger.info(f'Downloading documents from {chat_id}')
        target_id = MessageEntity.document_id
        target_entity = DocumentEntity
        target_col = DocumentEntity.id
        saved_col = DocumentEntity.saved
        limit = config['download']['concurrent']

    subq = (
        select(
            MessageEntity.id,
            target_id.label('media_id')
        )
        .join(target_entity, target_id == target_col)
        .where(
            MessageEntity.chat_id == chat_id,
            saved_col == False
        )
        .order_by(target_id, MessageEntity.id)
        .distinct(target_id)
        .subquery()
    )
    stmt = (
        select(subq.c.id, subq.c.media_id)
        .where(subq.c.id > bindparam('min_id'))
        .order_by(subq.c.id)
        .limit(limit)
    )

    queue = asyncio.Queue(maxsize=(limit//2))
    progress_summary = ProgressSummary()

    workers = [asyncio.create_task(save_worker(i, queue, progress_summary, client))
               for i in range(config['download']['concurrent'])]


    try:
        min_id = 0
        while True:
            with session_generator() as session:
                msg_ids = session.execute(stmt, {'min_id': min_id}).scalars().all()

            if not msg_ids:
                logger.info(f'All {"Photos" if photo else "Documents"} saved for {chat_id}')
                break

            msgs = await client.get_messages(
                chat_id,
                ids=msg_ids,
                limit=config['tg']['message_limit'],
            )

            for msg in msgs:
                await queue.put(msg)

            min_id = msg_ids[-1]

        await queue.join()

    except Exception:
        logger.error(traceback.format_exc())

    finally:
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


async def main():
    from sys import argv
    client = await get_client()

    await save_all(client, int(argv[1]), argv[2]=='photo')


if __name__ == '__main__':
    asyncio.run(main())
