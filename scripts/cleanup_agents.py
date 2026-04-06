#!/usr/bin/env python3
"""Clean up all deployed AgentCore agents using boto3 API directly."""
import boto3
import sys
import time
import os

REGION = os.environ.get("AWS_REGION", "us-east-1")
AGENT_NAMES = [
    "database_health_agent",
    "query_performance_agent",
    "security_audit_agent",
    "data_lifecycle_agent",
    "supervisor_agent",
]


def main():
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # List all agent runtimes
    print("Fetching agent runtimes...\n")
    runtimes = []
    next_token = None
    while True:
        kwargs = {"maxResults": 50}
        if next_token:
            kwargs["nextToken"] = next_token
        resp = client.list_agent_runtimes(**kwargs)
        runtimes.extend(resp.get("agentRuntimes", []))
        next_token = resp.get("nextToken")
        if not next_token:
            break

    # Filter to our agents
    our_agents = [r for r in runtimes if r["agentRuntimeName"] in AGENT_NAMES]

    # Collect memory IDs from agent runtime configs, then delete agents
    memory_ids = set()

    if not our_agents:
        print("No deployed agents found.")
    else:
        print(f"Found {len(our_agents)} agent(s) to remove:\n")
        for agent in our_agents:
            print(f"  - {agent['agentRuntimeName']} ({agent['agentRuntimeId']}) [{agent.get('status', 'unknown')}]")
        print()

        for agent in our_agents:
            runtime_id = agent["agentRuntimeId"]
            name = agent["agentRuntimeName"]

            # Get memory associated with this agent before deleting it
            try:
                detail = client.get_agent_runtime(agentRuntimeId=runtime_id)
                # environmentVariables is a dict, e.g. {"MEMORY_ID": "...", "AWS_REGION": "..."}
                env_vars = detail.get("environmentVariables", {})
                mem_id = env_vars.get("MEMORY_ID") or env_vars.get("BEDROCK_AGENTCORE_MEMORY_ID")
                if mem_id:
                    memory_ids.add(mem_id)
                # Also check nested config patterns
                mem_cfg = detail.get("memoryConfiguration", {})
                if mem_cfg.get("memoryId"):
                    memory_ids.add(mem_cfg["memoryId"])
            except Exception:
                pass

            try:
                print(f"  Deleting agent runtime {name} ({runtime_id})...")
                client.delete_agent_runtime(agentRuntimeId=runtime_id)
                print(f"  ✅ {name} deleted")
            except Exception as e:
                print(f"  ⚠️  Error deleting {name}: {e}")

            print()

    # Delete memories found on the agent runtimes
    if memory_ids:
        print(f"Found {len(memory_ids)} memory(s) associated with agents:\n")
        for mem_id in memory_ids:
            try:
                status = client.get_memory(memoryId=mem_id).get("memory", {}).get("status", "")
                if status == "DELETING":
                    print(f"  Memory {mem_id} already deleting, skipping")
                    continue
                print(f"  Deleting memory {mem_id}...")
                client.delete_memory(memoryId=mem_id)
                print(f"  ✅ Memory deleted")
            except client.exceptions.ResourceNotFoundException:
                print(f"  Memory {mem_id} not found (already deleted)")
            except Exception as e:
                print(f"  ⚠️  Error deleting memory {mem_id}: {e}")
    else:
        print("No memories associated with agents.")

    # ENI notice
    print()
    print("  ℹ️  Note: AgentCore VPC ENIs are shared resources and may persist")
    print("     in your VPC for up to 8 hours after agent deletion.")
    print("     They will be automatically removed — no manual action needed.")
    print("     If deleting the VPC/subnet via CloudFormation, use --retain-resources")
    print("     for the subnet and security group, then retry after ENIs are released.")

    print("\n✅ Cleanup complete")


if __name__ == "__main__":
    main()
