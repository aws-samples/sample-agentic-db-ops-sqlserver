-- =============================================================================
-- 05_enrich_for_app_search.sql
-- Additive, idempotent enrichment of TravelHub so the ReefShark main-page search
-- (Destinations, Flights, Hotels, Activities) behaves like a real travel app
-- using plain TEXT SEARCH (no semantic / no TravelAI dependency).
--
-- NON-DESTRUCTIVE: only ADDs nullable columns and UPDATEs descriptive/display
-- data. It does NOT alter or drop the benchmark anti-pattern procedures or any
-- existing columns they depend on. Safe to re-run.
-- =============================================================================
USE TravelHub;
GO

-- ---------------------------------------------------------------------------
-- 1. Schema additions (guarded / idempotent)
-- ---------------------------------------------------------------------------
IF COL_LENGTH('dbo.Destinations','DisplayName') IS NULL
    ALTER TABLE dbo.Destinations ADD DisplayName NVARCHAR(120) NULL;
GO
IF COL_LENGTH('dbo.Destinations','Tags') IS NULL
    ALTER TABLE dbo.Destinations ADD Tags NVARCHAR(500) NULL;
GO
IF COL_LENGTH('dbo.Hotels','City') IS NULL
    ALTER TABLE dbo.Hotels ADD City NVARCHAR(120) NULL;
GO
IF COL_LENGTH('dbo.Hotels','Amenities') IS NULL
    ALTER TABLE dbo.Hotels ADD Amenities NVARCHAR(500) NULL;
GO
IF COL_LENGTH('dbo.Activities','Category') IS NULL
    ALTER TABLE dbo.Activities ADD Category NVARCHAR(60) NULL;
GO
IF COL_LENGTH('dbo.Activities','Tags') IS NULL
    ALTER TABLE dbo.Activities ADD Tags NVARCHAR(300) NULL;
GO
IF COL_LENGTH('dbo.Activities','City') IS NULL
    ALTER TABLE dbo.Activities ADD City NVARCHAR(120) NULL;
GO
IF COL_LENGTH('dbo.Flights','OriginCity') IS NULL
    ALTER TABLE dbo.Flights ADD OriginCity NVARCHAR(60) NULL;
GO
IF COL_LENGTH('dbo.Flights','DestCity') IS NULL
    ALTER TABLE dbo.Flights ADD DestCity NVARCHAR(60) NULL;
GO

-- ---------------------------------------------------------------------------
-- 2. Destinations: clean DisplayName (strip synthetic " Zone N") + curated
--    themed descriptions and searchable tags per real city.
-- ---------------------------------------------------------------------------
UPDATE dbo.Destinations
SET DisplayName = LTRIM(RTRIM(
    LEFT(CityName, CASE WHEN CHARINDEX(' Zone', CityName) > 0
                        THEN CHARINDEX(' Zone', CityName) - 1
                        ELSE LEN(CityName) END)));
GO

