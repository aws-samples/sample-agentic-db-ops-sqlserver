-- TravelHub Data Population
-- Generates ~3M rows of realistic travel data

USE TravelHub;
GO

SET NOCOUNT ON;
DECLARE @cnt INT;

PRINT '========================================';
PRINT 'Populating TravelHub with test data';
PRINT '========================================';

-- =============================================
-- Preference Tags (200 tags across categories)
-- =============================================
PRINT 'Creating preference tags...';

INSERT INTO PreferenceTags (TagName, Category) VALUES
-- Activities (50)
('snorkeling', 'Activity'), ('scuba-diving', 'Activity'), ('surfing', 'Activity'),
('hiking', 'Activity'), ('skiing', 'Activity'), ('kayaking', 'Activity'),
('rock-climbing', 'Activity'), ('zip-lining', 'Activity'), ('parasailing', 'Activity'),
('whale-watching', 'Activity'), ('fishing', 'Activity'), ('sailing', 'Activity'),
('yoga', 'Activity'), ('meditation', 'Activity'), ('spa', 'Activity'),
('golf', 'Activity'), ('tennis', 'Activity'), ('cycling', 'Activity'),
('horseback-riding', 'Activity'), ('bungee-jumping', 'Activity'),
('cooking-class', 'Activity'), ('wine-tasting', 'Activity'), ('photography', 'Activity'),
('bird-watching', 'Activity'), ('stargazing', 'Activity'), ('camping', 'Activity'),
('rafting', 'Activity'), ('canoeing', 'Activity'), ('jet-skiing', 'Activity'),
('paddleboarding', 'Activity'), ('sandboarding', 'Activity'), ('caving', 'Activity'),
('volcano-tour', 'Activity'), ('glacier-walk', 'Activity'), ('safari', 'Activity'),
('wildlife', 'Activity'), ('aquarium', 'Activity'), ('zoo', 'Activity'),
('theme-park', 'Activity'), ('water-park', 'Activity'), ('museum', 'Activity'),
('art-gallery', 'Activity'), ('theater', 'Activity'), ('concert', 'Activity'),
('nightlife', 'Activity'), ('casino', 'Activity'), ('shopping', 'Activity'),
('food-tour', 'Activity'), ('street-food', 'Activity'), ('fine-dining', 'Activity'),
('local-markets', 'Activity'),
-- Environment (30)
('beach', 'Environment'), ('mountain', 'Environment'), ('jungle', 'Environment'),
('desert', 'Environment'), ('island', 'Environment'), ('lake', 'Environment'),
('river', 'Environment'), ('waterfall', 'Environment'), ('coral-reef', 'Environment'),
('rainforest', 'Environment'), ('savanna', 'Environment'), ('arctic', 'Environment'),
('tropical', 'Environment'), ('mediterranean', 'Environment'), ('coastal', 'Environment'),
('countryside', 'Environment'), ('urban', 'Environment'), ('rural', 'Environment'),
('historic-city', 'Environment'), ('modern-city', 'Environment'), ('village', 'Environment'),
('vineyard', 'Environment'), ('plantation', 'Environment'), ('national-park', 'Environment'),
('marine-reserve', 'Environment'), ('hot-springs', 'Environment'), ('caves', 'Environment'),
('cliffs', 'Environment'), ('dunes', 'Environment'), ('fjord', 'Environment'),
-- Budget (10)
('budget', 'Budget'), ('mid-range', 'Budget'), ('luxury', 'Budget'),
('ultra-luxury', 'Budget'), ('backpacker', 'Budget'), ('all-inclusive', 'Budget'),
('value', 'Budget'), ('splurge', 'Budget'), ('free-activities', 'Budget'),
('deals', 'Budget'),
-- Travel Style (30)
('family', 'Style'), ('couples', 'Style'), ('solo', 'Style'),
('group', 'Style'), ('adventure', 'Style'), ('relaxation', 'Style'),
('cultural', 'Style'), ('romantic', 'Style'), ('eco-friendly', 'Style'),
('sustainable', 'Style'), ('digital-nomad', 'Style'), ('wellness', 'Style'),
('spiritual', 'Style'), ('foodie', 'Style'), ('photography-trip', 'Style'),
('road-trip', 'Style'), ('cruise', 'Style'), ('backpacking', 'Style'),
('glamping', 'Style'), ('staycation', 'Style'), ('workation', 'Style'),
('honeymoon', 'Style'), ('anniversary', 'Style'), ('birthday', 'Style'),
('graduation', 'Style'), ('retirement', 'Style'), ('pet-friendly', 'Style'),
('accessible', 'Style'), ('kid-friendly', 'Style'), ('adults-only', 'Style'),
-- Season (10)
('summer', 'Season'), ('winter', 'Season'), ('spring', 'Season'),
('autumn', 'Season'), ('year-round', 'Season'), ('dry-season', 'Season'),
('monsoon', 'Season'), ('peak-season', 'Season'), ('off-season', 'Season'),
('shoulder-season', 'Season'),
-- Amenity (30)
('pool', 'Amenity'), ('gym', 'Amenity'), ('wifi', 'Amenity'),
('parking', 'Amenity'), ('restaurant', 'Amenity'), ('bar', 'Amenity'),
('room-service', 'Amenity'), ('airport-shuttle', 'Amenity'), ('concierge', 'Amenity'),
('laundry', 'Amenity'), ('business-center', 'Amenity'), ('conference-room', 'Amenity'),
('kids-club', 'Amenity'), ('babysitting', 'Amenity'), ('pet-allowed', 'Amenity'),
('ocean-view', 'Amenity'), ('balcony', 'Amenity'), ('kitchen', 'Amenity'),
('jacuzzi', 'Amenity'), ('sauna', 'Amenity'), ('spa-facility', 'Amenity'),
('private-beach', 'Amenity'), ('dive-center', 'Amenity'), ('tennis-court', 'Amenity'),
('golf-course', 'Amenity'), ('ski-in-ski-out', 'Amenity'), ('rooftop', 'Amenity'),
('garden', 'Amenity'), ('terrace', 'Amenity'), ('fireplace', 'Amenity');

