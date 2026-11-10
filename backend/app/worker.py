"""Background worker: `python -m app.worker`. Several can run side by side to process more files at once."""
import logging

from rq import Queue, Worker

from .db import init_db, reset_engine
from .queue import QUEUE_NAME, redis_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    init_db()
    reset_engine()  # each forked job opens its own DB connections (never share sockets across fork)
    conn = redis_conn()
    Worker([Queue(QUEUE_NAME, connection=conn)], connection=conn).work(with_scheduler=False)