IF OBJECT_ID('tempdb..#CityMeta') IS NOT NULL DROP TABLE #CityMeta;
CREATE TABLE #CityMeta (BaseCity NVARCHAR(120) PRIMARY KEY, Blurb NVARCHAR(600), Tags NVARCHAR(500));
INSERT INTO #CityMeta (BaseCity, Blurb, Tags) VALUES
(N'Amsterdam',    N'Charming canals, world-class museums and lively bike-friendly streets in the heart of the Netherlands.', N'canals, museums, cycling, art, nightlife, historic, city break, tulips'),
(N'Bali',         N'Palm-fringed beaches, world-class surf breaks, lush rice terraces and clifftop temples.', N'beach, surfing, snorkeling, diving, temples, rice terraces, yoga, tropical, island'),
(N'Bangkok',      N'Golden temples, buzzing street-food markets and vibrant nightlife.', N'temples, street food, markets, nightlife, culture, shopping, tropical'),
(N'Barcelona',    N'Gaudi architecture, sunny Mediterranean beaches and legendary tapas.', N'beach, architecture, tapas, art, nightlife, mediterranean, city break'),
(N'Cancun',       N'White-sand Caribbean beaches, coral reefs and ancient Mayan ruins.', N'beach, snorkeling, diving, resort, nightlife, mayan ruins, tropical'),
(N'Cape Town',    N'Table Mountain hikes, scenic coastal drives and nearby vineyards and safaris.', N'mountain, hiking, beach, wine, safari, coastal'),
(N'Costa Rica',   N'Rainforest zip lines, volcano hikes, surf beaches and abundant wildlife.', N'rainforest, wildlife, surfing, zip line, volcano, eco, beach, tropical'),
(N'Dubai',        N'Futuristic skyscrapers, luxury shopping, desert safaris and gold souks.', N'desert, luxury, shopping, skyscrapers, safari, beach, nightlife'),
(N'Fiji',         N'Idyllic islands, coral reefs and world-class snorkeling and diving.', N'beach, snorkeling, diving, island, resort, tropical, reef'),
(N'Hawaii',       N'Volcanic landscapes, legendary surf, waterfalls and golden beaches.', N'beach, surfing, volcano, snorkeling, hiking, tropical, island'),
(N'Istanbul',     N'Grand mosques, historic bazaars and a cruise-worthy Bosphorus strait.', N'history, mosques, bazaar, culture, food, mediterranean'),
(N'Kyoto',        N'Ancient temples, zen gardens, geisha districts and cherry blossoms.', N'temples, gardens, culture, cherry blossom, history, temperate'),
(N'Lisbon',       N'Pastel hills, historic trams, fresh seafood and sunny Atlantic beaches.', N'coastal, history, food, trams, nightlife, beach, mediterranean'),
(N'London',       N'Iconic landmarks, world-class museums, West End theatre and royal history.', N'history, museums, theatre, shopping, culture, royal, city break'),
(N'Machu Picchu', N'The legendary Inca citadel, dramatic mountain treks and the historic Inca Trail.', N'hiking, ruins, mountains, trekking, history, inca, highland'),
(N'Maldives',     N'Overwater villas, turquoise lagoons and pristine coral reefs.', N'beach, snorkeling, diving, island, luxury, resort, tropical, honeymoon'),
(N'Marrakech',    N'Bustling souks, ornate palaces, tranquil gardens and a gateway to the Sahara.', N'desert, souks, culture, palaces, food, gardens'),
(N'New York',     N'Skyscrapers, Broadway shows, world-class museums and endless dining.', N'city, museums, shopping, theatre, nightlife, food, city break'),
(N'Paris',        N'The Eiffel Tower, Louvre masterpieces, chic cafes and romantic boulevards.', N'art, museums, cafes, romance, fashion, history, architecture, city break'),
(N'Phuket',       N'Tropical beaches, island-hopping, diving and buzzing nightlife.', N'beach, snorkeling, diving, nightlife, island, tropical'),
(N'Prague',       N'A fairytale old town, a hilltop castle and famous Czech beer halls.', N'history, architecture, castle, beer, culture, old town, city break'),
(N'Queenstown',   N'The adventure capital: skiing, bungee, jet boating and alpine lakes.', N'adventure, skiing, bungee, hiking, lake, mountains, snow'),
(N'Reykjavik',    N'Northern lights, glaciers, geothermal spas and whale watching.', N'northern lights, glacier, geothermal, whale watching, volcano, arctic'),
(N'Rio de Janeiro', N'Copacabana beaches, Christ the Redeemer and infectious carnival energy.', N'beach, carnival, nightlife, mountains, samba, tropical'),
(N'Rome',         N'Ancient ruins, the Colosseum, Vatican art and timeless Italian cuisine.', N'history, ruins, art, food, architecture, mediterranean, city break'),
(N'Santorini',    N'Whitewashed cliffs, blue-domed churches and world-famous caldera sunsets.', N'beach, sunset, wine, coastal, romance, mediterranean, honeymoon'),
(N'Singapore',    N'Futuristic gardens, hawker food, luxury shopping and family attractions.', N'city, food, gardens, shopping, nightlife, family, tropical'),
(N'Sydney',       N'Harbour icons, surf beaches, coastal walks and the famous Opera House.', N'beach, harbour, surfing, opera, coastal, hiking, city break'),
(N'Tokyo',        N'Neon districts, ancient temples, incredible food and endless shopping.', N'city, food, culture, shopping, temples, nightlife, technology'),
(N'Zanzibar',     N'Spice-island beaches, turquoise water, diving and historic Stone Town.', N'beach, snorkeling, diving, spice, island, tropical, history');
GO

UPDATE d
SET d.Description = m.Blurb,
    d.Tags        = m.Tags
