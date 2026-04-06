#!/usr/bin/env python3
"""Create shared AgentCore Memory with semantic + summarization strategies."""
import boto3
import os
import random
import sys
import time

REGION = os.environ.get("AWS_REGION", "us-east-1")
MEMORY_NAME = f"dbops_shared_memory_{random.randint(1000, 9999)}"

def log(msg):
    """Print to stderr so it streams immediately when stdout is captured."""
    print(msg, file=sys.stderr, flush=True)


def wait_for_active(client, memory_id, timeout=600):
    """Wait for memory to reach ACTIVE status."""
    start = time.time()
    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        try:
            resp = client.get_memory(memoryId=memory_id)
            status = resp.get("memory", {}).get("status") or resp.get("status", "UNKNOWN")
        except Exception as e:
            log(f"  ⚠️  get_memory error ({elapsed}s elapsed): {e}")
            time.sleep(10)
            continue
        if status == "ACTIVE":
            log(f"  ✅ Memory is ACTIVE (took {elapsed}s)")
            return True
        if status in ("FAILED", "DELETE_FAILED"):
            log(f"  ❌ Memory entered {status} state")
            return False
        log(f"  ⏳ Memory: {status} ({elapsed}s elapsed)")
        time.sleep(10)
    log(f"  ❌ Timeout after {timeout}s waiting for memory to become ACTIVE")
    return False


def main():
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    log(f"Creating shared memory '{MEMORY_NAME}' with semantic + summarization strategies...")
    resp = client.create_memory(
        name=MEMORY_NAME,
        description="Shared memory for all DBOps agents - semantic extraction + session summarization",
        eventExpiryDuration=365,
        memoryStrategies=[
            {
                "semanticMemoryStrategy": {
                    "name": "dbops_semantic",
                    "description": "Extract and store database operational facts across all agents",
                    "namespaces": ["dbops"],
                }
            },
            {
                "summaryMemoryStrategy": {
                    "name": "dbops_summarization",
                    "description": "Summarize investigation sessions for cross-agent recall",
                    "namespaces": ["dbops/{sessionId}"],
                }
            },
        ],
    )

    mem_id = resp.get("memoryId") or resp.get("memory", {}).get("id") or resp.get("id")
    if not mem_id:
        log(f"  [DEBUG] create_memory response keys: {list(resp.keys())}")
        memories = client.list_memories().get("memories", [])
        for m in memories:
            if MEMORY_NAME in m.get("id", "") and m.get("status") != "DELETING":
                mem_id = m["id"]
                break
    if not mem_id:
        log("  ❌ Could not determine memory ID from create response")
        sys.exit(1)
    log(f"  Created: {mem_id}")
    log(f"  Waiting for ACTIVE status (may take 30-180 seconds)...")

    if wait_for_active(client, mem_id):
        log(f"✅ Shared memory ready: {mem_id}")
        return mem_id
    else:
        sys.exit(1)


if __name__ == "__main__":
    mem_id = main()
    # Only this line goes to stdout — everything else went to stderr
    print(f"MEMORY_ID={mem_id}")
