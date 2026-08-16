-- Test semantic search with VECTOR_DISTANCE
-- Usage: python3.11 run_sql_file.py load_generator/07_test_semantic_search.sql
USE TravelAI;
GO

-- Query 1: relaxing tropical escape
DECLARE @q1 VECTOR(1024) = AI_GENERATE_EMBEDDINGS(N'relaxing tropical escape' USE MODEL bedrock_embed);
SELECT TOP 5 name, country_code, climate, VECTOR_DISTANCE('cosine', description_vector, @q1) AS Distance
FROM Destinations WHERE description_vector IS NOT NULL
ORDER BY VECTOR_DISTANCE('cosine', description_vector, @q1);
GO

-- Query 2: adventure sports
DECLARE @q2 VECTOR(1024) = AI_GENERATE_EMBEDDINGS(N'adrenaline outdoor extreme sports' USE MODEL bedrock_embed);
SELECT TOP 3 name, country_code FROM Destinations WHERE description_vector IS NOT NULL
ORDER BY VECTOR_DISTANCE('cosine', description_vector, @q2);
GO

-- Query 3: cultural history
DECLARE @q3 VECTOR(1024) = AI_GENERATE_EMBEDDINGS(N'ancient history museums art galleries' USE MODEL bedrock_embed);
SELECT TOP 3 name, country_code FROM Destinations WHERE description_vector IS NOT NULL
ORDER BY VECTOR_DISTANCE('cosine', description_vector, @q3);
GO
