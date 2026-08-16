USE TravelAI;
GO

-- Drop existing vector index if re-running
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Destinations_Vector')
    DROP INDEX IX_Destinations_Vector ON Destinations;
GO

-- Create vector index on destinations (enables fast ANN search)
CREATE VECTOR INDEX IX_Destinations_Vector
ON Destinations(description_vector)
WITH (METRIC = 'cosine');
GO

-- Note: DocumentChunks uses BIGINT primary key which requires INT for vector index.
-- Vector search on DocumentChunks still works via brute-force VECTOR_DISTANCE
-- (fast enough for <1000 rows). For large-scale, alter chunk_id to INT.

-- Verify
SELECT name, type_desc 
FROM sys.indexes 
WHERE name LIKE 'IX_%Vector%';
GO
