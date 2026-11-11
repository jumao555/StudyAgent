import os
import logging
import json
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI,APIError
from tools.file_tools import read_file,list_files,search_notes
from tools.plan_tools import save_plan
from database import(init_db,load_session,save_session,register_plan)

logger = logging.getLogger(__name__)

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "按行读取 notes 目录中的 txt 笔记，返回带原始行号的内容。"
                "检索片段不足时，根据检索结果的行号选择需要补充的范围。"
                "起始行和结束行都包含，每次最多读取50行。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "笔记文件名，如 kotlin.txt"
                    },
                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "起始行号，从1开始"
                    },
                    "end_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "结束行号，包含这一行"
                    }
                },
                "required": ["filename", "start_line", "end_line"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出 notes 目录中可读取的 txt 笔记文件名",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": (
                "搜索学习笔记，多个关键词用空格分隔，任意一个词匹配即可。"
                "按片段覆盖的不同查询词数量排序，最多返回5个片段。"
                "结果包含文件名、命中行、上下文范围和原文。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "一个关键词，或用空格分隔的多个关键词，例如 网络 failed"
                    }
                },
                "required": ["keyword"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_plan",
            "description": (
                "用户要求保存学习计划时使用。"
                "保存前程序会展示内容并要求用户确认。"
                "只能新建计划文件，不能覆盖已有文件。"
                "正文应包含学习目标、时间安排、具体任务和验收方式；"
                "引用笔记时注明真实来源，资料不足时明确说明。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "计划标题，单行，不超过100个字符"
                    },
                    "content": {
                        "type": "string",
                        "description": "Markdown格式的计划正文，不超过20000个字符"
                    }
                },
                "required": ["title", "content"],
                "additionalProperties": False
            }
        }
    }
]

def execute_tool(name,arguments,user_id,plan_handler=None):
    if name not in ["read_file","list_files","search_notes","save_plan"]:
        return "错误：未知工具"

    # 第一阶段：解析json参数
    try:
        args = json.loads(arguments)
    except(json.JSONDecodeError, TypeError):
        return "错误，工具参数格式不正确"

    if not isinstance(args,dict):
        return "错误，工具参数必须是对象"

    # filename只属于read_file
    if name == "list_files":
        if args:
            return "错误，list_files不接受参数"
        return list_files()

    if name == "search_notes":
        if set(args) != {"keyword"}:
            return "错误，search_notes 只接受 keyword 参数"
        return search_notes(args["keyword"])

    if name == "save_plan":
        if set(args) != {"title", "content"}:
            return "错误，save_plan必须且只能提供title和content"

        title = args["title"]
        content = args["content"]

        # 在展示确认内容之前，先排除无效输入
        if not isinstance(title,str) or not title.strip():
            return "错误，计划标题必须是非空字符串"
        if not isinstance(content,str) or not content.strip():
            return "错误，计划正文必须是非空字符串"
        title = title.strip()
        content = content.strip()

        if len(title) > 100 or "\n" in title or "\r" in title:
            return "错误，标题必须是单行且不能超过100个字符"

        if len(content) > 20000:
            return "错误，正文不能超过20000个字符"

        if plan_handler is not None:
            result = plan_handler(title,content)
            return json.dumps(result, ensure_ascii=False)

        print("\n即将保存以下学习计划：")
        print(f"{title}\n\n{content}")

        # 确认来自真实的命令行输入，不接受模型传入的确认字段
        confirmation = input(
            "\n 输入 yes 确认保存，其他输入取消："

        ).strip().lower()

        if confirmation != "yes":
            return json.dumps(
                {
                    "ok": False,
                    "cancelled": True,
                    "error": "用户取消保存，未创建文件"
                },
                ensure_ascii=False,
            )
        result = save_plan(title,content)

        # 文件没有保存成功，就不创建数据库记录
        if not result["ok"]:
            return json.dumps(result, ensure_ascii=False)

        try:
            plan_id = register_plan(
                user_id = user_id,
                title = result["title"],
                filename=result["filename"],

            )
        except sqlite3.Error as exc:
            logger.error(
                "计划文件已保存，但登记失败 error_type=%s",
                type(exc).__name__
            )

            # 文件已保存，明确报告部分成功
            # 保留文件位置，不能声称已进入计划列表
            return json.dumps(
                {
                    "ok":False,
                    "file_saved": True,
                    "registered": False,
                    "relative_path": result["relative_path"],
                    "error": (
                        "计划文件已保存，但数据库登记失败"
                        "暂未进入计划列表，请保留该文件"
                        "不要自动重复保存"
                    ),
                },
                ensure_ascii=False,
            )

        # 文件写入与数据库登记都已成功，才报告完整成功
        result["plan_id"] = plan_id
        result["status"] = "pending"
        result["registered"] = True

        return json.dumps(result, ensure_ascii=False)

    # 前面的分支已经处理了其他工具，走到这里的是read_file
    expected_keys = {"filename", "start_line", "end_line"}

    # 必须恰好提供这三个参数
    if set(args) != expected_keys:
        return "错误，read_file必须且只能提供filename，start_line,end_line"

    # 字段齐全不代表值合法
    # 显示检查None，避免两个null触发底层函数的全文读取模式
    if args["start_line"] is None or args["end_line"] is None:
        return "错误，起始行和结束行不能为null"

    read_result = read_file(
        filename = args["filename"],
        start_line = args["start_line"],
        end_line = args["end_line"]
    )

    # python内部使用字典，回传模型的tool消息使用字符串
    return json.dumps(read_result, ensure_ascii=False)


