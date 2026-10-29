# Mini Agent Notebook

用 **OpenAI Python SDK Responses API + 自定义兼容接口**，逐步理解 Agent。

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

`base_url` 是接口根路径，不要填 `/responses`。接口需支持 `/v1/responses`、`function_call` 和 `function_call_output`；仅兼容 Chat Completions 不够。Key 放环境变量或被 Git 忽略的本地 `.env`，Notebook 自动加载 `.env`（已有环境变量优先）；不提交输出或凭据。

## 内容

| 概念 | 最小实现 |
|---|---|
| LLM / Prompt | 模型 API 调用与 system 消息 |
| Function Calling / Tool | 扁平 schema、参数校验、call_id 结果回传 |
| ReAct | 有上限的决策—行动—观察循环 |
| MCP | 本地 stdio server，发现并调用乘法工具 |
| Skill | 白名单加载可信 Markdown 操作规则 |
| Compaction | 摘要旧完整轮次，保留最近两轮 |

使用 `responses.create(input=..., store=False)`，手动保存完整 output（含 reasoning 项），不使用 `previous_response_id`。

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

## 模型服务过载

429/503 仅重试模型请求（最多 4 次），指数退避并尊重 Retry-After；不会重跑已执行的工具。长于 20 秒的服务等待要求直接提示稍后重试。MCP 单一异常组会展开为原始错误，多根因异常仍保留。持续 ServerOverloaded 需等待服务恢复或检查配额/负载；重试不保证解决过载。重试计入本轮 90 秒总超时。

## 观察真实调用

Tool/ReAct/MCP 单元默认打印：LLM 工具 schema → 模型真实 output → 宿主分派 → 本地工具或 MCP tools/call → function_call_output → 下一次 LLM 回答。
MCP 工具对模型仍是普通 function_call，协议请求由宿主执行。日志不显示 Key、隐藏推理或加密载荷；任务参数和结果仍可能敏感，分享前清空输出。
`import tracing; tracing.ENABLED = False` 可关闭展示。

## Request / Response 分区

Notebook 用蓝/绿卡片及同一 `LLM #编号` 配对请求与响应，紫色工具/MCP事件沿用来源编号。Request 展示实际发送的完整 body（含 input 与 tools），JSON 可折叠、滚动查看。凭据、内部推理与加密载荷隐藏；任务文本和结果仍可能敏感。重试沿用本轮编号。终端使用分隔线输出；`tracing.HTML_MODE = False` 可切换为纯文本。
