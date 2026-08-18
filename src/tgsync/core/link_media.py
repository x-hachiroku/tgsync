import re
import os
from datetime import timezone, timedelta
from mimetypes import guess_extension

from tgsync.config import config
from tgsync.logger import logger
from tgsync.db.session import session_generator
from tgsync.db.entities import MessageEntity, PhotoEntity, DocumentEntity


def make_safe_filename(name):
    invalit_table = {
        '/': '／', '\\': '＼', '?': '？', '!': '！', '"': "'",
        '<': '＜', '>': '＞', '|': '｜', ':': '：', '*': '＊',
    }
    invalid_chars = ''.join(invalit_table.keys())
    invalid_pattern = re.compile(f'[{re.escape(invalid_chars)}]')

    name = invalid_pattern.sub(lambda m: invalit_table[m.group(0)], name)

    name = name.strip(' .')

    reserved = {
        'CON', 'PRN', 'AUX', 'NUL',
        *(f'COM{i}' for i in range(1, 10)),
        *(f'LPT{i}' for i in range(1, 10)),
    }
    if name.upper().split('.')[0] in reserved:
        name = f'_{name}'

    encoded = name.encode('utf-8')
    if len(encoded) > 250:
        encoded = encoded[:230] + encoded[-20:]
    safe_name = encoded.decode('utf-8', errors='ignore')

    return safe_name


def get_channel_dir(chat_id, channel_name, channel_dirs):
    if chat_id not in channel_dirs:
        media_dir = config.download.media
        channel_id = str(chat_id)
        existing_dirs = sorted(
            path for path in media_dir.iterdir()
            if path.is_dir() and (path.name == channel_id or path.name.startswith(f'{channel_id} - '))
        ) if media_dir.exists() else []

        if existing_dirs:
            channel_dirs[chat_id] = existing_dirs[0]
        else:
            channel_dir_name = channel_id
            if channel_name is not None:
                channel_dir_name = make_safe_filename(f'{channel_id} - {channel_name}')
            channel_dirs[chat_id] = media_dir / channel_dir_name
            channel_dirs[chat_id].mkdir(parents=True, exist_ok=True)

    return channel_dirs[chat_id]


def get_shard_dir(message_date, sharding):
    if sharding is None:
        return None

    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=timezone.utc)
    local_date = message_date.astimezone().date()

    if sharding == 'month':
        local_date = local_date.replace(day=1)
    elif sharding == 'week':
        local_date -= timedelta(days=local_date.weekday())

    return local_date.strftime('%Y%m%d')


def get_media_dir(msg, channel_names, channel_dirs):
    chat_config = config.tg.chats.get(str(msg.chat_id))
    if chat_config is None:
        return get_channel_dir(msg.chat_id, None, channel_dirs)

    channel_name = channel_names.get(msg.chat_id, str(msg.chat_id))
    chat_dir = get_channel_dir(msg.chat_id, channel_name, channel_dirs)
    shard_dir = get_shard_dir(msg.date, chat_config.sharding)
    if shard_dir is None:
        return chat_dir

    media_dir = chat_dir / shard_dir
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir


def link_media(chats):
    channel_names = {int(chat_id): name for name, chat_id in chats.items()}
    channel_dirs = {}

    with session_generator() as session:
        candidates = (
            session.query(
                MessageEntity,
                PhotoEntity.id.label('photo_id'),
            )
            .join(PhotoEntity, MessageEntity.photo_id == PhotoEntity.id)
            .filter(
                MessageEntity.linked == False,
                PhotoEntity.saved == True
            )
        ).all()

        for msg, photo_id in candidates:
            chat_dir = get_media_dir(msg, channel_names, channel_dirs)

            dst = chat_dir / f'{msg.id:010d}_{photo_id}.jpg'

            logger.debug(f'Linking {photo_id} to {dst}')
            if os.path.exists(config.download.media / 'photos-by-id' / f'{photo_id}.jpg'):
                if not os.path.exists(dst):
                    os.link(config.download.media / 'photos-by-id' / f'{photo_id}.jpg', dst)
                else:
                    logger.warning(f'File {dst} already exists, skipping...')
            else:
                logger.warning(f'Previous saved photo {photo_id} is removed, skipping {msg.chat_id}/{msg.id}')

            msg.linked = True

    with session_generator() as session:
        candidates = (
            session.query(
                MessageEntity,
                DocumentEntity.id.label('document_id'),
                DocumentEntity.name.label('document_name'),
                DocumentEntity.type.label('document_type')
            )
            .join(DocumentEntity, MessageEntity.document_id == DocumentEntity.id)
            .filter(
                MessageEntity.linked == False,
                DocumentEntity.saved == True
            )
        ).all()

        for msg, document_id, document_name, document_type in candidates:
            chat_dir = get_media_dir(msg, channel_names, channel_dirs)

            ext = guess_extension(document_type)
            if ext is None:
                ext = '.bin'
            src = config.download.media / 'documents-by-id' / f'{document_id}{ext}'

            filename = f'{msg.id:010d}'
            if document_name:
                filename += f' {document_name}'
            else:
                filename += ext
            filename = make_safe_filename(filename)
            dst = chat_dir / filename

            logger.debug(f'Linking {src} to {dst}')
            if os.path.exists(src):
                if not os.path.exists(dst):
                    os.link(src, dst)
                else:
                    logger.warning(f'File {dst} already exists, skipping...')
            else:
                logger.warning(f'Previous saved document {document_id} is removed, skipping {msg.chat_id}/{msg.id}')

            msg.linked = True


if __name__ == '__main__':
    import json

    from tgsync.config import appdata

    with open(appdata / 'chats.json', 'r', encoding='utf-8') as f:
        link_media(json.load(f))
