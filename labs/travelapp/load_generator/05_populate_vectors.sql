-- Populate vector embeddings using AI_GENERATE_EMBEDDINGS
-- Usage: python3.11 run_sql_file.py load_generator/05_populate_vectors.sql
USE TravelAI;
GO

-- Embed all destinations (one line per table)
UPDATE Destinations
SET description_vector = AI_GENERATE_EMBEDDINGS(description USE MODEL bedrock_embed)
WHERE description_vector IS NULL;
GO

-- Embed all document chunks
UPDATE DocumentChunks
SET content_vector = AI_GENERATE_EMBEDDINGS(content USE MODEL bedrock_embed)
WHERE content_vector IS NULL;
GO

-- Verify
SELECT 'Destinations' AS Source, COUNT(*) AS Embedded FROM Destinations WHERE description_vector IS NOT NULL
UNION ALL
SELECT 'DocumentChunks', COUNT(*) FROM DocumentChunks WHERE content_vector IS NOT NULL;
GO
