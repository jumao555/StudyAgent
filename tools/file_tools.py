import keyword
from pathlib import Path
import json

NOTES_DIR = (
    Path(__file__).resolve().parent.parent / "notes"

).resolve()

def read_file(filename):
    if not isinstance(filename, str):
        return "错误，文件名必须是字符串"
    file_path = (NOTES_DIR / filename).resolve()

    if file_path.parent != NOTES_DIR:
        return "错误，禁止访问笔记目录之外的文件"

    if file_path.suffix.lower() != ".txt":
        return "错误：只允许读取 txt 文件"

    try:
        return file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "错误，文件不存在"
    except PermissionError:
        return "错误，没有文件访问权限"
    except UnicodeDecodeError:
        return "错误，文件编码不是utf-8"

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
        content = read_file(filename)
        if content.startswith("错误"):
            return f"错误，无法搜索笔记{filename}"

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
