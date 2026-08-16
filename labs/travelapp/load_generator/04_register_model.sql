-- Register Bedrock Embedding Model via API Gateway proxy
-- NOTE: Replace <API_GATEWAY_URL> with the endpoint from 03_deploy_embedding_proxy.py
-- Usage: python3.11 run_sql_file.py load_generator/04_register_model.sql
USE TravelAI;
GO

-- Create credential for API Gateway (no auth needed, just a placeholder header)
IF EXISTS (SELECT 1 FROM sys.database_scoped_credentials WHERE name LIKE '%execute-api%')
BEGIN
    -- Drop model first if exists
    IF EXISTS (SELECT 1 FROM sys.external_models WHERE name = 'bedrock_embed')
        DROP EXTERNAL MODEL bedrock_embed;
    
    DECLARE @cred_name NVARCHAR(500);
    SELECT @cred_name = name FROM sys.database_scoped_credentials WHERE name LIKE '%execute-api%';
    EXEC('DROP DATABASE SCOPED CREDENTIAL [' + @cred_name + ']');
END
GO

-- Read endpoint from file (written by 03_deploy_embedding_proxy.py)
-- For manual setup, replace the URL below with your API Gateway endpoint
DECLARE @endpoint NVARCHAR(500) = N'<API_GATEWAY_URL>';

-- Create credential
DECLARE @sql NVARCHAR(MAX) = N'
CREATE DATABASE SCOPED CREDENTIAL [' + @endpoint + N']
WITH IDENTITY = ''HTTPEndpointHeaders'',
     SECRET = ''{"x-api-key":"none"}''';
EXEC sp_executesql @sql;

-- Create external model
SET @sql = N'
CREATE EXTERNAL MODEL bedrock_embed
WITH (
    LOCATION = ''' + @endpoint + N''',
    API_FORMAT = ''OpenAI'',
    MODEL_TYPE = EMBEDDINGS,
    MODEL = ''amazon.titan-embed-text-v2'',
    CREDENTIAL = [' + @endpoint + N']
)';
EXEC sp_executesql @sql;

PRINT 'External model bedrock_embed registered successfully';
PRINT 'Test: SELECT DATALENGTH(AI_GENERATE_EMBEDDINGS(N''hello'' USE MODEL bedrock_embed))';
GO
