# Repository Guidelines

## Project Structure & Module Organization

Application code lives in `src/tgsync/`. `main.py` is the long-running entry
point; `core/` contains Telegram synchronization, downloads, and media-linking
workflows; `db/` contains SQLAlchemy models and session setup; and `extras/`
contains optional integrations such as file bots. Runtime configuration starts
from `appdata/config.example.json`; local `appdata/`, `media/`, `incomplete/`,
and `postgres/data/` contents are runtime data and should not be committed.

## Build, Test, and Development Commands

Use the container workflow for normal development:

```sh
podman compose up -d postgres       # start the database
podman compose run --rm tgsync      # interactively create a Telegram session
podman compose up -d --build        # build and run the synchronizer
podman compose logs -f tgsync       # follow service logs
```

Copy `appdata/config.example.json` to `appdata/config.json` and set Telegram
credentials before running. For local execution, install dependencies with
`python -m pip install -r requirements.txt`, then run
`APPDATA="$PWD/appdata" PYTHONPATH=src python -m tgsync.main --setup`.
The `--setup` mode performs login/session setup.

## Coding Style & Naming Conventions

Target Python 3.14+ and follow the existing style: four-space indentation,
single-quoted strings, `snake_case` functions and variables, and `PascalCase`
SQLAlchemy entity classes. Keep modules focused on one workflow and place new
sync logic under `core/` or persistence changes under `db/`. No formatter or
linter is configured; avoid unrelated formatting churn and match nearby code.
