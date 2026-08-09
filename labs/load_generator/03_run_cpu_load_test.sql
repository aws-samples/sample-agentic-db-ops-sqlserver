-- Updated: 2026-03-15
-- =============================================
-- Sustained CPU Load Generator
-- Runs procedures in loops to generate sustained high CPU
-- Use this to see CPU metrics in Performance Insights
-- =============================================

USE DBOpsLab;
GO

SET NOCOUNT ON;

-- Clear cache for clean test results
PRINT 'Clearing procedure cache...';
DBCC FREEPROCCACHE;     -- Clear execution plan cache
PRINT 'Cache cleared.';
PRINT '';

PRINT '========================================';
PRINT 'SUSTAINED CPU LOAD GENERATOR';
PRINT 'WARNING: This will run for several minutes!';
PRINT 'Monitor CPU in Performance Insights/Task Manager';
PRINT '========================================';
PRINT '';

DECLARE @StartTime DATETIME = GETDATE();
DECLARE @Iterations INT = 0;
DECLARE @MaxIterations INT = 5;  -- Run each test 5 times (~5 minutes total)
DECLARE @TestNumber INT = 1;

-- =============================================
-- Tests 1-5: Disabled (code-level anti-patterns, not fixable with indexes)
-- Uncomment to include for broader CPU pressure testing
-- =============================================

-- Test 1: Customer Order Summary (scalar subqueries)
-- Test 2: Product Sales with UDF (scalar UDF per row)
-- Test 3: Order Analysis (implicit conversions, NOT IN)
-- Test 4: Nested Subqueries (4 levels deep)
-- Test 5: Cartesian Product (CROSS JOIN)

-- =============================================
-- Test 6: Full Table Scans (5 iterations)
-- sp_MonthlyOrderReport - fixable with index + SP rewrite
-- =============================================
SET @StartTime = GETDATE();
PRINT 'Running Test 6: Full Table Scans (5 iterations)...';
SET @Iterations = 0;
SET @MaxIterations = 5;

WHILE @Iterations < @MaxIterations
BEGIN
    EXEC sp_MonthlyOrderReport;
    SET @Iterations = @Iterations + 1;
    
    IF @Iterations % 5 = 0
        PRINT '  Completed ' + CAST(@Iterations AS VARCHAR) + ' iterations...';
END

PRINT 'Test 6 completed in ' + CAST(DATEDIFF(SECOND, @StartTime, GETDATE()) AS VARCHAR) + ' seconds';
PRINT '';

-- =============================================
-- Summary
-- =============================================
PRINT '========================================';
PRINT 'SUSTAINED CPU LOAD TEST COMPLETE';
PRINT '========================================';
PRINT '';
PRINT 'Check Performance Insights for:';
PRINT '- High CPU utilization over the test period';
PRINT '- Top SQL queries consuming CPU';
PRINT '- Wait events (should show CPU as dominant)';
PRINT '';

SET NOCOUNT OFF;
GO
