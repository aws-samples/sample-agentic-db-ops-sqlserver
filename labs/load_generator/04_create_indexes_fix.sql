-- Updated: 2026-03-15
-- =============================================
-- Resolution Script - Performance Optimization --takes about 50 seconds to create the index
-- Creates indexes and optimizes queries
-- =============================================

USE DBOpsLab;
GO

SET NOCOUNT ON;

PRINT '========================================';
PRINT 'PERFORMANCE OPTIMIZATION';
PRINT 'Creating indexes and optimizing queries';
PRINT '========================================';
PRINT '';

-- =============================================
-- Step 1: Create Foreign Key Indexes
-- =============================================
PRINT 'Step 1: Creating Foreign Key Indexes...';

-- Orders.CustomerID
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Orders_CustomerID' AND object_id = OBJECT_ID('Orders'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Orders_CustomerID 
    ON Orders(CustomerID)
    INCLUDE (OrderDate, TotalAmount, Status, OrderID);
    PRINT '  Created: IX_Orders_CustomerID';
END

-- OrderDetails.OrderID
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OrderDetails_OrderID' AND object_id = OBJECT_ID('OrderDetails'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_OrderDetails_OrderID 
    ON OrderDetails(OrderID)
    INCLUDE (ProductID, Quantity, UnitPrice, LineTotal);
    PRINT '  Created: IX_OrderDetails_OrderID';
END

-- OrderDetails.ProductID
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OrderDetails_ProductID' AND object_id = OBJECT_ID('OrderDetails'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_OrderDetails_ProductID 
    ON OrderDetails(ProductID)
    INCLUDE (OrderID, Quantity, UnitPrice, LineTotal);
    PRINT '  Created: IX_OrderDetails_ProductID';
END

-- Inventory.ProductID
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Inventory_ProductID' AND object_id = OBJECT_ID('Inventory'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Inventory_ProductID 
    ON Inventory(ProductID)
    INCLUDE (WarehouseLocation, Quantity);
    PRINT '  Created: IX_Inventory_ProductID';
END

PRINT '';

-- =============================================
-- Step 2: Create Filtered Indexes
-- =============================================
PRINT 'Step 2: Creating Filtered Indexes...';

-- Orders by Status (for active orders)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Orders_Status_Active' AND object_id = OBJECT_ID('Orders'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Orders_Status_Active 
    ON Orders(Status, OrderDate)
    INCLUDE (CustomerID, TotalAmount, OrderID)
    WHERE Status IN ('Pending', 'Processing', 'Shipped');
    PRINT '  Created: IX_Orders_Status_Active';
END

-- Products by Category
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Products_Category' AND object_id = OBJECT_ID('Products'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Products_Category 
    ON Products(Category, Price)
    INCLUDE (ProductID, ProductName, SubCategory, StockQuantity);
    PRINT '  Created: IX_Products_Category';
END

PRINT '';

-- =============================================
-- Step 3: Create Date-Based Indexes
-- =============================================
PRINT 'Step 3: Creating Date-Based Indexes...';

-- Orders by OrderDate
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Orders_OrderDate' AND object_id = OBJECT_ID('Orders'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Orders_OrderDate 
    ON Orders(OrderDate DESC)
    INCLUDE (CustomerID, TotalAmount, Status, OrderID);
    PRINT '  Created: IX_Orders_OrderDate';
END

-- Customers by CreatedDate
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Customers_CreatedDate' AND object_id = OBJECT_ID('Customers'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Customers_CreatedDate 
    ON Customers(CreatedDate)
    INCLUDE (CustomerID, FirstName, LastName, Email, City, State);
    PRINT '  Created: IX_Customers_CreatedDate';
END

PRINT '';

-- =============================================
-- Step 4: Create Composite Indexes
-- =============================================
PRINT 'Step 4: Creating Composite Indexes...';

-- Customers by State and City
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Customers_State_City' AND object_id = OBJECT_ID('Customers'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Customers_State_City 
    ON Customers(State, City)
    INCLUDE (CustomerID, FirstName, LastName, Email, CreatedDate);
    PRINT '  Created: IX_Customers_State_City';
