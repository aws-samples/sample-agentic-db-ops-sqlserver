-- Updated: 2026-03-15
-- =============================================
-- Database Setup and Data Population Script
-- Creates database, tables, and loads test data
-- --EXEC msdb.dbo.rds_drop_database N'dbopslab'
--ALTER DATABASE DBOpsLab SET QUERY_STORE = ON (OPERATION_MODE = READ_WRITE);---enable query store
-- =============================================
--
-- Create database if not exists
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'DBOpsLab')
BEGIN
    CREATE DATABASE DBOpsLab;
    PRINT 'Database DBOpsLab created successfully';
END
ELSE
BEGIN
    PRINT 'Database DBOpsLab already exists';
END
GO

USE DBOpsLab;
GO

SET NOCOUNT ON;

-- =============================================
-- Create Tables if not exist
-- =============================================
PRINT 'Creating tables...';

-- Customers table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Customers')
BEGIN
    CREATE TABLE Customers (
        CustomerID INT IDENTITY(1,1) PRIMARY KEY,
        FirstName NVARCHAR(50) NOT NULL,
        LastName NVARCHAR(50) NOT NULL,
        Email NVARCHAR(100) NOT NULL,
        Phone NVARCHAR(20),
        City NVARCHAR(50),
        State NVARCHAR(50),
        Country NVARCHAR(50) DEFAULT 'USA',
        DateOfBirth DATE,
        CreatedDate DATETIME DEFAULT GETDATE(),
        LastModified DATETIME DEFAULT GETDATE()
    );
    PRINT '  Created: Customers';
END
ELSE
    PRINT '  Already exists: Customers';

-- Products table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Products')
BEGIN
    CREATE TABLE Products (
        ProductID INT IDENTITY(1,1) PRIMARY KEY,
        ProductName NVARCHAR(100) NOT NULL,
        Category NVARCHAR(50),
        SubCategory NVARCHAR(50),
        Price DECIMAL(10,2) NOT NULL,
        Cost DECIMAL(10,2),
        StockQuantity INT DEFAULT 0,
        ReorderLevel INT DEFAULT 10,
        Supplier NVARCHAR(100),
        CreatedDate DATETIME DEFAULT GETDATE()
    );
    PRINT '  Created: Products';
END
ELSE
    PRINT '  Already exists: Products';

-- Orders table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Orders')
BEGIN
    CREATE TABLE Orders (
        OrderID INT IDENTITY(1,1) PRIMARY KEY,
        CustomerID INT NOT NULL,
        OrderDate DATETIME NOT NULL DEFAULT GETDATE(),
        ShipDate DATETIME,
        TotalAmount DECIMAL(12,2) NOT NULL,
        Status NVARCHAR(20) DEFAULT 'Pending',
        ShippingCity NVARCHAR(50),
        ShippingState NVARCHAR(50),
        PaymentMethod NVARCHAR(50)
    );
    PRINT '  Created: Orders';
END
ELSE
    PRINT '  Already exists: Orders';

-- OrderDetails table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'OrderDetails')
BEGIN
    CREATE TABLE OrderDetails (
        OrderDetailID INT IDENTITY(1,1) PRIMARY KEY,
        OrderID INT NOT NULL,
        ProductID INT NOT NULL,
        Quantity INT NOT NULL,
        UnitPrice DECIMAL(10,2) NOT NULL,
        Discount DECIMAL(5,2) DEFAULT 0,
        LineTotal AS (Quantity * UnitPrice * (1 - Discount/100)) PERSISTED
    );
    PRINT '  Created: OrderDetails';
END
ELSE
    PRINT '  Already exists: OrderDetails';

-- Inventory table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Inventory')
BEGIN
    CREATE TABLE Inventory (
        InventoryID INT IDENTITY(1,1) PRIMARY KEY,
        ProductID INT NOT NULL,
        WarehouseLocation NVARCHAR(50),
        Quantity INT NOT NULL,
        LastRestocked DATETIME DEFAULT GETDATE()
    );
    PRINT '  Created: Inventory';
END
ELSE
    PRINT '  Already exists: Inventory';

PRINT '';

-- =============================================
-- Populate Data
-- =============================================
PRINT 'Starting data population...';
PRINT '';

