USE TravelAI;
GO

CREATE OR ALTER PROCEDURE dbo.usp_BedrockEmbedText
    @InputText NVARCHAR(4000),
    @EmbeddingVector VECTOR(1024) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @url NVARCHAR(500) = N'https://bedrock-runtime.us-west-2.amazonaws.com/model/amazon.titan-embed-text-v2:0/invoke';
    DECLARE @payload NVARCHAR(MAX) = N'{"inputText":"' + STRING_ESCAPE(@InputText, 'json') + N'","dimensions":1024,"normalize":true}';
    DECLARE @response NVARCHAR(MAX);
    
    EXEC sys.sp_invoke_external_rest_endpoint
        @url = @url,
        @method = 'POST',
        @credential = [https://bedrock-runtime.us-west-2.amazonaws.com],
        @payload = @payload,
        @response = @response OUTPUT;
    
    SET @EmbeddingVector = CAST(JSON_QUERY(@response, '$.result.embedding') AS VECTOR(1024));
END;
GO

PRINT 'Created usp_BedrockEmbedText';
GO
