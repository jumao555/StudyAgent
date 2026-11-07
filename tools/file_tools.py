import keyword
from pathlib import Path
import json

NOTES_DIR = (
    Path(__file__).resolve().parent.parent / "notes"

).resolve()

def read_file(filename,start_line=None,end_line=None):
    if not isinstance(filename, str) or not filename.strip():
        return {
            "ok": False,
            "error": "错误，文件名必须是非空字符串"
        }

    # 任意一个行号被提供，就进入按行读取模式
    use_range = start_line is not None or end_line is not None

    if use_range:
        # type(...) is int 同时排除 True、False：
        # Python 中 bool 是 int 的子类，isinstance(True, int) 会返回 True
        if type(start_line) is not int or type(end_line) is not int:
            return {
                "ok": False,
                "error": "错误，起始行和结束行必须同时提供，且必须是整数"
            }

        if start_line < 1 or end_line < start_line:
            return {
                "ok": False,
                "error": "错误，行号必须从1开始，结束行不能小于起始行"
            }
            # 首尾都包含，所以需要加1。
        if end_line - start_line + 1 > 50:
            return {"ok": False, "error": "错误，每次最多读取50行"}
    try:
        file_path = (NOTES_DIR / filename).resolve()

        # 保留现有安全边界，只读取notes 直接包含的文件
        if file_path.parent != NOTES_DIR:
            return {"ok": False, "error": "错误，禁止访问笔记目录之外的文件"}

        if file_path.suffix.lower() != ".txt":
            return {"ok": False, "error": "错误，只允许读取 txt 文件"}


        content = file_path.read_text(encoding="utf-8")

        if not use_range:
            return {"ok":True, "content":content}
        lines = content.splitlines()
        if start_line > len(lines):
            return {
                "ok": False,
                "error": f"错误，起始行超出文件范围，文件共{len(lines)}行"
            }

        actual_end = min(len(lines), end_line)

        # 行号从1开始，列表索引从0开始；
        # 切片右侧不包含，因此结束位置直接用 actual_end。
        selected_lines = lines[start_line - 1:actual_end]

        # 从原始行号开始编号，方便模型引用、用户核对。
        numbered_lines = [
            f"{line_number}: {text}"
            for line_number, text in enumerate(
                selected_lines, start=start_line
            )
        ]
        return {
            "ok":True,
            "content":"\n".join(numbered_lines)
        }


    except FileNotFoundError:

        return {"ok": False, "error": "错误，文件不存在"}

    except PermissionError:

        return {"ok": False, "error": "错误，没有文件访问权限"}

    except UnicodeDecodeError:

        return {"ok": False, "error": "错误，文件编码不是UTF-8"}

    except OSError:

        return {"ok": False, "error": "错误，文件访问失败"}

def list_files():
    try:
        filenames = []

        # 遍历笔记目录的直接子项
        for path in NOTES_DIR.iterdir():
            if(
                path.is_file()
                and path.suffix.lower() == ".txt"
                and path.resolve().parent == NOTES_DIR
            ):
                filenames.append(path.name)

        return json.dumps(
            sorted(filenames),
            ensure_ascii=False,
        )

    except OSError:
        return "错误，无法列出笔记文件"

def search_notes(keyword):
    if not isinstance(keyword,str) or not keyword.strip():
        return "错误，搜索关键词必须是非空字符串"

    keyword = keyword.strip()
    keywords = keyword.casefold().split()
    # 去重，避免重复计分
    keywords = sorted(set(keywords))
    result = []
    MAX_CONTENT_LINES = 8
    MAX_RESULTS = 5

    try:
        filenames = json.loads(list_files())
    except json.JSONDecodeError:
        return "错误，无法获取文件列表"

    for filename in filenames:
        read_result = read_file(filename)

        # 根据明确的状态判断，不会被正文的文字所影响
        if not read_result["ok"]:
            return(
                f"错误，无法搜索笔记{filename}"
                f"{read_result['error']}"
            )
        content = read_result["content"]
        lines = content.splitlines()

        for index,line in enumerate(lines):
            # 任意一个查询词出现，就收集这一行及其附近内容
            if any(word in line.casefold() for word in keywords):
                start = max(0,index - 1)
                end = min(len(lines), index + 2)

                if(
                    result
                    and result[-1]["filename"] == filename
                    and start + 1 <= result[-1]["content_end_line"]
                    # 合并后仍然不超过单个片段的行数上限
                    and (end - result[-1]["content_start_line"] + 1
                         <= MAX_CONTENT_LINES )
                ):
                    previous = result[-1]

                    # 合并范围取两个片段中更靠后的结束位置
                    previous["matched_lines"].append(index + 1)
                    previous["content_end_line"] = max(previous["content_end_line"], end)

                    content_start = previous["content_start_line"] - 1
                    content_end = previous["content_end_line"]

                    previous["context"] = "\n".join(
                        lines[content_start:content_end]
                    )
                else:
                    result.append(
                        {
                            "filename": filename,
                            "line": index + 1,
                            "text": line,
                            "matched_lines": [index + 1],
                            "content_start_line": start + 1,
                            "content_end_line": end,
                            "context": "\n".join(lines[start:end]),
                        }
                    )

    for item in result :
        matched_keywords = []
        context = item["context"].casefold()

        for word in keywords:
            if word in context :
                matched_keywords.append(word)

        item['matched_keywords'] = matched_keywords
        item["score"] = len(matched_keywords)
# 先对全部候选片段排序，保留高分结果
    result.sort(key = lambda item: item["score"],reverse=True)

    # 再限制返回数量
    return json.dumps(
        result[:MAX_RESULTS],
        ensure_ascii=False
    )
