-- Updated: 2026-03-15
-- =============================================
-- High CPU Load Test Script - Stored Procedures
-- WARNING: This will cause extreme CPU utilization with workers
-- Creates intentionally unoptimized stored procedures
-- =============================================

USE DBOpsLab;
GO

SET NOCOUNT ON;

PRINT '========================================';
PRINT 'CREATING HIGH CPU TEST PROCEDURES';
PRINT 'WARNING: These will max out CPU!';
PRINT '========================================';
PRINT '';

-- =============================================
-- Helper: Scalar UDF for Discount Calculation (SLOW)
-- Row-by-row processing with intentional inefficiency
-- =============================================
IF OBJECT_ID('dbo.fn_CalculateDiscountSlow', 'FN') IS NOT NULL
    DROP FUNCTION dbo.fn_CalculateDiscountSlow;
GO

CREATE FUNCTION dbo.fn_CalculateDiscountSlow(@Price DECIMAL(10,2), @Quantity INT)
RETURNS DECIMAL(10,2)
AS
BEGIN
    DECLARE @Discount DECIMAL(10,2);
    DECLARE @Counter INT = 0;
    
    -- Intentionally inefficient loop (simulates row-by-row processing)
    WHILE @Counter < @Quantity
    BEGIN
        SET @Counter = @Counter + 1;
    END
    
    -- Calculate discount based on quantity
    IF @Quantity >= 10
        SET @Discount = @Price * 0.15;
    ELSE IF @Quantity >= 5
        SET @Discount = @Price * 0.10;
    ELSE
        SET @Discount = @Price * 0.05;
    
    RETURN @Discount;
END
GO

PRINT 'Created: fn_CalculateDiscountSlow (Scalar UDF)';
PRINT '';

