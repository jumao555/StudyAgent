sessions = {}

SYSTEM_PROMPT = "你是 StudyAgent 学习助手。"

def get_session(user_id,session_id):
    key = (user_id, session_id)
    if key not in sessions:
        new_session = {
            "messages": [
                {
                    "role": "user",
                    "content": SYSTEM_PROMPT
                }
            ],
            "status": "idle",
            "tool_history": []
        }
        sessions[key] = new_session
    else:
        return sessions[key]

    return new_session