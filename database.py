import sqlite3
import json
from contextlib import closing
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

    with closing(sqlite3.connect(DB_PATH)) as conn, conn:
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
    with closing(sqlite3.connect(DB_PATH)) as conn, conn:
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
def list_plans(user_id):
    conn = sqlite3.connect(DB_PATH)

    # 让查询结果可以通过列名访问，便于转成字典
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute(
            """
           SELECT id, title, filename, created_at, status
           FROM plans
           WHERE user_id = ?
           ORDER BY created_at DESC, id DESC
           """,
            (user_id,)

        )
        # 获取所有匹配列表，没有计划时返回空列表
        rows = cursor.fetchall()
        return [dict(row)for row in rows]
    finally:
        conn.close()

def update_plan_status(user_id,plan_id,status):
    # 在执行SQL之前，先检查调用方传入的数据
    if type(plan_id) is not int or plan_id < 1:
        raise ValueError("计划id必须是正整数")

    if status not in ["pending", "completed"]:
        raise ValueError("计划状态只能是pending 或 completed")
    conn = sqlite3.connect(DB_PATH)

    try :
        cursor = conn.execute(
            """
            UPDATE plans
            SET status = ?
            WHERE id = ? AND user_id = ?
            """,
            (status,plan_id,user_id),

        )
        conn.commit()

        # 匹配到一条记录，表示更新成功
        # 不存在或者不属于当前用户时，返回false
        return cursor.rowcount == 1
    finally:
        conn.close()
def get_plan(user_id,plan_id):
    if type(plan_id) is not int or plan_id < 1:
        raise ValueError("计划id必须是正整数")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            """
           SELECT id, title, filename, created_at, status
           FROM plans
           WHERE id = ? AND user_id = ?
           """,
            (plan_id,user_id),
        ).fetchone()

        return dict(row) if row is not None else None
    finally:
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
