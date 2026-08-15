/*==============================================================================
  FILE 04 of 05 : PROGRAMMABILITY  (embedding helpers, retrieval + rerank procs,
                                    diagnostics view, recommendation tool)

  Run AFTER 03_indexes_and_fulltext.sql. Depends on:
    * The Bedrock DATABASE SCOPED CREDENTIAL from file 01.
    * All tables + the RerankInput table type from file 02.
    * The full-text indexes from file 03 (used by FREETEXTTABLE).

  After loading data (file 05), populate embeddings by running the batch procs
  in section 7 until they return 0.
==============================================================================*/
USE TravelAI;
GO


/*==============================================================================
  7. EMBEDDING GENERATION HELPERS  (Amazon Bedrock Titan Text Embeddings V2)
     Bedrock is not a CREATE EXTERNAL MODEL API_FORMAT, so we generate vectors
     by POSTing to the Bedrock InvokeModel endpoint and CASTing the returned
     JSON array to VECTOR. sp_invoke_external_rest_endpoint is scalar per call,
     so the batch procs loop row-by-row (a cursor) rather than a set-based
     UPDATE. Run as a batch job, never in a trigger, to keep synchronous REST
     calls out of user transactions.
==============================================================================*/

/*------------------------------------------------------------------------------
  7a. CORE HELPER -- embed one string with Titan Text Embeddings V2.
      Titan v2 request:  {"inputText":"...","dimensions":1024,"normalize":true}
      Titan v2 response: {"embedding":[...],"inputTextTokenCount":N}
      sp_invoke_external_rest_endpoint nests the model body under $.result,
      so the vector array is at $.result.embedding.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_BedrockEmbedText
    @text    NVARCHAR(MAX),
    @vector  VECTOR(1024) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @vector = NULL;
    IF @text IS NULL OR LEN(@text) = 0 RETURN;

    -- STRING_ESCAPE keeps arbitrary content valid inside the JSON payload.
    DECLARE @payload NVARCHAR(MAX) =
        N'{"inputText":"' + STRING_ESCAPE(@text, 'json')
      + N'","dimensions":1024,"normalize":true}';

    DECLARE @response NVARCHAR(MAX), @ret INT;
    EXEC @ret = sys.sp_invoke_external_rest_endpoint
        @url        = N'https://bedrock-runtime.us-west-2.amazonaws.com/model/amazon.titan-embed-text-v2:0/invoke',
        @method     = 'POST',
        @headers    = N'{"Content-Type":"application/json"}',
        @credential = [https://bedrock-runtime.us-west-2.amazonaws.com],
        @payload    = @payload,
        @response   = @response OUTPUT;

    -- Extract the embedding array and cast the JSON array string to VECTOR.
    DECLARE @arr NVARCHAR(MAX) = JSON_QUERY(@response, '$.result.embedding');
    IF @arr IS NOT NULL
        SET @vector = CAST(@arr AS VECTOR(1024));
END;
GO

/*------------------------------------------------------------------------------
  7b. Batch-embed pending DocumentChunks. Returns the number of rows embedded;
      call repeatedly until it returns 0. @batch_size caps rows per invocation.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_EmbedDocumentChunks
    @batch_size INT = 200
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @done INT = 0;
    DECLARE @chunk_id BIGINT, @content NVARCHAR(MAX), @vec VECTOR(1024);

    DECLARE chunk_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT TOP (@batch_size) chunk_id, content
        FROM dbo.DocumentChunks
        WHERE content_vector IS NULL AND content IS NOT NULL
        ORDER BY chunk_id;

    OPEN chunk_cur;
    FETCH NEXT FROM chunk_cur INTO @chunk_id, @content;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        BEGIN TRY
            SET @vec = NULL;
            EXEC dbo.usp_BedrockEmbedText @text = @content, @vector = @vec OUTPUT;
            IF @vec IS NOT NULL
            BEGIN
                UPDATE dbo.DocumentChunks
                    SET content_vector = @vec
                    WHERE chunk_id = @chunk_id;
                SET @done += 1;
            END
        END TRY
        BEGIN CATCH
            -- Skip a row that fails (e.g. transient Bedrock error); rerun later.
            PRINT CONCAT(N'Embed failed for chunk_id ', @chunk_id, N': ', ERROR_MESSAGE());
        END CATCH
        FETCH NEXT FROM chunk_cur INTO @chunk_id, @content;
    END
    CLOSE chunk_cur;
    DEALLOCATE chunk_cur;
    RETURN @done;
END;
GO

/*------------------------------------------------------------------------------
  7c. Batch-embed Property descriptions (name + description).
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_EmbedProperties
    @batch_size INT = 200
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @done INT = 0;
    DECLARE @property_id INT, @text NVARCHAR(MAX), @vec VECTOR(1024);

    DECLARE prop_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT TOP (@batch_size) property_id, CONCAT(name, N'. ', description)
        FROM dbo.Properties
        WHERE description_vector IS NULL AND description IS NOT NULL
        ORDER BY property_id;

    OPEN prop_cur;
    FETCH NEXT FROM prop_cur INTO @property_id, @text;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        BEGIN TRY
            SET @vec = NULL;
            EXEC dbo.usp_BedrockEmbedText @text = @text, @vector = @vec OUTPUT;
            IF @vec IS NOT NULL
            BEGIN
                UPDATE dbo.Properties
                    SET description_vector = @vec
                    WHERE property_id = @property_id;
                SET @done += 1;
            END
        END TRY
        BEGIN CATCH
            PRINT CONCAT(N'Embed failed for property_id ', @property_id, N': ', ERROR_MESSAGE());
        END CATCH
        FETCH NEXT FROM prop_cur INTO @property_id, @text;
    END
    CLOSE prop_cur;
    DEALLOCATE prop_cur;
    RETURN @done;
END;
GO


/*==============================================================================
  8. RETRIEVAL PRIMITIVES  (agent "tools")
==============================================================================*/