FROM dbo.Destinations d
JOIN #CityMeta m ON m.BaseCity = d.DisplayName;
GO

-- Fallback: keep any unmapped destination searchable/consistent.
UPDATE dbo.Destinations
SET Tags = CONCAT(Climate, N', ', Country, N', ', Continent, N', travel')
WHERE Tags IS NULL;
GO

-- ---------------------------------------------------------------------------
-- 3. Hotels: denormalized City, realistic names, amenities + rich description.
-- ---------------------------------------------------------------------------
UPDATE h
SET h.City = d.DisplayName
FROM dbo.Hotels h
JOIN dbo.Destinations d ON h.DestinationID = d.DestinationID;
GO

UPDATE h
SET h.Amenities = CONCAT(
      N'Free WiFi, 24/7 Reception, Air Conditioning',
      CASE WHEN h.StarRating >= 3 THEN N', Swimming Pool, Restaurant, Fitness Center' ELSE N'' END,
      CASE WHEN h.StarRating >= 4 THEN N', Spa, Bar, Room Service' ELSE N'' END,
      CASE WHEN h.StarRating >= 5 THEN N', Airport Shuttle, Concierge, Rooftop Pool' ELSE N'' END,
      CASE WHEN d.Climate IN (N'Tropical', N'Mediterranean') THEN N', Beachfront, Ocean View' ELSE N'' END,
      CASE WHEN d.Climate = N'Arid' THEN N', Desert View, Pool Bar' ELSE N'' END)
FROM dbo.Hotels h
JOIN dbo.Destinations d ON h.DestinationID = d.DestinationID;
GO

;WITH B AS (
    SELECT HotelID, City, StarRating,
        CASE HotelID % 10
            WHEN 0 THEN N'The Grand'   WHEN 1 THEN N'Royal'     WHEN 2 THEN N'Seaside'
            WHEN 3 THEN N'Boutique'    WHEN 4 THEN N'Plaza'     WHEN 5 THEN N'Harbour View'
            WHEN 6 THEN N'Riverside'   WHEN 7 THEN N'Sunset'    WHEN 8 THEN N'Imperial'
            ELSE N'Parkside' END AS Brand,
        CASE WHEN StarRating >= 5 THEN N'Resort & Spa'
             WHEN StarRating  = 4 THEN N'Hotel & Suites'
             WHEN StarRating  = 3 THEN N'Hotel'
             ELSE N'Inn' END AS Kind
    FROM dbo.Hotels
)
UPDATE h
SET h.HotelName = CONCAT(B.Brand, N' ', h.City, N' ', B.Kind)
FROM dbo.Hotels h
JOIN B ON B.HotelID = h.HotelID;
GO

UPDATE h
SET h.Description = CONCAT(
      CAST(h.StarRating AS NVARCHAR(2)), N'-star stay in ', h.City, N', ', d.Country,
      N'. Amenities: ', h.Amenities,
      N'. Guest rating ', CAST(h.ReviewScore AS NVARCHAR(5)), N'/5.')
FROM dbo.Hotels h
JOIN dbo.Destinations d ON h.DestinationID = d.DestinationID;
GO

-- ---------------------------------------------------------------------------
-- 4. Activities: realistic, varied types mapped by destination climate.
-- ---------------------------------------------------------------------------
UPDATE a
SET a.City = d.DisplayName
FROM dbo.Activities a
JOIN dbo.Destinations d ON a.DestinationID = d.DestinationID;
GO

