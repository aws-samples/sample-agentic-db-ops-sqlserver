USE TravelAI;
GO

-- Check tables exist
SELECT 'Destinations' AS [Table], COUNT(*) AS Rows FROM Destinations
UNION ALL
SELECT 'DocumentChunks', COUNT(*) FROM DocumentChunks;
GO

-- Check VECTOR column exists
SELECT COLUMN_NAME, DATA_TYPE 
FROM INFORMATION_SCHEMA.COLUMNS 
WHERE TABLE_NAME = 'Destinations' AND COLUMN_NAME = 'description_vector';
GO

-- Check Full-Text Search works
SELECT TOP 3 d.name, d.country_code
FROM Destinations d
INNER JOIN FREETEXTTABLE(Destinations, description, 'beach snorkeling') ft
  ON d.destination_id = ft.[KEY]
ORDER BY ft.[RANK] DESC;
GO