/*------------------------------------------------------------------------------
  8a. LEXICAL SEARCH TOOL  -- BM25-style ranking via Full-Text CONTAINSTABLE
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_LexicalSearchChunks
    @query_text  NVARCHAR(4000),
    @top_k       INT = 20
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@top_k)
        c.chunk_id,
        d.doc_id,
        d.title,
        c.section_path,
        c.content,
        ft.RANK AS lexical_score
    FROM FREETEXTTABLE(dbo.DocumentChunks, content, @query_text, @top_k) AS ft
    JOIN dbo.DocumentChunks c ON c.chunk_id = ft.[KEY]
    JOIN dbo.KnowledgeDocuments d ON d.doc_id = c.doc_id
    WHERE d.is_active = 1
    ORDER BY ft.RANK DESC;
END;
GO

/*------------------------------------------------------------------------------
  8b. SEMANTIC SEARCH TOOL  -- exact kNN with VECTOR_DISTANCE (GA)
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_SemanticSearchChunks
    @query_text   NVARCHAR(4000) = NULL,
    @query_vector VECTOR(1024)   = NULL,
    @top_k        INT = 20
AS
BEGIN
    SET NOCOUNT ON;
    IF @query_vector IS NULL AND @query_text IS NOT NULL
        EXEC dbo.usp_BedrockEmbedText @text = @query_text, @vector = @query_vector OUTPUT;

    SELECT TOP (@top_k)
        c.chunk_id,
        d.doc_id,
        d.title,
        c.section_path,
        c.content,
        VECTOR_DISTANCE('cosine', c.content_vector, @query_vector) AS semantic_distance
    FROM dbo.DocumentChunks c
    JOIN dbo.KnowledgeDocuments d ON d.doc_id = c.doc_id
    WHERE c.content_vector IS NOT NULL AND d.is_active = 1
    ORDER BY semantic_distance;   -- lower distance = more similar
END;
GO

/*------------------------------------------------------------------------------
  8c. FUZZY MATCH TOOL  -- tolerant entity name lookup (typos / phonetics)
      SQL Server has no pg_trgm; use SOUNDEX + DIFFERENCE (0-4 similarity).
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_FuzzyMatchDestination
    @term         NVARCHAR(200),
    @min_score    INT = 3,        -- DIFFERENCE score threshold (4 = strongest)
    @top_k        INT = 10
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@top_k)
        destination_id,
        name,
        country_code,
        DIFFERENCE(name, @term) AS phonetic_score
    FROM dbo.Destinations
    WHERE DIFFERENCE(name, @term) >= @min_score
    ORDER BY phonetic_score DESC, popularity_score DESC;
END;
GO

/*------------------------------------------------------------------------------
  8d. HYBRID SEARCH TOOL  -- Reciprocal Rank Fusion (RRF) over lexical + semantic
      RRF score = SUM over rankers of 1 / (k + rank). k (@rrf_k) dampens the
      contribution of low ranks; 60 is the common default.
      Metadata / SQL filters (@doc_type, @language, @min_trust, @topic) are
      applied as iterative filters so fusion happens over the eligible set.
------------------------------------------------------------------------------*/
CREATE OR ALTER PROCEDURE dbo.usp_HybridSearchChunks
    @query_text     NVARCHAR(4000),
    @top_k          INT           = 10,
    @candidate_n    INT           = 50,      -- pool depth per ranker before fusion
    @rrf_k          INT           = 60,
    @doc_type       NVARCHAR(50)  = NULL,    -- metadata filter
    @language       CHAR(2)       = NULL,    -- metadata filter
    @min_trust      DECIMAL(3,2)  = NULL,    -- metadata filter (source quality)
    @topic          NVARCHAR(100) = NULL     -- json metadata filter
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @qv VECTOR(1024);
    EXEC dbo.usp_BedrockEmbedText @text = @query_text, @vector = @qv OUTPUT;

    -- Eligible set after SQL + metadata filters (shared by both rankers)
    ;WITH eligible AS (
        SELECT c.chunk_id, c.doc_id, c.content, c.section_path, c.content_vector
        FROM dbo.DocumentChunks c
        JOIN dbo.KnowledgeDocuments d ON d.doc_id = c.doc_id
        WHERE d.is_active = 1
          AND (@doc_type  IS NULL OR d.doc_type      = @doc_type)
          AND (@language  IS NULL OR d.language_code = @language)
          AND (@min_trust IS NULL OR d.trust_score  >= @min_trust)
          AND (@topic     IS NULL OR JSON_VALUE(c.metadata,'$.topic') = @topic)
    ),
    -- Ranker 1: lexical (BM25-style) rank position
    lexical AS (
        SELECT e.chunk_id,
               ROW_NUMBER() OVER (ORDER BY ft.RANK DESC) AS lex_rank,
               ft.RANK AS lex_score
        FROM FREETEXTTABLE(dbo.DocumentChunks, content, @query_text, @candidate_n) AS ft
        JOIN eligible e ON e.chunk_id = ft.[KEY]
    ),
    -- Ranker 2: semantic (vector) rank position (exact kNN)
    semantic AS (
        SELECT TOP (@candidate_n)
               e.chunk_id,
               ROW_NUMBER() OVER (
                   ORDER BY VECTOR_DISTANCE('cosine', e.content_vector, @qv)) AS sem_rank,
               VECTOR_DISTANCE('cosine', e.content_vector, @qv) AS sem_distance
        FROM eligible e
        WHERE e.content_vector IS NOT NULL
        ORDER BY sem_distance
    ),
    -- Reciprocal Rank Fusion
    fused AS (
        SELECT
            COALESCE(l.chunk_id, s.chunk_id) AS chunk_id,
            ISNULL(1.0 / (@rrf_k + l.lex_rank), 0)
          + ISNULL(1.0 / (@rrf_k + s.sem_rank), 0) AS rrf_score,
            l.lex_rank, s.sem_rank, l.lex_score, s.sem_distance
        FROM lexical l
        FULL OUTER JOIN semantic s ON l.chunk_id = s.chunk_id
    )
    SELECT TOP (@top_k)
        f.chunk_id,
        d.doc_id,
        d.title,
        d.source_uri,                       -- source attribution
        c.section_path,                     -- citation anchor
        c.content,
        f.rrf_score,
        f.lex_rank,
        f.sem_rank,
        f.lex_score,
        f.sem_distance,
        -- transparent explanation of which signals fired
        CONCAT(
            CASE WHEN f.lex_rank IS NOT NULL THEN CONCAT('lexical#', f.lex_rank, ' ') ELSE '' END,
            CASE WHEN f.sem_rank IS NOT NULL THEN CONCAT('semantic#', f.sem_rank) ELSE '' END
        ) AS ranking_signals
    FROM fused f
    JOIN dbo.DocumentChunks c     ON c.chunk_id = f.chunk_id
    JOIN dbo.KnowledgeDocuments d ON d.doc_id   = c.doc_id
    ORDER BY f.rrf_score DESC;
