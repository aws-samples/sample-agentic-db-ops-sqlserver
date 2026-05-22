"""
Connect to AgentCore Gateway and verify SQL Server diagnostic tools work end-to-end.

Usage:
    python3 agent_gateway.py              # IAM SigV4 auth (default)
    python3 agent_gateway.py --cognito    # Cognito OAuth

Requires gateway_config.json (created by setup_gateway.py).
"""

import json
import sys

import httpx
import botocore.session
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client


class SigV4AuthHttpx(httpx.Auth):
    """httpx Auth that signs every request with SigV4."""
    requires_request_body = True

    def __init__(self, region):
        self.region = region
        session = botocore.session.get_session()
        self.credentials = session.get_credentials().get_frozen_credentials()

    def auth_flow(self, request):
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            headers={"Content-Type": request.headers.get("content-type", "application/json")},
            data=request.content or b"",
        )
        SigV4Auth(self.credentials, "bedrock-agentcore", self.region).add_auth(aws_request)
        for key, val in aws_request.headers.items():
            request.headers[key] = val
        yield request


def main():
    use_cognito = "--cognito" in sys.argv

    with open("gateway_config.json", "r") as f:
        config = json.load(f)

    region = config["region"]
    gateway_url = config["gateway_url"]

    if use_cognito:
        from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
        print("Connecting to AgentCore Gateway (Cognito OAuth)...")
        client = GatewayClient(region_name=region)
        access_token = client.get_access_token_for_cognito(config["client_info"])
        mcp_client = MCPClient(
            lambda: streamablehttp_client(
                gateway_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        )
    else:
        print("Connecting to AgentCore Gateway (IAM auth)...")
        mcp_client = MCPClient(
            lambda: streamablehttp_client(gateway_url, auth=SigV4AuthHttpx(region))
        )

    with mcp_client:
        tools = mcp_client.list_tools_sync()
        print(f"Connected! {len(tools)} tools available via Gateway.\n")

        model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-6",
            region_name=region,
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