-- Check if data already exists
DECLARE @CustomerCount INT = (SELECT COUNT(*) FROM Customers);
DECLARE @ProductCount INT = (SELECT COUNT(*) FROM Products);

IF @CustomerCount > 0 OR @ProductCount > 0
BEGIN
    PRINT 'WARNING: Tables already contain data.';
    PRINT 'Current counts - Customers: ' + CAST(@CustomerCount AS NVARCHAR(10)) + ', Products: ' + CAST(@ProductCount AS NVARCHAR(10));
    PRINT 'Skipping data population. Truncate tables first if you want to reload.';
    PRINT '';
END
ELSE
BEGIN
    -- Populate Customers (500,000 records)
    PRINT 'Populating Customers (500,000 records)...';
    
    DECLARE @CustBatch INT = 0;
    DECLARE @MaxCust INT = 500000;
    
    WHILE @CustBatch < @MaxCust
    BEGIN
        INSERT INTO Customers (FirstName, LastName, Email, Phone, City, State, Country, DateOfBirth, CreatedDate)
        SELECT TOP 10000
            'First' + CAST(n AS NVARCHAR(10)),
            'Last' + CAST(n AS NVARCHAR(10)),
            'user' + CAST(n AS NVARCHAR(10)) + '@email.com',
            '555-' + RIGHT('000000' + CAST(n AS NVARCHAR(10)), 6),
            CASE (n % 20)
                WHEN 0 THEN 'New York' WHEN 1 THEN 'Los Angeles' WHEN 2 THEN 'Chicago'
                WHEN 3 THEN 'Houston' WHEN 4 THEN 'Phoenix' WHEN 5 THEN 'Philadelphia'
                WHEN 6 THEN 'San Antonio' WHEN 7 THEN 'San Diego' WHEN 8 THEN 'Dallas'
                WHEN 9 THEN 'Austin' WHEN 10 THEN 'Seattle' WHEN 11 THEN 'Denver'
                WHEN 12 THEN 'Boston' WHEN 13 THEN 'Portland' WHEN 14 THEN 'Miami'
                WHEN 15 THEN 'Atlanta' WHEN 16 THEN 'Detroit' WHEN 17 THEN 'Minneapolis'
                WHEN 18 THEN 'Tampa' ELSE 'Orlando'
            END,
            CASE (n % 20)
                WHEN 0 THEN 'NY' WHEN 1 THEN 'CA' WHEN 2 THEN 'IL' WHEN 3 THEN 'TX'
                WHEN 4 THEN 'AZ' WHEN 5 THEN 'PA' WHEN 6 THEN 'TX' WHEN 7 THEN 'CA'
                WHEN 8 THEN 'TX' WHEN 9 THEN 'TX' WHEN 10 THEN 'WA' WHEN 11 THEN 'CO'
                WHEN 12 THEN 'MA' WHEN 13 THEN 'OR' WHEN 14 THEN 'FL' WHEN 15 THEN 'GA'
                WHEN 16 THEN 'MI' WHEN 17 THEN 'MN' WHEN 18 THEN 'FL' ELSE 'FL'
            END,
            'USA',
            DATEADD(YEAR, -(18 + (n % 60)), GETDATE()),
            DATEADD(DAY, -(n % 1095), GETDATE())
        FROM (
            SELECT ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) + @CustBatch AS n
            FROM sys.all_objects a CROSS JOIN sys.all_objects b
        ) AS Numbers;
        
        SET @CustBatch = @CustBatch + 10000;
        
        IF @CustBatch % 50000 = 0
            PRINT '  Inserted ' + CAST(@CustBatch AS NVARCHAR(10)) + ' customers...';
    END
    
    PRINT 'Customers completed: 500,000';
    PRINT '';
    
    -- Populate Products (20,000 records)
    PRINT 'Populating Products (20,000 records)...';
    
    INSERT INTO Products (ProductName, Category, SubCategory, Price, Cost, StockQuantity, ReorderLevel, Supplier)
    SELECT TOP 20000
        'Product ' + CAST(ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS NVARCHAR(10)),
        CASE (ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) % 10)
            WHEN 0 THEN 'Electronics' WHEN 1 THEN 'Clothing' WHEN 2 THEN 'Books'
            WHEN 3 THEN 'Home' WHEN 4 THEN 'Sports' WHEN 5 THEN 'Toys'
            WHEN 6 THEN 'Food' WHEN 7 THEN 'Beauty' WHEN 8 THEN 'Automotive' ELSE 'Health'
        END,
        CASE (ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) % 5)
            WHEN 0 THEN 'Premium' WHEN 1 THEN 'Standard' WHEN 2 THEN 'Budget'
            WHEN 3 THEN 'Luxury' ELSE 'Economy'
        END,
        CAST((RAND(CHECKSUM(NEWID())) * 1000 + 10) AS DECIMAL(10,2)),
        CAST((RAND(CHECKSUM(NEWID())) * 500 + 5) AS DECIMAL(10,2)),
        CAST((RAND(CHECKSUM(NEWID())) * 500) AS INT),
        CAST((RAND(CHECKSUM(NEWID())) * 50 + 5) AS INT),
        'Supplier ' + CAST((ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) % 100) AS NVARCHAR(10))
    FROM sys.all_objects a CROSS JOIN sys.all_objects b;
    
    PRINT 'Products completed: 20,000';
    PRINT '';
    
    -- Populate Orders (2,000,000 records)
    PRINT 'Populating Orders (2,000,000 records)...';
    
    DECLARE @OrderBatch INT = 0;
    DECLARE @MaxOrders INT = 2000000;
    
    WHILE @OrderBatch < @MaxOrders
    BEGIN
        INSERT INTO Orders (CustomerID, OrderDate, ShipDate, TotalAmount, Status, ShippingCity, ShippingState, PaymentMethod)
        SELECT TOP 50000
            CAST((RAND(CHECKSUM(NEWID())) * 499999 + 1) AS INT),
            DATEADD(SECOND, -CAST((RAND(CHECKSUM(NEWID())) * 31536000) AS INT), GETDATE()),
            DATEADD(DAY, CAST((RAND(CHECKSUM(NEWID())) * 7) AS INT), DATEADD(SECOND, -CAST((RAND(CHECKSUM(NEWID())) * 31536000) AS INT), GETDATE())),
            CAST((RAND(CHECKSUM(NEWID())) * 5000 + 10) AS DECIMAL(12,2)),
            CASE CAST((RAND(CHECKSUM(NEWID())) * 5) AS INT)
                WHEN 0 THEN 'Pending' WHEN 1 THEN 'Processing' WHEN 2 THEN 'Shipped'
                WHEN 3 THEN 'Delivered' ELSE 'Completed'
            END,
            CASE CAST((RAND(CHECKSUM(NEWID())) * 20) AS INT)
                WHEN 0 THEN 'New York' WHEN 1 THEN 'Los Angeles' WHEN 2 THEN 'Chicago'
                WHEN 3 THEN 'Houston' WHEN 4 THEN 'Phoenix' WHEN 5 THEN 'Philadelphia'
                WHEN 6 THEN 'San Antonio' WHEN 7 THEN 'San Diego' WHEN 8 THEN 'Dallas'
                WHEN 9 THEN 'Austin' WHEN 10 THEN 'Seattle' WHEN 11 THEN 'Denver'
                WHEN 12 THEN 'Boston' WHEN 13 THEN 'Portland' WHEN 14 THEN 'Miami'
                WHEN 15 THEN 'Atlanta' WHEN 16 THEN 'Detroit' WHEN 17 THEN 'Minneapolis'
                WHEN 18 THEN 'Tampa' ELSE 'Orlando'
            END,
            CASE CAST((RAND(CHECKSUM(NEWID())) * 20) AS INT)
                WHEN 0 THEN 'NY' WHEN 1 THEN 'CA' WHEN 2 THEN 'IL' WHEN 3 THEN 'TX'
                WHEN 4 THEN 'AZ' WHEN 5 THEN 'PA' WHEN 6 THEN 'TX' WHEN 7 THEN 'CA'
                WHEN 8 THEN 'TX' WHEN 9 THEN 'TX' WHEN 10 THEN 'WA' WHEN 11 THEN 'CO'
                WHEN 12 THEN 'MA' WHEN 13 THEN 'OR' WHEN 14 THEN 'FL' WHEN 15 THEN 'GA'
                WHEN 16 THEN 'MI' WHEN 17 THEN 'MN' WHEN 18 THEN 'FL' ELSE 'FL'
            END,
            CASE CAST((RAND(CHECKSUM(NEWID())) * 4) AS INT)
                WHEN 0 THEN 'Credit Card' WHEN 1 THEN 'Debit Card'
                WHEN 2 THEN 'PayPal' ELSE 'Bank Transfer'
            END
        FROM sys.all_objects a CROSS JOIN sys.all_objects b;
        
        SET @OrderBatch = @OrderBatch + 50000;
        
        IF @OrderBatch % 200000 = 0
            PRINT '  Inserted ' + CAST(@OrderBatch AS NVARCHAR(10)) + ' orders...';
    END
    
    PRINT 'Orders completed: 2,000,000';
    PRINT '';
    
    -- Populate OrderDetails (6,000,000 records)
    PRINT 'Populating OrderDetails (6,000,000 records)...';
    
    DECLARE @DetailBatch INT = 0;
    DECLARE @MaxDetails INT = 6000000;
    
    WHILE @DetailBatch < @MaxDetails
    BEGIN
        INSERT INTO OrderDetails (OrderID, ProductID, Quantity, UnitPrice, Discount)
        SELECT TOP 100000
            CAST((RAND(CHECKSUM(NEWID())) * 1999999 + 1) AS INT),
            CAST((RAND(CHECKSUM(NEWID())) * 19999 + 1) AS INT),
            CAST((RAND(CHECKSUM(NEWID())) * 10 + 1) AS INT),
            CAST((RAND(CHECKSUM(NEWID())) * 1000 + 10) AS DECIMAL(10,2)),
            CAST((RAND(CHECKSUM(NEWID())) * 20) AS DECIMAL(5,2))
        FROM sys.all_objects a CROSS JOIN sys.all_objects b;
        
        SET @DetailBatch = @DetailBatch + 100000;
        
        IF @DetailBatch % 500000 = 0
            PRINT '  Inserted ' + CAST(@DetailBatch AS NVARCHAR(10)) + ' order details...';
    END
    
    PRINT 'OrderDetails completed: 6,000,000';
    PRINT '';
    
    -- Populate Inventory (100,000 records)
    PRINT 'Populating Inventory (100,000 records)...';
    
    INSERT INTO Inventory (ProductID, WarehouseLocation, Quantity, LastRestocked)
    SELECT TOP 100000
        CAST((RAND(CHECKSUM(NEWID())) * 19999 + 1) AS INT),
        'Warehouse-' + CAST((ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) % 10) AS NVARCHAR(10)),
        CAST((RAND(CHECKSUM(NEWID())) * 1000) AS INT),
        DATEADD(DAY, -CAST((RAND(CHECKSUM(NEWID())) * 365) AS INT), GETDATE())
    FROM sys.all_objects a CROSS JOIN sys.all_objects b;
    
    PRINT 'Inventory completed: 100,000';
    PRINT '';
