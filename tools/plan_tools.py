from pathlib import Path
from uuid import uuid4

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
