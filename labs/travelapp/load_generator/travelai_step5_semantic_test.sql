USE TravelAI;
GO

-- Embed the search query
DECLARE @queryVec VECTOR(1024);
EXEC dbo.usp_BedrockEmbedText 
    @text = 'relaxing tropical escape', 
    @vector = @queryVec OUTPUT;

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
EXEC dbo.usp_BedrockEmbedText @text = 'adrenaline outdoor extreme sports', @vector = @queryVec2 OUTPUT;
SELECT TOP 3 name, country_code FROM Destinations WHERE description_vector IS NOT NULL ORDER BY VECTOR_DISTANCE('cosine', description_vector, @queryVec2) ASC;
GO

-- Cultural query
DECLARE @queryVec3 VECTOR(1024);
EXEC dbo.usp_BedrockEmbedText @text = 'ancient history museums art galleries', @vector = @queryVec3 OUTPUT;
SELECT TOP 3 name, country_code FROM Destinations WHERE description_vector IS NOT NULL ORDER BY VECTOR_DISTANCE('cosine', description_vector, @queryVec3) ASC;
GO
