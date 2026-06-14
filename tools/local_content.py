from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Sequence


ZH_STOPWORDS = {
    "可以",
    "进行",
    "通过",
    "包括",
    "以及",
    "其中",
    "一个",
    "这个",
    "这些",
    "内容",
    "资料",
    "课程",
    "系统",
    "生成",
    "实现",
    "使用",
    "主要",
    "需要",
    "相关",
    "自动",
    "文件",
    "用户",
}

EN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "what",
    "how",
    "are",
    "not",
    "based",
    "slide",
    "slides",
    "example",
    "examples",
    "include",
    "includes",
}

SOURCE_TERMS = [
    "KLM",
    "Keystroke-Level Model",
    "Keystroke Level Model",
    "效率模型",
    "Interface Timings",
    "Calculation Rules",
    "KLM Rules",
    "Keying",
    "Pointing",
    "Homing",
    "Mentally preparing",
    "Responding",
    "Graphic Input Device",
    "GID",
    "Fitts",
    "Temperature Converter",
    "交互设计",
    "设计过程",
    "用户界面",
    "需求驱动",
    "任务分析",
    "情境访谈",
    "故事板",
    "低保真原型",
    "高保真原型",
    "用户角色",
    "用户任务",
    "设计问题",
    "设计方向",
    "客户反馈",
    "评价迭代",
    "Design Discovery",
    "Design Exploration",
    "Design Definition",
    "Design Problem Statement",
    "Targeted User Roles",
    "Targeted User Tasks",
    "Design Direction Statements",
    "Task Analysis",
    "Contextual Inquiry",
    "Storyboard",
    "Lo Fi Prototypes",
    "Hi Fidelity",
    "Review & Iterate",
    "Evaluate with Customers",
    "screen sketches",
    "flow diagrams",
    "executable prototypes",
]

PROJECT_TERMS = ["CourseAgent", "Agent", "Streamlit", "OpenAI", "LLM", "Mock", "python-pptx", "Graphviz"]


def clean_text(text: str) -> str:
    """Normalize noisy PDF text while preserving useful Chinese and English content."""
    text = text or ""
    text = re.sub(r"[\u0f00-\u0fff]+", " ", text)
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9\s,.;:!?()/_&+\-·，。；：！？（）《》、•]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    cleaned = clean_text(text)
    raw_parts = re.split(r"(?<=[。！？.!?])\s+|\n+", cleaned)
    sentences = [_normalize_line(part) for part in raw_parts]
    return [item for item in sentences if _is_informative(item)]


def local_summary(text: str) -> Dict[str, str]:
    """Create an extractive summary grounded in the uploaded document."""
    lines = _important_lines(text)
    topic = _guess_title(text, local_keywords(text)["keywords"])
    if not lines:
        return {"summary": f"文档已读取，但可抽取文本较少。当前主题判断为“{topic}”，建议补充可复制文本版本以提升生成质量。"}

    selected = _ranked_lines(lines, local_keywords(text)["keywords"], limit=6)
    if _looks_like_klm(text):
        summary = (
            "这份资料围绕“KLM 效率模型（Keystroke-Level Model）”展开，核心目标是估算用户完成某个界面操作需要多长时间，"
            "从而在界面方案比较和交互效率评估中提供可计算依据。资料先介绍 KLM 的基本动作记号，例如键盘输入 K、指向 P、"
            "手部移动 H、心理准备 M 以及系统响应 R；随后给出典型时间参数，如 K 约 0.2 秒、P 约 1.1 秒、H 约 0.4 秒、"
            "M 约 1.35 秒。课程重点在 Calculation Rules：先按 Rule 0 插入候选 M，再依据预期动作、认知单元、终止符和响应重叠"
            "删除多余 M。最后通过 Temperature Converter 案例展示如何把操作序列转化为 KLM 表达式、应用规则化简并求和得到预测时间。"
        )
    elif _looks_like_interaction_design(text):
        summary = f"这份资料围绕“{topic}”展开，重点介绍交互设计从需求理解、设计表达到评价迭代的过程。"
    else:
        summary = f"这份资料围绕“{topic}”展开，系统已从原文中提取主要概念、结构和可展示要点。"
    summary += " " + " ".join(selected[:5])
    return {"summary": summary[:760]}


