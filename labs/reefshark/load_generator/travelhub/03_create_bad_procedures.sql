-- TravelHub Load-Generating Stored Procedures
-- =============================================================================
-- These procedures drive the benchmark workload. They are written to be
-- SARGable and set-based (single pass, bounded TOP N, no per-row correlated
-- subqueries, no cartesian joins), so that:
--   * WITHOUT the supporting indexes they run as table SCANS -> high CPU under
--     concurrency, but each individual call still completes quickly.
--   * WITH the supporting indexes (created by the DBOps Actions Agent) the
--     scans become seeks -> CPU drops immediately for subsequent executions.
--
-- the agent is expected to detect the missing indexes and create them.
-- =============================================================================

USE TravelHub;
GO

SET NOCOUNT ON;
GO

-- =============================================================================
-- 1) sp_MatchDestinationsByPreferences
--    Now: set-based pre-aggregation via CTEs, one pass per table.
-- =============================================================================
CREATE OR ALTER PROCEDURE dbo.sp_MatchDestinationsByPreferences
    @UserID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @uid INT = ISNULL(@UserID, (SELECT TOP 1 UserID FROM Users ORDER BY NEWID()));

    SELECT TOP 100 da.DestinationID,
           COUNT(DISTINCT at2.TagID) AS MatchingActivityTags
    INTO #TopMatches
    FROM DestinationActivities da
    INNER JOIN ActivityTags at2 ON at2.ActivityID = da.ActivityID
    WHERE at2.TagID IN (SELECT TagID FROM UserPreferences WHERE UserID = @uid)
    GROUP BY da.DestinationID
    ORDER BY COUNT(DISTINCT at2.TagID) DESC;

    -- Aggregates scoped to the (<=100) matched destinations, materialized above so
    -- once DestinationID indexes exist.
    ;WITH DestAmenities AS (
        SELECT h.DestinationID, COUNT(*) AS AmenityCount
        FROM Hotels h
        INNER JOIN HotelAmenities ha ON ha.HotelID = h.HotelID
        WHERE h.DestinationID IN (SELECT DestinationID FROM #TopMatches)
        GROUP BY h.DestinationID
    ),
    DestActivityPrice AS (
        SELECT DestinationID, AVG(Price) AS AvgActivityPrice
        FROM Activities
        WHERE DestinationID IN (SELECT DestinationID FROM #TopMatches)
        GROUP BY DestinationID
    ),
    DestBookings AS (
        SELECT DestinationID, COUNT(*) AS TotalBookings
        FROM Bookings
        WHERE Status = 'Confirmed'
          AND DestinationID IN (SELECT DestinationID FROM #TopMatches)
        GROUP BY DestinationID
    )
    SELECT
        d.DestinationID, d.CityName, d.Country, d.Climate,
        tm.MatchingActivityTags,
        ISNULL(am.AmenityCount, 0)   AS AmenityCount,
        ap.AvgActivityPrice,
        ISNULL(bk.TotalBookings, 0)  AS TotalBookings
    FROM #TopMatches tm
    INNER JOIN Destinations d       ON d.DestinationID  = tm.DestinationID
    LEFT  JOIN DestAmenities am     ON am.DestinationID = tm.DestinationID
    LEFT  JOIN DestActivityPrice ap ON ap.DestinationID = tm.DestinationID
    LEFT  JOIN DestBookings bk      ON bk.DestinationID = tm.DestinationID
    ORDER BY tm.MatchingActivityTags DESC;

    DROP TABLE #TopMatches;
END
GO

-- =============================================================================
-- 2) sp_SearchDestinationsByDescription
--    Was: LEFT JOIN Hotels + LEFT JOIN Reviews (cartesian blow-up) with
--         LIKE '%term%' on NVARCHAR(MAX) -> 100s+ per call.
--    Now: scoped to the small Destinations table only (~5k rows), single scan,
--         bounded TOP 50 -> completes in a few ms.
--          It is deliberately kept small here so it is not a bottleneck.
-- =============================================================================
CREATE OR ALTER PROCEDURE dbo.sp_SearchDestinationsByDescription
    @SearchTerms NVARCHAR(500) = 'eco-friendly resort snorkeling coral reef'
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @t NVARCHAR(510) = '%' + @SearchTerms + '%';

    SELECT TOP 50
        d.DestinationID, d.CityName, d.Country, d.Description, d.PopularityScore
    FROM Destinations d
    WHERE d.Description LIKE @t
       OR d.CityName    LIKE @t
    ORDER BY d.PopularityScore DESC;
END
GO

-- =============================================================================
-- 3) sp_FilterDestinationsAdvanced
--    Now: pre-aggregate in CTEs, JOIN once, SARGable month range, bounded TOP 200.
--                 Reviews(ItemType,ItemID) INCLUDE(Rating),
--                 Activities(DestinationID), Bookings(DestinationID) INCLUDE(BookingDate).
-- =============================================================================
CREATE OR ALTER PROCEDURE dbo.sp_FilterDestinationsAdvanced
    @MinPrice DECIMAL(10,2) = 50,
    @MaxPrice DECIMAL(10,2) = 500,
    @MinRating DECIMAL(3,1) = 3.0,
    @Continent NVARCHAR(30) = NULL,
    @Climate NVARCHAR(30) = NULL,
    @MinActivities INT = 3
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @monthStart DATE = DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1);

    ;WITH DestActivities AS (
        SELECT DestinationID, COUNT(*) AS ActivityCount
        FROM Activities GROUP BY DestinationID
        HAVING COUNT(*) >= @MinActivities
    ),
    DestHotelPrices AS (
        SELECT DestinationID, AVG(PricePerNight) AS AvgHotelPrice
        FROM Hotels GROUP BY DestinationID
        HAVING AVG(PricePerNight) BETWEEN @MinPrice AND @MaxPrice
    ),
    DestRatings AS (
        SELECT ItemID AS DestinationID, AVG(CAST(Rating AS DECIMAL(3,1))) AS AvgRating
        FROM Reviews WHERE ItemType = 'Destination'
        GROUP BY ItemID
        HAVING AVG(CAST(Rating AS DECIMAL(3,1))) >= @MinRating
    ),
    DestBookings AS (
        SELECT DestinationID, COUNT(*) AS BookingsThisMonth
        FROM Bookings WHERE BookingDate >= @monthStart
        GROUP BY DestinationID
    )
    SELECT TOP 200
        d.DestinationID, d.CityName, d.Country, d.Continent, d.Climate, d.PopularityScore,
        da.ActivityCount, hp.AvgHotelPrice, dr.AvgRating,
        ISNULL(db.BookingsThisMonth, 0) AS BookingsThisMonth,
        ROW_NUMBER() OVER (ORDER BY da.ActivityCount DESC, dr.AvgRating DESC, d.PopularityScore DESC) AS Ranking
    FROM Destinations d
    INNER JOIN DestActivities da  ON da.DestinationID = d.DestinationID
    INNER JOIN DestHotelPrices hp ON hp.DestinationID = d.DestinationID
    INNER JOIN DestRatings dr     ON dr.DestinationID = d.DestinationID
    LEFT  JOIN DestBookings db    ON db.DestinationID = d.DestinationID
    WHERE (@Continent IS NULL OR d.Continent = @Continent)
      AND (@Climate   IS NULL OR d.Climate   = @Climate)
    ORDER BY Ranking;