IF OBJECT_ID('tempdb..#ActTypes') IS NOT NULL DROP TABLE #ActTypes;
CREATE TABLE #ActTypes (Climate NVARCHAR(30), Idx INT, Name NVARCHAR(60), Difficulty NVARCHAR(20), Tags NVARCHAR(200));
INSERT INTO #ActTypes (Climate, Idx, Name, Difficulty, Tags) VALUES
(N'Tropical',0,N'Scuba Diving',N'Medium',N'diving, reef, underwater, ocean, adventure'),
(N'Tropical',1,N'Snorkeling Tour',N'Easy',N'snorkeling, reef, beach, family, ocean'),
(N'Tropical',2,N'Surfing Lesson',N'Medium',N'surfing, beach, waves, watersports'),
(N'Tropical',3,N'Island Hopping Cruise',N'Easy',N'island, boat, cruise, beach, sightseeing'),
(N'Tropical',4,N'Sunset Beach BBQ',N'Easy',N'beach, food, sunset, relaxing'),
(N'Tropical',5,N'Jungle Zip Line',N'Medium',N'zip line, jungle, adventure, rainforest'),
(N'Mediterranean',0,N'Wine Tasting Tour',N'Easy',N'wine, food, vineyard, culture'),
(N'Mediterranean',1,N'Historic Old Town Walk',N'Easy',N'history, walking, culture, architecture'),
(N'Mediterranean',2,N'Sailing Day Trip',N'Easy',N'sailing, coast, boat, sea'),
(N'Mediterranean',3,N'Cooking Class',N'Easy',N'cooking, food, cuisine, culture'),
(N'Mediterranean',4,N'Coastal Cliff Hike',N'Medium',N'hiking, coast, nature, views'),
(N'Temperate',0,N'City Walking Tour',N'Easy',N'city, walking, culture, sightseeing'),
(N'Temperate',1,N'Museum and Art Pass',N'Easy',N'museum, art, culture, history, indoor'),
(N'Temperate',2,N'Food and Market Tour',N'Easy',N'food, market, culture, local'),
(N'Temperate',3,N'Bike City Tour',N'Medium',N'cycling, bike, city, active'),
(N'Temperate',4,N'Evening Ghost Walk',N'Easy',N'history, walking, evening, stories'),
(N'Arid',0,N'Desert Safari',N'Medium',N'desert, safari, dunes, adventure, offroad'),
(N'Arid',1,N'Camel Trek at Dawn',N'Easy',N'camel, desert, sunrise, culture'),
(N'Arid',2,N'Old Souk Market Tour',N'Easy',N'market, souk, shopping, culture'),
(N'Arid',3,N'Dune Buggy Adventure',N'Hard',N'dunes, adventure, offroad, desert'),
(N'Highland',0,N'Inca Trail Trek',N'Hard',N'hiking, trekking, ruins, mountains, inca'),
(N'Highland',1,N'Ancient Ruins Tour',N'Medium',N'ruins, history, culture, mountains'),
(N'Highland',2,N'Mountain Village Hike',N'Medium',N'hiking, mountains, nature, villages'),
(N'Arctic',0,N'Northern Lights Tour',N'Easy',N'northern lights, aurora, night, winter'),
(N'Arctic',1,N'Glacier Hike',N'Hard',N'glacier, ice, hiking, adventure'),
(N'Arctic',2,N'Whale Watching Cruise',N'Easy',N'whale, wildlife, boat, ocean'),
(N'Arctic',3,N'Geothermal Spa Day',N'Easy',N'spa, geothermal, relaxing, hot spring');
GO

