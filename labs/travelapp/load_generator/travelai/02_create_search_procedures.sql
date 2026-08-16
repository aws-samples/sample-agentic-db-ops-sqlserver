SET QUOTED_IDENTIFIER ON;
GO
-- TravelAI Search Procedures
-- Usage: python3.11 run_sql_file.py load_generator/02_create_search_procedures.sql
USE TravelAI;
GO

SET NOCOUNT ON;
GO

-- usp_SearchSQL: Pure WHERE clause matching
CREATE OR ALTER PROCEDURE dbo.usp_SearchSQL
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Climate NVARCHAR(30) = NULL;
    IF @QueryText LIKE '%beach%' OR @QueryText LIKE '%tropical%' OR @QueryText LIKE '%island%'
        SET @Climate = 'tropical';
    ELSE IF @QueryText LIKE '%mountain%' OR @QueryText LIKE '%hiking%' OR @QueryText LIKE '%alpine%'
        SET @Climate = 'alpine';
    ELSE IF @QueryText LIKE '%desert%' OR @QueryText LIKE '%arid%'
        SET @Climate = 'semi-arid';

    IF @Climate IS NOT NULL
        SELECT TOP (@TopK) destination_id, name AS Title, country_code AS Country, region AS Continent, climate AS Climate, best_season AS Season, LEFT(description,200) AS Snippet, popularity_score, 100 AS RelevanceScore
        FROM Destinations WHERE climate = @Climate ORDER BY popularity_score DESC;
    ELSE
        SELECT TOP (@TopK) destination_id, name AS Title, country_code AS Country, region AS Continent, climate AS Climate, best_season AS Season, LEFT(description,200) AS Snippet, popularity_score, 50 AS RelevanceScore
        FROM Destinations ORDER BY popularity_score DESC;
END;
GO

-- usp_SearchLIKE: Pattern matching
CREATE OR ALTER PROCEDURE dbo.usp_SearchLIKE
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Word1 NVARCHAR(100) = LEFT(@QueryText, CHARINDEX(' ', @QueryText + ' ') - 1);
    SELECT TOP (@TopK)
        destination_id, name AS Title, country_code AS Country, region AS Continent, climate AS Climate, best_season AS Season,
        LEFT(description,200) AS Snippet, popularity_score, 120 AS RelevanceScore
    FROM Destinations
    WHERE description LIKE '%' + @Word1 + '%'
       OR name LIKE '%' + @Word1 + '%'
       OR country_code LIKE '%' + @Word1 + '%'
    ORDER BY popularity_score DESC;
END;
GO

-- usp_SearchFreetext: Full-Text Search
CREATE OR ALTER PROCEDURE dbo.usp_SearchFreetext
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@TopK) d.destination_id, d.name AS Title, d.country_code AS Country, d.region AS Continent, d.climate AS Climate, d.best_season AS Season, d.description AS Snippet, d.popularity_score, ft.[RANK] AS RelevanceScore
    FROM Destinations d
    INNER JOIN FREETEXTTABLE(Destinations, description, @QueryText) ft ON d.destination_id = ft.[KEY]
    ORDER BY ft.[RANK] DESC;
END;
GO

-- usp_TravelSearch: Hybrid (FREETEXT + RAG document chunks)
CREATE OR ALTER PROCEDURE dbo.usp_TravelSearch
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@TopK)
        'Destination' AS ResultType,
        d.destination_id AS SourceID,
        d.name AS Title,
        d.country_code AS Country,
        d.region AS Continent,
        d.climate AS Climate,
        d.best_season AS Season,
        d.description AS Snippet,
        d.popularity_score,
        ft.[RANK] AS RelevanceScore
    FROM Destinations d
    INNER JOIN FREETEXTTABLE(Destinations, description, @QueryText) ft
        ON d.destination_id = ft.[KEY]
    ORDER BY ft.[RANK] DESC;

    SELECT TOP 3
        'Document' AS ResultType,
        dc.chunk_id AS SourceID,
        dc.section_path AS Title,
        dc.content AS Snippet,
        ft.[RANK] AS RelevanceScore
    FROM DocumentChunks dc
    INNER JOIN FREETEXTTABLE(DocumentChunks, content, @QueryText) ft
        ON dc.chunk_id = ft.[KEY]
    ORDER BY ft.[RANK] DESC;
END;
GO

-- usp_SearchVector: Semantic vector search
CREATE OR ALTER PROCEDURE dbo.usp_SearchVector
    @QueryEmbedding VECTOR(1024),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP(@TopK)
        d.destination_id,
        d.name AS Title,
        d.country_code AS Country,
        d.region AS Continent,
        d.climate AS Climate,
        d.best_season AS Season,
        LEFT(d.description, 200) AS Snippet,
        d.popularity_score,
        CAST(VECTOR_DISTANCE('cosine', d.description_vector, @QueryEmbedding) * 1000 AS INT) AS RelevanceScore
    FROM Destinations d
    WHERE d.description_vector IS NOT NULL
    ORDER BY VECTOR_DISTANCE('cosine', d.description_vector, @QueryEmbedding) ASC;
END;
GO
