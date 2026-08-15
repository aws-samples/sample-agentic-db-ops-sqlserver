#!/usr/bin/env python3
"""
Populate VECTOR(1024) embeddings in TravelAI using Amazon Bedrock Titan V2.
Reads destination descriptions and document chunks, generates embeddings,
and writes them back to SQL Server as VECTOR(1024) columns.

Usage:
    cd /workshop/labs/travelapp
    python3 populate_embeddings.py
"""
import pymssql
import json
import boto3
import os
import time

region = os.environ.get('AWS_REGION', 'us-west-2')
secret_id = os.environ.get('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')

# Get database credentials
sm = boto3.client('secretsmanager', region_name=region)
creds = json.loads(sm.get_secret_value(SecretId=secret_id)['SecretString'])

# Bedrock client
bedrock = boto3.client('bedrock-runtime', region_name=region)


def get_embedding(text):
    """Call Bedrock Titan V2 to get a 1024-dim embedding."""
    resp = bedrock.invoke_model(
        modelId='amazon.titan-embed-text-v2:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({'inputText': text[:8000], 'dimensions': 1024})
    )
    result = json.loads(resp['body'].read())
    return result['embedding']


def main():
    conn = pymssql.connect(
        server=creds['host'], user=creds['username'],
        password=creds['password'], port=int(creds['port']),
        database='TravelAI'
    )
    conn.autocommit(True)
    cur = conn.cursor()

    # Ensure embedding column exists on Destinations
    cur.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME='Destinations' AND COLUMN_NAME='description_vector'
        )
        ALTER TABLE Destinations ADD description_vector VECTOR(1024) NULL
    """)

    # Populate Destinations
    cur2 = conn.cursor(as_dict=True)
    cur2.execute("SELECT destination_id, name, description FROM Destinations WHERE description_vector IS NULL")
    rows = cur2.fetchall()
    print(f"\nDestinations to embed: {len(rows)}")
    print("-" * 40)

    for i, row in enumerate(rows, 1):
        text = f"{row['name']}. {row['description']}"
        emb = get_embedding(text)
        vec_json = json.dumps(emb)
        cur.execute(f"UPDATE Destinations SET description_vector = CAST('{vec_json}' AS VECTOR(1024)) WHERE destination_id = {row['destination_id']}")
        print(f"  [{i}/{len(rows)}] {row['name']} - embedded")
        time.sleep(0.2)  # Rate limiting

    # Populate DocumentChunks
    cur2.execute("SELECT chunk_id, section_path, content FROM DocumentChunks WHERE content_vector IS NULL")
    rows = cur2.fetchall()
    print(f"\nDocumentChunks to embed: {len(rows)}")
    print("-" * 40)

    for i, row in enumerate(rows, 1):
        text = f"{row['section_path'] or 'chunk'}. {row['content']}"
        emb = get_embedding(text)
        vec_json = json.dumps(emb)
        cur.execute(f"UPDATE DocumentChunks SET content_vector = CAST('{vec_json}' AS VECTOR(1024)) WHERE chunk_id = {row['chunk_id']}")
        print(f"  [{i}/{len(rows)}] {row['section_path'] or 'chunk'} - embedded")
        time.sleep(0.2)

    # Verify
    cur.execute("SELECT COUNT(*) FROM Destinations WHERE description_vector IS NOT NULL")
    dest_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM DocumentChunks WHERE content_vector IS NOT NULL")
    chunk_count = cur.fetchone()[0]

    print(f"\n{'=' * 40}")
    print(f"DONE! Embeddings populated:")
    print(f"  Destinations: {dest_count}")
    print(f"  DocumentChunks: {chunk_count}")
    print(f"  Total: {dest_count + chunk_count}")
    print(f"\nVector search is now active in the UI!")
    print(f"Try searching: https://your-cloudfront-url/app/")

    conn.close()


if __name__ == '__main__':
    main()
