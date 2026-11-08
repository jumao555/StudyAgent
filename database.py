import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "studyagent.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                messages TEXT NOT NULL,
                PRIMARY KEY (user_id, session_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                filename TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'completed'))
            )
        """)
        conn.commit()

    finally:
        conn.close()


def save_session(user_id,session_id,state):
    messages_json = json.dumps(
        state["messages"],
        ensure_ascii=False
    )

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO sessions
            (user_id,session_id,status,messages)
            VALUES (?,?,?,?)
            ON CONFLICT (user_id, session_id)
            DO UPDATE SET
                status = excluded.status,
                messages = excluded.messages
            """,(
                user_id,
                session_id,
                state["status"],
                messages_json
            )
        )

def load_session(user_id,session_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT status,messages FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id,session_id)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        messages = json.loads(row[1])
        return {
            "status": row[0],
            "messages": messages
        }

def register_plan(user_id, title, filename):
    """登记一个已成功写入的计划文件，返回计划ID。"""
    conn = sqlite3.connect(DB_PATH)

    try:
        # 状态和创建时间使用数据表中声明的默认值。
        cursor = conn.execute(
            """
            INSERT INTO plans (user_id, title, filename)
            VALUES (?, ?, ?)
            """,
            (user_id, title, filename),
        )

        conn.commit()

        # 取得刚刚插入的记录ID，后续查看、更新都用它。
        return cursor.lastrowid

    finally:
        # 无论成功还是异常，都释放数据库连接。
        conn.close()


if __name__ == "__main__":
    init_db()

    state = {
        "status": "idle",
        "messages": [
            {
                "role": "system",
                "content": "你是 StudyAgent"
            },
            {
                "role": "user",
                "content": "我要学习 Kotlin"
            }
        ]
    }

    save_session("user_A", "session_1", state)

    restored = load_session("user_A", "session_1")

    print("恢复的会话：", restored)
    print("消息类型：", type(restored["messages"]))
