"""
title: Web search via n8n
"""

import requests
from typing import Optional
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        n8n_webhook_url: str = Field(
            default="http://n8n_automation:5678/webhook/ai-agent-search",
            description="Production URL of the n8n web-search webhook.",
        )
        timeout_seconds: int = Field(
            default=60,
            description="How long to wait for the n8n agent before giving up.",
        )
        auth_header_name: str = Field(
            default="",
            description="Optional. Header name if the n8n webhook uses Header Auth.",
        )
        auth_header_value: str = Field(
            default="",
            description="Optional. Header value if the n8n webhook uses Header Auth.",
        )

    def __init__(self):
        self.valves = self.Valves()

    def search_web_via_n8n(
        self,
        query: str,
        __user__: Optional[dict] = None,
        __chat_id__: Optional[str] = None,
    ) -> str:
        """
        Search the web for real-time information using the n8n AI Agent.
        :param query: The search query to send to the web agent.
        """
        try:
            # Use the Open WebUI chat ID as the n8n session ID, so every chat
            # gets its own memory. Fall back to the user ID, then a fixed string.
            if __chat_id__:
                session_id = __chat_id__
            elif __user__ and isinstance(__user__, dict):
                session_id = f"user_{__user__.get('id', 'unknown')}"
            else:
                session_id = "open_webui_fallback_session"

            payload = {
                "chat_input": query,
                "session_id": str(session_id),
                "source": "open_webui_tool",
            }

            headers = {}
            if self.valves.auth_header_name and self.valves.auth_header_value:
                headers[self.valves.auth_header_name] = self.valves.auth_header_value

            response = requests.post(
                self.valves.n8n_webhook_url,
                json=payload,
                headers=headers,
                timeout=self.valves.timeout_seconds,
            )

            if response.status_code == 200:
                if not response.text.strip():
                    return "Error: n8n returned an empty response."
                try:
                    result = response.json()
                    return result.get(
                        "output", "n8n returned JSON but no 'output' field."
                    )
                except ValueError:
                    return (
                        f"Error: Response was not JSON. Response: {response.text[:100]}"
                    )
            else:
                return f"Error: The web search service returned status code {response.status_code}."

        except requests.exceptions.Timeout:
            return (
                "The web search is taking too long. Please try a more specific query."
            )
        except Exception as e:
            return f"An error occurred while searching the web: {str(e)}"
