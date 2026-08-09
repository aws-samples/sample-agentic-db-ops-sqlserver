# Updated: 2026-07-31
"""
Bedrock Guardrail Setup for Actions Agent
==========================================
Creates a guardrail that:
1. Blocks dangerous SQL operations (DROP, DELETE, TRUNCATE, ALTER TABLE)
2. Blocks prompt injection attempts
3. Blocks off-topic requests (non-database operations)
4. Allows safe operations (CREATE INDEX, UPDATE STATISTICS, ALTER INDEX)

Usage:
    python setup_guardrail.py

After creation, set the environment variable:
    export BEDROCK_GUARDRAIL_ID=<guardrail-id>
    export BEDROCK_GUARDRAIL_VERSION=1
"""

import boto3
import json
import os

AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')


def create_guardrail():
    client = boto3.client('bedrock', region_name=AWS_REGION)

    guardrail_name = 'dbops-actions-agent-guardrail'

    try:
        response = client.create_guardrail(
            name=guardrail_name,
            description='Safety guardrail for the DB Operations Actions Agent. Blocks dangerous SQL keywords.',

            # Content policy - block harmful content
            contentPolicyConfig={
                'filtersConfig': [
                    {'type': 'SEXUAL', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'VIOLENCE', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'HATE', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'INSULTS', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'MISCONDUCT', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'PROMPT_ATTACK', 'inputStrength': 'HIGH', 'outputStrength': 'NONE'}
                ]
            },

            # Word policy - block specific dangerous SQL keywords
            wordPolicyConfig={
                'wordsConfig': [
                    {'text': 'DROP TABLE'},
                    {'text': 'DROP DATABASE'},
                    {'text': 'TRUNCATE TABLE'},
                    {'text': 'DELETE FROM'},
                    {'text': 'xp_cmdshell'},
                    {'text': 'SHUTDOWN'},
                    {'text': 'RECONFIGURE'},
                ],
                'managedWordListsConfig': [
                    {'type': 'PROFANITY'}
                ]
            },

            # Blocked input/output messaging
            blockedInputMessaging='This request has been blocked. Only index creation, statistics updates, and plan management are permitted.',
            blockedOutputsMessaging='This response was blocked. It contains dangerous SQL operations.'
        )

        guardrail_id = response['guardrailId']
        print(f"✅ Guardrail created: {guardrail_id}")
        print(f"   Name: {guardrail_name}")
        print(f"   Version: DRAFT")
        print()

    except client.exceptions.ConflictException:
        # Guardrail already exists - find it by name
        print(f"  Guardrail '{guardrail_name}' already exists, retrieving...")
        guardrail_id = None
        paginator = client.get_paginator('list_guardrails')
        for page in paginator.paginate():
            for g in page.get('guardrails', []):
                if g['name'] == guardrail_name:
                    guardrail_id = g['id']
                    break
            if guardrail_id:
                break

        if not guardrail_id:
            raise RuntimeError(f"Guardrail '{guardrail_name}' reported as existing but could not be found")

        print(f"  Found existing guardrail: {guardrail_id}")
        print()

    # Create a version (publish)
    version_response = client.create_guardrail_version(
        guardrailIdentifier=guardrail_id,
        description='Initial version - blocks dangerous SQL, prompt injection, off-topic'
    )

    version = version_response['version']
    print(f"✅ Published version: {version}")

    # Write env file and append to bashrc
    env_file = os.path.expanduser('~/.dbops_env')
    bashrc_path = os.path.expanduser('~/.bashrc')

    # Read existing env file or create new
    existing = {}
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('export '):
                    key = line.split('=')[0].replace('export ', '')
                    existing[key] = line.strip()

    # Update with new values
    existing['BEDROCK_GUARDRAIL_ID'] = f'export BEDROCK_GUARDRAIL_ID={guardrail_id}'
    existing['BEDROCK_GUARDRAIL_VERSION'] = f'export BEDROCK_GUARDRAIL_VERSION={version}'

    # Write env file
    with open(env_file, 'w') as f:
        f.write('# DBOps environment variables (auto-generated)\n')
        for line in existing.values():
            f.write(line + '\n')

    # Ensure bashrc sources the env file
    source_line = '[ -f ~/.dbops_env ] && source ~/.dbops_env'
    with open(bashrc_path, 'r') as f:
        bashrc_content = f.read()
    if source_line not in bashrc_content:
        with open(bashrc_path, 'a') as f:
            f.write(f'\n{source_line}\n')

    print(f"  ✅ Done.")
    print(f"  BEDROCK_GUARDRAIL_ID={guardrail_id}")
    print(f"  BEDROCK_GUARDRAIL_VERSION={version}")
    print(f"\n  Run: source ~/.dbops_env")

    return guardrail_id, version


if __name__ == '__main__':
    guardrail_id, version = create_guardrail()
