# Open WebUI tool: web search through n8n

[tool-n8n-connection.py](tool-n8n-connection.py) is an [Open WebUI tool](https://docs.openwebui.com/features/plugin/tools/) that lets a chat model call the n8n web-search agent from [examples/n8n](../../examples/n8n/README.md). The model decides when it needs fresh information, calls the tool, and uses the agent's answer in its reply.

![Open WebUI calling the search tool](../../docs/images/open-webui-chat.png)

```
You -> Open WebUI model -> tool: search_web_via_n8n -> n8n webhook -> AI Agent -> SearXNG
                        <-------------------------- {"output": "..."} <---------'
```

## Prerequisites

- The stack is running (`docker compose up -d`).
- The [n8n workflow](../../examples/n8n/README.md) is imported, has its credentials set, and is **active**.
- The model you chat with supports tool calling.

## Install

Menu names can differ slightly between Open WebUI versions.

1. In Open WebUI (http://localhost:3000), go to **Workspace > Tools** and click **+** to create a tool.
2. Paste the contents of [tool-n8n-connection.py](tool-n8n-connection.py) and save.
3. Attach it to a model. Either:
   - **Workspace > Models**: create or edit a model, choose your base model, and tick the tool under **Tools**. Then chat with that model; or
   - in a chat, open the **+** menu in the message box and enable the tool for that conversation.
4. Ask something that needs current information, for example: *"What are the top 3 AI or tech news stories from today? Give a one-line summary of each with the source."* Open WebUI shows a **View Result from search_web_via_n8n** entry when the tool runs.

## Recommended model system prompt

The n8n agent writes the search result, but the Open WebUI model writes the final reply, and models tend to shorten "Source: [Reuters](https://...)" to just "(Reuters)". In the model's settings (*Workspace > Models > edit > System Prompt*), add:

```
You have a web search tool. Use it for anything that needs current information.
When the tool result contains source links, keep them as markdown links with their
full URLs in your answer. Never drop, shorten or invent links.
```

## How it works

- The tool sends `POST http://n8n_automation:5678/webhook/ai-agent-search` with this JSON body:

  ```json
  { "chat_input": "<the model's query>", "session_id": "<Open WebUI chat id>", "source": "open_webui_tool" }
  ```

- `session_id` is the Open WebUI chat ID, so every chat gets its own conversation memory in n8n's Postgres.
- n8n answers with `{"output": "<text>"}`, and the tool returns that text to the model.
- `n8n_automation` is the n8n container name. It resolves only because Open WebUI and n8n share the compose network.
- The request times out after 60 seconds by default.

## Settings

The webhook URL and the timeout are tool settings (Open WebUI calls them *Valves*), so you can change them without editing the code: in **Workspace > Tools**, click the gear icon next to the tool.

| Setting | Default | Change it when |
|---|---|---|
| `n8n_webhook_url` | `http://n8n_automation:5678/webhook/ai-agent-search` | n8n runs outside this compose stack, or you renamed the webhook path. |
| `timeout_seconds` | `60` | Your model or searches are slow and requests time out. |
| `auth_header_name` / `auth_header_value` | empty | The n8n webhook uses *Header Auth*. The tool then sends this header with every request. Leave both empty if the webhook has no authentication. |

## Troubleshooting

The tool returns these messages to the model, so you will see them in the chat.

| Message | Likely cause |
|---|---|
| `returned status code 401` or `403` | The webhook requires Header Auth, and `auth_header_name` / `auth_header_value` are empty or do not match the n8n credential. |
| `returned status code 404` | The n8n workflow is not active, or the webhook path is not `ai-agent-search`. Production URLs work only when the workflow is active. |
| `returned status code 500` | The workflow ran and failed. Open the execution in n8n to see which node errored, often a missing credential or a model that does not exist. |
| `n8n returned an empty response` | The **Respond to Webhook** node did not run, or the workflow's response mode was changed. |
| `The web search is taking too long` | The model or search was slow. Try a more specific query, a faster model, or raise `timeout_seconds` in the tool settings. |
| `An error occurred ... Connection refused / Name not known` | Open WebUI cannot reach `n8n_automation:5678`. Check that both containers are running and on the same compose network. |
| The model never calls the tool | The model may not support tool calling, or needs native function calling enabled in the model's advanced parameters. |