END

-- Orders by CustomerID and OrderDate
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Orders_CustomerID_OrderDate' AND object_id = OBJECT_ID('Orders'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Orders_CustomerID_OrderDate 
    ON Orders(CustomerID, OrderDate DESC)
    INCLUDE (OrderID, TotalAmount, Status);
    PRINT '  Created: IX_Orders_CustomerID_OrderDate';
END

-- Orders by ShippingState
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Orders_ShippingState' AND object_id = OBJECT_ID('Orders'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Orders_ShippingState 
    ON Orders(ShippingState)
    INCLUDE (OrderID, CustomerID, TotalAmount, OrderDate);
    PRINT '  Created: IX_Orders_ShippingState';
END

-- Products by Price
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Products_Price' AND object_id = OBJECT_ID('Products'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Products_Price 
    ON Products(Price)
    INCLUDE (ProductID, ProductName, Category, StockQuantity);
    PRINT '  Created: IX_Products_Price';
END

-- Products by StockQuantity
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Products_StockQuantity' AND object_id = OBJECT_ID('Products'))
BEGIN
    CREATE NONCLUSTERED INDEX IX_Products_StockQuantity 
    ON Products(StockQuantity)
    INCLUDE (ProductID, ProductName, Category);
    PRINT '  Created: IX_Products_StockQuantity';
END

PRINT '';

-- =============================================
-- Step 5: Update Statistics
-- =============================================
PRINT 'Step 5: Updating Statistics...';

UPDATE STATISTICS Customers WITH FULLSCAN;
PRINT '  Updated: Customers';

UPDATE STATISTICS Products WITH FULLSCAN;
PRINT '  Updated: Products';

UPDATE STATISTICS Orders WITH FULLSCAN;
PRINT '  Updated: Orders';

UPDATE STATISTICS OrderDetails WITH FULLSCAN;
PRINT '  Updated: OrderDetails';

UPDATE STATISTICS Inventory WITH FULLSCAN;
PRINT '  Updated: Inventory';

PRINT '';

-- =============================================
-- Step 6: Display Index Summary
-- =============================================
PRINT '========================================';
PRINT 'OPTIMIZATION COMPLETE!';
PRINT '========================================';
PRINT '';
PRINT 'Index Summary:';

SELECT 
    OBJECT_NAME(i.object_id) AS TableName,
    i.name AS IndexName,
    i.type_desc AS IndexType,
    CASE WHEN i.is_unique = 1 THEN 'Yes' ELSE 'No' END AS IsUnique,
    CASE WHEN i.has_filter = 1 THEN 'Yes' ELSE 'No' END AS IsFiltered,
    STUFF((
        SELECT ', ' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE ic.object_id = i.object_id 
        AND ic.index_id = i.index_id
        AND ic.is_included_column = 0
        ORDER BY ic.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '') AS KeyColumns,
    STUFF((
        SELECT ', ' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE ic.object_id = i.object_id 
        AND ic.index_id = i.index_id
        AND ic.is_included_column = 1
        ORDER BY ic.index_column_id
        FOR XML PATH('')
    ), 1, 2, '') AS IncludedColumns
FROM sys.indexes i
WHERE i.object_id IN (
    OBJECT_ID('Customers'),
    OBJECT_ID('Products'),
    OBJECT_ID('Orders'),
    OBJECT_ID('OrderDetails'),
    OBJECT_ID('Inventory')
)
AND i.type > 0
AND i.name LIKE 'IX_%'
ORDER BY TableName, IndexName;

PRINT '';
PRINT 'Performance Improvements:';
PRINT '- Foreign key joins now use index seeks';
PRINT '- Date range queries use indexes efficiently';
PRINT '- Filtered indexes reduce overhead';
PRINT '- Composite indexes support complex queries';
PRINT '';
PRINT 'Next: Re-run the load tests to see the improvement!';

SET NOCOUNT OFF;
GO
