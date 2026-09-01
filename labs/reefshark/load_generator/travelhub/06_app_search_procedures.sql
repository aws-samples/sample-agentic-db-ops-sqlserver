-- =============================================================================
-- 06_app_search_procedures.sql
-- Stored procedures that back the ReefShark main-page search (Destinations,
-- Flights, Hotels, Activities). These replace the inline queries that used to
-- live in the FastAPI backend (backend/db.py), so the customer-facing search
-- workload shows up in Query Store as named procedures.
--
-- Plain TEXT SEARCH only (no semantic / no TravelAI). Multi-word queries are
-- tokenized with STRING_SPLIT and matched with OR-any-token across the relevant
-- descriptive columns (same behaviour as the previous inline queries).
--
-- Depends on the enrichment columns added by 05_enrich_for_app_search.sql
-- (DisplayName/Tags, Hotels.City/Amenities, Activities.Category/Tags/City,
-- Flights.OriginCity/DestCity). Idempotent via CREATE OR ALTER; safe to re-run.
--
-- NOTE: these are intentionally separate from the sp_* anti-pattern procedures
-- used by the benchmark/SRE scenario and do not modify them.
-- =============================================================================
USE TravelHub;
GO

-- ---------------------------------------------------------------------------
-- Destinations: de-duplicated to one row per real city, ranked by popularity.
-- ---------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.usp_App_SearchDestinations
    @Search NVARCHAR(400) = N'',
    @TopK   INT           = 8
AS
BEGIN
    SET NOCOUNT ON;
    ;WITH tokens AS (
        SELECT value AS tok
        FROM STRING_SPLIT(REPLACE(REPLACE(REPLACE(@Search, '-', ' '), ',', ' '), '/', ' '), ' ')
        WHERE LEN(value) >= 1
    ),
    ded AS (
        SELECT DisplayName, Country, Continent, Climate, Season, Tags,
               CAST(Description AS NVARCHAR(4000)) AS Description, PopularityScore,
               ROW_NUMBER() OVER (PARTITION BY DisplayName ORDER BY PopularityScore DESC) AS rn
        FROM dbo.Destinations
    )
    SELECT TOP (@TopK)
        DisplayName, Country, Continent, Climate, Season, Tags, Description, PopularityScore
    FROM ded
    WHERE rn = 1
      AND (LTRIM(RTRIM(@Search)) = N'' OR EXISTS (
            SELECT 1 FROM tokens t
            WHERE ded.DisplayName            LIKE '%' + t.tok + '%'
               OR ded.Country                LIKE '%' + t.tok + '%'
               OR ded.Continent              LIKE '%' + t.tok + '%'
               OR ded.Climate                LIKE '%' + t.tok + '%'
               OR ded.Season                 LIKE '%' + t.tok + '%'
               OR ISNULL(ded.Tags, '')        LIKE '%' + t.tok + '%'
               OR ISNULL(ded.Description, '')  LIKE '%' + t.tok + '%'))
    ORDER BY PopularityScore DESC;
END
GO

-- ---------------------------------------------------------------------------
-- Flights: single leg (origin -> destination on/after an optional date).
-- The backend calls this twice for a round-trip (outbound + return).
-- ---------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.usp_App_SearchFlights
    @Origin      NVARCHAR(200) = N'',
    @Destination NVARCHAR(200) = N'',
    @DepartDate  DATE          = NULL,
    @TopK        INT           = 8
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@TopK)
        Airline, FlightNumber, OriginCity, DestCity, Origin, Destination,
        CONVERT(varchar(10), DepartDate, 23) AS DepartDate,
        CONVERT(varchar(5),  DepartTime, 108) AS DepartTime,
        CONVERT(varchar(5),  ArriveTime, 108) AS ArriveTime,
        DurationMinutes, Price, SeatsAvailable, Aircraft
    FROM dbo.Flights
    WHERE (LTRIM(RTRIM(@Origin)) = N'' OR EXISTS (
            SELECT 1 FROM STRING_SPLIT(REPLACE(@Origin, '-', ' '), ' ') s
            WHERE LEN(s.value) >= 1
              AND (OriginCity LIKE '%' + s.value + '%' OR Origin LIKE '%' + s.value + '%')))
      AND (LTRIM(RTRIM(@Destination)) = N'' OR EXISTS (
            SELECT 1 FROM STRING_SPLIT(REPLACE(@Destination, '-', ' '), ' ') s
            WHERE LEN(s.value) >= 1
              AND (DestCity LIKE '%' + s.value + '%' OR Destination LIKE '%' + s.value + '%')))
      AND (@DepartDate IS NULL OR DepartDate >= @DepartDate)
    ORDER BY DepartDate ASC, Price ASC;
END
GO

-- ---------------------------------------------------------------------------
-- Hotels: text search by city / name / amenities / country.
-- (Nights and total stay price are computed in the backend from check-in/out.)
-- ---------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.usp_App_SearchHotels
    @Search NVARCHAR(400) = N'',
    @TopK   INT           = 8
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@TopK)
        h.HotelName, h.City, d.Country, h.StarRating, h.PricePerNight, h.ReviewScore, h.Amenities
    FROM dbo.Hotels h
    JOIN dbo.Destinations d ON h.DestinationID = d.DestinationID
    WHERE (LTRIM(RTRIM(@Search)) = N'' OR EXISTS (
            SELECT 1 FROM STRING_SPLIT(REPLACE(REPLACE(@Search, '-', ' '), ',', ' '), ' ') s
            WHERE LEN(s.value) >= 1
              AND (h.City LIKE '%' + s.value + '%'
                   OR h.HotelName LIKE '%' + s.value + '%'
                   OR ISNULL(h.Amenities, '') LIKE '%' + s.value + '%'
                   OR d.Country LIKE '%' + s.value + '%')))
    ORDER BY h.ReviewScore DESC, h.PricePerNight ASC;
END
GO

-- ---------------------------------------------------------------------------
-- Activities: text search by name / category / tags / city / country / desc.
-- ---------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.usp_App_SearchActivities
    @Search NVARCHAR(400) = N'',
    @TopK   INT           = 8
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@TopK)
        a.ActivityName, a.Category, a.Tags, a.City, d.Country,
        a.Price, a.DurationHours, a.DifficultyLevel
    FROM dbo.Activities a
    JOIN dbo.Destinations d ON a.DestinationID = d.DestinationID
    WHERE (LTRIM(RTRIM(@Search)) = N'' OR EXISTS (
            SELECT 1 FROM STRING_SPLIT(REPLACE(REPLACE(@Search, '-', ' '), ',', ' '), ' ') s
            WHERE LEN(s.value) >= 1
              AND (a.ActivityName LIKE '%' + s.value + '%'
                   OR a.Category LIKE '%' + s.value + '%'
                   OR ISNULL(a.Tags, '') LIKE '%' + s.value + '%'
                   OR a.City LIKE '%' + s.value + '%'
                   OR d.Country LIKE '%' + s.value + '%'
                   OR CAST(a.Description AS NVARCHAR(4000)) LIKE '%' + s.value + '%')))
    ORDER BY a.Price ASC;
END
GO

PRINT 'App search stored procedures (usp_App_Search*) created/updated.';
GO