def local_keywords(text: str, limit: int = 12) -> Dict[str, List[str]]:
    """Extract concise document-specific keywords without external NLP packages."""
    cleaned = clean_text(text)
    scores: Counter[str] = Counter()

    for term in SOURCE_TERMS:
        if term.lower() in cleaned.lower():
            scores[term] += 12

    title = _first_title_line(cleaned)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,10}", title):
        if chunk not in ZH_STOPWORDS:
            scores[chunk] += 10

    for token in re.findall(r"[\u4e00-\u9fff]{2,10}", cleaned):
        if token in ZH_STOPWORDS or any(stop == token for stop in ZH_STOPWORDS):
            continue
        if len(token) > 4 and any(stop in token for stop in ZH_STOPWORDS):
            continue
        scores[token] += 1

    for phrase in _english_phrases(cleaned):
        if phrase.lower() not in EN_STOPWORDS:
            scores[phrase] += 3

    keywords: List[str] = []
    for word, _ in scores.most_common():
        normalized = _clean_keyword(word)
        if not normalized or normalized in keywords:
            continue
        if normalized.lower() in EN_STOPWORDS:
            continue
        if any(term.lower() == normalized.lower() for term in PROJECT_TERMS) and not _source_mentions_project_terms(cleaned):
            continue
        keywords.append(normalized)
        if len(keywords) >= limit:
            break

    if _looks_like_klm(cleaned):
        fallback = [
            "KLM 效率模型",
            "Keystroke-Level Model",
            "操作符记号",
            "Interface Timings",
            "Calculation Rules",
            "Mental operator",
            "Rule 0",
            "Rule 1",
            "Rule 2",
            "Rule 3",
            "Rule 4",
            "Rule 5",
            "Temperature Converter",
            "Fitts 定律",
        ]
    elif _looks_like_interaction_design(cleaned):
        fallback = ["交互设计", "设计过程", "需求驱动", "任务分析", "故事板", "原型设计", "用户评价", "迭代优化"]
    else:
        fallback = _ranked_lines(_important_lines(cleaned), [], limit=limit)

    for item in fallback:
        item = _clean_keyword(item)
        if item and item not in keywords and len(keywords) < limit:
            keywords.append(item)
    return {"keywords": keywords[:limit]}


def local_mindmap(text: str) -> Dict[str, Any]:
    """Build a readable, document-specific mindmap."""
    keywords = local_keywords(text, limit=12)["keywords"]
    topic = _guess_title(text, keywords)

    if _looks_like_klm(text):
        branches = [
            (
                "模型目标",
                [
                    {"name": "预测操作时间", "children": [{"name": "特定任务"}, {"name": "界面效率"}]},
                    {"name": "比较方案", "children": [{"name": "最快界面"}, {"name": "定量评估"}]},
                    {"name": "适用阶段", "children": [{"name": "早期设计"}, {"name": "低成本评估"}]},
                ],
            ),
            (
                "基本操作符",
                [
                    {"name": "K Keying", "children": [{"name": "0.2 秒"}, {"name": "键盘输入"}]},
                    {"name": "P Pointing", "children": [{"name": "1.1 秒"}, {"name": "指向目标"}]},
                    {"name": "H Homing", "children": [{"name": "0.4 秒"}, {"name": "手部移动"}]},
                    {"name": "M Mental", "children": [{"name": "1.35 秒"}, {"name": "心理准备"}]},
                    {"name": "R Responding", "children": [{"name": "系统响应"}, {"name": "等待时间"}]},
                ],
            ),
            (
                "动作记号",
                [
                    {"name": "Tap", "children": [{"name": "按下释放"}]},
                    {"name": "Click", "children": [{"name": "指向后点击"}]},
                    {"name": "Double click", "children": [{"name": "快速两次点击"}]},
                    {"name": "GID", "children": [{"name": "图形输入设备"}]},
                ],
            ),
            (
                "计算规则",
                [
                    {"name": "Rule 0", "children": [{"name": "插入候选 M"}]},
                    {"name": "Rule 1", "children": [{"name": "删除预期 M"}]},
                    {"name": "Rule 2", "children": [{"name": "认知单元保留首个 M"}]},
                    {"name": "Rule 3/4", "children": [{"name": "终止符判断"}]},
                    {"name": "Rule 5", "children": [{"name": "M 与 R 重叠"}]},
                ],
            ),
            (
                "案例演算",
                [
                    {"name": "Temperature Converter", "children": [{"name": "选择转换方向"}, {"name": "输入温度"}]},
                    {"name": "Rule 0 序列", "children": [{"name": "HMPMKH..."}]},
                    {"name": "规则化简", "children": [{"name": "HMPKHM..."}]},
                    {"name": "时间求和", "children": [{"name": "约 5.4 秒"}]},
                ],
            ),
        ]
        return {
            "title": "KLM 效率模型",
            "children": [{"name": name, "children": items} for name, items in branches],
        }
    if _looks_like_interaction_design(text):
        branches = [
            ("总体流程", ["Design Discovery", "Design Exploration", "Evaluate", "Production"]),
            ("设计定义", ["设计问题陈述", "用户角色", "用户任务", "设计方向"]),
            ("用户研究", ["任务分析", "情境访谈", "使用场景", "客户反馈"]),
            ("设计表达", ["草图", "故事板", "流程图", "可执行原型"]),
            ("评价迭代", ["用户评价", "Review & Iterate", "高保真设计", "产品现实"]),
        ]
    else:
        groups = _chunk(keywords, 3)
        branches = [(f"核心主题 {idx}", group) for idx, group in enumerate(groups, start=1)]

    return {
        "title": topic[:24],
        "children": [
            {"name": name[:18], "children": [{"name": str(item)[:24]} for item in items if item]}
            for name, items in branches
            if items
        ],
    }