END

-- =============================================
-- Summary
-- =============================================
PRINT '========================================';
PRINT 'Setup and Population Complete!';
PRINT '========================================';
PRINT '';

SELECT 
    'Customers' AS TableName, 
    COUNT(*) AS RecordCount,
    CAST(SUM(CAST(DATALENGTH(FirstName) + DATALENGTH(LastName) + DATALENGTH(Email) AS BIGINT)) / 1024.0 / 1024.0 AS DECIMAL(10,2)) AS ApproxSizeMB
FROM Customers
UNION ALL
SELECT 
    'Products', 
    COUNT(*),
    CAST(SUM(CAST(DATALENGTH(ProductName) + DATALENGTH(Category) AS BIGINT)) / 1024.0 / 1024.0 AS DECIMAL(10,2))
FROM Products
UNION ALL
SELECT 
    'Orders', 
    COUNT(*),
    CAST(COUNT(*) * 100.0 / 1024.0 / 1024.0 AS DECIMAL(10,2))
FROM Orders
UNION ALL
SELECT 
    'OrderDetails', 
    COUNT(*),
    CAST(COUNT(*) * 50.0 / 1024.0 / 1024.0 AS DECIMAL(10,2))
FROM OrderDetails
UNION ALL
SELECT 
    'Inventory', 
    COUNT(*),
    CAST(COUNT(*) * 30.0 / 1024.0 / 1024.0 AS DECIMAL(10,2))
FROM Inventory;

PRINT '';
PRINT 'Database is ready for load testing!';

SET NOCOUNT OFF;
GO
