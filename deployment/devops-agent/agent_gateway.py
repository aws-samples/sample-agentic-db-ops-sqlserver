"""
Connect to AgentCore Gateway and verify SQL Server diagnostic tools work end-to-end.

Usage:
    python3 agent_gateway.py

Requires gateway_config.json (created by deploy_gateway.sh).
"""

import json

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient


def main():
    with open("gateway_config.json", "r") as f:
        config = json.load(f)

    print("Connecting to AgentCore Gateway...")
    client = GatewayClient(region_name=config["region"])
    access_token = client.get_access_token_for_cognito(config["client_info"])

    mcp_client = MCPClient(
        lambda: streamablehttp_client(
            config["gateway_url"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
    )

    with mcp_client:
        tools = mcp_client.list_tools_sync()
        print(f"Connected! {len(tools)} tools available via Gateway.\n")

        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-6",
            region_name=config["region"],
            streaming=True,
        )
        agent = Agent(model=model, tools=tools)

        print("Gateway Agent - Ask questions about your SQL Server database.")
        print("Type 'exit' or 'quit' to end.\n")

        while True:
            try:
                prompt = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if prompt.lower() in ("exit", "quit", ""):
                break
            response = agent(prompt)
            print(response.message["content"][0]["text"])
            print()

    print("Goodbye!")


if __name__ == "__main__":
    main()
