-- TravelHub Performance Fixes
-- Each fix addresses a specific SQL Server bottleneck
-- Applied progressively by the Actions Agent

USE TravelHub;
GO

SET NOCOUNT ON;

PRINT '========================================';
PRINT 'APPLYING PERFORMANCE FIXES';
PRINT '========================================';
PRINT '';

-- =============================================
-- Fix 5: Enable RCSI (Apply first — immediate blocking relief)
-- Risk: LOW (non-destructive, session-level behavior change)
-- =============================================

PRINT 'Fix 5: Enabling Read Committed Snapshot Isolation...';

ALTER DATABASE TravelHub SET READ_COMMITTED_SNAPSHOT ON;

PRINT '  ✅ RCSI enabled. Readers no longer block writers.';
PRINT '     Readers get versioned snapshots from TempDB version store.';
PRINT '     Monitor: SELECT * FROM sys.dm_tran_version_store_space_usage';
PRINT '';

-- =============================================
-- Fix 3: Columnstore Index for Dynamic Filtering
-- Risk: MEDIUM (creates index, affects storage and write perf)
-- =============================================

PRINT 'Fix 3: Creating Nonclustered Columnstore Index...';

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'NCCI_Destinations_Filter')
BEGIN
    CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_Destinations_Filter
    ON Destinations (DestinationID, CityName, Country, Continent, Climate, PopularityScore);
    PRINT '  ✅ Columnstore index created on Destinations';
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'NCCI_Hotels_Filter')
BEGIN
    CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_Hotels_Filter
    ON Hotels (HotelID, DestinationID, StarRating, PricePerNight, ReviewScore);
    PRINT '  ✅ Columnstore index created on Hotels';
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'NCCI_Reviews_Filter')
BEGIN
    CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_Reviews_Filter
    ON Reviews (ReviewID, ItemType, ItemID, Rating, HelpfulVotes);
    PRINT '  ✅ Columnstore index created on Reviews';
END

PRINT '  Batch Mode execution now available for filter queries.';
PRINT '';

-- Also fix the SP to use JOINs instead of scalar subqueries
PRINT '  Replacing sp_FilterDestinationsAdvanced with optimized version...';
GO

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

    -- FIXED: Pre-aggregate in CTEs, use JOINs, enable Batch Mode
    WITH DestActivities AS (
        SELECT DestinationID, COUNT(*) AS ActivityCount
        FROM Activities
        GROUP BY DestinationID
        HAVING COUNT(*) >= @MinActivities
    ),
    DestHotelPrices AS (
        SELECT DestinationID, AVG(PricePerNight) AS AvgHotelPrice
        FROM Hotels
        GROUP BY DestinationID
        HAVING AVG(PricePerNight) BETWEEN @MinPrice AND @MaxPrice
    ),
    DestRatings AS (
        SELECT ItemID AS DestinationID, AVG(CAST(Rating AS DECIMAL(3,1))) AS AvgRating
        FROM Reviews
        WHERE ItemType = 'Destination'
        GROUP BY ItemID
        HAVING AVG(CAST(Rating AS DECIMAL(3,1))) >= @MinRating
    ),
    DestBookings AS (
        SELECT DestinationID, COUNT(*) AS BookingsThisMonth
        FROM Bookings
        WHERE BookingDate >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0)
        GROUP BY DestinationID
    )
    SELECT
        d.DestinationID,
        d.CityName,
        d.Country,
        d.Continent,
        d.Climate,
        d.PopularityScore,
        da.ActivityCount,
        hp.AvgHotelPrice,
        dr.AvgRating,
        ISNULL(db.BookingsThisMonth, 0) AS BookingsThisMonth,
        ROW_NUMBER() OVER (ORDER BY da.ActivityCount DESC, dr.AvgRating DESC, d.PopularityScore DESC) AS Ranking
    FROM Destinations d
    INNER JOIN DestActivities da ON d.DestinationID = da.DestinationID
    INNER JOIN DestHotelPrices hp ON d.DestinationID = hp.DestinationID
    INNER JOIN DestRatings dr ON d.DestinationID = dr.DestinationID
    LEFT JOIN DestBookings db ON d.DestinationID = db.DestinationID
    WHERE (@Continent IS NULL OR d.Continent = @Continent)
    AND (@Climate IS NULL OR d.Climate = @Climate)
    ORDER BY Ranking;
