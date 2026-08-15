-- TravelAI Search Stored Procedures
-- Created for the Search UI comparison demo
-- These run against the TravelAI database

USE TravelAI;
GO

SET NOCOUNT ON;
GO

-- =============================================
-- usp_SearchSQL: Pure WHERE clause matching
-- Maps keywords to climate categories
-- =============================================
CREATE OR ALTER PROCEDURE dbo.usp_SearchSQL
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Climate NVARCHAR(30) = NULL;
    IF @QueryText LIKE '%beach%' OR @QueryText LIKE '%tropical%' OR @QueryText LIKE '%island%'
        SET @Climate = 'Tropical';
    ELSE IF @QueryText LIKE '%mountain%' OR @QueryText LIKE '%hiking%'
        SET @Climate = 'Temperate';
    ELSE IF @QueryText LIKE '%desert%' OR @QueryText LIKE '%arid%'
        SET @Climate = 'Arid';
    ELSE IF @QueryText LIKE '%arctic%' OR @QueryText LIKE '%glacier%'
        SET @Climate = 'Arctic';

    IF @Climate IS NOT NULL
        SELECT TOP (@TopK) destination_id, name AS Title, country_code AS Country, region AS Continent, climate AS Climate, best_season AS Season, LEFT(description,200) AS Snippet, popularity_score, 100 AS RelevanceScore
        FROM Destinations WHERE Climate = @Climate ORDER BY popularity_score DESC;
    ELSE
        SELECT TOP (@TopK) destination_id, name AS Title, country_code AS Country, region AS Continent, climate AS Climate, best_season AS Season, LEFT(description,200) AS Snippet, popularity_score, 50 AS RelevanceScore
        FROM Destinations ORDER BY popularity_score DESC;
END;
GO

-- =============================================
-- usp_SearchLIKE: LIKE pattern matching
-- Splits first two words, searches description + name + Country
-- =============================================
CREATE OR ALTER PROCEDURE dbo.usp_SearchLIKE
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @Word1 NVARCHAR(100) = LEFT(@QueryText, CHARINDEX(' ', @QueryText + ' ') - 1);
    DECLARE @Word2 NVARCHAR(100) = NULL;
    
    IF CHARINDEX(' ', @QueryText) > 0
        SET @Word2 = SUBSTRING(@QueryText, CHARINDEX(' ', @QueryText) + 1, 
            CHARINDEX(' ', @QueryText + ' ', CHARINDEX(' ', @QueryText) + 1) - CHARINDEX(' ', @QueryText) - 1);

    SELECT TOP (@TopK) 
        destination_id, name AS Title, country_code AS Country, region AS Continent, climate AS Climate, best_season AS Season, 
        description AS Snippet, popularity_score, 120 AS RelevanceScore
    FROM Destinations
    WHERE Description LIKE '%' + @Word1 + '%'
       OR (@Word2 IS NOT NULL AND Description LIKE '%' + @Word2 + '%')
       OR name LIKE '%' + @Word1 + '%'
       OR country_code LIKE '%' + @Word1 + '%'
    ORDER BY popularity_score DESC;
END;
GO

-- =============================================
-- usp_SearchFreetext: Full-Text Search (FREETEXT only, no RAG)
-- Uses SQL Server Full-Text engine with stemming and word forms
-- =============================================
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

-- =============================================
-- usp_TravelSearch: Hybrid (FREETEXT + RAG document chunks)
-- Returns 2 result sets: destinations + supporting document context
-- =============================================
CREATE OR ALTER PROCEDURE dbo.usp_TravelSearch
    @QueryText NVARCHAR(1000),
    @TopK INT = 5
AS
BEGIN
    SET NOCOUNT ON;

    -- Result set 1: Destinations ranked by Full-Text relevance
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

    -- Result set 2: RAG context from document chunks
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

PRINT 'Search SPs created: usp_SearchSQL, usp_SearchLIKE, usp_SearchFreetext, usp_TravelSearch';
GO
