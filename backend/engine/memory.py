import uuid
import datetime
from psycopg2.extras import RealDictCursor

class ConversationMemory:
    def __init__(self, db_manager, user_id, thread_id=None,title="New Conversation"):
        self.db = db_manager
        self.user_id = user_id
        self.thread_id = thread_id or str(uuid.uuid4())
        self.title = title
        self._ensure_user()

    def _ensure_user(self):
        with self.db.pg.cursor() as cur:
            cur.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (self.user_id,))
            self.db.pg.commit()  
           
    def _ensure_thread(self):
        with self.db.pg.cursor() as cur:
            cur.execute("""
                INSERT INTO threads (thread_id, user_id, title) 
                VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
            """, (self.thread_id, self.user_id, self.title))
            self.db.pg.commit()  

    def get_working_context(self):
        """Fetches shared profile + last 3 turns from MongoDB."""
        # Shared context (Postgres)
        with self.db.pg.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT key, value FROM shared_memory WHERE user_id = %s", (self.user_id,))
            shared_memory = {row['key']: row['value'] for row in cur.fetchall()}

        with self.db.pg.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT key, value FROM thread_memory WHERE thread_id = %s", (self.thread_id,))
            thread_memory = {row['key']: row['value'] for row in cur.fetchall()}

        # History context (MongoDB)
        history_doc = self.db.mongo["history"].find_one({"thread_id": self.thread_id})
        history = history_doc.get("turns", [])[-5:] if history_doc else []

        return {"shared_memory": shared_memory, "thread_memory": thread_memory, "history": history}

    def fetch_thread_history(self):
        """Fetches the entire conversation history from MongoDB."""
        history_doc = self.db.mongo["history"].find_one({"thread_id": self.thread_id})
        format_history = []
        if history_doc:
            for turn in history_doc.get("turns", []):
                thread_obj = {
                    "role": "user",
                    "content": turn.get("query"),
                    "timestamp": turn.get("ts")
                }
                format_history.append(thread_obj)
                if turn.get("analysis"):
                    thread_obj = {
                        "role": "assistant",
                        "content": turn.get("analysis"),
                        "timestamp": turn.get("ts")
                    }
                    format_history.append(thread_obj)
        return format_history

    def save_to_memory(self, key, value, shared=False):
        """Saves a key-value pair to either shared or thread memory in Postgres."""
        table = "shared_memory" if shared else "thread_memory"
        id_field = "user_id" if shared else "thread_id"
        id_value = self.user_id if shared else self.thread_id

        with self.db.pg.cursor() as cur:
            cur.execute(f"""
                INSERT INTO {table} ({id_field}, key, value) 
                VALUES (%s, %s, %s) 
                ON CONFLICT ({id_field}, key) DO UPDATE SET value = EXCLUDED.value
            """, (id_value, key, value))
            self.db.pg.commit()

    def save_turn(self, query, result):
        """Saves turn to Mongo and updates PG timestamp."""
        self.db.mongo["history"].update_one(
            {"thread_id": self.thread_id},
            {"$push": {"turns": {"query": query, "analysis": result, "ts": datetime.datetime.utcnow()}}},
            upsert=True
        )
        with self.db.pg.cursor() as cur:
            cur.execute("UPDATE threads SET last_active = CURRENT_TIMESTAMP WHERE thread_id = %s", (self.thread_id,))
            self.db.pg.commit()

    # Fetch all threads for a user
    def fetch_user_threads(self):
        with self.db.pg.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT thread_id, title, last_active FROM threads WHERE user_id = %s ORDER BY last_active DESC", (self.user_id,))
            return cur.fetchall()

    def update_thread_title(self, new_title):
        with self.db.pg.cursor() as cur:
            cur.execute("UPDATE threads SET title = %s WHERE thread_id = %s", (new_title, self.thread_id))
            self.db.pg.commit()
            self.title = new_title

    def fetch_final_analysis(self):
        history_doc = self.db.mongo["history"].find_one({"thread_id": self.thread_id})
        history = history_doc.get("turns", []) if history_doc else []
        return history[-1]["analysis"] if history else {}