PRINT '  ✅ Created ' + CAST(@@ROWCOUNT AS VARCHAR) + ' preference tags';

-- =============================================
-- Destinations (5000)
-- =============================================
PRINT 'Creating destinations...';

DECLARE @Cities TABLE (CityName NVARCHAR(100), Country NVARCHAR(50), Continent NVARCHAR(30), Climate NVARCHAR(30), Season NVARCHAR(20));
INSERT INTO @Cities VALUES
('Paris', 'France', 'Europe', 'Temperate', 'spring'),
('Bali', 'Indonesia', 'Asia', 'Tropical', 'dry-season'),
('Tokyo', 'Japan', 'Asia', 'Temperate', 'spring'),
('Cancun', 'Mexico', 'North America', 'Tropical', 'winter'),
('Barcelona', 'Spain', 'Europe', 'Mediterranean', 'summer'),
('Maldives', 'Maldives', 'Asia', 'Tropical', 'winter'),
('New York', 'USA', 'North America', 'Temperate', 'autumn'),
('Dubai', 'UAE', 'Asia', 'Arid', 'winter'),
('Rome', 'Italy', 'Europe', 'Mediterranean', 'spring'),
('Sydney', 'Australia', 'Oceania', 'Temperate', 'summer'),
('Cape Town', 'South Africa', 'Africa', 'Mediterranean', 'summer'),
('Reykjavik', 'Iceland', 'Europe', 'Arctic', 'summer'),
('Marrakech', 'Morocco', 'Africa', 'Arid', 'spring'),
('Bangkok', 'Thailand', 'Asia', 'Tropical', 'dry-season'),
('Santorini', 'Greece', 'Europe', 'Mediterranean', 'summer'),
('Machu Picchu', 'Peru', 'South America', 'Highland', 'dry-season'),
('Queenstown', 'New Zealand', 'Oceania', 'Temperate', 'winter'),
('Phuket', 'Thailand', 'Asia', 'Tropical', 'dry-season'),
('London', 'UK', 'Europe', 'Temperate', 'summer'),
('Rio de Janeiro', 'Brazil', 'South America', 'Tropical', 'summer'),
('Istanbul', 'Turkey', 'Europe', 'Mediterranean', 'spring'),
('Kyoto', 'Japan', 'Asia', 'Temperate', 'autumn'),
('Hawaii', 'USA', 'North America', 'Tropical', 'year-round'),
('Amsterdam', 'Netherlands', 'Europe', 'Temperate', 'spring'),
('Singapore', 'Singapore', 'Asia', 'Tropical', 'year-round'),
('Zanzibar', 'Tanzania', 'Africa', 'Tropical', 'dry-season'),
('Lisbon', 'Portugal', 'Europe', 'Mediterranean', 'summer'),
('Fiji', 'Fiji', 'Oceania', 'Tropical', 'dry-season'),
('Prague', 'Czech Republic', 'Europe', 'Temperate', 'spring'),
('Costa Rica', 'Costa Rica', 'North America', 'Tropical', 'dry-season');