def run_agent(user_task,session_id,plan_handler=None):
    logging.basicConfig(
        filename=Path(__file__).resolve().parent / "studyagent.log",
        encoding = "utf-8",
        level = logging.INFO,
        format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    # load_dotenv 读取文件，再把配置加载到当前进程的环境变量中
    load_dotenv(Path(__file__).resolve().parent / ".env")

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        timeout=30,
        max_retries=1
    )

    MODEL = os.environ["MODEL"]

    # 初始化数据库
    init_db()

    USER_ID = "user_A"
    SESSION_ID = session_id

    # 尝试加载之前的会话
    state = load_session(USER_ID, SESSION_ID)

    # 如果没有会话，就创建新状态
    if state is None:
        state = {
            "status": "idle",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 StudyAgent 学习助手。"
                        "用户要求浏览文件列表时，调用 list_files。"
                        "查找知识点时优先调用 search_notes，它会搜索整个笔记目录。"
                        "检索片段足够支持回答时，直接根据片段回答。"
                        "需要完整文件、更多上下文或核对缺失内容时，再调用 read_file。"
                        "搜索为空时，可以尝试同义词或其他相关术语，避免重复无效查询。"
                        "根据工具真实结果回答，不能编造文件名或文件内容。"
                        "引用时注明文件名和实际支持结论的行号范围。"
                        "区分笔记原文与补充解释，资料不足时明确说明。"
                    )
                }
            ]
        }

    messages = state["messages"]

    messages.append({
        "role": "user",
        "content": user_task
    })

    state["status"] = "running"
    save_session(USER_ID, SESSION_ID, state)

    logger.info(
        "任务开始 user=%r session=%r",
        USER_ID,SESSION_ID
    )

    MAX_STEPS = 6

    for step in range(MAX_STEPS):
        logger.info(
            "请求模型 session=%r step=%d",
            SESSION_ID,step + 1
        )
        print(f"\n---第{step + 1}轮 ---")

        try:
            response = client.chat.completions.create(
                model = MODEL,
                messages = messages,
                tools = tools,
                tool_choice="auto"
            )
        except APIError as exc:
            # 标记任务失败
            state["status"] = "failed"
            # 将状态保存到SQLite
            save_session(USER_ID, SESSION_ID, state)
            logger.warning(
                "模型请求失败 session=%r error_type=%s",
                SESSION_ID, type(exc).__name__
            )
            print("模型请求失败，错误类型：", type(exc).__name__)
            break

        # 空列表里没有第0项，必须先检查再取值
        if not response.choices:
            state["status"] = "failed"
            save_session(USER_ID, SESSION_ID, state)
            logger.warning(
                "模型响应无候选结果 session=%r",
                SESSION_ID
            )
            print("模型响应异常：没有返回候选结果")
            break
        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason
        tool_calls = message.tool_calls or []

        logger.info(
            "模型响应 session = %r step = %d finish_reason = %r",
            SESSION_ID, step + 1, finish_reason
        )

        print("本轮结束原因：",finish_reason)

        # 截断，过滤或未知原因：停止，不执行可能不完整的工具请求
        if finish_reason not in ["tool_calls","stop"]:
            state["status"] = "stopped"
            save_session(USER_ID, SESSION_ID, state)
            print("本次运行停止，原因为",finish_reason)
            break


        # 检查结束标记与工具请求是否一致
        if(
            finish_reason  == "tool_calls" and not tool_calls
        )or (
            finish_reason == "stop" and tool_calls
        ):
            state["status"] = "failed"
            save_session(USER_ID, SESSION_ID, state)
            print("模型响应异常：结束原因与工具调用不一致")
            break

        if not tool_calls:
            content = message.content

            if not isinstance(content, str) or not content.strip():
                state["status"] = "failed"
                save_session(USER_ID, SESSION_ID, state)

                logger.warning(
                    "模型最终回答为空 session=%r",
                    SESSION_ID
                )
                print("模型响应异常：最终回答为空")
                break

        messages.append(message.model_dump(exclude_none=True))


    # 没用工具调用，结束agent Loop
        if not tool_calls:
            state["status"] = "completed"
            save_session(USER_ID, SESSION_ID, state)
            print("Agent 回复：", message.content)
            break


        for call in message.tool_calls:
            name = call.function.name
            arguments = call.function.arguments

            print("调用工具：", name)
            print("工具参数：", arguments)


            logger.info(
                "工具开始 session=%r step=%d tool=%r call_id=%r",
                SESSION_ID, step + 1, name, call.id
            )
            # 真正执行读取操作的是python，而不是Gemini
            result = execute_tool(name,
                                  arguments,
                                  USER_ID,
                                  plan_handler = plan_handler,
            )

            logger.info(
                "工具返回 session=%r step=%d tool=%r call_id=%r",
                SESSION_ID, step + 1, name, call.id
            )
            print("执行结果：", result)

        # 把工具结果放回消息历史
            messages.append({
                "role": "tool",
                "content": result,
                "tool_call_id": call.id
            })

        save_session(USER_ID, SESSION_ID, state)
    else:
        state["status"] = "stopped"
        save_session(USER_ID, SESSION_ID, state)
        print("达到最大执行轮数，Agent已终止")

    logger.info(
        "任务结束 session=%r status=%r",
        SESSION_ID,state["status"]
    )

    return state


if __name__ == "__main__":
    session_id = input("请输入会话编号（直接回车使用default）：").strip()
    session_id = session_id or "default"

    print("请输入学习任务,输入/exit退出")

    while True:
        user_task = input("\n你：").strip()

        if user_task == "/exit":
            print("本次对话结束")
            break
        if not user_task:
            print("任务不能为空")
            continue
        run_agent(user_task, session_id)
