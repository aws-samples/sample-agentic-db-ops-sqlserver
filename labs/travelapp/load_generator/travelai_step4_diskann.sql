USE TravelAI;
GO

-- Enable preview features (required for vector index)
ALTER DATABASE SCOPED CONFIGURATION SET PREVIEW_FEATURES = ON;
GO

-- Create DiskANN index on destinations
CREATE VECTOR INDEX IX_Destinations_Vector
ON Destinations(description_vector)
WITH (METRIC = 'cosine', TYPE = DISKANN);
GO

-- Create DiskANN index on document chunks
CREATE VECTOR INDEX IX_DocumentChunks_Vector
ON DocumentChunks(content_vector)
WITH (METRIC = 'cosine', TYPE = DISKANN);
GO

-- Verify
SELECT name, type_desc 
FROM sys.indexes 
WHERE name LIKE 'IX_%Vector%';
GO
