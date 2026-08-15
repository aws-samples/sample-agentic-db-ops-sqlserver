-- TravelAI Search Stored Procedures
-- Created for the Search UI comparison demo
-- These run against the TravelAI database

USE TravelAI;
GO

SET NOCOUNT ON;

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
        SELECT TOP (@TopK) DestinationID, CityName AS Title, Country, Continent, Climate, Season, Description AS Snippet, PopularityScore, 100 AS RelevanceScore
        FROM Destinations WHERE Climate = @Climate ORDER BY PopularityScore DESC;
    ELSE
        SELECT TOP (@TopK) DestinationID, CityName AS Title, Country, Continent, Climate, Season, Description AS Snippet, PopularityScore, 50 AS RelevanceScore
        FROM Destinations ORDER BY PopularityScore DESC;
END;
GO

-- =============================================
-- usp_SearchLIKE: LIKE pattern matching
-- Splits first two words, searches Description + CityName + Country
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
        DestinationID, CityName AS Title, Country, Continent, Climate, Season, 
        Description AS Snippet, PopularityScore, 120 AS RelevanceScore
    FROM Destinations
    WHERE Description LIKE '%' + @Word1 + '%'
       OR (@Word2 IS NOT NULL AND Description LIKE '%' + @Word2 + '%')
       OR CityName LIKE '%' + @Word1 + '%'
       OR Country LIKE '%' + @Word1 + '%'
    ORDER BY PopularityScore DESC;
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
    SELECT TOP (@TopK) d.DestinationID, d.CityName AS Title, d.Country, d.Continent, d.Climate, d.Season, d.Description AS Snippet, d.PopularityScore, ft.[RANK] AS RelevanceScore
    FROM Destinations d
    INNER JOIN FREETEXTTABLE(Destinations, Description, @QueryText) ft ON d.DestinationID = ft.[KEY]
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
        d.DestinationID AS SourceID,
        d.CityName AS Title,
        d.Country,
        d.Continent,
        d.Climate,
        d.Season,
        d.Description AS Snippet,
        d.PopularityScore,
        ft.[RANK] AS RelevanceScore
    FROM Destinations d
    INNER JOIN FREETEXTTABLE(Destinations, Description, @QueryText) ft
        ON d.DestinationID = ft.[KEY]
    ORDER BY ft.[RANK] DESC;

    -- Result set 2: RAG context from document chunks
    SELECT TOP 3
        'Document' AS ResultType,
        dc.ChunkID AS SourceID,
        dc.DocumentName AS Title,
        dc.ContentText AS Snippet,
        ft.[RANK] AS RelevanceScore
    FROM DocumentChunks dc
    INNER JOIN FREETEXTTABLE(DocumentChunks, ContentText, @QueryText) ft
        ON dc.ChunkID = ft.[KEY]
    ORDER BY ft.[RANK] DESC;
END;
GO

PRINT 'Search SPs created: usp_SearchSQL, usp_SearchLIKE, usp_SearchFreetext, usp_TravelSearch';
GO
