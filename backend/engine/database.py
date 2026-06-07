import psycopg2
from pymongo import MongoClient
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger(__name__)

# --- Configuration ---
MONGO_URI = "mongodb://mongodb:27017/"
PG_CONN_STR = "dbname=spic user=user password=pass host=postgres"

class DBManager:
    def __init__(self):
        logger.info("Initializing database connections...")
        self.mongo = MongoClient(MONGO_URI)["spic"]
        self.pg = psycopg2.connect(PG_CONN_STR)
        self.pg.autocommit = True
        self._init_pg_schema()

    def _init_pg_schema(self):
        with self.pg.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (user_id UUID PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(user_id),
                    title TEXT,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS thread_memory (
                    thread_id UUID REFERENCES threads(thread_id),
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (thread_id, key)
                );
                CREATE TABLE IF NOT EXISTS shared_memory (
                    user_id UUID REFERENCES users(user_id),
                    key TEXT,
                    value TEXT,
                    PRIMARY KEY (user_id, key)
                );
            """)