-- Generate 5000 destinations by duplicating with variations
DECLARE @i INT = 1;
WHILE @i <= 167
BEGIN
    INSERT INTO Destinations (CityName, Country, Continent, Climate, Description, PopularityScore, Season)
    SELECT
        CityName + ' Zone ' + CAST(@i AS VARCHAR),
        Country,
        Continent,
        Climate,
        'A wonderful destination in ' + Country + ' known for its ' + Climate + ' climate and diverse activities. Perfect for travelers seeking authentic experiences.',
        ABS(CHECKSUM(NEWID())) % 100,
        Season
    FROM @Cities;
    SET @i = @i + 1;
END

SET @cnt = (SELECT COUNT(*) FROM Destinations); PRINT '  ✅ Created destinations: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Users (500,000)
-- =============================================
PRINT 'Creating users (500K)...';

DECLARE @batch INT = 1;
DECLARE @batchSize INT = 10000;

WHILE @batch <= 50
BEGIN
    ;WITH Numbers AS (
        SELECT TOP (@batchSize) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n
        FROM sys.all_objects a CROSS JOIN sys.all_objects b
    )
    INSERT INTO Users (FirstName, LastName, Email, MembershipTier, Country, City, CreatedDate)
    SELECT
        'User' + CAST((@batch - 1) * @batchSize + n AS VARCHAR),
        'Traveler' + CAST(n % 1000 AS VARCHAR),
        'user' + CAST((@batch - 1) * @batchSize + n AS VARCHAR) + '@travelhub.com',
        CASE ((@batch - 1) * @batchSize + n) % 10
            WHEN 0 THEN 'Platinum'
            WHEN 1 THEN 'Gold'
            WHEN 2 THEN 'Gold'
            WHEN 3 THEN 'Silver'
            WHEN 4 THEN 'Silver'
            WHEN 5 THEN 'Silver'
            ELSE 'Free'
        END,
        CASE n % 10
            WHEN 0 THEN 'USA' WHEN 1 THEN 'UK' WHEN 2 THEN 'Germany'
            WHEN 3 THEN 'France' WHEN 4 THEN 'Japan' WHEN 5 THEN 'Australia'
            WHEN 6 THEN 'Canada' WHEN 7 THEN 'Brazil' WHEN 8 THEN 'India'
            ELSE 'Singapore'
        END,
        'City' + CAST(n % 200 AS VARCHAR),
        DATEADD(DAY, -ABS(CHECKSUM(NEWID())) % 730, GETDATE())
    FROM Numbers;

    IF @batch % 10 = 0
        PRINT '    Users: ' + CAST(@batch * @batchSize AS VARCHAR);
    SET @batch = @batch + 1;
END

