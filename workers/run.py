# SPDX-License-Identifier: MIT
"""Run with PYTHONPATH=apps/api python -m workers.run."""
from redis import Redis
from rq import Queue, Worker

from app.config import settings


def main():
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(settings.queue_name, connection=connection)
    Worker([queue], connection=connection).work(with_scheduler=True)


if __name__ == "__main__":
    main()
