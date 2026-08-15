/*==============================================================================
  Travel Site - Gen-AI / Agentic Hybrid Retrieval  (Amazon RDS SQL Server 2025
  + Amazon Bedrock)

  FILE 01 of 05 : PREREQUISITES + AMAZON BEDROCK CREDENTIAL

  DEPLOYMENT ORDER
    01_prerequisites.sql        <-- you are here  (EDIT the secrets in this file)
    02_create_schema.sql        tables + table types
    03_indexes_and_fulltext.sql full-text catalog/indexes + b-tree indexes
    04_programmability.sql      embedding helpers, retrieval/rerank procs, view
    05_seed_data.sql            sample rows + 117 document chunks
    (then run the Bedrock embed procs; see 04 / README)

  BEFORE RUNNING (AWS / RDS prerequisites - see README):
    * RDS custom parameter group with "external rest endpoint enabled" = 1
      (family sqlserver-ee-17.0), applied + instance rebooted.
    * Network egress from the RDS instance to
      bedrock-runtime.<region>.amazonaws.com on port 443.
    * Bedrock model access enabled for Titan Text Embeddings V2, your Claude
      model, and Cohere Rerank.
    * A Bedrock API key. NOTE: model-catalog API keys expire after 12 hours;
      rotate the credential via a SQL Agent job / scheduler.

  Models used (invoked with sys.sp_invoke_external_rest_endpoint, no middleware):
    * Embeddings ..... amazon.titan-embed-text-v2:0     -> 1024-dim vectors
    * Chat / reason .. us.anthropic.claude-sonnet-4-6   (Converse API)
    * Reranking ...... cohere.rerank-v3-5:0

  WHY EMBEDDINGS GO THROUGH sp_invoke_external_rest_endpoint (not AI_GENERATE_EMBEDDINGS):
    CREATE EXTERNAL MODEL / AI_GENERATE_EMBEDDINGS only accept API_FORMAT of
    'Azure OpenAI', 'OpenAI', 'Ollama' or 'ONNX Runtime' (Microsoft Learn,
    ver17). Amazon Bedrock is NOT one of those formats, so 04 generates
    embeddings by calling the Bedrock InvokeModel REST endpoint directly and
    CAST-ing the returned JSON array to VECTOR.
==============================================================================*/

/*------------------------------------------------------------------------------
  0. DATABASE + PREREQUISITES
------------------------------------------------------------------------------*/
IF DB_ID(N'TravelAI') IS NULL
    CREATE DATABASE TravelAI;
GO
ALTER DATABASE TravelAI SET COMPATIBILITY_LEVEL = 170;  -- SQL Server 2025
GO
USE TravelAI;
GO

-- Required only for the OPTIONAL preview vector index (file 03) and
-- VECTOR_SEARCH. Exact VECTOR_DISTANCE kNN (the default retrieval path) is GA
-- and does not need this. Safe to leave ON.
ALTER DATABASE SCOPED CONFIGURATION SET PREVIEW_FEATURES = ON;
GO

-- Embedding dimensionality is set to match Amazon Titan Text Embeddings V2.
--   amazon.titan-embed-text-v2:0 => 1024 (default; also supports 256 / 512)
--   cohere.embed-english-v3       => 1024
-- (Change every VECTOR(1024) in file 02/04 if you pick a model with different
--  dims, and update the "dimensions" value in dbo.usp_BedrockEmbedText.)


/*------------------------------------------------------------------------------
  1. AMAZON BEDROCK ACCESS (secure credential)
     Every model call (embeddings, chat, rerank) is made with
     sys.sp_invoke_external_rest_endpoint against the Bedrock runtime endpoint,
     authenticated by a single DATABASE SCOPED CREDENTIAL whose SECRET is
     injected as HTTP headers. The key is encrypted at rest by the master key
     and never appears in query text, plan cache, or logs.
------------------------------------------------------------------------------*/

-- One-time: master key encrypts all database scoped credentials in this DB.
IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys WHERE name = N'##MS_DatabaseMasterKey##')
    CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'<StrongPassword-change-me>';
GO

-- One credential covers embeddings, chat and rerank: they share the host
-- bedrock-runtime.<region>.amazonaws.com. The credential NAME must be a URL
-- that is a prefix (more generic) of every endpoint URL it is used for.
-- Replace us-west-2 with your Region in BOTH the name here AND every @url in
-- file 04 if you deploy elsewhere.
IF NOT EXISTS (SELECT 1 FROM sys.database_scoped_credentials
               WHERE name = N'https://bedrock-runtime.us-west-2.amazonaws.com')
    CREATE DATABASE SCOPED CREDENTIAL [https://bedrock-runtime.us-west-2.amazonaws.com]
        WITH IDENTITY = 'HTTPEndpointHeaders',
             SECRET   = '{"Authorization":"Bearer <YOUR_BEDROCK_API_KEY>"}';
GO

/*
  Model endpoints invoked in file 04 (all POST to bedrock-runtime):
    Embeddings : /model/amazon.titan-embed-text-v2:0/invoke
    Chat       : /model/us.anthropic.claude-sonnet-4-6/converse   (orchestration)
    Rerank     : /model/cohere.rerank-v3-5:0/invoke
  Adjust model IDs / Region to match what you have enabled in Bedrock.
*/
GO
