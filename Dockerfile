FROM docker.io/library/python:3.14

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install the project and its dependencies from pyproject.toml.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install .

ENV PYTHONPATH="/app/src"

CMD ["python", "-m", "tgsync.main"]