SET @cnt = (SELECT COUNT(*) FROM Users); PRINT '  ✅ Created users: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- User Preferences (2M - ~4 tags per user)
-- =============================================
PRINT 'Creating user preferences (2M)...';

DECLARE @maxTagID INT;
SET @maxTagID = (SELECT MAX(TagID) FROM PreferenceTags);
SET @batch = 1;

WHILE @batch <= 50
BEGIN
    ;WITH UserBatch AS (
        SELECT UserID FROM Users
        WHERE UserID BETWEEN (@batch - 1) * 10000 + 1 AND @batch * 10000
    )
    INSERT INTO UserPreferences (UserID, TagID, Strength)
    SELECT UserID, TagID, MAX(Strength)
    FROM (
        SELECT u.UserID AS UserID,
               (ABS(CHECKSUM(NEWID())) % @maxTagID) + 1 AS TagID,
               CAST((ABS(CHECKSUM(NEWID())) % 100) / 100.0 AS DECIMAL(3,2)) AS Strength
        FROM UserBatch u
        CROSS APPLY (SELECT TOP (3 + ABS(CHECKSUM(NEWID())) % 6) n = 1 FROM sys.all_objects) tags
    ) g
    GROUP BY UserID, TagID;

    IF @batch % 10 = 0
        PRINT '    Preferences batch: ' + CAST(@batch AS VARCHAR);
    SET @batch = @batch + 1;
END

SET @cnt = (SELECT COUNT(*) FROM UserPreferences); PRINT '  ✅ Created user preferences: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Activities (50,000)
-- =============================================
PRINT 'Creating activities...';

DECLARE @activityNames TABLE (Name NVARCHAR(100), Difficulty NVARCHAR(20), AvgPrice DECIMAL(10,2), AvgDuration DECIMAL(4,1));
INSERT INTO @activityNames VALUES
('Snorkeling Tour', 'Easy', 75, 3), ('Deep Sea Diving', 'Hard', 150, 4),
('Sunset Cruise', 'Easy', 90, 3), ('Mountain Hiking', 'Medium', 45, 6),
('City Walking Tour', 'Easy', 30, 3), ('Cooking Class', 'Easy', 80, 3),
('Wine Tasting', 'Easy', 95, 4), ('Kayaking Adventure', 'Medium', 65, 3),
('Zip Line Experience', 'Medium', 85, 2), ('Safari Drive', 'Easy', 200, 8),
('Surfing Lesson', 'Medium', 70, 2), ('Temple Visit', 'Easy', 25, 2),
('Hot Air Balloon', 'Easy', 250, 2), ('Rock Climbing', 'Hard', 90, 4),
('Whale Watching', 'Easy', 120, 4), ('Parasailing', 'Medium', 80, 1),
('Jet Ski Rental', 'Medium', 100, 1), ('Photography Tour', 'Easy', 60, 3),
('Food Market Tour', 'Easy', 40, 3), ('Spa Day', 'Easy', 150, 5);

DECLARE @destCount INT;
SET @destCount = (SELECT COUNT(*) FROM Destinations);

;WITH DestBatch AS (
    SELECT DestinationID, ROW_NUMBER() OVER (ORDER BY DestinationID) AS rn
    FROM Destinations
)
INSERT INTO Activities (ActivityName, DestinationID, Description, Price, DurationHours, DifficultyLevel)
SELECT
    a.Name + ' - ' + CAST(d.DestinationID AS VARCHAR),
    d.DestinationID,
    'Experience ' + a.Name + ' in this amazing destination. Perfect for all skill levels.',
    a.AvgPrice + (ABS(CHECKSUM(NEWID())) % 50),
    a.AvgDuration,
    a.Difficulty
FROM DestBatch d
CROSS APPLY (
    SELECT TOP (2 + ABS(CHECKSUM(NEWID())) % 8) Name, Difficulty, AvgPrice, AvgDuration
    FROM @activityNames
    ORDER BY NEWID()
) a
WHERE d.rn <= 5000;

SET @cnt = (SELECT COUNT(*) FROM Activities); PRINT '  ✅ Created activities: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Activity Tags (150,000)
-- =============================================
PRINT 'Creating activity tags...';