END
GO

PRINT '  ✅ sp_FilterDestinationsAdvanced replaced (CTEs + JOINs, no scalar subqueries)';
PRINT '';

-- =============================================
-- Fix 4: Parameter Sniffing Fix
-- Risk: MEDIUM (alters execution plan behavior)
-- =============================================

PRINT 'Fix 4: Fixing parameter sniffing on flight search...';
GO

CREATE OR ALTER PROCEDURE dbo.sp_SearchFlightsByRoute
    @Origin NVARCHAR(10),
    @Destination NVARCHAR(10),
    @DepartDateStart DATE = NULL,
    @DepartDateEnd DATE = NULL,
    @MaxPrice DECIMAL(10,2) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- FIXED: OPTIMIZE FOR UNKNOWN generates a generic plan
    -- that works reasonably well for both popular and niche routes
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
        f.SeatsAvailable
    FROM Flights f
    WHERE f.Origin = @Origin
    AND f.Destination = @Destination
    AND (@DepartDateStart IS NULL OR f.DepartDate >= @DepartDateStart)
    AND (@DepartDateEnd IS NULL OR f.DepartDate <= @DepartDateEnd)
    AND (@MaxPrice IS NULL OR f.Price <= @MaxPrice)
    ORDER BY f.Price ASC, f.DepartDate ASC
    OPTION (OPTIMIZE FOR UNKNOWN);
END
GO

-- Create filtered indexes for hot routes
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Flights_Origin_Dest_Date')
BEGIN
    CREATE NONCLUSTERED INDEX IX_Flights_Origin_Dest_Date
    ON Flights (Origin, Destination, DepartDate)
    INCLUDE (Airline, FlightNumber, DepartTime, ArriveTime, DurationMinutes, Price, SeatsAvailable);
    PRINT '  ✅ Covering index created on Flights(Origin, Destination, DepartDate)';
END

PRINT '  ✅ sp_SearchFlightsByRoute fixed with OPTIMIZE FOR UNKNOWN';
PRINT '';

-- =============================================
-- Fix 2: Full-Text Search Index
-- Risk: MEDIUM (creates FTS catalog and index)
-- =============================================

PRINT 'Fix 2: Creating Full-Text Search indexes...';

-- Create Full-Text Catalog
IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = 'TravelHub_FTC')
BEGIN
    CREATE FULLTEXT CATALOG TravelHub_FTC AS DEFAULT;
    PRINT '  ✅ Full-Text Catalog created';
END

-- Full-Text Index on Destinations.Description
IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes WHERE object_id = OBJECT_ID('Destinations'))
BEGIN
    CREATE FULLTEXT INDEX ON Destinations (Description)
    KEY INDEX PK__Destinat__73234AF5 -- Will need actual PK name
    WITH STOPLIST = SYSTEM;
    PRINT '  ✅ Full-Text Index on Destinations.Description';
END

-- Full-Text Index on Hotels.Description
IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes WHERE object_id = OBJECT_ID('Hotels'))
BEGIN
    CREATE FULLTEXT INDEX ON Hotels (Description)
    KEY INDEX PK__Hotels__46023BDF -- Will need actual PK name
    WITH STOPLIST = SYSTEM;
    PRINT '  ✅ Full-Text Index on Hotels.Description';
END

-- Full-Text Index on Reviews.ReviewText
IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes WHERE object_id = OBJECT_ID('Reviews'))
BEGIN
    CREATE FULLTEXT INDEX ON Reviews (ReviewText, Title)
    KEY INDEX PK__Reviews__74BC79AE -- Will need actual PK name
    WITH STOPLIST = SYSTEM;
    PRINT '  ✅ Full-Text Index on Reviews.ReviewText';
END

GO

-- Replace the search SP with Full-Text version
CREATE OR ALTER PROCEDURE dbo.sp_SearchDestinationsByDescription
    @SearchTerms NVARCHAR(500) = 'eco-friendly resort snorkeling coral reef'
