USE TravelAI;
GO

-- Create vector index on destinations
CREATE VECTOR INDEX IX_Destinations_Vector
ON Destinations(description_vector)
WITH (METRIC = 'cosine');
GO

-- Create vector index on document chunks
CREATE VECTOR INDEX IX_DocumentChunks_Vector
ON DocumentChunks(content_vector)
WITH (METRIC = 'cosine');
GO

-- Verify
SELECT name, type_desc 
FROM sys.indexes 
WHERE name LIKE 'IX_%Vector%';
GO