END;
GO

/*------------------------------------------------------------------------------
  8e. ANN variant (PREVIEW) -- use when a VECTOR INDEX exists and scale demands
      approximate search. Requires the vector index in file 03 (section 6).
------------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.usp_SemanticSearchChunks_ANN
    @query_text NVARCHAR(4000),
    @top_k      INT = 20
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @qv VECTOR(1024);
    EXEC dbo.usp_BedrockEmbedText @text = @query_text, @vector = @qv OUTPUT;

    SELECT TOP (@top_k) WITH APPROXIMATE
        t.chunk_id,
        t.content,
        r.distance
    FROM VECTOR_SEARCH(
            TABLE      = dbo.DocumentChunks AS t,
            COLUMN     = content_vector,
            SIMILAR_TO = @qv,
            METRIC     = 'cosine'
         ) AS r
    ORDER BY r.distance;   -- distance-only, ascending (ANN requirement)
END;
GO
------------------------------------------------------------------------------*/


/*==============================================================================
  9. MODEL-BASED RERANKING  (cross-encoder via Amazon Bedrock Cohere Rerank)
     Takes the fused candidates + query, calls Cohere Rerank on Bedrock, and
     returns the re-scored order. Cohere's response
     ({"results":[{"index":..,"relevance_score":..}]}) maps cleanly back to the
     candidate ordinals. To use Claude as an LLM-judge reranker instead, POST to
     the /converse endpoint (see section 11) and parse a scored JSON reply.
     Requires the dbo.RerankInput table type from file 02.
==============================================================================*/
CREATE OR ALTER PROCEDURE dbo.usp_RerankResults
    @query_text  NVARCHAR(4000),
    @candidates  dbo.RerankInput READONLY,
    @top_n       INT = 50