END
GO

-- =============================================================================
-- 4) sp_SearchFlightsByRoute
--    Now: single-table SARGable filter, no subqueries, parameter-sniffed, TOP 100.
--    (No OPTIMIZE FOR UNKNOWN - that hint made the optimizer use average route density and
--     pick a full scan; sniffing the actual Origin/Destination lets it seek IX_Flights_Origin_Destination.)
--                 INCLUDE(Airline,FlightNumber,DepartTime,ArriveTime,DurationMinutes,Price,SeatsAvailable).
-- =============================================================================
CREATE OR ALTER PROCEDURE dbo.sp_SearchFlightsByRoute
    @Origin NVARCHAR(10),
    @Destination NVARCHAR(10),
    @DepartDateStart DATE = NULL,
    @DepartDateEnd DATE = NULL,
    @MaxPrice DECIMAL(10,2) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP 100
        f.FlightID, f.Airline, f.FlightNumber, f.Origin, f.Destination,
        f.DepartDate, f.DepartTime, f.ArriveTime, f.DurationMinutes,
        f.Price, f.SeatsAvailable
    FROM Flights f
    WHERE f.Origin = @Origin
      AND f.Destination = @Destination
      AND (@DepartDateStart IS NULL OR f.DepartDate >= @DepartDateStart)
      AND (@DepartDateEnd   IS NULL OR f.DepartDate <= @DepartDateEnd)
      AND (@MaxPrice        IS NULL OR f.Price <= @MaxPrice)
    ORDER BY f.Price ASC, f.DepartDate ASC;
END
GO

-- =============================================================================
-- 5) sp_CheckAndBookAvailability
--         blocking, deadlocks; no index => scan lengthens the lock hold.
--                 INCLUDE(TotalUnits,BookedUnits).
-- =============================================================================
CREATE OR ALTER PROCEDURE dbo.sp_CheckAndBookAvailability
    @ItemType NVARCHAR(20),
    @ItemID INT,
    @AvailableDate DATE,
    @UnitsRequested INT = 1
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE AvailabilityInventory
    SET BookedUnits = BookedUnits + @UnitsRequested,
        LastUpdated = GETDATE()
    WHERE ItemType = @ItemType
      AND ItemID = @ItemID
      AND AvailableDate = @AvailableDate
      AND (TotalUnits - BookedUnits) >= @UnitsRequested;

    IF @@ROWCOUNT > 0
        SELECT 'Booked' AS Result, @UnitsRequested AS UnitsBooked;
    ELSE
        SELECT 'Unavailable' AS Result, 0 AS UnitsBooked;
END
GO

PRINT 'TravelHub load-generating procedures (SARGable / index-resolvable) created.';
GO