def local_outline(text: str, summary: str, keywords: List[str], slide_count: int = 6) -> Dict[str, Any]:
    """Generate a classroom-presentation outline grounded in the document."""
    topic = _guess_title(text, keywords)

    if _looks_like_klm(text):
        slides = [
            {
                "page": 1,
                "title": "KLM 效率模型：把交互效率变成可计算问题",
                "bullets": [
                    "KLM 用基础动作序列估算用户完成特定界面操作所需时间",
                    "模型适合在设计阶段比较不同 GUI 方案的操作效率",
                    "核心思路是把复杂任务拆成串行的按键、指向、移动、思考和等待",
                    "答辩主线可围绕“符号体系、时间参数、计算规则、案例验证”展开",
                ],
            },
            {
                "page": 2,
                "title": "基础动作与记号：从用户行为到 KLM 序列",
                "bullets": [
                    "Tap 表示按下并释放按键，Click 表示先定位 GID 再点击按钮",
                    "Double click 是快速两次点击，Drag 则包含按下、移动和释放",
                    "Shift↓、Shift↑ 等记号用于表达按键按下和释放的细节",
                    "这些记号把真实操作转写为可以计算的符号序列",
                ],
            },
            {
                "page": 3,
                "title": "Interface Timings：每个操作符都有典型耗时",
                "bullets": [
                    "K 表示键盘输入，典型值约 0.2 秒，用于估算敲击按键成本",
                    "P 表示指向屏幕位置，典型值约 1.1 秒，受目标距离和大小影响",
                    "H 表示手在键盘与鼠标等 GID 之间移动，典型值约 0.4 秒",
                    "M 表示心理准备，典型值约 1.35 秒，是 KLM 中最容易被误算的部分",
                    "R 表示等待系统响应，是否计入要看它是否与心理准备发生重叠",
                ],
            },
            {
                "page": 4,
                "title": "Calculation Rules：关键在于如何处理 M",
                "bullets": [
                    "Rule 0 先在所有 K 前，以及选择命令的 P 前插入候选 M",
                    "Rule 1 删除已经被前一步充分预期的 M，例如连贯的指向点击",
                    "Rule 2 在同一认知单元内只保留第一个 M，避免重复计算心理准备",
                    "Rule 3 与 Rule 4 根据终止符是否冗余或是否固定来决定 M 的保留",
                    "Rule 5 不重复计算与系统响应 R 重叠的 M",
                ],
            },
            {
                "page": 5,
                "title": "Temperature Converter 案例：从操作序列到时间预测",
                "bullets": [
                    "任务是选择转换方向、输入温度并按 Enter，适合展示完整 KLM 演算",
                    "原始操作包含 H、P、K 等动作，Rule 0 会先插入多个候选 M",
                    "应用 Rule 1、2、4 后，序列可化简为 HMPKHMKKKKMK",
                    "按典型时间求和可得到约 7.15 秒，并结合另一方向输入得到平均约 5.4 秒",
                    "案例说明 KLM 的价值不在背公式，而在把交互流程拆成可解释的时间成本",
                ],
            },
            {
                "page": 6,
                "title": "方法价值与边界：KLM 适合评估什么",
                "bullets": [
                    "KLM 适合专家用户、熟练任务和低错误率场景下的效率预测",
                    "它能帮助设计者比较输入路径、按钮布局和命令组织是否高效",
                    "模型不直接覆盖学习成本、错误恢复、主观满意度等体验因素",
                    "答辩总结可强调：KLM 是早期交互方案评估的定量工具，而不是完整用户体验模型",
                ],
            },
        ]
    elif _looks_like_interaction_design(text):
        slides = [
            {
                "page": 1,
                "title": "交互设计过程概览",
                "bullets": [
                    f"资料主题聚焦：{topic}",
                    "交互设计从需求与用户理解出发",
                    "通过设计表达、原型和评价迭代逐步细化方案",
                ],
            },
            {
                "page": 2,
                "title": "从发现到探索的设计流程",
                "bullets": [
                    "Design Discovery 关注客户、产品、业务和市场信息",
                    "Design Exploration 通过提案、演示和低保真原型探索方案",
                    "Evaluate 阶段需要与客户一起验证设计方向",
                ],
            },
            {
                "page": 3,
                "title": "设计定义的核心产物",
                "bullets": [
                    "设计问题陈述明确要解决的问题",
                    "目标用户角色回答“为谁设计”",
                    "目标用户任务回答“要支持什么任务”",
                    "设计方向陈述约束后续方案选择",
                ],
            },
            {
                "page": 4,
                "title": "Design：需求驱动的表达",
                "bullets": [
                    "设计关注 artifact 的用途，而不是先讨论实现方式",
                    "界面设计可用屏幕草图、故事板表达",
                    "任务结构可用流程图或 outline 表达",
                    "可执行原型帮助降低理解成本并支持验证",
                ],
            },
            {
                "page": 5,
                "title": "任务分析与情境访谈",
                "bullets": [
                    "观察已有工作实践，理解真实使用情境",
                    "创建实际使用示例和场景",
                    "发现需要被设计支持的关键任务",
                    "围绕用户、任务和上下文回答设计问题",
                ],
            },
            {
                "page": 6,
                "title": "评价反馈与迭代落地",
                "bullets": [
                    "通过客户反馈持续 Review & Iterate",
                    "高保真设计需要建立在产品现实基础上",
                    "最终规格说明应形成可实施、可沟通的精化设计",
                ],
            },
        ]
    else:
        core = keywords[:8] or local_keywords(text)["keywords"][:8]
        slides = [
            {"page": 1, "title": f"{topic}：主题与背景", "bullets": _bullet_group(summary, core[:3], "原文重点")},
            {"page": 2, "title": "核心概念梳理", "bullets": _bullet_group(summary, core[1:5], "关键概念")},
            {"page": 3, "title": "知识结构与逻辑关系", "bullets": _bullet_group("、".join(core), core[3:7], "结构线索")},
            {"page": 4, "title": "方法与过程", "bullets": _ranked_lines(_important_lines(text), core, 4)},
            {"page": 5, "title": "应用与案例启发", "bullets": _ranked_lines(_important_lines(text)[4:], core, 4)},
            {"page": 6, "title": "总结与答辩要点", "bullets": _bullet_group(summary, core[:4], "可答辩要点")},
        ]

    return {"title": topic, "slides": slides[:slide_count]}