-- =============================================
-- SP 1: Customer Order Summary with Scalar Subqueries
-- Issue: Row-by-row processing via scalar subqueries
-- =============================================
IF OBJECT_ID('dbo.sp_CustomerOrderSummary', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_CustomerOrderSummary;
GO

CREATE PROCEDURE dbo.sp_CustomerOrderSummary
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Uses scalar subqueries (executes once per row - VERY SLOW)
    SELECT TOP 50000
        c.CustomerID,
        c.FirstName,
        c.LastName,
        c.Email,
        c.City,
        c.State,
        -- Each subquery scans Orders table for every customer row
        (SELECT COUNT(*) FROM Orders o WHERE o.CustomerID = c.CustomerID) AS TotalOrders,
        (SELECT SUM(o.TotalAmount) FROM Orders o WHERE o.CustomerID = c.CustomerID) AS TotalSpent,
        (SELECT MAX(o.OrderDate) FROM Orders o WHERE o.CustomerID = c.CustomerID) AS LastOrderDate,
        (SELECT MIN(o.OrderDate) FROM Orders o WHERE o.CustomerID = c.CustomerID) AS FirstOrderDate,
        -- Function on column prevents index usage
        YEAR(c.CreatedDate) AS YearJoined
    FROM Customers c
    WHERE 
        -- Function prevents index seek
        YEAR(c.CreatedDate) >= 2023
        -- String concatenation prevents index usage
        AND c.FirstName + ' ' + c.LastName LIKE '%First%'
    ORDER BY 
        (SELECT COUNT(*) FROM Orders o WHERE o.CustomerID = c.CustomerID) DESC;
END
GO

PRINT 'Created: sp_CustomerOrderSummary';
PRINT '';

-- =============================================
-- SP 2: Product Sales with Scalar UDF
-- Issue: Scalar UDF called for each row
-- =============================================
IF OBJECT_ID('dbo.sp_ProductSalesReport', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_ProductSalesReport;
GO

CREATE PROCEDURE dbo.sp_ProductSalesReport
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Uses scalar UDF for row-by-row discount calculation
    SELECT TOP 50000
        p.ProductID,
        p.ProductName,
        p.Category,
        p.Price,
        od.Quantity,
        od.UnitPrice,
        -- Scalar UDF called for each row (VERY SLOW)
        dbo.fn_CalculateDiscountSlow(od.UnitPrice, od.Quantity) AS DiscountAmount,
        od.UnitPrice - dbo.fn_CalculateDiscountSlow(od.UnitPrice, od.Quantity) AS FinalPrice,
        -- Correlated subquery adds more overhead
        (SELECT COUNT(*) FROM OrderDetails od2 WHERE od2.ProductID = p.ProductID) AS TotalOrders
    FROM Products p
    INNER JOIN OrderDetails od ON p.ProductID = od.ProductID
    WHERE 
        -- Function prevents index usage
        UPPER(p.Category) IN ('ELECTRONICS', 'CLOTHING', 'BOOKS')
    ORDER BY p.ProductID;
END
GO

PRINT 'Created: sp_ProductSalesReport';
PRINT '';

-- =============================================
-- SP 3: Order Analysis with Implicit Conversions
-- Issue: Type conversions prevent index usage
-- =============================================
IF OBJECT_ID('dbo.sp_OrderAnalysisByYear', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_OrderAnalysisByYear;
GO

CREATE PROCEDURE dbo.sp_OrderAnalysisByYear
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Uses implicit conversions and correlated subqueries
    SELECT TOP 100000
        o.OrderID,
        o.OrderDate,
        o.Status,
        o.TotalAmount,
        c.FirstName,
        c.LastName,
        -- Correlated subquery
        (SELECT COUNT(*) FROM OrderDetails od WHERE od.OrderID = o.OrderID) AS ItemCount,
        -- String aggregation (expensive)
        (SELECT STRING_AGG(p.ProductName, ', ')
         FROM OrderDetails od
         INNER JOIN Products p ON od.ProductID = p.ProductID
         WHERE od.OrderID = o.OrderID) AS ProductList
    FROM Orders o
    -- Implicit conversion in JOIN (prevents index usage)
    INNER JOIN Customers c ON CAST(o.CustomerID AS VARCHAR(20)) = CAST(c.CustomerID AS VARCHAR(20))
    WHERE 
        -- OR condition prevents index usage
        (o.Status = 'Pending' OR o.Status = 'Processing')
        -- Function on date
        AND MONTH(o.OrderDate) BETWEEN 1 AND 6
        -- NOT IN with subquery (very slow)
        AND o.OrderID NOT IN (
            SELECT od.OrderID FROM OrderDetails od WHERE od.Quantity > 8
        )
    ORDER BY o.OrderDate DESC;
END
GO

PRINT 'Created: sp_OrderAnalysisByYear';
PRINT '';

-- =============================================
-- SP 4: Nested Subqueries with NOT IN
-- Issue: Multiple levels of nested subqueries
-- =============================================
IF OBJECT_ID('dbo.sp_CustomerPurchaseHistory', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_CustomerPurchaseHistory;
GO

CREATE PROCEDURE dbo.sp_CustomerPurchaseHistory
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Multiple levels of nested subqueries
    SELECT TOP 50000
        o.OrderID,
        o.CustomerID,
        o.OrderDate,
        o.TotalAmount,
        -- Multiple levels of nesting (executes repeatedly)
        (SELECT COUNT(*) 
         FROM OrderDetails od 
         WHERE od.OrderID = o.OrderID 
         AND od.ProductID IN (
             SELECT p.ProductID 
             FROM Products p 
             WHERE p.Category IN (
                 SELECT DISTINCT p2.Category 
                 FROM Products p2 
                 WHERE p2.Price > (SELECT AVG(Price) FROM Products)
             )
         )) AS ExpensiveCategoryItems,
        -- Another nested nightmare
        (SELECT SUM(od.Quantity * od.UnitPrice)
         FROM OrderDetails od
         WHERE od.OrderID = o.OrderID
         AND od.ProductID IN (
             SELECT ProductID 
             FROM Products 
             WHERE StockQuantity < (
                 SELECT AVG(StockQuantity) FROM Products
             )
         )) AS LowStockTotal
    FROM Orders o
    WHERE 
        YEAR(o.OrderDate) = YEAR(GETDATE())
        AND o.CustomerID IN (
            SELECT CustomerID 
            FROM Customers 
            WHERE State IN (
                SELECT DISTINCT State FROM Customers WHERE City LIKE '%New%'
            )
        )
    ORDER BY o.OrderDate DESC;
END
GO

PRINT 'Created: sp_CustomerPurchaseHistory';
PRINT '';

-- =============================================
-- SP 5: Cartesian Product with Functions
-- Issue: CROSS JOIN creates massive result set
-- =============================================
IF OBJECT_ID('dbo.sp_ProductInventoryMatrix', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_ProductInventoryMatrix;
GO

CREATE PROCEDURE dbo.sp_ProductInventoryMatrix
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Cartesian join with functions preventing index usage
    SELECT TOP 10000
        c1.CustomerID AS Customer1,
        c2.CustomerID AS Customer2,
        c1.City AS City1,
        c2.City AS City2,
        -- Correlated subquery for each combination
        (SELECT COUNT(*) FROM Orders o WHERE o.CustomerID = c1.CustomerID) AS Customer1Orders,
        (SELECT COUNT(*) FROM Orders o WHERE o.CustomerID = c2.CustomerID) AS Customer2Orders
    FROM Customers c1
    CROSS JOIN Customers c2
    WHERE 
        c1.CustomerID < c2.CustomerID
        AND c1.State = c2.State
        -- Function prevents index usage
        AND DATEDIFF(DAY, c1.CreatedDate, c2.CreatedDate) < 30
    ORDER BY c1.CustomerID, c2.CustomerID;
END
GO

PRINT 'Created: sp_ProductInventoryMatrix';
PRINT '';

-- =============================================
-- SP 6: Monthly Order Report
-- Issue: Full clustered index scan on Orders (no index on TotalAmount)
-- Groups by ShippingState and PaymentMethod without supporting index
-- =============================================
IF OBJECT_ID('dbo.sp_MonthlyOrderReport', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_MonthlyOrderReport;
GO

CREATE PROCEDURE dbo.sp_MonthlyOrderReport
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        c.State,
        COUNT(DISTINCT c.CustomerID) AS CustomerCount,
        COUNT(DISTINCT o.OrderID) AS OrderCount,
        SUM(o.TotalAmount) AS TotalRevenue,
        COUNT(DISTINCT od.ProductID) AS UniqueProducts,
        AVG(CASE WHEN YEAR(o.OrderDate) = YEAR(GETDATE()) THEN o.TotalAmount END) AS AvgOrderThisYear
    FROM Customers c
    LEFT JOIN Orders o ON o.ShippingState = c.State
    LEFT JOIN OrderDetails od ON o.OrderID = od.OrderID
    WHERE c.Country = 'USA'
    GROUP BY c.State
    HAVING COUNT(DISTINCT c.CustomerID) > 100
    ORDER BY CustomerCount DESC;
END
GO

PRINT 'Created: sp_MonthlyOrderReport';
PRINT '';

-- =============================================
-- Summary
-- =============================================
PRINT '========================================';
PRINT 'HIGH CPU STORED PROCEDURES CREATED';
PRINT '========================================';
PRINT '';
PRINT 'Created Procedures:';
PRINT '  1. sp_CustomerOrderSummary';
PRINT '  2. sp_ProductSalesReport';
PRINT '  3. sp_OrderAnalysisByYear';
PRINT '  4. sp_CustomerPurchaseHistory';
PRINT '  5. sp_ProductInventoryMatrix';
PRINT '  6. sp_MonthlyOrderReport';
PRINT '';
PRINT 'Performance Issues:';
PRINT '- Scalar UDF with row-by-row processing';
PRINT '- Correlated subqueries instead of JOINs';
PRINT '- Functions on indexed columns';
PRINT '- Implicit type conversions';
PRINT '- Multiple full table scans';
PRINT '- Nested subqueries';
PRINT '';
PRINT 'To test, run: EXEC sp_CustomerOrderSummary';
PRINT 'Monitor CPU in Performance Insights or Task Manager';
PRINT '';
PRINT 'Next: Run load test (script 03)';

SET NOCOUNT OFF;
GO
