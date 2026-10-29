# Mini Agent Notebook

用 **OpenAI Python SDK + 自定义 OpenAI 兼容接口**，逐步理解 Agent。

[打开 Notebook](mini_agent.ipynb)：LLM → Prompt → Function Calling/Tool → ReAct → MCP → Skill → Compaction。

## 运行

Python 3.11+。在项目根目录启动 Jupyter，依次运行单元：

```bash
git clone https://github.com/Jiang-Ciel/mini-agent-notebook.git
cd mini-agent-notebook
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export OPENAI_BASE_URL="https://your-model-endpoint.example/v1"
export OPENAI_API_KEY="你的 Key"
export OPENAI_MODEL="支持工具调用的模型名"
python -m jupyterlab mini_agent.ipynb
```

`base_url` 是接口根路径，不要填 `/chat/completions`。接口需支持 Chat Completions、tool_calls 和 tool 消息；不支持 function calling 时，第 3 步起无法运行。Key 只放环境变量，不提交输出或凭据；Notebook 不自动读取 `.env`。

## 内容

| 概念 | 最小实现 |
|---|---|
| LLM / Prompt | 模型 API 调用与 system 消息 |
| Function Calling / Tool | schema、参数校验、执行、结果回传 |
| ReAct | 有上限的决策—行动—观察循环 |
| MCP | 本地 stdio server，发现并调用乘法工具 |
| Skill | 白名单加载可信 Markdown 操作规则 |
| Compaction | 摘要旧完整轮次，保留最近两轮 |

MCP server 自动启动，无需另开终端。Skill 是教学简化，不包含自动发现。Compaction 是应用层摘要，不是专有端点，也不是精确 token 门禁。仅演示只读算术，不用于未经改造的生产系统。

## 验证

```bash
python -m unittest discover -s tests -v
```

离线测试不访问模型服务，使用模拟响应；MCP 测试启动真实子进程。真实接口的权限、兼容性和回答效果需配置后自行验证。API 调用与摘要均有费用。

提交前清空 Notebook 输出：

```bash
python -m jupyter nbconvert --clear-output --inplace mini_agent.ipynb
```