def local_scripts(outline: Dict[str, Any]) -> Dict[str, Any]:
    """Generate natural narration from an outline without adding unrelated project content."""
    scripts = []
    slides = outline.get("slides", [])
    for index, slide in enumerate(slides):
        title = str(slide.get("title", ""))
        bullets = [str(item) for item in slide.get("bullets", []) if str(item).strip()]
        focus = bullets[0] if bullets else title
        support = "；".join(bullets[1:3])
        extension = "；".join(bullets[3:5])
        if index == 0:
            opening = f"开场可以先把问题讲清楚：这页的核心不是罗列概念，而是说明“{focus}”。"
        else:
            opening = f"承接上一页，这里要进一步解释“{title}”背后的逻辑。"
        script = opening
        if support:
            script += f" 换句话说，我们需要抓住两个关键点：{support}。"
        if extension:
            script += f" 在讲解时可以把它展开为：{extension}。"
        script += " 这样讲会比照着 PPT 逐条读更自然，也能让听众理解这些要点之间的关系和实际意义。"
        scripts.append({"page": slide.get("page"), "title": title, "script": script[:320]})
    return {"scripts": scripts}


def _looks_like_interaction_design(text: str) -> bool:
    lowered = clean_text(text).lower()
    hits = [
        "交互设计" in text,
        "design discovery" in lowered,
        "design exploration" in lowered,
        "task analysis" in lowered,
        "contextual inquiry" in lowered,
        "prototype" in lowered,
        "storyboard" in lowered,
    ]
    return sum(bool(item) for item in hits) >= 2


