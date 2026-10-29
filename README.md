# Mini Agent Notebook

## 1. Lecture

| Lecture 文件 | 核心 Topic |
|---|---|
| [Mini Agent](lecture/mini_agent.ipynb) | Responses API、LLM、Prompt、Function Calling / Tool、ReAct、MCP、Skill、Compaction；逐轮展示 Request / Response 与实际工具调用 |

## 2. 环境部署与 Notebook 启动

需要 Python 3.11+，以及支持 Responses API 和工具调用的模型接口。

**首次部署：**

```bash
git clone https://github.com/Jiang-Ciel/mini-agent-notebook.git
cd mini-agent-notebook
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

编辑项目根目录的 `.env`，填入自己的接口配置：

```dotenv
OPENAI_BASE_URL=https://your-model-endpoint.example/v1
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=your-model-name
```

接口地址填写根路径，不附加 `/responses`。服务必须支持 Responses API、`function_call` 和 `function_call_output`，仅兼容 Chat Completions 不够。Notebook 自动读取 `.env`，已有环境变量优先；`.env` 不提交 Git，模型调用会产生费用。

**启动 Notebook：**

```bash
cd mini-agent-notebook
source .venv/bin/activate
python -m jupyterlab lecture/mini_agent.ipynb
```

浏览器中选择项目 `.venv` 对应的 Python 内核，按顺序运行单元。MCP 服务自动启动，无需另开终端；修改代码或接口配置后，重启内核再从头运行。
