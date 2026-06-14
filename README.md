# CourseAgent：课程资料自动整理与学习材料生成系统

CourseAgent 是一个基于 Python 和大语言模型 Agent 思想的课程文档自动整理项目。用户上传 `.txt`、`.docx` 或 `.pdf` 课程资料后，系统会按照“计划生成、工具调用、状态记录、结果输出”的流程，自动生成摘要、关键词、思维导图、PPT 大纲、每页讲稿和 PPT 文件。

当前版本采用更完整的 Agent 架构：`Planner -> Tool Executor -> Verifier -> Auto-Repair -> Report`。Planner 会根据用户目标动态选择工具，而不是固定生成全部产物；Tool Executor 按计划调用工具；Verifier 检查计划内产物是否存在且非空；Auto-Repair 在发现缺失产物时自动补救。

## 功能列表

- 上传课程文档并读取文本内容
- 自动生成 Agent 任务计划
- 生成课程资料摘要和关键词
- 生成思维导图 JSON，并优先输出 PNG
- 生成 5 分钟课堂答辩 PPT 大纲
- 生成每页口语化讲稿
- 自动生成可下载的 `.pptx` 文件
- 自动生成字幕式讲解视频 `.mp4`
- 自动生成字幕 `.srt`、重点时间戳 `video_markers.json` 和章节说明
- 使用 MoviePy 进行字幕过滤剪辑、敏感词片段移除和多视频合成
- 在没有 API Key 时使用 Mock 模式跑完整流程
- 输出运行报告，便于答辩展示和问题排查

## 技术栈

- Python 3.10+
- Streamlit
- python-docx
- PyMuPDF
- python-pptx
- Graphviz
- OpenAI Python SDK
- python-dotenv
- pytest

## 目录结构

```text
.
├── app.py
├── agent_graph.py
├── config.py
├── requirements.txt
├── README.md
├── .env.example
├── tools/
├── prompts/
├── uploads/
├── output/
└── tests/
```

## 安装方法

```bash
pip install -r requirements.txt
```

如果需要生成 PNG 思维导图，除了安装 Python 的 `graphviz` 包，系统中还需要安装 Graphviz 可执行程序并确保 `dot` 命令可用。未安装系统 Graphviz 时，程序不会崩溃，会自动退化为输出 `output/mindmap.mmd` Mermaid 文本。

## 运行方法

```bash
streamlit run app.py
```

打开页面后，上传课程资料，输入任务目标，点击“运行 Agent”即可查看日志、中间结果和下载文件。

## API Key 配置

复制 `.env.example` 为 `.env`，按需填写：

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.4-mini
MOCK_MODE=true
LLM_PROVIDER=openai
LLM_API_TYPE=auto
LLM_TIMEOUT=60
```

`MOCK_MODE=true` 时不会调用真实 API。`MOCK_MODE=false` 且配置了 `OPENAI_API_KEY` 后，系统会优先使用 OpenAI Responses API 和 Structured Outputs 生成 JSON；如果兼容平台不支持 Responses API，会回退到 Chat Completions。API 调用失败或 JSON 解析失败时会回退到本地规则结果，保证主流程稳定。

推荐配置：

- 默认性价比：`OPENAI_MODEL=gpt-5.4-mini`
- 更高质量：`OPENAI_MODEL=gpt-5.5`
- OpenAI 官方：`OPENAI_BASE_URL=https://api.openai.com/v1`
- 兼容平台：填写对应平台的 OpenAI-compatible base URL

Gemini 配置示例：

```env
LLM_PROVIDER=gemini
OPENAI_API_KEY=your_google_ai_studio_key_here
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
OPENAI_MODEL=gemini-2.5-flash
MOCK_MODE=false
LLM_API_TYPE=chat_completions
LLM_TIMEOUT=60
```

## Mock 模式说明

Mock 模式会返回固定的任务计划、摘要、关键词、思维导图、大纲和讲稿，但仍会真实生成以下文件：

- `output/summary.md`
- `output/keywords.json`
- `output/mindmap.json`
- `output/mindmap.png` 或 `output/mindmap.mmd`
- `output/ppt_outline.json`
- `output/speech_script.md`
- `output/generated_presentation.pptx`
- `output/final_video.mp4`
- `output/subtitles.srt`
- `output/video_markers.json`
- `output/video_chapters.md`
- `output/run_report.md`

## 课堂视频分析工作台

页面底部提供课堂视频分析工作台，用于把老师课程录屏或已有课程视频转成可复习材料。讲解视频生成已放在上方一键工作流中：

- 课堂视频分析：上传视频，可选上传 `.srt` 字幕；系统会生成课程摘要、核心知识点、思维导图、重点时间戳和 Highlight 重点片段。
- 字幕识别：未上传 `.srt` 时会尝试调用本地 `faster-whisper` 转录；如果当前环境未安装或磁盘空间不足，可先上传 SRT 使用分析功能。
- Agent 生成视频时会同步输出字幕、重点时间戳和章节文件，便于后续剪辑和答辩说明。

## 示例使用流程

1. 运行 `streamlit run app.py`
2. 上传一份课程资料
3. 输入“请把这份课程资料整理成 5 分钟答辩 PPT，并生成摘要、关键词、思维导图和每页讲稿。”
4. 点击“运行 Agent”
5. 查看任务计划、摘要、关键词、思维导图、PPT 大纲和讲稿
6. 下载 PPT 和运行报告

## 答辩演示建议

- 先说明项目不是普通聊天机器人，而是一个固定流程的课程资料处理 Agent
- 展示 `agent_graph.py` 中的节点流转和 `AgentState`
- 演示 Mock 模式，证明无 API Key 时也能稳定运行
- 展示 `output/` 中的结构化结果和最终 PPT
- 说明后续可扩展真实模型、语音生成和讲解视频

## 常见问题

**没有 API Key 能运行吗？**

可以。默认 `MOCK_MODE=true`，会跑完整流程并生成真实文件。

**为什么没有 mindmap.png？**

通常是系统未安装 Graphviz 可执行程序。程序会自动生成 `output/mindmap.mmd`，可以复制到支持 Mermaid 的编辑器中查看。

**PDF 读取失败怎么办？**

请确认安装了 `pymupdf`，并确认 PDF 不是纯扫描图片。如果是扫描件，需要额外 OCR 功能，本项目 MVP 暂未包含。

**PPT 里讲稿在哪里？**

系统会生成 `output/speech_script.md`。同时会尽力写入 PPT speaker notes，但不同环境对 notes 支持不完全一致，答辩时建议以 Markdown 讲稿文件为准。
