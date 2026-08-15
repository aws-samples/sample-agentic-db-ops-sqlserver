USE TravelAI;
GO

CREATE OR ALTER PROCEDURE dbo.usp_HybridSearch
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Embed the query
    DECLARE @queryVec VECTOR(1024);
    EXEC dbo.usp_BedrockEmbedText @text = @QueryText, @vector = @queryVec OUTPUT;
    
    -- Vector search (semantic)
    ;WITH VectorResults AS (
        SELECT destination_id,
               ROW_NUMBER() OVER (ORDER BY VECTOR_DISTANCE('cosine', description_vector, @queryVec) ASC) AS VectorRank
        FROM Destinations WHERE description_vector IS NOT NULL
    ),
    -- Full-Text search (lexical)
    FTSResults AS (
        SELECT [KEY] AS destination_id,
               ROW_NUMBER() OVER (ORDER BY [RANK] DESC) AS FTSRank
        FROM FREETEXTTABLE(Destinations, description, @QueryText)
    )
    -- Reciprocal Rank Fusion
    SELECT TOP (@TopK)
        d.name AS Title, d.country_code AS Country, d.region AS Continent, 
        d.climate AS Climate, d.best_season AS Season,
        LEFT(d.description, 200) AS Snippet, d.popularity_score,
        (1.0 / (60 + ISNULL(v.VectorRank, 100))) + (1.0 / (60 + ISNULL(f.FTSRank, 100))) AS RRFScore
    FROM Destinations d
    LEFT JOIN VectorResults v ON d.destination_id = v.destination_id
    LEFT JOIN FTSResults f ON d.destination_id = f.destination_id
    WHERE v.destination_id IS NOT NULL OR f.destination_id IS NOT NULL
    ORDER BY RRFScore DESC;

    -- RAG context from document chunks
    ;WITH ChunkVector AS (
        SELECT chunk_id,
               ROW_NUMBER() OVER (ORDER BY VECTOR_DISTANCE('cosine', content_vector, @queryVec) ASC) AS Rank
        FROM DocumentChunks WHERE content_vector IS NOT NULL
    )
    SELECT TOP 3
        dc.section_path AS Title, dc.content AS Snippet, cv.Rank
    FROM DocumentChunks dc
    INNER JOIN ChunkVector cv ON dc.chunk_id = cv.chunk_id
    ORDER BY cv.Rank ASC;
END;
GO

-- Test it
EXEC usp_HybridSearch 'sustainable eco-friendly family vacation with ocean activities';
GO