INSERT INTO ActivityTags (ActivityID, TagID)
SELECT DISTINCT
    a.ActivityID,
    (ABS(CHECKSUM(NEWID())) % @maxTagID) + 1
FROM Activities a
CROSS APPLY (SELECT TOP (2 + ABS(CHECKSUM(NEWID())) % 4) n = 1 FROM sys.all_objects) tags;

SET @cnt = (SELECT COUNT(*) FROM ActivityTags); PRINT '  ✅ Created activity tags: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Destination Activities junction
-- =============================================
PRINT 'Creating destination-activity links...';

INSERT INTO DestinationActivities (DestinationID, ActivityID)
SELECT DISTINCT DestinationID, ActivityID FROM Activities;

SET @cnt = (SELECT COUNT(*) FROM DestinationActivities); PRINT '  ✅ Created destination-activity links: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Hotels (100,000)
-- =============================================
PRINT 'Creating hotels...';

;WITH DestBatch AS (
    SELECT DestinationID, CityName, Country
    FROM Destinations WHERE DestinationID <= 5000
)
INSERT INTO Hotels (HotelName, DestinationID, StarRating, PricePerNight, TotalRooms, Description, ReviewScore)
SELECT
    CASE (d.DestinationID * 20 + n) % 5
        WHEN 0 THEN 'Grand Hotel ' WHEN 1 THEN 'Resort ' WHEN 2 THEN 'Inn '
        WHEN 3 THEN 'Lodge ' WHEN 4 THEN 'Suites '
    END + d.CityName + ' ' + CAST(n AS VARCHAR),
    d.DestinationID,
    1 + ABS(CHECKSUM(NEWID())) % 5,
    50 + ABS(CHECKSUM(NEWID())) % 450,
    20 + ABS(CHECKSUM(NEWID())) % 280,
    'A ' + CASE (d.DestinationID + n) % 3 WHEN 0 THEN 'luxurious' WHEN 1 THEN 'comfortable' ELSE 'modern' END + ' hotel in ' + d.Country + ' offering world-class amenities and stunning views.',
    CAST(2.0 + (ABS(CHECKSUM(NEWID())) % 30) / 10.0 AS DECIMAL(3,1))
FROM DestBatch d
CROSS APPLY (SELECT TOP 20 ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n FROM sys.all_objects) nums;

SET @cnt = (SELECT COUNT(*) FROM Hotels); PRINT '  ✅ Created hotels: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Hotel Amenities (400,000)
-- =============================================
PRINT 'Creating hotel amenities...';

INSERT INTO HotelAmenities (HotelID, AmenityName, TagID)
SELECT DISTINCT
    h.HotelID,
    pt.TagName,
    pt.TagID
FROM Hotels h
CROSS APPLY (
    SELECT TOP (3 + ABS(CHECKSUM(NEWID())) % 5) TagID, TagName
    FROM PreferenceTags
    WHERE Category = 'Amenity'
    ORDER BY NEWID()
) pt;

SET @cnt = (SELECT COUNT(*) FROM HotelAmenities); PRINT '  ✅ Created hotel amenities: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Flights (500,000)
-- =============================================
PRINT 'Creating flights (500K)...';

DECLARE @airlines TABLE (Airline NVARCHAR(50), Code NVARCHAR(3));
INSERT INTO @airlines VALUES
('United Airlines', 'UA'), ('Delta', 'DL'), ('American Airlines', 'AA'),
('British Airways', 'BA'), ('Emirates', 'EK'), ('Lufthansa', 'LH'),
('Singapore Airlines', 'SQ'), ('Qantas', 'QF'), ('Air France', 'AF'),
('Japan Airlines', 'JL');

DECLARE @airports TABLE (Code NVARCHAR(10), DestID INT);
INSERT INTO @airports
SELECT TOP 50
    LEFT(REPLACE(CityName, ' ', ''), 3),
    DestinationID
