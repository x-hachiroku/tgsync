# Telegram Sync

Synchronize Telegram messages and media to local storage.


## Quick Start

1. Clone this repo, configure `docker-compose.yaml`.
    * `/appdata`: Configuration files, session data, and logs

2. Start the container in interactive mode to login:
   ```sh
   docker compose up -d postgres
   # Wait for a few seconds for postgres to start
   docker compose run --rm tgsync
   ```

3. Configure the application:
   - Copy `appdata/config.example.yaml` to `appdata/config.yaml` and make your changes.

4. Start services:
   ```sh
   docker compose up -d
   ```


## Media Storage Structure

The application implements an efficient storage system for media files:

1. Original media files are stored in corresponding repos, `/media/{photo,documents}-by-id/`, with name `<media_id>.ext`
2. Hard links are created to `/media/<chat_id> - <channel_name>/<shard_start_date>/` with name `<msg_id>_<photo_id>.ext` or
  `<msg_id> <original_filename>.ext` for any message containing that media. The first existing directory matching the
  channel ID is reused when a channel name changes.

  - Shard dir marks the start date of a shard, calculated in local time.

This ensures that duplicate media files are not downloaded multiple times, and no additional space is used while each
chat maintains its own organized media directory.


#### Managing Media Files

To delete a specific media file from repo and all chat dirs:
```sh
find /media -samefile "<awful_media>" -delete
```

To clean up orphaned media files (those no longer referenced by any chat) in repos:
```sh
find /media/{photo,documents}-by-id/ -links 1 -delete
```

**NOTE**: Once a media file is deleted from the repo, it will not be re-downloaded even when referenced by new messages.

For more information about hard links, see [Wikipedia](https://en.wikipedia.org/wiki/Hard_link).
