-- TravelHub Anti-Pattern Stored Procedures
-- These are intentionally poorly written to cause performance issues
-- Each one maps to a specific SQL Server bottleneck

USE TravelHub;

SET NOCOUNT ON;

PRINT '========================================';
PRINT 'CREATING PERFORMANCE PROBLEM PROCEDURES';
PRINT '========================================';
PRINT '';

-- =============================================
-- Problem 1: Multi-Tag Join Explosion
-- Correlated subqueries that self-join for each tag
-- Causes: Massive nested loop operations, CPU spike
-- =============================================

IF OBJECT_ID('dbo.sp_MatchDestinationsByPreferences', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_MatchDestinationsByPreferences;
GO

CREATE PROCEDURE dbo.sp_MatchDestinationsByPreferences
    @UserID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @uid INT = ISNULL(@UserID, (SELECT TOP 1 UserID FROM Users ORDER BY NEWID()));

    SELECT TOP 100
        d.DestinationID,
        d.CityName,
        d.Country,
        d.Climate,
        (SELECT COUNT(DISTINCT at2.TagID)
         FROM DestinationActivities da
         INNER JOIN ActivityTags at2 ON da.ActivityID = at2.ActivityID
         WHERE da.DestinationID = d.DestinationID
         AND at2.TagID IN (SELECT TagID FROM UserPreferences WHERE UserID = @uid)
        ) AS MatchingActivityTags,
        (SELECT COUNT(DISTINCT ha.AmenityName)
         FROM Hotels h
         INNER JOIN HotelAmenities ha ON h.HotelID = ha.HotelID
         WHERE h.DestinationID = d.DestinationID
        ) AS AmenityCount,
        (SELECT AVG(a.Price)
         FROM Activities a
         WHERE a.DestinationID = d.DestinationID
        ) AS AvgActivityPrice,
        (SELECT COUNT(*)
         FROM Bookings b
         WHERE b.DestinationID = d.DestinationID
         AND b.Status = 'Confirmed'
        ) AS TotalBookings
    FROM Destinations d
    WHERE d.DestinationID IN (
        SELECT DISTINCT da.DestinationID
        FROM DestinationActivities da
        INNER JOIN ActivityTags at3 ON da.ActivityID = at3.ActivityID
        WHERE at3.TagID IN (
            SELECT up.TagID FROM UserPreferences up WHERE up.UserID = @uid
        )
    )
    ORDER BY
        (SELECT COUNT(DISTINCT at4.TagID)
         FROM DestinationActivities da2
         INNER JOIN ActivityTags at4 ON da2.ActivityID = at4.ActivityID
         WHERE da2.DestinationID = d.DestinationID
         AND at4.TagID IN (SELECT TagID FROM UserPreferences WHERE UserID = @uid)
        ) DESC;
END
GO

PRINT 'Created: sp_MatchDestinationsByPreferences (Problem 1: Multi-Tag Join Explosion)';

-- =============================================
-- Problem 2: Full Table Scans on Text Searches
-- LIKE '%keyword%' on VARCHAR(MAX) columns
-- Causes: High I/O, bypasses all indexes
-- =============================================

IF OBJECT_ID('dbo.sp_SearchDestinationsByDescription', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SearchDestinationsByDescription;
GO

CREATE PROCEDURE dbo.sp_SearchDestinationsByDescription
    @SearchTerms NVARCHAR(500) = 'eco-friendly resort snorkeling coral reef'
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP 50
        d.DestinationID,
        d.CityName,
        d.Country,
        d.Description,
        h.HotelName,
        h.Description AS HotelDescription,
        r.ReviewText,
        (CASE WHEN d.Description LIKE '%eco%' THEN 1 ELSE 0 END +
         CASE WHEN d.Description LIKE '%resort%' THEN 1 ELSE 0 END +
         CASE WHEN d.Description LIKE '%snorkeling%' THEN 1 ELSE 0 END +
         CASE WHEN d.Description LIKE '%coral%' THEN 1 ELSE 0 END +
         CASE WHEN d.Description LIKE '%reef%' THEN 1 ELSE 0 END +
         CASE WHEN h.Description LIKE '%eco%' THEN 1 ELSE 0 END +
         CASE WHEN h.Description LIKE '%resort%' THEN 1 ELSE 0 END +
         CASE WHEN r.ReviewText LIKE '%eco%' THEN 1 ELSE 0 END +
         CASE WHEN r.ReviewText LIKE '%snorkeling%' THEN 1 ELSE 0 END +
         CASE WHEN r.ReviewText LIKE '%coral%' THEN 1 ELSE 0 END
        ) AS RelevanceScore
    FROM Destinations d
    LEFT JOIN Hotels h ON h.DestinationID = d.DestinationID
    LEFT JOIN Reviews r ON r.ItemType = 'Destination' AND r.ItemID = d.DestinationID
    WHERE
        d.Description LIKE '%' + @SearchTerms + '%'
        OR h.Description LIKE '%' + @SearchTerms + '%'
        OR r.ReviewText LIKE '%' + @SearchTerms + '%'
        OR d.Description LIKE '%eco%'
        OR d.Description LIKE '%resort%'
        OR d.Description LIKE '%snorkeling%'
    ORDER BY RelevanceScore DESC;
END
GO

PRINT 'Created: sp_SearchDestinationsByDescription (Problem 2: Full Table Scans on Text)';

-- =============================================
-- Problem 3: TempDB Contention from Dynamic Filtering
-- Complex OR conditions, computed columns, row-by-row processing
-- Causes: Large hash/sort spills to TempDB, PAGELATCH waits
-- =============================================

IF OBJECT_ID('dbo.sp_FilterDestinationsAdvanced', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_FilterDestinationsAdvanced;
GO

CREATE PROCEDURE dbo.sp_FilterDestinationsAdvanced
    @MinPrice DECIMAL(10,2) = 50,
    @MaxPrice DECIMAL(10,2) = 500,
    @MinRating DECIMAL(3,1) = 3.0,
    @Continent NVARCHAR(30) = NULL,
    @Climate NVARCHAR(30) = NULL,
    @MinActivities INT = 3
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        d.DestinationID,
        d.CityName,
        d.Country,
        d.Continent,
        d.Climate,
        d.PopularityScore,
        (SELECT COUNT(*) FROM Activities a WHERE a.DestinationID = d.DestinationID) AS ActivityCount,
        (SELECT AVG(h.PricePerNight) FROM Hotels h WHERE h.DestinationID = d.DestinationID) AS AvgHotelPrice,
        (SELECT AVG(CAST(r.Rating AS DECIMAL(3,1)))
         FROM Reviews r WHERE r.ItemType = 'Destination' AND r.ItemID = d.DestinationID) AS AvgRating,
        (SELECT COUNT(*)
         FROM Bookings b
         WHERE b.DestinationID = d.DestinationID
         AND MONTH(b.BookingDate) = MONTH(GETDATE())
         AND YEAR(b.BookingDate) = YEAR(GETDATE())) AS BookingsThisMonth,
        ROW_NUMBER() OVER (ORDER BY
            (SELECT COUNT(*) FROM Activities a WHERE a.DestinationID = d.DestinationID) DESC,
            (SELECT AVG(CAST(r.Rating AS DECIMAL(3,1)))
             FROM Reviews r WHERE r.ItemType = 'Destination' AND r.ItemID = d.DestinationID) DESC,
            d.PopularityScore DESC
        ) AS Ranking
    FROM Destinations d
    WHERE
        (d.Continent = @Continent OR @Continent IS NULL)
        AND (d.Climate = @Climate OR @Climate IS NULL)
        AND (SELECT AVG(h2.PricePerNight) FROM Hotels h2 WHERE h2.DestinationID = d.DestinationID)
            BETWEEN @MinPrice AND @MaxPrice
        AND (SELECT AVG(CAST(r2.Rating AS DECIMAL(3,1)))
             FROM Reviews r2 WHERE r2.ItemType = 'Destination' AND r2.ItemID = d.DestinationID) >= @MinRating
        AND (SELECT COUNT(*) FROM Activities a2 WHERE a2.DestinationID = d.DestinationID) >= @MinActivities
    ORDER BY Ranking;
END
GO

PRINT 'Created: sp_FilterDestinationsAdvanced (Problem 3: TempDB Contention)';

-- =============================================
-- Problem 4: Parameter Sniffing
-- Single plan compiled for first parameter set
-- Causes: Wildly inconsistent performance, wrong memory grants
-- =============================================

IF OBJECT_ID('dbo.sp_SearchFlightsByRoute', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_SearchFlightsByRoute;
GO

CREATE PROCEDURE dbo.sp_SearchFlightsByRoute
    @Origin NVARCHAR(10),
    @Destination NVARCHAR(10),
    @DepartDateStart DATE = NULL,
    @DepartDateEnd DATE = NULL,
    @MaxPrice DECIMAL(10,2) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- ANTI-PATTERN: No hint for parameter sniffing
    -- Plan compiled for first execution parameters (e.g., popular JFK->LAX route)
    -- Subsequent calls with niche routes get catastrophically wrong plan
    SELECT
        f.FlightID,
        f.Airline,
        f.FlightNumber,
        f.Origin,
        f.Destination,
        f.DepartDate,
        f.DepartTime,
        f.ArriveTime,
        f.DurationMinutes,
        f.Price,
        f.SeatsAvailable,
        -- Correlated subquery that inflates memory grant
        (SELECT TOP 1 h.HotelName FROM Hotels h
         INNER JOIN Destinations d ON h.DestinationID = d.DestinationID
         WHERE d.CityName LIKE '%' + f.Destination + '%'
         ORDER BY h.ReviewScore DESC) AS TopHotelAtDest,
        -- Another correlated subquery
        (SELECT COUNT(*) FROM Bookings b
         INNER JOIN BookingFlights bf ON b.BookingID = bf.BookingID
         WHERE bf.FlightID = f.FlightID) AS TimesBooked
    FROM Flights f
    WHERE f.Origin = @Origin
    AND f.Destination = @Destination
    AND (@DepartDateStart IS NULL OR f.DepartDate >= @DepartDateStart)
    AND (@DepartDateEnd IS NULL OR f.DepartDate <= @DepartDateEnd)
    AND (@MaxPrice IS NULL OR f.Price <= @MaxPrice)
    ORDER BY f.Price ASC, f.DepartDate ASC;
END
GO

PRINT 'Created: sp_SearchFlightsByRoute (Problem 4: Parameter Sniffing)';

-- =============================================
-- Problem 5: Lock Contention on Availability
-- Readers block writers under default isolation
-- Causes: LCK_M_S/LCK_M_X waits, deadlocks, timeouts
-- =============================================

IF OBJECT_ID('dbo.sp_CheckAndBookAvailability', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_CheckAndBookAvailability;
GO

CREATE PROCEDURE dbo.sp_CheckAndBookAvailability
    @ItemType NVARCHAR(20),
    @ItemID INT,
    @AvailableDate DATE,
    @UnitsRequested INT = 1
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Available INT;
    DECLARE @Booked INT;

    -- Step 1: Read current availability (takes S lock on row)
    SELECT @Available = TotalUnits, @Booked = BookedUnits
    FROM AvailabilityInventory
    WHERE ItemType = @ItemType
    AND ItemID = @ItemID
    AND AvailableDate = @AvailableDate;

    -- Simulate processing time (makes lock contention worse)
    WAITFOR DELAY '00:00:00.100';

    -- Step 2: Check if enough units available
    IF (@Available - @Booked) >= @UnitsRequested
    BEGIN
        -- Step 3: Update booking count (takes X lock, blocks all other readers)
        UPDATE AvailabilityInventory
        SET BookedUnits = BookedUnits + @UnitsRequested,
            LastUpdated = GETDATE()
        WHERE ItemType = @ItemType
        AND ItemID = @ItemID
        AND AvailableDate = @AvailableDate;

        SELECT 'Booked' AS Result, @UnitsRequested AS UnitsBooked,
               @Available - @Booked - @UnitsRequested AS RemainingUnits;
    END
    ELSE
    BEGIN
        SELECT 'Unavailable' AS Result, 0 AS UnitsBooked,
               @Available - @Booked AS RemainingUnits;
    END
END
GO

PRINT 'Created: sp_CheckAndBookAvailability (Problem 5: Lock Contention)';

PRINT '';
PRINT '========================================';
PRINT 'ALL PROCEDURES CREATED';
PRINT '========================================';

SET NOCOUNT OFF;
