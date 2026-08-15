USE TravelAI;
GO

DECLARE @vec VECTOR(1024);
EXEC dbo.usp_BedrockEmbedText 
    @InputText = 'tropical beach with snorkeling and coral reefs', 
    @EmbeddingVector = @vec OUTPUT;

SELECT DATALENGTH(@vec) AS VectorBytes;
GO