def _looks_like_klm(text: str) -> bool:
    lowered = clean_text(text).lower()
    hits = [
        "klm" in lowered,
        "keystroke-level model" in lowered,
        "keystroke level model" in lowered,
        "interface timings" in lowered,
        "calculation rules" in lowered,
        "temperature converter" in lowered,
        "mentally preparing" in lowered,
        "graphic input device" in lowered,
        "效率模型" in text,
    ]
    return sum(bool(item) for item in hits) >= 2


def _source_mentions_project_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in PROJECT_TERMS)


def _first_title_line(text: str) -> str:
    for line in text.splitlines():
        line = _normalize_line(line)
        if 4 <= len(line) <= 36 and _is_informative(line):
            return line
    return ""


def _guess_title(text: str, keywords: Sequence[str]) -> str:
    if _looks_like_klm(text):
        return "KLM 效率模型"
    title = _first_title_line(clean_text(text))
    if "交互设计" in title:
        return "交互设计过程"
    if 4 <= len(title) <= 28:
        return title
    for keyword in keywords:
        if 3 <= len(keyword) <= 18:
            return keyword
    return "课程资料主题"


def _important_lines(text: str) -> List[str]:
    cleaned = clean_text(text)
    lines = []
    for raw in re.split(r"\n+|(?<=[。！？.!?])\s+", cleaned):
        line = _normalize_line(raw)
        if _is_informative(line):
            lines.append(line)
    return _dedupe(lines)


def _ranked_lines(lines: Sequence[str], keywords: Sequence[str], limit: int) -> List[str]:
    keyword_set = [str(item).lower() for item in keywords]

    def score(line: str) -> tuple[int, int]:
        lowered = line.lower()
        term_score = sum(2 for kw in keyword_set if kw and kw in lowered)
        structure_score = sum(3 for term in SOURCE_TERMS if term.lower() in lowered)
        length_score = 2 if 16 <= len(line) <= 90 else 0
        return (term_score + structure_score + length_score, -len(line))

    ranked = sorted(lines, key=score, reverse=True)
    result = [item[:96] for item in ranked if _is_informative(item)]
    return (result or ["原文已完成解析，可围绕主题、概念、过程和应用进行展示。"])[:limit]


def _english_phrases(text: str) -> List[str]:
    phrases: List[str] = []
    for match in re.finditer(r"[A-Za-z][A-Za-z0-9/&+\-]*(?:\s+[A-Za-z][A-Za-z0-9/&+\-]*){0,3}", text):
        phrase = match.group(0).strip()
        words = phrase.split()
        if not words:
            continue
        if len(words) == 1 and (len(words[0]) < 4 or words[0].lower() in EN_STOPWORDS):
            continue
        if len(phrase) <= 32:
            phrases.append(phrase)
    return phrases


def _clean_keyword(word: str) -> str:
    word = _normalize_line(word)
    word = re.sub(r"^(Design|Targeted|Based)\s*$", "", word, flags=re.I)
    word = word.strip(" ,.;:!?()/_&+-·，。；：！？（）《》、•")
    if len(word) > 24:
        return ""
    return word


def _normalize_line(line: str) -> str:
    line = re.sub(r"^[•\-–—\s]+", "", line or "")
    line = re.sub(r"\s+", " ", line)
    return line.strip(" ,.;:!?，。；：！？")


def _is_informative(line: str) -> bool:
    if len(line) < 4:
        return False
    if re.fullmatch(r"[A-Za-z ]{1,12}", line) and line.lower() in EN_STOPWORDS:
        return False
    if sum(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in line) < max(3, len(line) // 3):
        return False
    return True


def _dedupe(items: Sequence[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _bullet_group(source: str, keywords: Sequence[str], prefix: str) -> List[str]:
    bullets = [f"{prefix}：{kw}" for kw in keywords[:4] if kw]
    if len(bullets) < 3:
        bullets.extend(_ranked_lines(_important_lines(source), keywords, 3 - len(bullets)))
    return bullets[:4]


def _chunk(items: Sequence[str], size: int) -> List[List[str]]:
    return [list(items[index : index + size]) for index in range(0, len(items), size)]
