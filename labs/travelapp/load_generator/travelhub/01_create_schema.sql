-- TravelHub Database Schema
-- Creates all tables for the travel booking platform

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'TravelHub')
BEGIN
    CREATE DATABASE TravelHub;
    PRINT 'Database TravelHub created';
END
GO

USE TravelHub;
GO

SET NOCOUNT ON;

-- =============================================
-- Users & Preferences
-- =============================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
CREATE TABLE Users (
    UserID INT IDENTITY(1,1) PRIMARY KEY,
    FirstName NVARCHAR(50) NOT NULL,
    LastName NVARCHAR(50) NOT NULL,
    Email NVARCHAR(100) NOT NULL,
    PasswordHash NVARCHAR(256),
    MembershipTier NVARCHAR(20) DEFAULT 'Free',
    Country NVARCHAR(50),
    City NVARCHAR(50),
    DateOfBirth DATE,
    CreatedDate DATETIME DEFAULT GETDATE(),
    LastLoginDate DATETIME
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'PreferenceTags')
CREATE TABLE PreferenceTags (
    TagID INT IDENTITY(1,1) PRIMARY KEY,
    TagName NVARCHAR(50) NOT NULL,
    Category NVARCHAR(30) NOT NULL,
    CONSTRAINT UQ_TagName UNIQUE (TagName)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserPreferences')
CREATE TABLE UserPreferences (
    UserID INT NOT NULL,
    TagID INT NOT NULL,
    Strength DECIMAL(3,2) DEFAULT 1.0,
    AddedDate DATETIME DEFAULT GETDATE(),
    PRIMARY KEY (UserID, TagID),
    FOREIGN KEY (UserID) REFERENCES Users(UserID),
    FOREIGN KEY (TagID) REFERENCES PreferenceTags(TagID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'UserSessions')
CREATE TABLE UserSessions (
    SessionID INT IDENTITY(1,1) PRIMARY KEY,
    UserID INT NOT NULL,
    LoginTime DATETIME NOT NULL,
    LogoutTime DATETIME,
    IPAddress NVARCHAR(45),
    DeviceType NVARCHAR(20),
    FOREIGN KEY (UserID) REFERENCES Users(UserID)
);

-- =============================================
-- Destinations & Inventory
-- =============================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Destinations')
CREATE TABLE Destinations (
    DestinationID INT IDENTITY(1,1) PRIMARY KEY,
    CityName NVARCHAR(100) NOT NULL,
    Country NVARCHAR(50) NOT NULL,
    Continent NVARCHAR(30) NOT NULL,
    Climate NVARCHAR(30),
    Description NVARCHAR(MAX),
    Latitude DECIMAL(9,6),
    Longitude DECIMAL(9,6),
    PopularityScore INT DEFAULT 0,
    Season NVARCHAR(20)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Activities')
CREATE TABLE Activities (
    ActivityID INT IDENTITY(1,1) PRIMARY KEY,
    ActivityName NVARCHAR(100) NOT NULL,
    DestinationID INT NOT NULL,
    Description NVARCHAR(MAX),
    Price DECIMAL(10,2),
    DurationHours DECIMAL(4,1),
    DifficultyLevel NVARCHAR(20),
    MinAge INT DEFAULT 0,
    MaxGroupSize INT DEFAULT 20,
    FOREIGN KEY (DestinationID) REFERENCES Destinations(DestinationID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'ActivityTags')
CREATE TABLE ActivityTags (
    ActivityID INT NOT NULL,
    TagID INT NOT NULL,
    PRIMARY KEY (ActivityID, TagID),
    FOREIGN KEY (ActivityID) REFERENCES Activities(ActivityID),
    FOREIGN KEY (TagID) REFERENCES PreferenceTags(TagID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'DestinationActivities')
CREATE TABLE DestinationActivities (
    DestinationID INT NOT NULL,
    ActivityID INT NOT NULL,
    AvailableFrom DATE,
    AvailableTo DATE,
    PRIMARY KEY (DestinationID, ActivityID),
    FOREIGN KEY (DestinationID) REFERENCES Destinations(DestinationID),
    FOREIGN KEY (ActivityID) REFERENCES Activities(ActivityID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Flights')
CREATE TABLE Flights (
    FlightID INT IDENTITY(1,1) PRIMARY KEY,
    Airline NVARCHAR(50) NOT NULL,
    FlightNumber NVARCHAR(10) NOT NULL,
    Origin NVARCHAR(10) NOT NULL,
    Destination NVARCHAR(10) NOT NULL,
    OriginDestinationID INT,
    DestDestinationID INT,
    DepartDate DATE NOT NULL,
    DepartTime TIME NOT NULL,
    ArriveTime TIME NOT NULL,
    DurationMinutes INT,
    Price DECIMAL(10,2) NOT NULL,
    SeatsAvailable INT DEFAULT 180,
    Aircraft NVARCHAR(30),
    FOREIGN KEY (OriginDestinationID) REFERENCES Destinations(DestinationID),
    FOREIGN KEY (DestDestinationID) REFERENCES Destinations(DestinationID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Hotels')
CREATE TABLE Hotels (
    HotelID INT IDENTITY(1,1) PRIMARY KEY,
    HotelName NVARCHAR(100) NOT NULL,
    DestinationID INT NOT NULL,
    StarRating INT CHECK (StarRating BETWEEN 1 AND 5),
    PricePerNight DECIMAL(10,2) NOT NULL,
    TotalRooms INT DEFAULT 100,
    Description NVARCHAR(MAX),
    Address NVARCHAR(200),
    ReviewScore DECIMAL(3,1) DEFAULT 0,
    FOREIGN KEY (DestinationID) REFERENCES Destinations(DestinationID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'HotelAmenities')
CREATE TABLE HotelAmenities (
    HotelID INT NOT NULL,
    AmenityName NVARCHAR(50) NOT NULL,
    TagID INT,
    PRIMARY KEY (HotelID, AmenityName),
    FOREIGN KEY (HotelID) REFERENCES Hotels(HotelID),
    FOREIGN KEY (TagID) REFERENCES PreferenceTags(TagID)
);

-- =============================================
-- Bookings & Transactions
-- =============================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Bookings')
CREATE TABLE Bookings (
    BookingID INT IDENTITY(1,1) PRIMARY KEY,
    UserID INT NOT NULL,
    DestinationID INT,
    BookingDate DATETIME DEFAULT GETDATE(),
    TravelStartDate DATE NOT NULL,
    TravelEndDate DATE NOT NULL,
    TotalAmount DECIMAL(12,2),
    Status NVARCHAR(20) DEFAULT 'Confirmed',
    CancellationDate DATETIME,
    FOREIGN KEY (UserID) REFERENCES Users(UserID),
    FOREIGN KEY (DestinationID) REFERENCES Destinations(DestinationID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'BookingFlights')
CREATE TABLE BookingFlights (
    BookingFlightID INT IDENTITY(1,1) PRIMARY KEY,
    BookingID INT NOT NULL,
    FlightID INT NOT NULL,
    SeatClass NVARCHAR(20) DEFAULT 'Economy',
    Price DECIMAL(10,2),
    FOREIGN KEY (BookingID) REFERENCES Bookings(BookingID),
    FOREIGN KEY (FlightID) REFERENCES Flights(FlightID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'BookingHotels')
CREATE TABLE BookingHotels (
    BookingHotelID INT IDENTITY(1,1) PRIMARY KEY,
    BookingID INT NOT NULL,
    HotelID INT NOT NULL,
    CheckInDate DATE NOT NULL,
    CheckOutDate DATE NOT NULL,
    RoomType NVARCHAR(30) DEFAULT 'Standard',
    Price DECIMAL(10,2),
    FOREIGN KEY (BookingID) REFERENCES Bookings(BookingID),
    FOREIGN KEY (HotelID) REFERENCES Hotels(HotelID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'BookingActivities')
CREATE TABLE BookingActivities (
    BookingActivityID INT IDENTITY(1,1) PRIMARY KEY,
    BookingID INT NOT NULL,
    ActivityID INT NOT NULL,
    ActivityDate DATE NOT NULL,
    Participants INT DEFAULT 1,
    Price DECIMAL(10,2),
    FOREIGN KEY (BookingID) REFERENCES Bookings(BookingID),
    FOREIGN KEY (ActivityID) REFERENCES Activities(ActivityID)
);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'AvailabilityInventory')
CREATE TABLE AvailabilityInventory (
    InventoryID INT IDENTITY(1,1) PRIMARY KEY,
    ItemType NVARCHAR(20) NOT NULL,
    ItemID INT NOT NULL,
    AvailableDate DATE NOT NULL,
    TotalUnits INT NOT NULL,
    BookedUnits INT DEFAULT 0,
    LastUpdated DATETIME DEFAULT GETDATE()
);

-- =============================================
-- Reviews
-- =============================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Reviews')
CREATE TABLE Reviews (
    ReviewID INT IDENTITY(1,1) PRIMARY KEY,
    UserID INT NOT NULL,
    ItemType NVARCHAR(20) NOT NULL,
    ItemID INT NOT NULL,
    Rating INT CHECK (Rating BETWEEN 1 AND 5),
    Title NVARCHAR(200),
    ReviewText NVARCHAR(MAX),
    ReviewDate DATETIME DEFAULT GETDATE(),
    HelpfulVotes INT DEFAULT 0,
    FOREIGN KEY (UserID) REFERENCES Users(UserID)
);

GO

PRINT '========================================';
PRINT 'TravelHub schema created successfully';
PRINT '========================================';

SET NOCOUNT OFF;
GO
