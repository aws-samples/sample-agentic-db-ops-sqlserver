USE TravelAI;
GO

-- Embed the search query
DECLARE @queryVec VECTOR(1024);
EXEC dbo.usp_BedrockEmbedText 
    @InputText = 'relaxing tropical escape', 
    @EmbeddingVector = @queryVec OUTPUT;

-- Find similar destinations (lower distance = more similar)
SELECT TOP 5
    name, country_code, climate,
    VECTOR_DISTANCE('cosine', description_vector, @queryVec) AS Distance
FROM Destinations
WHERE description_vector IS NOT NULL
ORDER BY VECTOR_DISTANCE('cosine', description_vector, @queryVec) ASC;
GO

-- Adventure query
DECLARE @queryVec2 VECTOR(1024);
EXEC dbo.usp_BedrockEmbedText @InputText = 'adrenaline outdoor extreme sports', @EmbeddingVector = @queryVec2 OUTPUT;
SELECT TOP 3 name, country_code FROM Destinations WHERE description_vector IS NOT NULL ORDER BY VECTOR_DISTANCE('cosine', description_vector, @queryVec2) ASC;
GO

-- Cultural query
DECLARE @queryVec3 VECTOR(1024);
EXEC dbo.usp_BedrockEmbedText @InputText = 'ancient history museums art galleries', @EmbeddingVector = @queryVec3 OUTPUT;
SELECT TOP 3 name, country_code FROM Destinations WHERE description_vector IS NOT NULL ORDER BY VECTOR_DISTANCE('cosine', description_vector, @queryVec3) ASC;
GO