-- Use ROW_NUMBER per climate (not ActivityID % n) so every type in a climate's
-- pool is used and the distribution is even (ActivityIDs cluster by climate).
;WITH cnt AS (SELECT Climate, COUNT(*) AS c FROM #ActTypes GROUP BY Climate),
ranked AS (
    SELECT a.ActivityID, d.Climate, d.DisplayName, d.Country,
           (ROW_NUMBER() OVER (PARTITION BY d.Climate ORDER BY a.ActivityID) - 1) AS rn
    FROM dbo.Activities a
    JOIN dbo.Destinations d ON a.DestinationID = d.DestinationID
)
UPDATE a
SET a.ActivityName   = t.Name,
    a.Category       = t.Name,
    a.Tags           = t.Tags,
    a.DifficultyLevel= t.Difficulty,
    a.Description     = CONCAT(N'Enjoy ', t.Name, N' in ', r.DisplayName, N', ', r.Country, N'. ', t.Tags, N'.')
FROM dbo.Activities a
JOIN ranked r ON r.ActivityID = a.ActivityID
JOIN cnt ON cnt.Climate = r.Climate
JOIN #ActTypes t ON t.Climate = r.Climate AND t.Idx = (r.rn % cnt.c);
GO

-- Fallback for any climate without a defined pool.
UPDATE a
SET a.ActivityName = ISNULL(a.ActivityName, N'Guided City Tour'),
    a.Category     = ISNULL(a.Category, N'Guided City Tour'),
    a.Tags         = ISNULL(a.Tags, N'sightseeing, city, culture')
FROM dbo.Activities a
WHERE a.Category IS NULL;
GO

-- ---------------------------------------------------------------------------
-- 5. Flights: map 3-letter codes to real city names for both ends + aircraft.
-- ---------------------------------------------------------------------------
IF OBJECT_ID('tempdb..#Codes') IS NOT NULL DROP TABLE #Codes;
CREATE TABLE #Codes (Code NVARCHAR(10) PRIMARY KEY, City NVARCHAR(60));
INSERT INTO #Codes (Code, City) VALUES
(N'Bal',N'Bali'),(N'Bar',N'Barcelona'),(N'Can',N'Cancun'),(N'Cap',N'Cape Town'),
(N'Cos',N'Costa Rica'),(N'Fij',N'Fiji'),(N'Haw',N'Hawaii'),(N'Kyo',N'Kyoto'),
(N'Lis',N'Lisbon'),(N'Mac',N'Machu Picchu'),(N'Mal',N'Maldives'),(N'Mar',N'Marrakech'),
(N'Phu',N'Phuket'),(N'Pra',N'Prague'),(N'Que',N'Queenstown'),(N'Rey',N'Reykjavik'),
(N'Rio',N'Rio de Janeiro'),(N'Rom',N'Rome'),(N'San',N'Santorini'),(N'Sin',N'Singapore'),
(N'Syd',N'Sydney'),(N'Tok',N'Tokyo'),(N'Zan',N'Zanzibar');
GO

UPDATE f SET f.OriginCity = co.City
FROM dbo.Flights f JOIN #Codes co ON co.Code = f.Origin;
GO
UPDATE f SET f.DestCity = cd.City
FROM dbo.Flights f JOIN #Codes cd ON cd.Code = f.Destination;
GO
UPDATE dbo.Flights SET OriginCity = Origin WHERE OriginCity IS NULL;
UPDATE dbo.Flights SET DestCity   = Destination WHERE DestCity IS NULL;
GO
UPDATE dbo.Flights
SET Aircraft = CASE FlightID % 5
        WHEN 0 THEN N'Boeing 787 Dreamliner'
        WHEN 1 THEN N'Airbus A350'
        WHEN 2 THEN N'Boeing 777'
        WHEN 3 THEN N'Airbus A320neo'
        ELSE N'Boeing 737 MAX' END
WHERE Aircraft IS NULL;
GO

-- ---------------------------------------------------------------------------
-- 6. Verification
-- ---------------------------------------------------------------------------
PRINT 'TravelHub app-search enrichment complete.';
SELECT
    (SELECT COUNT(*) FROM dbo.Destinations WHERE Tags IS NOT NULL)      AS Destinations_Tagged,
    (SELECT COUNT(DISTINCT DisplayName) FROM dbo.Destinations)          AS Distinct_Cities,
    (SELECT COUNT(*) FROM dbo.Hotels WHERE Amenities IS NOT NULL)       AS Hotels_Enriched,
    (SELECT COUNT(DISTINCT ActivityName) FROM dbo.Activities)           AS Distinct_Activities,
    (SELECT COUNT(*) FROM dbo.Flights WHERE OriginCity IS NOT NULL)     AS Flights_Mapped;
GO


-- ---------------------------------------------------------------------------
-- 7. Generate flights for cities that shipped with no routes (Amsterdam,
--    Bangkok, Dubai, Istanbul, London, New York, Paris). Creates both
--    directions between each of these and every other city, spread across the
--    existing 2026-09-01 .. 2027-08-31 window, using the real airlines and
--    aircraft. Idempotent: only runs when those cities have no flights yet.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM dbo.Flights WHERE OriginCity = N'Paris')
BEGIN
    IF OBJECT_ID('tempdb..#AllCities') IS NOT NULL DROP TABLE #AllCities;
    CREATE TABLE #AllCities (Name NVARCHAR(60), Code NVARCHAR(10));
    INSERT INTO #AllCities (Name, Code) VALUES
    (N'Amsterdam',N'Ams'),(N'Bali',N'Bal'),(N'Bangkok',N'Ban'),(N'Barcelona',N'Bar'),
    (N'Cancun',N'Can'),(N'Cape Town',N'Cap'),(N'Costa Rica',N'Cos'),(N'Dubai',N'Dub'),
    (N'Fiji',N'Fij'),(N'Hawaii',N'Haw'),(N'Istanbul',N'Ist'),(N'Kyoto',N'Kyo'),
    (N'Lisbon',N'Lis'),(N'London',N'Lon'),(N'Machu Picchu',N'Mac'),(N'Maldives',N'Mal'),
    (N'Marrakech',N'Mar'),(N'New York',N'New'),(N'Paris',N'Par'),(N'Phuket',N'Phu'),
    (N'Prague',N'Pra'),(N'Queenstown',N'Que'),(N'Reykjavik',N'Rey'),(N'Rio de Janeiro',N'Rio'),
    (N'Rome',N'Rom'),(N'Santorini',N'San'),(N'Singapore',N'Sin'),(N'Sydney',N'Syd'),
    (N'Tokyo',N'Tok'),(N'Zanzibar',N'Zan');

    IF OBJECT_ID('tempdb..#Missing') IS NOT NULL DROP TABLE #Missing;
    CREATE TABLE #Missing (Name NVARCHAR(60) PRIMARY KEY);
    INSERT INTO #Missing (Name) VALUES
    (N'Amsterdam'),(N'Bangkok'),(N'Dubai'),(N'Istanbul'),(N'London'),(N'New York'),(N'Paris');

    IF OBJECT_ID('tempdb..#Air') IS NOT NULL DROP TABLE #Air;
    CREATE TABLE #Air (Name NVARCHAR(50), IATA NVARCHAR(2));
    INSERT INTO #Air (Name, IATA) VALUES
    (N'Air France',N'AF'),(N'American Airlines',N'AA'),(N'British Airways',N'BA'),
    (N'Delta',N'DL'),(N'Emirates',N'EK'),(N'Japan Airlines',N'JL'),
    (N'Lufthansa',N'LH'),(N'Qantas',N'QF'),(N'Singapore Airlines',N'SQ'),
    (N'United Airlines',N'UA');

    -- ~100 flights per route => roughly one every 3-4 days across the year.
    IF OBJECT_ID('tempdb..#N') IS NOT NULL DROP TABLE #N;
    CREATE TABLE #N (n INT);
    INSERT INTO #N (n)
    SELECT TOP (100) ROW_NUMBER() OVER (ORDER BY (SELECT NULL))
    FROM sys.all_objects;

    ;WITH routes AS (
        SELECT o.Name AS OName, o.Code AS OCode, d.Name AS DName, d.Code AS DCode
        FROM #AllCities o
        CROSS JOIN #AllCities d
        WHERE o.Name <> d.Name
          AND (o.Name IN (SELECT Name FROM #Missing)
               OR d.Name IN (SELECT Name FROM #Missing))
    )
    INSERT INTO dbo.Flights
        (Airline, FlightNumber, Origin, Destination, DepartDate, DepartTime, ArriveTime,
         DurationMinutes, Price, SeatsAvailable, Aircraft, OriginCity, DestCity)
    SELECT
        a.Name,
        a.IATA + RIGHT('0000' + CAST(ABS(CHECKSUM(NEWID())) % 9000 + 1000 AS NVARCHAR(4)), 4),
        r.OCode, r.DCode,
        DATEADD(DAY, ABS(CHECKSUM(NEWID())) % 365, '2026-09-01'),
        CAST(DATEADD(MINUTE, ABS(CHECKSUM(NEWID())) % 1440, CAST('00:00:00' AS TIME)) AS TIME),
        CAST(DATEADD(MINUTE, ABS(CHECKSUM(NEWID())) % 1440, CAST('00:00:00' AS TIME)) AS TIME),
        180 + ABS(CHECKSUM(NEWID())) % 720,
        CAST(100 + ABS(CHECKSUM(NEWID())) % 1900 AS DECIMAL(10,2)),
        20 + ABS(CHECKSUM(NEWID())) % 280,
        CASE ABS(CHECKSUM(NEWID())) % 5
            WHEN 0 THEN N'Boeing 787 Dreamliner' WHEN 1 THEN N'Airbus A350'
            WHEN 2 THEN N'Boeing 777' WHEN 3 THEN N'Airbus A320neo'
            ELSE N'Boeing 737 MAX' END,
        r.OName, r.DName
    FROM routes r
    CROSS JOIN #N
    CROSS APPLY (SELECT TOP 1 Name, IATA FROM #Air ORDER BY NEWID()) a;

    PRINT 'Generated flights for previously-uncovered cities.';
END
ELSE
BEGIN
    PRINT 'Uncovered-city flights already present. Skipping generation.';
END
GO
