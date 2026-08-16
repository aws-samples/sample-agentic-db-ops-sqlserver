-- Create vector indexes for fast ANN search
-- Usage: python3.11 run_sql_file.py load_generator/06_create_vector_index.sql
USE TravelAI;
GO

ALTER DATABASE SCOPED CONFIGURATION SET PREVIEW_FEATURES = ON;
GO

IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Destinations_Vector')
    DROP INDEX IX_Destinations_Vector ON Destinations;
GO

CREATE VECTOR INDEX IX_Destinations_Vector
ON Destinations(description_vector)
WITH (METRIC = 'cosine');
GO

SELECT name, type_desc FROM sys.indexes WHERE name LIKE 'IX_%Vector%';
GO