AS
BEGIN
    SET NOCOUNT ON;

    -- Build a JSON array of document strings, ORDERED BY ordinal so the
    -- reranker's returned index lines up with @candidates.ordinal.
    DECLARE @docs NVARCHAR(MAX) =
        N'[' + ISNULL(
            (SELECT STRING_AGG(N'"' + STRING_ESCAPE(content, 'json') + N'"', N',')
                    WITHIN GROUP (ORDER BY ordinal)
             FROM @candidates), N'') + N']';

    -- Cohere Rerank on Bedrock requires api_version = 2.
    DECLARE @payload NVARCHAR(MAX) = JSON_OBJECT(
        'query':       @query_text,
        'documents':   JSON_QUERY(@docs),
        'top_n':       @top_n,
        'api_version': 2
    );

    DECLARE @response NVARCHAR(MAX), @ret INT;
    EXEC @ret = sys.sp_invoke_external_rest_endpoint
        @url        = N'https://bedrock-runtime.us-west-2.amazonaws.com/model/cohere.rerank-v3-5:0/invoke',
        @method     = 'POST',
        @headers    = N'{"Content-Type":"application/json"}',
        @credential = [https://bedrock-runtime.us-west-2.amazonaws.com],
        @payload    = @payload,
        @response   = @response OUTPUT;

    -- Parse reranker scores (shape: {"results":[{"index":..,"relevance_score":..}]})
    SELECT
        c.chunk_id,
        c.content,
        j.relevance_score AS rerank_score,
        ROW_NUMBER() OVER (ORDER BY j.relevance_score DESC) AS final_rank
    FROM OPENJSON(@response, '$.result.results')
        WITH (
            doc_index       INT     '$.index',
            relevance_score FLOAT   '$.relevance_score'
        ) AS j
    JOIN @candidates c
        ON c.ordinal = j.doc_index      -- ordinal = 0-based position sent to API
    ORDER BY j.relevance_score DESC;
END;
GO


/*==============================================================================
  10. RETRIEVAL DIAGNOSTICS VIEW  (table dbo.RetrievalLog is created in file 02)
==============================================================================*/
CREATE OR ALTER VIEW dbo.vw_RetrievalQuality
AS
SELECT
    CAST(created_at AS DATE)                       AS log_date,
    strategy,
    COUNT(*)                                       AS retrievals,
    AVG(CAST(latency_ms AS DECIMAL(10,2)))         AS avg_latency_ms,
    AVG(CAST(returned_count AS DECIMAL(10,2)))     AS avg_returned
FROM dbo.RetrievalLog
GROUP BY CAST(created_at AS DATE), strategy;
GO


/*==============================================================================
  11. AGENT TOOL SURFACE  (recommendation tool + orchestration entry point)
      The dbo.RerankInput table type lives in file 02.
==============================================================================*/

-- Personalised recommendation tool: entity semantic search vs. traveler vector
CREATE OR ALTER PROCEDURE dbo.usp_RecommendProperties
    @traveler_id INT,
    @destination_id INT = NULL,
    @max_price   DECIMAL(10,2) = NULL,
    @top_k       INT = 10
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @pref VECTOR(1024) =
        (SELECT preference_vector FROM dbo.Travelers WHERE traveler_id = @traveler_id);

    SELECT TOP (@top_k)
        p.property_id, p.name, p.nightly_price_usd, p.star_rating, p.avg_review_score,
        VECTOR_DISTANCE('cosine', p.description_vector, @pref) AS match_distance
    FROM dbo.Properties p
    WHERE p.is_active = 1
      AND p.description_vector IS NOT NULL
      AND (@destination_id IS NULL OR p.destination_id = @destination_id)
      AND (@max_price      IS NULL OR p.nightly_price_usd <= @max_price)
    ORDER BY match_distance;
END;
GO

/*
  ORCHESTRATION PATTERN (implemented in the app / agent layer, or in-DB via
  sys.sp_invoke_external_rest_endpoint against the Bedrock Converse API):
    1. usp_DecomposeQuery  -> Claude on Bedrock splits a complex question into
                              sub-questions. POST to
                              .../model/us.anthropic.claude-sonnet-4-6/converse
                              and read $.result.output.message.content[0].text.
    2. For each sub-question:
         usp_HybridSearchChunks  (RRF over lexical + semantic, with filters)
    3. usp_RerankResults          (Cohere Rerank on Bedrock, section 9)
    4. App composes a cited answer using source_uri + section_path from the
       top reranked chunks, then writes/INSERTs into dbo.RetrievalLog.
    5. usp_RecommendProperties / Activities enrich the answer with bookable items.

  Example Converse call (Claude on Bedrock) for step 1 / step 4:
    DECLARE @resp NVARCHAR(MAX);
    EXEC sys.sp_invoke_external_rest_endpoint
      @url        = N'https://bedrock-runtime.us-west-2.amazonaws.com/model/us.anthropic.claude-sonnet-4-6/converse',
      @method     = 'POST',
      @credential = [https://bedrock-runtime.us-west-2.amazonaws.com],
      @payload    = N'{"messages":[{"role":"user","content":[{"text":"..."}]}],"inferenceConfig":{"maxTokens":800}}',
      @response   = @resp OUTPUT;
    SELECT JSON_VALUE(@resp, '$.result.output.message.content[0].text');

  QUICK SMOKE TESTS (after 05_seed_data.sql + running the embed procs):
    EXEC dbo.usp_EmbedDocumentChunks @batch_size = 200;  -- repeat until it returns 0
    EXEC dbo.usp_EmbedProperties     @batch_size = 200;  -- repeat until it returns 0
    EXEC dbo.usp_LexicalSearchChunks  @query_text = N'best time to visit Kyoto';
    EXEC dbo.usp_SemanticSearchChunks @query_text = N'quiet romantic getaway near the sea';
    EXEC dbo.usp_HybridSearchChunks   @query_text = N'family friendly ski resort with pool',
                                      @doc_type = N'guide', @min_trust = 0.7;
    EXEC dbo.usp_FuzzyMatchDestination @term = N'Barcelna';   -- typo tolerated
*/
GO
