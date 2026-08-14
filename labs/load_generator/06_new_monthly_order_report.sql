USE DBOpsLab;
  GO

  CREATE OR ALTER PROCEDURE dbo.sp_MonthlyOrderReport
      @ReportMonth DATE = NULL        -- any date in the target month
  AS
  BEGIN
      SET NOCOUNT ON;

      -- Default to the most recent COMPLETE month so the row volume is stable run to run.
      IF @ReportMonth IS NULL
          SET @ReportMonth = DATEADD(MONTH, -1, CAST(GETDATE() AS DATE));

      -- Boundaries precomputed into variables, and a half-open range, so no function is ever
      -- applied to OrderDate itself. This is what keeps the predicate SARGable and seekable.
      DECLARE @MonthStart DATETIME = DATEFROMPARTS(YEAR(@ReportMonth), MONTH(@ReportMonth), 1);
      DECLARE @MonthEnd   DATETIME = DATEADD(MONTH, 1, @MonthStart);

      ;WITH OrdersInMonth AS (
          SELECT o.OrderID, o.CustomerID, o.TotalAmount
          FROM Orders AS o
          WHERE o.OrderDate >= @MonthStart
            AND o.OrderDate <  @MonthEnd
      ),
      CustomersByState AS (
          SELECT c.State, COUNT(*) AS CustomerCount
          FROM Customers AS c
          WHERE c.Country = 'USA'
          GROUP BY c.State
      ),
      OrdersByState AS (
          SELECT c.State,
                 COUNT(*)                      AS OrderCount,
                 COUNT(DISTINCT om.CustomerID) AS OrderingCustomers,
                 SUM(om.TotalAmount)           AS TotalRevenue,
                 AVG(om.TotalAmount)           AS AvgOrderValue
          FROM OrdersInMonth AS om
          INNER JOIN Customers AS c ON c.CustomerID = om.CustomerID
          WHERE c.Country = 'USA'
          GROUP BY c.State
      ),
      ProductsByState AS (
          SELECT c.State,
                 COUNT(DISTINCT od.ProductID) AS UniqueProducts,
                 SUM(od.Quantity)             AS UnitsSold
          FROM OrdersInMonth AS om
          INNER JOIN Customers    AS c  ON c.CustomerID = om.CustomerID
          INNER JOIN OrderDetails AS od ON od.OrderID   = om.OrderID
          WHERE c.Country = 'USA'
          GROUP BY c.State
      )
      SELECT
          cs.State,
          cs.CustomerCount,
          ISNULL(os.OrderCount, 0)        AS OrderCount,
          ISNULL(os.OrderingCustomers, 0) AS OrderingCustomers,
          ISNULL(os.TotalRevenue, 0)      AS TotalRevenue,
          os.AvgOrderValue,
          ISNULL(ps.UniqueProducts, 0)    AS UniqueProducts,
          ISNULL(ps.UnitsSold, 0)         AS UnitsSold,
          @MonthStart                     AS ReportMonthStart
      FROM CustomersByState AS cs
      LEFT JOIN OrdersByState   AS os ON os.State = cs.State
      LEFT JOIN ProductsByState AS ps ON ps.State = cs.State
      WHERE cs.CustomerCount > 100
      ORDER BY cs.CustomerCount DESC;
  END
  GO