FROM Destinations
ORDER BY PopularityScore DESC;

SET @batch = 1;
WHILE @batch <= 50
BEGIN
    INSERT INTO Flights (Airline, FlightNumber, Origin, Destination, DepartDate, DepartTime, ArriveTime, DurationMinutes, Price, SeatsAvailable)
    SELECT TOP 10000
        al.Airline,
        al.Code + CAST(1000 + ABS(CHECKSUM(NEWID())) % 9000 AS VARCHAR),
        o.Code,
        d.Code,
        DATEADD(DAY, ABS(CHECKSUM(NEWID())) % 365, GETDATE()),
        CAST(DATEADD(MINUTE, ABS(CHECKSUM(NEWID())) % 1440, '00:00') AS TIME),
        CAST(DATEADD(MINUTE, ABS(CHECKSUM(NEWID())) % 1440, '00:00') AS TIME),
        60 + ABS(CHECKSUM(NEWID())) % 840,
        100 + ABS(CHECKSUM(NEWID())) % 1900,
        ABS(CHECKSUM(NEWID())) % 180
    FROM @airports o
    CROSS JOIN @airports d
    CROSS JOIN @airlines al
    WHERE o.Code <> d.Code
    ORDER BY NEWID();

    IF @batch % 10 = 0
        PRINT '    Flights: ' + CAST(@batch * 10000 AS VARCHAR);
    SET @batch = @batch + 1;
END

SET @cnt = (SELECT COUNT(*) FROM Flights); PRINT '  ✅ Created flights: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Bookings (800,000)
-- =============================================
PRINT 'Creating bookings (800K)...';

SET @batch = 1;
WHILE @batch <= 80
BEGIN
    ;WITH UserBatch AS (
        SELECT TOP 10000 UserID FROM Users ORDER BY NEWID()
    )
    INSERT INTO Bookings (UserID, DestinationID, BookingDate, TravelStartDate, TravelEndDate, TotalAmount, Status)
    SELECT
        u.UserID,
        (ABS(CHECKSUM(NEWID())) % @destCount) + 1,
        DATEADD(DAY, -ABS(CHECKSUM(NEWID())) % 730, GETDATE()),
        DATEADD(DAY, ABS(CHECKSUM(NEWID())) % 365, GETDATE()),
        DATEADD(DAY, ABS(CHECKSUM(NEWID())) % 365 + 3, GETDATE()),
        200 + ABS(CHECKSUM(NEWID())) % 4800,
        CASE ABS(CHECKSUM(NEWID())) % 10
            WHEN 0 THEN 'Cancelled'
            WHEN 1 THEN 'Pending'
            ELSE 'Confirmed'
        END
    FROM UserBatch u;

    IF @batch % 20 = 0
        PRINT '    Bookings: ' + CAST(@batch * 10000 AS VARCHAR);
    SET @batch = @batch + 1;
END

SET @cnt = (SELECT COUNT(*) FROM Bookings); PRINT '  ✅ Created bookings: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Availability Inventory (200,000)
-- =============================================
PRINT 'Creating availability inventory...';

DECLARE @hotelCount INT;  SET @hotelCount  = (SELECT COUNT(*) FROM Hotels);
DECLARE @flightCount INT; SET @flightCount = (SELECT COUNT(*) FROM Flights);
INSERT INTO AvailabilityInventory (ItemType, ItemID, AvailableDate, TotalUnits, BookedUnits)
SELECT TOP 200000
    x.ItemType,
    CASE WHEN x.ItemType = 'Hotel' THEN (ABS(CHECKSUM(NEWID())) % @hotelCount) + 1
         ELSE (ABS(CHECKSUM(NEWID())) % @flightCount) + 1 END,
    DATEADD(DAY, x.n % 365, GETDATE()),
    10 + ABS(CHECKSUM(NEWID())) % 90,
    ABS(CHECKSUM(NEWID())) % 50
