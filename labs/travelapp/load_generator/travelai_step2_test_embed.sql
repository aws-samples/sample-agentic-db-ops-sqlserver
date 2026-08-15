USE TravelAI;
GO

DECLARE @vec VECTOR(1024);
EXEC dbo.usp_BedrockEmbedText 
    @text = 'tropical beach with snorkeling and coral reefs', 
    @vector = @vec OUTPUT;

SELECT DATALENGTH(@vec) AS VectorBytes;
GO
