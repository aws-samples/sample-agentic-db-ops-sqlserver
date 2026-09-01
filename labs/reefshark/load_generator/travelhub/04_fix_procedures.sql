-- TravelHub Performance Fix — Enabling Indexes
-- =============================================================================
-- The load-generating procedures in 03_create_bad_procedures.sql are SARGable
-- and set-based. They run as table SCANS until these indexes exist, then become
-- SEEKS. This script is the intended remediation (created by the DBOps Actions
-- Agent one index at a time, or applied manually). It is NOT run during setup.
--
-- Each index below maps directly to a rewritten procedure's hot path.
-- =============================================================================

USE TravelHub;
GO

SET NOCOUNT ON;

-- 1) sp_MatchDestinationsByPreferences -------------------------------------------------
--    UserPreferences already has a clustered PK (UserID, TagID), so WHERE UserID=@uid seeks
--    with no extra index. The real cost is the tag-match join and the per-destination
--    aggregates, addressed by the DestinationID indexes below.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ActivityTags_ActivityID')
    CREATE NONCLUSTERED INDEX IX_ActivityTags_ActivityID
        ON ActivityTags (ActivityID) INCLUDE (TagID);

-- 2) sp_FilterDestinationsAdvanced + sp_MatchDestinationsByPreferences ------------------
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Activities_DestinationID')
    CREATE NONCLUSTERED INDEX IX_Activities_DestinationID
        ON Activities (DestinationID) INCLUDE (Price, ActivityName);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Hotels_DestinationID')
    CREATE NONCLUSTERED INDEX IX_Hotels_DestinationID
        ON Hotels (DestinationID) INCLUDE (PricePerNight, StarRating, ReviewScore);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Reviews_ItemType_ItemID')
    CREATE NONCLUSTERED INDEX IX_Reviews_ItemType_ItemID
        ON Reviews (ItemType, ItemID) INCLUDE (Rating);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Bookings_DestinationID')
    CREATE NONCLUSTERED INDEX IX_Bookings_DestinationID
        ON Bookings (DestinationID) INCLUDE (BookingDate, Status, TotalAmount);

-- 3) sp_SearchFlightsByRoute -----------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Flights_Origin_Dest_Date')
    CREATE NONCLUSTERED INDEX IX_Flights_Origin_Dest_Date
        ON Flights (Origin, Destination, DepartDate)
        INCLUDE (Airline, FlightNumber, DepartTime, ArriveTime, DurationMinutes, Price, SeatsAvailable);

-- 4) sp_CheckAndBookAvailability -------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Availability_Lookup')
    CREATE NONCLUSTERED INDEX IX_Availability_Lookup
        ON AvailabilityInventory (ItemType, ItemID, AvailableDate)
        INCLUDE (TotalUnits, BookedUnits);

-- Optional concurrency relief for the booking path (readers no longer block writers).
-- ALTER DATABASE TravelHub SET READ_COMMITTED_SNAPSHOT ON;

PRINT 'TravelHub enabling indexes created. Re-run the workload to observe CPU drop.';
GO