FROM (
    SELECT TOP 200000
        ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n,
        CASE ABS(CHECKSUM(NEWID())) % 2 WHEN 0 THEN 'Hotel' ELSE 'Flight' END AS ItemType
    FROM sys.all_objects a CROSS JOIN sys.all_objects b
) x;

SET @cnt = (SELECT COUNT(*) FROM AvailabilityInventory); PRINT '  ✅ Created availability records: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Reviews (500,000)
-- =============================================
PRINT 'Creating reviews (500K)...';

SET @batch = 1;
WHILE @batch <= 50
BEGIN
    INSERT INTO Reviews (UserID, ItemType, ItemID, Rating, Title, ReviewText, ReviewDate, HelpfulVotes)
    SELECT TOP 10000
        (ABS(CHECKSUM(NEWID())) % 500000) + 1,
        CASE ABS(CHECKSUM(NEWID())) % 3 WHEN 0 THEN 'Hotel' WHEN 1 THEN 'Activity' ELSE 'Destination' END,
        ABS(CHECKSUM(NEWID())) % 5000 + 1,
        1 + ABS(CHECKSUM(NEWID())) % 5,
        CASE ABS(CHECKSUM(NEWID())) % 5
            WHEN 0 THEN 'Amazing experience!'
            WHEN 1 THEN 'Highly recommended'
            WHEN 2 THEN 'Good but could be better'
            WHEN 3 THEN 'Exceeded expectations'
            ELSE 'Worth every penny'
        END,
        CASE ABS(CHECKSUM(NEWID())) % 4
            WHEN 0 THEN 'We had an absolutely wonderful time. The destination was beautiful and the service was impeccable. Would definitely come back again. The snorkeling was the highlight of our trip.'
            WHEN 1 THEN 'Great location with stunning views. The activities were well organized and the staff was friendly. The coral reef diving experience was unforgettable. Perfect for families.'
            WHEN 2 THEN 'A truly magical experience. From the moment we arrived, everything was perfect. The eco-friendly approach and sustainable tourism practices really stood out. Highly recommended for nature lovers.'
            ELSE 'Exceptional value for money. The all-inclusive package covered everything we needed. Shopping areas were walkable and the local food scene was incredible. Will definitely return next year.'
        END,
        DATEADD(DAY, -ABS(CHECKSUM(NEWID())) % 730, GETDATE()),
        ABS(CHECKSUM(NEWID())) % 50
    FROM sys.all_objects a CROSS JOIN sys.all_objects b;

    IF @batch % 10 = 0
        PRINT '    Reviews: ' + CAST(@batch * 10000 AS VARCHAR);
    SET @batch = @batch + 1;
END

SET @cnt = (SELECT COUNT(*) FROM Reviews); PRINT '  ✅ Created reviews: ' + CAST(@cnt AS VARCHAR);

-- =============================================
-- Summary
-- =============================================
PRINT '';
PRINT '========================================';
PRINT 'DATA POPULATION COMPLETE';
PRINT '========================================';

SELECT 'Users' AS TableName, COUNT(*) AS [RowCount] FROM Users
UNION ALL SELECT 'UserPreferences', COUNT(*) FROM UserPreferences
UNION ALL SELECT 'PreferenceTags', COUNT(*) FROM PreferenceTags
UNION ALL SELECT 'Destinations', COUNT(*) FROM Destinations
UNION ALL SELECT 'Activities', COUNT(*) FROM Activities
UNION ALL SELECT 'ActivityTags', COUNT(*) FROM ActivityTags
UNION ALL SELECT 'Hotels', COUNT(*) FROM Hotels
UNION ALL SELECT 'HotelAmenities', COUNT(*) FROM HotelAmenities
UNION ALL SELECT 'Flights', COUNT(*) FROM Flights
UNION ALL SELECT 'Bookings', COUNT(*) FROM Bookings
UNION ALL SELECT 'AvailabilityInventory', COUNT(*) FROM AvailabilityInventory
UNION ALL SELECT 'Reviews', COUNT(*) FROM Reviews
ORDER BY [RowCount] DESC;

SET NOCOUNT OFF;
GO
