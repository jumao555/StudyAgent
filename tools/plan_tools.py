from pathlib import Path
from uuid import uuid4
import sqlite3
from database import get_plan

PLANS_DIR = Path(__file__).resolve().parent.parent / "plans"

def save_plan(title, content):
    # 先校验，再操作文件，避免无效请求产生文件
    if not isinstance(title, str) or not title.strip():
        return {
            "ok": False,
            "error": "计划标题必须是非空字符串"
        }
    if not isinstance(content, str) or not content.strip():
        return {
            "ok": False,
            "error": "计划正文必须是非空字符串"
        }
    title = title.strip()
    content = content.strip()

    if len(title) > 100:
        return {
            "ok": False,
            "error": "计划标题不能超过100个字符"
        }
    if "\n" in title or "\r" in title:
        return {
            "ok": False,
            "error": "计划标题不能包含换行"
        }
    if len(content) > 20000:
        return {
            "ok": False,
            "error": "计划正文不能超过20000个字"
        }

    # 标题只进入正文，，不参与文件路径
    # uuid4 生成随机标识，降低不同计划重名的可能
    filename = f"plan_{uuid4().hex}.md"
    file_path = PLANS_DIR / filename

    document = f"# {title}\n\n{content}\n"
    try :
        PLANS_DIR.mkdir(parents=True, exist_ok=True)

        # x ： 仅创建新文件，如果文件已存在，就抛出异常
        # w : 会覆盖旧文件
        with file_path.open("x", encoding="utf-8") as file:
            file.write(document)

    except FileExistsError:
        return {
            "ok": False,
            "error": "文件名称冲突，未覆盖已有文件"
        }
    except OSError:
        return {
            "ok": False,
            "error": "计划保存失败"
        }


    # 只有写入及关闭文件成功后，才返回成功结果
    return {
        "ok": True,
        "filename": filename,
        "relative_path": f"plans/{filename}",
        "title": title,

    }


def open_plan(user_id,plan_id):
    if type(plan_id) is not int or plan_id < 1:
        return {
            "ok": False,
            "error": "计划id必须是正整数",
        }
    try:
        plan = get_plan(user_id,plan_id)
    except sqlite3.Error:
        return {
            "ok": False,
            "error": "无法查询计划记录"
        }
    if plan is None:
        return {
            "ok": False,
            "error": "计划不存在或不属于当前用户"
        }

    try:
        plans_dir = PLANS_DIR.resolve()
        file_path = (plans_dir / plan["filename"]).resolve()

        # 即使文件名来自数据库，也检查实际读取范围。
        if (
                file_path.parent != plans_dir
                or file_path.suffix.lower() != ".md"
        ):
            return {"ok": False, "error": "计划文件路径不合法"}

        content = file_path.read_text(encoding="utf-8")

    except FileNotFoundError:
        return {
            "ok": False,
            "error": "计划记录存在，但正文文件已丢失"
        }
    except UnicodeDecodeError:
        return {"ok": False, "error": "计划文件不是有效的UTF-8文本"}
    except OSError:
        return {"ok": False, "error": "计划文件读取失败"}
    except ValueError:
        return {"ok": False, "error": "计划文件路径不合法"}

    return {
        "ok": True,
        "plan": plan,
        "content": content,
    }