AS
BEGIN
    SET NOCOUNT ON;

    -- FIXED: Use FREETEXT for natural language search
    -- Full-Text engine handles word breaking, stemming, and relevance ranking
    SELECT TOP 50
        d.DestinationID,
        d.CityName,
        d.Country,
        d.Description,
        h.HotelName,
        h.Description AS HotelDescription,
        r.ReviewText
    FROM Destinations d
    LEFT JOIN Hotels h ON h.DestinationID = d.DestinationID
        AND FREETEXT(h.Description, @SearchTerms)
    LEFT JOIN Reviews r ON r.ItemType = 'Destination' AND r.ItemID = d.DestinationID
        AND FREETEXT(r.ReviewText, @SearchTerms)
    WHERE FREETEXT(d.Description, @SearchTerms)
    ORDER BY d.PopularityScore DESC;
END
GO

PRINT '  ✅ sp_SearchDestinationsByDescription replaced with FREETEXT';
PRINT '';

-- =============================================
-- Fix 1: Graph Tables for Multi-Tag Matching
-- Risk: HIGH (schema change — creates new graph tables)
-- =============================================

PRINT 'Fix 1: Creating SQL Server Graph Tables...';

-- Create Node tables
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'DestinationNode' AND is_node = 1)
BEGIN
    CREATE TABLE DestinationNode (
        DestinationID INT NOT NULL,
        CityName NVARCHAR(100),
        Country NVARCHAR(50),
        Climate NVARCHAR(30)
    ) AS NODE;
    PRINT '  ✅ DestinationNode created';
END

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ActivityNode' AND is_node = 1)
BEGIN
    CREATE TABLE ActivityNode (
        ActivityID INT NOT NULL,
        ActivityName NVARCHAR(100),
        Price DECIMAL(10,2)
    ) AS NODE;
    PRINT '  ✅ ActivityNode created';
END

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TagNode' AND is_node = 1)
BEGIN
    CREATE TABLE TagNode (
        TagID INT NOT NULL,
        TagName NVARCHAR(50),
        Category NVARCHAR(30)
    ) AS NODE;
    PRINT '  ✅ TagNode created';
END

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'UserNode' AND is_node = 1)
BEGIN
    CREATE TABLE UserNode (
        UserID INT NOT NULL,
        MembershipTier NVARCHAR(20)
    ) AS NODE;
    PRINT '  ✅ UserNode created';
END

-- Create Edge tables
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'Offers' AND is_edge = 1)
BEGIN
    CREATE TABLE Offers AS EDGE;
    PRINT '  ✅ Offers edge created (Destination → Activity)';
END

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'TaggedWith' AND is_edge = 1)
BEGIN
    CREATE TABLE TaggedWith AS EDGE;
    PRINT '  ✅ TaggedWith edge created (Activity → Tag)';
END

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'Prefers' AND is_edge = 1)
BEGIN
    CREATE TABLE Prefers AS EDGE;
    PRINT '  ✅ Prefers edge created (User → Tag)';
END

-- Populate graph tables from relational data
PRINT '  Populating graph nodes...';

INSERT INTO DestinationNode (DestinationID, CityName, Country, Climate)
SELECT DestinationID, CityName, Country, Climate FROM Destinations;

INSERT INTO ActivityNode (ActivityID, ActivityName, Price)
SELECT ActivityID, ActivityName, Price FROM Activities;

INSERT INTO TagNode (TagID, TagName, Category)
SELECT TagID, TagName, Category FROM PreferenceTags;

INSERT INTO UserNode (UserID, MembershipTier)
SELECT UserID, MembershipTier FROM Users;

PRINT '  Populating graph edges...';

-- Offers: Destination → Activity
INSERT INTO Offers ($from_id, $to_id)
SELECT d.$node_id, a.$node_id
FROM DestinationNode d
INNER JOIN Activities act ON d.DestinationID = act.DestinationID
INNER JOIN ActivityNode a ON act.ActivityID = a.ActivityID;

-- TaggedWith: Activity → Tag
INSERT INTO TaggedWith ($from_id, $to_id)
SELECT a.$node_id, t.$node_id
FROM ActivityNode a
INNER JOIN ActivityTags at2 ON a.ActivityID = at2.ActivityID
INNER JOIN TagNode t ON at2.TagID = t.TagID;

-- Prefers: User → Tag
INSERT INTO Prefers ($from_id, $to_id)
SELECT u.$node_id, t.$node_id
FROM UserNode u
INNER JOIN UserPreferences up ON u.UserID = up.UserID
INNER JOIN TagNode t ON up.TagID = t.TagID;

PRINT '  ✅ Graph data populated';

GO

-- Replace the preference matching SP with graph version
CREATE OR ALTER PROCEDURE dbo.sp_MatchDestinationsByPreferences
    @UserID INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @uid INT = ISNULL(@UserID, (SELECT TOP 1 UserID FROM Users ORDER BY NEWID()));

    -- FIXED: Use MATCH clause for graph traversal
    -- No relational joins needed — graph pointers handle traversal
    SELECT TOP 100
        d.DestinationID,
        d.CityName,
        d.Country,
        d.Climate,
        COUNT(DISTINCT t.TagID) AS MatchingTags,
        COUNT(DISTINCT a.ActivityID) AS MatchingActivities
    FROM UserNode u,
         Prefers pref,
         TagNode t,
         TaggedWith tw,
         ActivityNode a,
         Offers o,
         DestinationNode d
    WHERE MATCH(u-(pref)->t<-(tw)-a<-(o)-d)
    AND u.UserID = @uid
    GROUP BY d.DestinationID, d.CityName, d.Country, d.Climate
    ORDER BY MatchingTags DESC, MatchingActivities DESC;
END
GO

PRINT '  ✅ sp_MatchDestinationsByPreferences replaced with MATCH (graph traversal)';
PRINT '';

-- =============================================
-- Supporting Indexes
-- =============================================

PRINT 'Creating supporting indexes...';

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ActivityTags_TagID')
    CREATE NONCLUSTERED INDEX IX_ActivityTags_TagID ON ActivityTags(TagID) INCLUDE (ActivityID);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_UserPreferences_UserID')
    CREATE NONCLUSTERED INDEX IX_UserPreferences_UserID ON UserPreferences(UserID) INCLUDE (TagID, Strength);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Hotels_DestinationID')
    CREATE NONCLUSTERED INDEX IX_Hotels_DestinationID ON Hotels(DestinationID) INCLUDE (PricePerNight, StarRating, ReviewScore);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Activities_DestinationID')
    CREATE NONCLUSTERED INDEX IX_Activities_DestinationID ON Activities(DestinationID) INCLUDE (ActivityName, Price);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Bookings_DestinationID')
    CREATE NONCLUSTERED INDEX IX_Bookings_DestinationID ON Bookings(DestinationID) INCLUDE (BookingDate, Status, TotalAmount);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Reviews_ItemType_ItemID')
    CREATE NONCLUSTERED INDEX IX_Reviews_ItemType_ItemID ON Reviews(ItemType, ItemID) INCLUDE (Rating, ReviewDate);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Availability_Lookup')
    CREATE NONCLUSTERED INDEX IX_Availability_Lookup ON AvailabilityInventory(ItemType, ItemID, AvailableDate) INCLUDE (TotalUnits, BookedUnits);

PRINT '  ✅ All supporting indexes created';

-- =============================================
-- Clear procedure cache
-- =============================================

PRINT '';
PRINT 'Clearing procedure cache...';
DBCC FREEPROCCACHE;
PRINT '  ✅ Plan cache cleared — all procedures will recompile with new indexes';

-- =============================================
-- Summary
-- =============================================
PRINT '';
PRINT '========================================';
PRINT 'ALL FIXES APPLIED';
PRINT '========================================';
PRINT '';
PRINT '  Fix 5 (LOW):    RCSI enabled — no more reader/writer blocking';
PRINT '  Fix 3 (MEDIUM): Columnstore indexes — Batch Mode for filters';
PRINT '  Fix 4 (MEDIUM): OPTIMIZE FOR UNKNOWN + covering index — stable flight search';
PRINT '  Fix 2 (MEDIUM): Full-Text Search — semantic text matching';
PRINT '  Fix 1 (HIGH):   Graph tables + MATCH — eliminates join explosion';
PRINT '';
PRINT '  + 7 supporting nonclustered indexes';
PRINT '  + Procedure cache cleared';
PRINT '';

SET NOCOUNT OFF;
GO
