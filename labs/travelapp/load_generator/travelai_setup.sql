/*==============================================================================
  TravelAI Database - CREATE SCHEMA

  Creates the TravelAI database and all base tables (core travel domain,
  RAG knowledge base, retrieval diagnostics log) and the RerankInput table type.

  Every searchable entity carries three retrieval surfaces:
    * descriptive text  (full-text indexed)
    * a VECTOR embedding (semantic search; populated by the Bedrock embed procs)
    * a native json metadata bag + persisted computed columns (indexed SQL filters)
==============================================================================*/

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'TravelAI')
    CREATE DATABASE TravelAI;
GO

USE TravelAI;
GO


/*==============================================================================
  2. CORE TRAVEL DOMAIN
==============================================================================*/

-- Destinations: cities, regions, countries, POIs -----------------------------
CREATE TABLE dbo.Destinations
(
    destination_id      INT IDENTITY(1,1)
        CONSTRAINT PK_Destinations PRIMARY KEY CLUSTERED,
    name                NVARCHAR(200)   NOT NULL,
    destination_type    NVARCHAR(30)    NOT NULL          -- city|region|country|poi
        CONSTRAINT CK_Destinations_type
        CHECK (destination_type IN (N'city',N'region',N'country',N'poi')),
    country_code        CHAR(2)         NOT NULL,          -- ISO-3166 alpha-2
    region              NVARCHAR(100)   NULL,
    geo                 GEOGRAPHY       NULL,              -- point for proximity search
    description         NVARCHAR(MAX)   NULL,              -- full-text searched
    languages           NVARCHAR(200)   NULL,
    popularity_score    DECIMAL(5,2)    NOT NULL DEFAULT 0,
    attributes          JSON            NULL,              -- {"climate":"tropical","best_season":"spring", ...}
    description_vector  VECTOR(1024)    NULL,              -- semantic embedding
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME(),
    -- Persisted computed columns => cheap, indexable metadata filters
    best_season         AS CAST(JSON_VALUE(attributes,'$.best_season') AS NVARCHAR(50)) PERSISTED,
    climate             AS CAST(JSON_VALUE(attributes,'$.climate')     AS NVARCHAR(50)) PERSISTED
);
GO

-- Properties: hotels, resorts, hostels, rentals -------------------------------
CREATE TABLE dbo.Properties
(
    property_id         INT IDENTITY(1,1)
        CONSTRAINT PK_Properties PRIMARY KEY CLUSTERED,
    destination_id      INT             NOT NULL
        CONSTRAINT FK_Properties_Destinations
        REFERENCES dbo.Destinations(destination_id),
    name                NVARCHAR(200)   NOT NULL,
    property_type       NVARCHAR(30)    NOT NULL,          -- hotel|resort|hostel|apartment|villa
    star_rating         TINYINT         NULL CHECK (star_rating BETWEEN 1 AND 5),
    nightly_price_usd   DECIMAL(10,2)   NULL,
    avg_review_score    DECIMAL(3,2)    NULL,              -- rolled up from Reviews
    review_count        INT             NOT NULL DEFAULT 0,
    geo                 GEOGRAPHY       NULL,
    address             NVARCHAR(400)   NULL,
    description         NVARCHAR(MAX)   NULL,              -- full-text searched
    amenities           JSON            NULL,              -- {"pool":1,"wifi":true,"pet_friendly":0,...}
    description_vector  VECTOR(1024)    NULL,
    is_active           BIT             NOT NULL DEFAULT 1,
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME(),
    -- NOTE: amenities pool/pet_friendly must be numeric 1/0, not JSON booleans,
    -- because CAST(JSON_VALUE(...) AS BIT) cannot convert the string 'true'.
    has_pool            AS CAST(JSON_VALUE(amenities,'$.pool')         AS BIT) PERSISTED,
    pet_friendly        AS CAST(JSON_VALUE(amenities,'$.pet_friendly') AS BIT) PERSISTED
);
GO

-- Activities / tours / experiences -------------------------------------------
CREATE TABLE dbo.Activities
(
    activity_id         INT IDENTITY(1,1)
        CONSTRAINT PK_Activities PRIMARY KEY CLUSTERED,
    destination_id      INT             NOT NULL
        CONSTRAINT FK_Activities_Destinations
        REFERENCES dbo.Destinations(destination_id),
    name                NVARCHAR(200)   NOT NULL,
    category            NVARCHAR(50)    NOT NULL,          -- adventure|culture|food|nature|nightlife...
    duration_minutes    INT             NULL,
    price_usd           DECIMAL(10,2)   NULL,
    difficulty          NVARCHAR(20)    NULL,              -- easy|moderate|hard
    description         NVARCHAR(MAX)   NULL,
    tags                JSON            NULL,              -- ["family-friendly","outdoor","guided"]
    description_vector  VECTOR(1024)    NULL,
    is_active           BIT             NOT NULL DEFAULT 1,
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- Travelers / users -----------------------------------------------------------
CREATE TABLE dbo.Travelers
(
    traveler_id         INT IDENTITY(1,1)
        CONSTRAINT PK_Travelers PRIMARY KEY CLUSTERED,
    display_name        NVARCHAR(150)   NULL,
    home_country        CHAR(2)         NULL,
    preferences         JSON            NULL,              -- {"budget":"mid","interests":["food","hiking"],"pace":"relaxed"}
    -- Long-term preference embedding => personalised recommendations
    preference_vector   VECTOR(1024)    NULL,
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- Reviews (user generated content, also semantically searchable) --------------
CREATE TABLE dbo.Reviews
(
    review_id           BIGINT IDENTITY(1,1)
        CONSTRAINT PK_Reviews PRIMARY KEY CLUSTERED,
    entity_type         NVARCHAR(20)    NOT NULL           -- property|activity|destination
        CONSTRAINT CK_Reviews_entity
        CHECK (entity_type IN (N'property',N'activity',N'destination')),
    entity_id           INT             NOT NULL,
    traveler_id         INT             NULL
        CONSTRAINT FK_Reviews_Travelers REFERENCES dbo.Travelers(traveler_id),
    rating              TINYINT         NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title               NVARCHAR(300)   NULL,
    body                NVARCHAR(MAX)   NULL,              -- full-text searched
    language_code       CHAR(2)         NOT NULL DEFAULT 'en',
    body_vector         VECTOR(1024)    NULL,
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- Bookings (optional, supports agent "compare / availability" tools) ----------
CREATE TABLE dbo.Bookings
(
    booking_id          BIGINT IDENTITY(1,1)
        CONSTRAINT PK_Bookings PRIMARY KEY CLUSTERED,
    traveler_id         INT             NOT NULL
        CONSTRAINT FK_Bookings_Travelers REFERENCES dbo.Travelers(traveler_id),
    property_id         INT             NULL
        CONSTRAINT FK_Bookings_Properties REFERENCES dbo.Properties(property_id),
    activity_id         INT             NULL
        CONSTRAINT FK_Bookings_Activities REFERENCES dbo.Activities(activity_id),
    check_in            DATE            NULL,
    check_out           DATE            NULL,
    total_usd           DECIMAL(10,2)   NULL,
    status              NVARCHAR(20)    NOT NULL DEFAULT 'confirmed',
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO


/*==============================================================================
  3. RAG KNOWLEDGE BASE (chunked documents)
     Travel guides, destination articles, policies, FAQs -> chunked for RAG.
     This is the primary target for agentic hybrid retrieval + citations.
==============================================================================*/

CREATE TABLE dbo.KnowledgeDocuments
(
    doc_id              INT IDENTITY(1,1)
        CONSTRAINT PK_KnowledgeDocuments PRIMARY KEY CLUSTERED,
    title               NVARCHAR(400)   NOT NULL,
    doc_type            NVARCHAR(50)    NOT NULL,          -- guide|article|policy|faq|itinerary
    source_uri          NVARCHAR(1000)  NULL,              -- for source attribution
    publisher           NVARCHAR(200)   NULL,
    language_code       CHAR(2)         NOT NULL DEFAULT 'en',
    -- Optional linkage to a domain entity (e.g. a guide about a destination)
    entity_type         NVARCHAR(20)    NULL,
    entity_id           INT             NULL,
    metadata            JSON            NULL,              -- {"author":"...","published":"2025-06-01","trust":0.9}
    published_at        DATE            NULL,
    trust_score         AS CAST(JSON_VALUE(metadata,'$.trust') AS DECIMAL(3,2)) PERSISTED,
    is_active           BIT             NOT NULL DEFAULT 1,
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

CREATE TABLE dbo.DocumentChunks
(
    chunk_id            BIGINT IDENTITY(1,1)
        CONSTRAINT PK_DocumentChunks PRIMARY KEY CLUSTERED,
    doc_id              INT             NOT NULL
        CONSTRAINT FK_DocumentChunks_Documents
        REFERENCES dbo.KnowledgeDocuments(doc_id) ON DELETE CASCADE,
    ordinal             INT             NOT NULL,          -- chunk order within the doc
    section_path        NVARCHAR(400)   NULL,              -- "Getting There > By Train"  (citation anchor)
    content             NVARCHAR(MAX)   NOT NULL,          -- full-text searched
    token_count         INT             NULL,
    metadata            JSON            NULL,              -- {"season":"winter","region":"Alps","topic":"transport"}
    content_vector      VECTOR(1024)    NULL,              -- semantic embedding
    content_hash        VARBINARY(32)   NULL,              -- dedup / change detection
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_DocumentChunks_doc_ordinal UNIQUE (doc_id, ordinal)
);
GO


/*==============================================================================
  10a. RETRIEVAL DIAGNOSTICS TABLE  (log every retrieval for eval + debugging)
       The vw_RetrievalQuality view over this table is created in file 04.
==============================================================================*/
CREATE TABLE dbo.RetrievalLog
(
    retrieval_id        BIGINT IDENTITY(1,1)
        CONSTRAINT PK_RetrievalLog PRIMARY KEY CLUSTERED,
    session_id          UNIQUEIDENTIFIER NULL,
    traveler_id         INT             NULL,
    query_text          NVARCHAR(4000)  NOT NULL,
    strategy            NVARCHAR(40)     NOT NULL,          -- lexical|semantic|hybrid_rrf|hybrid_rerank
    filters_applied     JSON            NULL,
    candidate_count     INT             NULL,
    returned_count      INT             NULL,
    latency_ms          INT             NULL,
    -- per-result diagnostics: [{chunk_id, lex_rank, sem_rank, rrf, rerank, cited}]
    result_diagnostics  JSON            NULL,
    created_at          DATETIME2(3)    NOT NULL DEFAULT SYSUTCDATETIME()
);
GO


/*==============================================================================
  11a. TABLE TYPE used by the reranker tool (usp_RerankResults, file 04).
       Created here so the type exists before the procedure references it.
==============================================================================*/
IF TYPE_ID(N'dbo.RerankInput') IS NULL
    CREATE TYPE dbo.RerankInput AS TABLE
    (
        ordinal   INT           NOT NULL,   -- 0-based index sent to the reranker API
        chunk_id  BIGINT        NOT NULL,
        content   NVARCHAR(MAX) NOT NULL
    );
GO

/*==============================================================================
  FILE 03 of 05 : FULL-TEXT SEARCH + SUPPORTING INDEXES

  Run AFTER 02_create_schema.sql and BEFORE 04_programmability.sql (the
  retrieval procs use FREETEXTTABLE, which requires the full-text indexes
  created here).
==============================================================================*/
USE TravelAI;
GO


/*==============================================================================
  4. FULL-TEXT SEARCH (lexical retrieval)
     Requires a single-column unique index as the KEY INDEX per table.
==============================================================================*/
IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = N'TravelFTCatalog')
    CREATE FULLTEXT CATALOG TravelFTCatalog AS DEFAULT;
GO

-- KEY INDEXes for full-text (unique, single column)
CREATE UNIQUE INDEX UX_DocumentChunks_chunk_id ON dbo.DocumentChunks(chunk_id);
CREATE UNIQUE INDEX UX_KnowledgeDocuments_doc_id ON dbo.KnowledgeDocuments(doc_id);
CREATE UNIQUE INDEX UX_Destinations_destination_id ON dbo.Destinations(destination_id);
CREATE UNIQUE INDEX UX_Properties_property_id ON dbo.Properties(property_id);
CREATE UNIQUE INDEX UX_Activities_activity_id ON dbo.Activities(activity_id);
CREATE UNIQUE INDEX UX_Reviews_review_id ON dbo.Reviews(review_id);
GO

CREATE FULLTEXT INDEX ON dbo.DocumentChunks(content LANGUAGE 1033)
    KEY INDEX UX_DocumentChunks_chunk_id
    ON TravelFTCatalog WITH (CHANGE_TRACKING = AUTO, STOPLIST = SYSTEM);
GO
CREATE FULLTEXT INDEX ON dbo.KnowledgeDocuments(title LANGUAGE 1033)
    KEY INDEX UX_KnowledgeDocuments_doc_id
    ON TravelFTCatalog WITH (CHANGE_TRACKING = AUTO);
GO
CREATE FULLTEXT INDEX ON dbo.Destinations(name LANGUAGE 1033, description LANGUAGE 1033)
    KEY INDEX UX_Destinations_destination_id
    ON TravelFTCatalog WITH (CHANGE_TRACKING = AUTO);
GO
CREATE FULLTEXT INDEX ON dbo.Properties(name LANGUAGE 1033, description LANGUAGE 1033)
    KEY INDEX UX_Properties_property_id
    ON TravelFTCatalog WITH (CHANGE_TRACKING = AUTO);
GO
CREATE FULLTEXT INDEX ON dbo.Activities(name LANGUAGE 1033, description LANGUAGE 1033)
    KEY INDEX UX_Activities_activity_id
    ON TravelFTCatalog WITH (CHANGE_TRACKING = AUTO);
GO
CREATE FULLTEXT INDEX ON dbo.Reviews(title LANGUAGE 1033, body LANGUAGE 1033)
    KEY INDEX UX_Reviews_review_id
    ON TravelFTCatalog WITH (CHANGE_TRACKING = AUTO);
GO


/*==============================================================================
  5. SUPPORTING (B-TREE) INDEXES for metadata / SQL filters and joins
     These are used by iterative filtering alongside vector/lexical search.
==============================================================================*/
CREATE NONCLUSTERED INDEX IX_Properties_dest_active_price
    ON dbo.Properties(destination_id, is_active, nightly_price_usd)
    INCLUDE (star_rating, avg_review_score);
CREATE NONCLUSTERED INDEX IX_Activities_dest_cat
    ON dbo.Activities(destination_id, category, is_active) INCLUDE (price_usd);
CREATE NONCLUSTERED INDEX IX_Reviews_entity
    ON dbo.Reviews(entity_type, entity_id) INCLUDE (rating, created_at);
CREATE NONCLUSTERED INDEX IX_Chunks_doc
    ON dbo.DocumentChunks(doc_id) INCLUDE (ordinal, section_path);
CREATE NONCLUSTERED INDEX IX_Docs_type_lang
    ON dbo.KnowledgeDocuments(doc_type, language_code, is_active) INCLUDE (trust_score);
GO

-- Diagnostics log index (table created in file 02)
CREATE NONCLUSTERED INDEX IX_RetrievalLog_created ON dbo.RetrievalLog(created_at DESC);
GO


/*==============================================================================
  6. VECTOR INDEXES  (PREVIEW - optional, for ANN scale)
     NOTE for SQL Server 2025 box product:
       * Requires >= 100 non-null vectors before creation (populate embeddings
         via the procs in file 04 first).
       * Indexed table becomes read-only unless ALLOW_STALE_VECTOR_INDEX is set.
       * Query with VECTOR_SEARCH + SELECT TOP (N) WITH APPROXIMATE.
     Leave these commented until the tables are populated and you have accepted
     the read-only / staleness trade-off. The default procs use exact
     VECTOR_DISTANCE and do NOT need these indexes.
------------------------------------------------------------------------------
-- ALTER DATABASE SCOPED CONFIGURATION SET ALLOW_STALE_VECTOR_INDEX = ON;  -- if live DML needed

CREATE VECTOR INDEX VIX_Chunks_content ON dbo.DocumentChunks(content_vector)
    WITH (METRIC = 'cosine', TYPE = 'DiskANN');

CREATE VECTOR INDEX VIX_Properties_desc ON dbo.Properties(description_vector)
    WITH (METRIC = 'cosine', TYPE = 'DiskANN');

CREATE VECTOR INDEX VIX_Activities_desc ON dbo.Activities(description_vector)
    WITH (METRIC = 'cosine', TYPE = 'DiskANN');
==============================================================================*/

/*==============================================================================
  FILE 05 of 05 : SEED DATA  (Amazon RDS SQL Server 2025 + Amazon Bedrock build)

  Loads a realistic sample corpus for the Gen-AI / hybrid-retrieval workshop:
    - 18 Destinations, 30 Properties, 24 Activities, 10 Travelers,
      30 Reviews, 12 Bookings
    - 18 KnowledgeDocuments -> 117 DocumentChunks  (>= 100 required for the
      optional preview VECTOR INDEX in file 03)

  IMPORTANT
    * Run AFTER 01-04 (all objects must already exist):
        01_prerequisites.sql -> 02_create_schema.sql
        -> 03_indexes_and_fulltext.sql -> 04_programmability.sql -> (this file)
    * ALL vector columns are intentionally left NULL. Embeddings are generated
      server-side by the Bedrock procs (file 04), NOT stored inline:
          EXEC dbo.usp_EmbedDocumentChunks @batch_size = 200;  -- repeat until 0
          EXEC dbo.usp_EmbedProperties     @batch_size = 200;  -- repeat until 0
    * amenities pool/pet_friendly use numeric 1/0 (not true/false) because the
      persisted computed columns CAST(JSON_VALUE(...) AS BIT); a JSON boolean
      string ('true') cannot be cast to BIT.
    * best_season uses a scalar string (JSON_VALUE returns NULL for arrays).
    * Idempotent-ish: deletes existing sample rows first so it can be re-run.
==============================================================================*/
SET NOCOUNT ON;
USE TravelAI;
GO

/*------------------------------------------------------------------------------
  0. CLEAN SLATE (so the script can be re-run). Order respects FK dependencies.
------------------------------------------------------------------------------*/
DELETE FROM dbo.DocumentChunks;
DELETE FROM dbo.KnowledgeDocuments;
DELETE FROM dbo.Bookings;
DELETE FROM dbo.Reviews;
DELETE FROM dbo.Activities;
DELETE FROM dbo.Properties;
DELETE FROM dbo.Travelers;
DELETE FROM dbo.Destinations;
GO


/*==============================================================================
  1. DESTINATIONS   (explicit IDs so child tables can reference them)
==============================================================================*/
SET IDENTITY_INSERT dbo.Destinations ON;

INSERT INTO dbo.Destinations
    (destination_id, name, destination_type, country_code, region, geo,
     description, languages, popularity_score, attributes)
VALUES
 (1, N'Kyoto', N'city', 'JP', N'Kansai', geography::Point(35.0116, 135.7681, 4326),
  N'Japan''s former imperial capital, famous for classical Buddhist temples, imperial palaces, Shinto shrines, traditional wooden machiya houses and geisha districts.',
  N'Japanese', 92.0, N'{"climate":"temperate","best_season":"spring"}'),
 (2, N'Barcelona', N'city', 'ES', N'Catalonia', geography::Point(41.3874, 2.1686, 4326),
  N'A vibrant Mediterranean city known for Gaudi''s modernist architecture, beaches, tapas culture and the Gothic Quarter.',
  N'Spanish,Catalan', 90.0, N'{"climate":"mediterranean","best_season":"spring"}'),
 (3, N'Reykjavik', N'city', 'IS', N'Capital Region', geography::Point(64.1466, -21.9426, 4326),
  N'The compact northern capital of Iceland and gateway to geysers, waterfalls, the Golden Circle and northern lights.',
  N'Icelandic,English', 78.0, N'{"climate":"subarctic","best_season":"summer"}'),
 (4, N'Queenstown', N'city', 'NZ', N'Otago', geography::Point(-45.0312, 168.6626, 4326),
  N'New Zealand''s adventure capital on Lake Wakatipu, ringed by the Remarkables mountains, known for bungy, skiing and hiking.',
  N'English', 82.0, N'{"climate":"temperate","best_season":"summer"}'),
 (5, N'Santorini', N'region', 'GR', N'Cyclades', geography::Point(36.3932, 25.4615, 4326),
  N'A volcanic Greek island famed for whitewashed cliffside villages, blue-domed churches, caldera sunsets and romantic escapes.',
  N'Greek', 88.0, N'{"climate":"mediterranean","best_season":"summer"}'),
 (6, N'Bali', N'region', 'ID', N'Lesser Sunda Islands', geography::Point(-8.4095, 115.1889, 4326),
  N'An Indonesian island of forested volcanic mountains, rice paddies, beaches, coral reefs and Hindu temples, popular for wellness and surfing.',
  N'Indonesian,Balinese', 89.0, N'{"climate":"tropical","best_season":"dry season"}'),
 (7, N'Zermatt', N'city', 'CH', N'Valais', geography::Point(46.0207, 7.7491, 4326),
  N'A car-free Swiss alpine resort town at the foot of the Matterhorn, offering world-class skiing and glacier scenery.',
  N'German,French', 80.0, N'{"climate":"alpine","best_season":"winter"}'),
 (8, N'Marrakech', N'city', 'MA', N'Marrakesh-Safi', geography::Point(31.6295, -7.9811, 4326),
  N'A former imperial city in Morocco with a medieval walled medina, bustling souks, palaces, riads and the Jemaa el-Fnaa square.',
  N'Arabic,French', 75.0, N'{"climate":"semi-arid","best_season":"spring"}'),
 (9, N'Banff', N'city', 'CA', N'Alberta', geography::Point(51.1784, -115.5708, 4326),
  N'A resort town inside Banff National Park in the Canadian Rockies, surrounded by turquoise glacial lakes and mountain trails.',
  N'English,French', 79.0, N'{"climate":"alpine","best_season":"summer"}'),
 (10, N'Lisbon', N'city', 'PT', N'Lisboa', geography::Point(38.7223, -9.1393, 4326),
  N'Portugal''s hilly coastal capital, known for pastel buildings, tram 28, fado music, custard tarts and river views.',
  N'Portuguese', 84.0, N'{"climate":"mediterranean","best_season":"spring"}'),
 (11, N'Cape Town', N'city', 'ZA', N'Western Cape', geography::Point(-33.9249, 18.4241, 4326),
  N'A South African port city beneath Table Mountain, famous for beaches, winelands, penguins and the Cape of Good Hope.',
  N'English,Afrikaans', 83.0, N'{"climate":"mediterranean","best_season":"summer"}'),
 (12, N'Tokyo', N'city', 'JP', N'Kanto', geography::Point(35.6762, 139.6503, 4326),
  N'Japan''s bustling capital blending ultramodern skyscrapers and neon districts with historic temples, gardens and food culture.',
  N'Japanese', 91.0, N'{"climate":"temperate","best_season":"spring"}'),
 (13, N'Rome', N'city', 'IT', N'Lazio', geography::Point(41.9028, 12.4964, 4326),
  N'Italy''s capital, a sprawling city with nearly 3,000 years of art, architecture and culture, from the Colosseum to Vatican City.',
  N'Italian', 90.0, N'{"climate":"mediterranean","best_season":"spring"}'),
 (14, N'Paris', N'city', 'FR', N'Ile-de-France', geography::Point(48.8566, 2.3522, 4326),
  N'France''s capital, a global center for art, fashion and cuisine, home to the Eiffel Tower, the Louvre and the Seine.',
  N'French', 93.0, N'{"climate":"temperate","best_season":"spring"}'),
 (15, N'Dubrovnik', N'city', 'HR', N'Dalmatia', geography::Point(42.6507, 18.0944, 4326),
  N'A walled city on the Adriatic coast of Croatia, known for its medieval old town, limestone streets and sea views.',
  N'Croatian', 77.0, N'{"climate":"mediterranean","best_season":"summer"}'),
 (16, N'Chiang Mai', N'city', 'TH', N'Northern Thailand', geography::Point(18.7883, 98.9853, 4326),
  N'A mountainous northern Thai city of hundreds of temples, night markets, elephant sanctuaries and cooking schools.',
  N'Thai', 74.0, N'{"climate":"tropical","best_season":"winter"}'),
 (17, N'Machu Picchu', N'poi', 'PE', N'Cusco', geography::Point(-13.1631, -72.5450, 4326),
  N'A 15th-century Inca citadel set high in the Andes above the Sacred Valley, reached by the Inca Trail or train from Cusco.',
  N'Spanish,Quechua', 85.0, N'{"climate":"highland","best_season":"dry season"}'),
 (18, N'Serengeti', N'region', 'TZ', N'Mara', geography::Point(-2.3333, 34.8333, 4326),
  N'A vast Tanzanian savanna ecosystem famous for the annual wildebeest migration and Big Five safari game drives.',
  N'Swahili,English', 81.0, N'{"climate":"savanna","best_season":"dry season"}');

SET IDENTITY_INSERT dbo.Destinations OFF;
GO


/*==============================================================================
  2. PROPERTIES   (amenities: pool/pet_friendly numeric 1/0 -> persisted BITs)
==============================================================================*/
SET IDENTITY_INSERT dbo.Properties ON;

INSERT INTO dbo.Properties
    (property_id, destination_id, name, property_type, star_rating,
     nightly_price_usd, avg_review_score, review_count, address, description, amenities)
VALUES
 (1, 1, N'Gion Machiya Ryokan', N'hotel', 4, 320.00, 4.70, 128, N'Higashiyama, Kyoto',
  N'A restored traditional wooden ryokan in the Gion geisha district with tatami rooms, kaiseki dining and a cedar onsen bath.',
  N'{"pool":0,"wifi":true,"pet_friendly":0,"onsen":true,"breakfast":true}'),
 (2, 1, N'Kyoto Garden Hotel', N'hotel', 5, 480.00, 4.80, 210, N'Nakagyo, Kyoto',
  N'A luxury hotel near Nijo Castle with a rooftop pool, zen garden and Michelin-starred restaurant.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"spa":true,"gym":true}'),
 (3, 1, N'Arashiyama Riverside Inn', N'hostel', 2, 65.00, 4.30, 88, N'Arashiyama, Kyoto',
  N'A budget-friendly inn by the Katsura River, walking distance to the bamboo grove and monkey park.',
  N'{"pool":0,"wifi":true,"pet_friendly":1,"shared_kitchen":true}'),
 (4, 2, N'Eixample Boutique Hotel', N'hotel', 4, 210.00, 4.50, 175, N'Eixample, Barcelona',
  N'A modernist boutique hotel steps from the Sagrada Familia with a rooftop plunge pool and tapas bar.',
  N'{"pool":1,"wifi":true,"pet_friendly":1,"rooftop_bar":true}'),
 (5, 2, N'Barceloneta Beach Apartments', N'apartment', 3, 145.00, 4.20, 132, N'Barceloneta, Barcelona',
  N'Self-catering apartments one block from the beach, ideal for families and longer stays.',
  N'{"pool":0,"wifi":true,"pet_friendly":1,"kitchen":true,"laundry":true}'),
 (6, 2, N'Gothic Quarter Hostel', N'hostel', 2, 40.00, 4.10, 260, N'Ciutat Vella, Barcelona',
  N'A social hostel in the medieval old town with dorms, a bar and walking tours.',
  N'{"pool":0,"wifi":true,"pet_friendly":0,"bar":true}'),
 (7, 3, N'Reykjavik Harbour Hotel', N'hotel', 4, 260.00, 4.40, 96, N'Old Harbour, Reykjavik',
  N'A design hotel by the old harbour with northern-lights wake-up calls and a geothermal spa.',
  N'{"pool":0,"wifi":true,"pet_friendly":0,"spa":true,"geothermal":true}'),
 (8, 3, N'Golden Circle Cabins', N'villa', 3, 190.00, 4.60, 54, N'Selfoss, Iceland',
  N'Secluded glass-roof cabins with private hot tubs for aurora viewing, near the Golden Circle route.',
  N'{"pool":0,"wifi":true,"pet_friendly":1,"hot_tub":true}'),
 (9, 4, N'Remarkables Lodge', N'resort', 5, 540.00, 4.90, 143, N'Kelvin Heights, Queenstown',
  N'A family-friendly alpine resort with an indoor pool, ski shuttle and lake views of the Remarkables range.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"ski_shuttle":true,"kids_club":true}'),
 (10, 4, N'Lakefront Backpackers', N'hostel', 2, 55.00, 4.20, 189, N'Central Queenstown',
  N'A lively lakefront hostel close to the gondola, bungy bookings and adventure operators.',
  N'{"pool":0,"wifi":true,"pet_friendly":0,"tours":true}'),
 (11, 5, N'Oia Caldera Suites', N'resort', 5, 720.00, 4.90, 167, N'Oia, Santorini',
  N'Adults-only cave suites carved into the caldera cliff with private infinity plunge pools and famous sunset views.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"adults_only":true,"sunset_view":true}'),
 (12, 5, N'Fira Blue Dome Hotel', N'hotel', 4, 300.00, 4.50, 210, N'Fira, Santorini',
  N'A cliffside hotel near Fira''s shops and restaurants with a caldera-facing pool.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"caldera_view":true}'),
 (13, 6, N'Ubud Jungle Retreat', N'resort', 5, 260.00, 4.80, 198, N'Ubud, Bali',
  N'A wellness resort among the rice terraces with yoga pavilions, spa, and an infinity pool over the jungle.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"yoga":true,"spa":true}'),
 (14, 6, N'Seminyak Surf Villas', N'villa', 4, 175.00, 4.40, 121, N'Seminyak, Bali',
  N'Private villas near the surf beaches with plunge pools and a shared surf school.',
  N'{"pool":1,"wifi":true,"pet_friendly":1,"surf_school":true}'),
 (15, 7, N'Matterhorn Grand Hotel', N'resort', 5, 610.00, 4.90, 156, N'Zermatt Centre',
  N'A ski-in ski-out alpine grand hotel with a heated indoor pool, spa and direct Matterhorn views; excellent for families.',
  N'{"pool":1,"wifi":true,"pet_friendly":1,"ski_in_out":true,"kids_club":true,"spa":true}'),
 (16, 7, N'Zermatt Chalet Lodge', N'apartment', 3, 230.00, 4.50, 74, N'Winkelmatten, Zermatt',
  N'Cozy self-catering chalets a short walk from the ski lifts, with a sauna and boot room.',
  N'{"pool":0,"wifi":true,"pet_friendly":1,"sauna":true,"kitchen":true}'),
 (17, 8, N'Riad El Fenn', N'hotel', 4, 240.00, 4.70, 132, N'Medina, Marrakech',
  N'A stylish riad hidden in the medina with courtyard pools, rooftop terraces and a hammam.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"hammam":true,"rooftop":true}'),
 (18, 8, N'Palmeraie Desert Resort', N'resort', 5, 390.00, 4.60, 98, N'Palmeraie, Marrakech',
  N'A palm-grove resort with large pools, spa and camel excursions on the desert fringe.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"spa":true,"desert_tours":true}'),
 (19, 9, N'Fairview Mountain Lodge', N'resort', 4, 330.00, 4.70, 143, N'Banff Avenue, Banff',
  N'A mountain lodge on Banff Avenue with a hot pool, family suites and easy access to Lake Louise.',
  N'{"pool":1,"wifi":true,"pet_friendly":1,"hot_pool":true,"family_suites":true}'),
 (20, 9, N'Bow River Hostel', N'hostel', 2, 60.00, 4.30, 176, N'Central Banff',
  N'A budget hostel by the Bow River with gear rental and shuttle access to hiking trailheads.',
  N'{"pool":0,"wifi":true,"pet_friendly":0,"gear_rental":true}'),
 (21, 10, N'Alfama View Guesthouse', N'apartment', 3, 120.00, 4.40, 154, N'Alfama, Lisbon',
  N'Charming apartments in the historic Alfama district with tram views and a shared rooftop.',
  N'{"pool":0,"wifi":true,"pet_friendly":1,"kitchen":true,"rooftop":true}'),
 (22, 10, N'Belem Riverside Hotel', N'hotel', 4, 185.00, 4.50, 121, N'Belem, Lisbon',
  N'A riverfront hotel near the Belem Tower with a pool deck and pastel de nata breakfast.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"river_view":true}'),
 (23, 11, N'Table Mountain Boutique', N'hotel', 4, 200.00, 4.60, 138, N'City Bowl, Cape Town',
  N'A boutique hotel below Table Mountain with a heated pool and cable-car shuttle.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"mountain_view":true}'),
 (24, 11, N'Camps Bay Beach Villas', N'villa', 5, 420.00, 4.80, 87, N'Camps Bay, Cape Town',
  N'Luxury beachfront villas with infinity pools facing the Twelve Apostles and Atlantic sunsets.',
  N'{"pool":1,"wifi":true,"pet_friendly":1,"beachfront":true}'),
 (25, 12, N'Shinjuku Sky Hotel', N'hotel', 4, 220.00, 4.50, 245, N'Shinjuku, Tokyo',
  N'A high-rise hotel above Shinjuku station with skyline views and easy access to nightlife and transit.',
  N'{"pool":0,"wifi":true,"pet_friendly":0,"skyline_view":true}'),
 (26, 12, N'Asakusa Traditional Inn', N'hostel', 3, 85.00, 4.40, 167, N'Asakusa, Tokyo',
  N'A friendly inn near Senso-ji temple with capsule and family rooms and a communal lounge.',
  N'{"pool":0,"wifi":true,"pet_friendly":0,"family_rooms":true}'),
 (27, 13, N'Trastevere Charm Hotel', N'hotel', 4, 195.00, 4.60, 189, N'Trastevere, Rome',
  N'A romantic hotel in cobblestoned Trastevere, walking distance to the Vatican and great trattorias.',
  N'{"pool":0,"wifi":true,"pet_friendly":1,"terrace":true}'),
 (28, 14, N'Le Marais Family Suites', N'apartment', 4, 260.00, 4.70, 176, N'Le Marais, Paris',
  N'Spacious family apartments in Le Marais near the Pompidou, with connecting rooms and cribs on request.',
  N'{"pool":0,"wifi":true,"pet_friendly":1,"family_suites":true,"kitchen":true}'),
 (29, 16, N'Old City Temple Lodge', N'hotel', 3, 70.00, 4.50, 143, N'Old City, Chiang Mai',
  N'A serene lodge inside the old city walls with a garden pool and free bicycles to explore the temples.',
  N'{"pool":1,"wifi":true,"pet_friendly":1,"bicycles":true}'),
 (30, 18, N'Serengeti Tented Camp', N'resort', 5, 650.00, 4.90, 76, N'Central Serengeti',
  N'A luxury tented safari camp with game-drive guides, plunge pool and migration-season views.',
  N'{"pool":1,"wifi":true,"pet_friendly":0,"game_drives":true,"full_board":true}');

SET IDENTITY_INSERT dbo.Properties OFF;
GO


/*==============================================================================
  3. ACTIVITIES
==============================================================================*/
SET IDENTITY_INSERT dbo.Activities ON;

INSERT INTO dbo.Activities
    (activity_id, destination_id, name, category, duration_minutes, price_usd, difficulty, description, tags)
VALUES
 (1, 1, N'Fushimi Inari Shrine Hike', N'culture', 150, 0.00, N'moderate',
  N'Walk the thousands of vermilion torii gates winding up the sacred Mount Inari.', N'["outdoor","free","iconic"]'),
 (2, 1, N'Kyoto Tea Ceremony', N'culture', 90, 45.00, N'easy',
  N'Participate in a traditional matcha tea ceremony led by a kimono-clad host.', N'["indoor","cultural","guided"]'),
 (3, 1, N'Arashiyama Bamboo & Monkey Park', N'nature', 180, 12.00, N'easy',
  N'Stroll the famous bamboo grove and visit the hillside snow-monkey park.', N'["outdoor","family-friendly"]'),
 (4, 2, N'Sagrada Familia Skip-the-Line Tour', N'culture', 120, 39.00, N'easy',
  N'Guided tour of Gaudi''s unfinished basilica with tower access.', N'["indoor","guided","iconic"]'),
 (5, 2, N'Barcelona Tapas Crawl', N'food', 180, 75.00, N'easy',
  N'Evening walking tour sampling tapas and vermouth across the old town.', N'["food","evening","guided"]'),
 (6, 3, N'Golden Circle Day Tour', N'nature', 480, 95.00, N'easy',
  N'Full-day tour of Thingvellir, Geysir and Gullfoss waterfall.', N'["outdoor","guided","scenic"]'),
 (7, 3, N'Northern Lights Chase', N'nature', 240, 80.00, N'easy',
  N'Evening minibus hunt for the aurora borealis away from city lights.', N'["evening","seasonal","scenic"]'),
 (8, 4, N'Nevis Bungy Jump', N'adventure', 240, 205.00, N'hard',
  N'Leap 134 meters from the Nevis bungy pod over a river canyon.', N'["adrenaline","outdoor","iconic"]'),
 (9, 4, N'Milford Sound Cruise', N'nature', 720, 130.00, N'easy',
  N'Scenic coach and boat trip through the fjords of Milford Sound.', N'["scenic","family-friendly","guided"]'),
 (10, 5, N'Santorini Caldera Sunset Sail', N'nature', 300, 140.00, N'easy',
  N'Catamaran cruise to the volcanic hot springs with a sunset dinner.', N'["romantic","evening","scenic"]'),
 (11, 5, N'Akrotiri Archaeological Tour', N'culture', 120, 30.00, N'easy',
  N'Explore the preserved Bronze Age town buried by a volcanic eruption.', N'["indoor","guided","history"]'),
 (12, 6, N'Ubud Rice Terrace Yoga', N'nature', 90, 25.00, N'easy',
  N'Sunrise yoga session overlooking the Tegallalang rice terraces.', N'["wellness","outdoor","morning"]'),
 (13, 6, N'Uluwatu Surf Lesson', N'adventure', 120, 40.00, N'moderate',
  N'Beginner-friendly surf lesson on Bali''s famous west-coast breaks.', N'["outdoor","water","guided"]'),
 (14, 7, N'Matterhorn Glacier Paradise', N'nature', 180, 110.00, N'easy',
  N'Ride Europe''s highest cable car to the glacier viewing platform and ice palace.', N'["scenic","family-friendly"]'),
 (15, 7, N'Zermatt Ski Day Pass', N'adventure', 480, 90.00, N'moderate',
  N'Full-day lift pass across Zermatt''s interconnected ski slopes.', N'["winter","outdoor","snow"]'),
 (16, 8, N'Jemaa el-Fnaa Food Tour', N'food', 180, 55.00, N'easy',
  N'Evening street-food tour of Marrakech''s legendary night market.', N'["food","evening","guided"]'),
 (17, 9, N'Lake Louise Canoe', N'nature', 120, 60.00, N'easy',
  N'Paddle the turquoise glacial waters of Lake Louise beneath the peaks.', N'["outdoor","water","scenic"]'),
 (18, 9, N'Johnston Canyon Ice Walk', N'adventure', 210, 70.00, N'moderate',
  N'Guided winter hike to frozen waterfalls with ice cleats provided.', N'["winter","outdoor","guided"]'),
 (19, 11, N'Table Mountain Cable Car', N'nature', 150, 32.00, N'easy',
  N'Ascend Table Mountain by rotating cable car for panoramic city views.', N'["scenic","family-friendly"]'),
 (20, 11, N'Cape Peninsula & Penguins', N'nature', 540, 85.00, N'easy',
  N'Day tour to the Cape of Good Hope and the Boulders Beach penguin colony.', N'["outdoor","family-friendly","guided"]'),
 (21, 13, N'Colosseum Underground Tour', N'culture', 180, 65.00, N'moderate',
  N'Guided access to the Colosseum arena floor and underground chambers.', N'["history","guided","iconic"]'),
 (22, 14, N'Louvre Highlights Tour', N'culture', 150, 55.00, N'easy',
  N'Skip-the-line guided tour of the Louvre''s masterpieces including the Mona Lisa.', N'["indoor","guided","family-friendly"]'),
 (23, 17, N'Inca Trail to Machu Picchu', N'adventure', 2880, 650.00, N'hard',
  N'Classic four-day guided trek along the Andes to the Sun Gate of Machu Picchu.', N'["multi-day","outdoor","iconic"]'),
 (24, 18, N'Great Migration Game Drive', N'nature', 600, 220.00, N'easy',
  N'Full-day 4x4 safari tracking the wildebeest migration and Big Five.', N'["wildlife","guided","scenic"]');

SET IDENTITY_INSERT dbo.Activities OFF;
GO


/*==============================================================================
  4. TRAVELERS   (preference_vector left NULL - personalize later if desired)
==============================================================================*/
SET IDENTITY_INSERT dbo.Travelers ON;

INSERT INTO dbo.Travelers (traveler_id, display_name, home_country, preferences)
VALUES
 (1, N'Aiko Tanaka',    'JP', N'{"budget":"mid","interests":["culture","food"],"pace":"relaxed"}'),
 (2, N'Liam O''Brien',   'IE', N'{"budget":"low","interests":["adventure","hiking"],"pace":"fast"}'),
 (3, N'Sofia Marino',    'IT', N'{"budget":"high","interests":["romance","beaches"],"pace":"relaxed"}'),
 (4, N'James Carter',    'US', N'{"budget":"mid","interests":["family","nature"],"pace":"moderate"}'),
 (5, N'Priya Nair',      'IN', N'{"budget":"mid","interests":["wellness","food"],"pace":"relaxed"}'),
 (6, N'Lucas Silva',     'BR', N'{"budget":"low","interests":["nightlife","beaches"],"pace":"fast"}'),
 (7, N'Emma Johansson',  'SE', N'{"budget":"high","interests":["skiing","luxury"],"pace":"moderate"}'),
 (8, N'Noah Meyer',      'DE', N'{"budget":"mid","interests":["history","architecture"],"pace":"moderate"}'),
 (9, N'Grace Kim',       'KR', N'{"budget":"mid","interests":["shopping","food"],"pace":"fast"}'),
 (10, N'Oliver Brown',   'GB', N'{"budget":"high","interests":["wildlife","photography"],"pace":"relaxed"}');

SET IDENTITY_INSERT dbo.Travelers OFF;
GO


/*==============================================================================
  5. REVIEWS   (body_vector left NULL; entity_id references the tables above)
==============================================================================*/
INSERT INTO dbo.Reviews (entity_type, entity_id, traveler_id, rating, title, body, language_code)
VALUES
 (N'property', 2, 1, 5, N'Impeccable Kyoto stay', N'The rooftop pool and zen garden were stunning, and the staff arranged a private tea ceremony. Worth every yen.', 'en'),
 (N'property', 1, 8, 5, N'Authentic ryokan experience', N'Sleeping on tatami and soaking in the cedar onsen was unforgettable. Right in the heart of Gion.', 'en'),
 (N'property', 3, 2, 4, N'Great budget base', N'Simple but clean, and the location by the river near the bamboo grove is unbeatable for the price.', 'en'),
 (N'property', 9, 4, 5, N'Perfect for families', N'The indoor pool and kids club kept the children happy, and the ski shuttle made mornings easy.', 'en'),
 (N'property', 11, 3, 5, N'Most romantic sunset ever', N'Our cave suite had a private plunge pool facing the caldera. The Oia sunset from our terrace was magical.', 'en'),
 (N'property', 15, 7, 5, N'Ski-in ski-out heaven', N'Stepped straight onto the slopes with the Matterhorn in view. The spa and pool were the perfect after-ski wind down.', 'en'),
 (N'property', 13, 5, 5, N'Jungle wellness bliss', N'Morning yoga over the rice terraces and an infinity pool in the treetops. Deeply relaxing.', 'en'),
 (N'property', 24, 3, 5, N'Beachfront luxury', N'Infinity pool facing the Atlantic and sunsets over the Twelve Apostles. Camps Bay is spectacular.', 'en'),
 (N'property', 19, 4, 4, N'Solid Rockies base', N'The hot pool after a day of hiking was wonderful, and Lake Louise is a short drive away.', 'en'),
 (N'property', 6, 6, 4, N'Fun and cheap', N'Lively hostel bar and great walking tours. Perfect if you want to meet people in Barcelona.', 'en'),
 (N'property', 4, 8, 4, N'Great location', N'A short walk to the Sagrada Familia and the rooftop plunge pool was a nice surprise.', 'en'),
 (N'property', 25, 9, 4, N'Convenient Tokyo hub', N'Right above Shinjuku station, so getting anywhere was effortless. Small rooms but great views.', 'en'),
 (N'property', 30, 10, 5, N'Safari of a lifetime', N'Woke to the sound of the migration and watched lions from the plunge pool deck. Incredible guides.', 'en'),
 (N'property', 17, 5, 5, N'Riad oasis', N'A calm courtyard pool hidden from the medina chaos. The rooftop breakfast was lovely.', 'en'),
 (N'property', 28, 4, 5, N'Ideal for kids in Paris', N'Connecting family rooms and a crib on request. Le Marais is central and walkable.', 'en'),
 (N'activity', 8, 2, 5, N'Terrifying and amazing', N'The Nevis bungy was the scariest 8 seconds of my life. Do it!', 'en'),
 (N'activity', 10, 3, 5, N'Dreamy sunset sail', N'The catamaran cruise with dinner and the caldera sunset was the highlight of our honeymoon.', 'en'),
 (N'activity', 6, 4, 4, N'Golden Circle worth it', N'Geysir and Gullfoss were breathtaking. Long day but the guide was excellent.', 'en'),
 (N'activity', 23, 2, 5, N'Bucket list trek', N'Four hard days on the Inca Trail rewarded with the Sun Gate at dawn. Unforgettable.', 'en'),
 (N'activity', 24, 10, 5, N'Migration magic', N'We saw a river crossing and all of the Big Five in one day. Bring a long lens.', 'en'),
 (N'activity', 12, 5, 5, N'Serene rice terrace yoga', N'Sunrise yoga above Tegallalang set the tone for the whole trip.', 'en'),
 (N'activity', 15, 7, 5, N'World-class skiing', N'Endless interconnected slopes and the Matterhorn everywhere you look.', 'en'),
 (N'activity', 5, 6, 4, N'Delicious tapas crawl', N'Great value and our guide knew all the best little bars off the tourist track.', 'en'),
 (N'activity', 21, 8, 5, N'History come alive', N'Standing on the Colosseum arena floor was surreal. Book the underground.', 'en'),
 (N'activity', 3, 1, 4, N'Lovely with kids', N'The bamboo grove was magical early morning and the monkeys delighted the children.', 'en'),
 (N'destination', 5, 3, 5, N'Santorini is pure romance', N'Every corner is a postcard. Perfect for couples chasing sunsets.', 'en'),
 (N'destination', 1, 1, 5, N'Kyoto in spring', N'Cherry blossoms along the Philosopher''s Path were unforgettable. Visit early to beat crowds.', 'en'),
 (N'destination', 7, 7, 5, N'Alpine paradise', N'Car-free, charming, and the skiing under the Matterhorn is world class.', 'en'),
 (N'destination', 18, 10, 5, N'Wildlife wonderland', N'The Serengeti during the dry season delivered non-stop game viewing.', 'en'),
 (N'destination', 4, 2, 5, N'Adventure capital lives up to it', N'Bungy, jet boats, hiking - Queenstown packs it all against a stunning backdrop.', 'en');
GO


/*==============================================================================
  6. BOOKINGS
==============================================================================*/
INSERT INTO dbo.Bookings (traveler_id, property_id, activity_id, check_in, check_out, total_usd, status)
VALUES
 (1, 2,  NULL, '2026-04-02', '2026-04-06', 1920.00, 'confirmed'),
 (3, 11, NULL, '2026-06-10', '2026-06-14', 2880.00, 'confirmed'),
 (4, 9,  NULL, '2026-07-18', '2026-07-23', 2700.00, 'confirmed'),
 (7, 15, NULL, '2026-01-20', '2026-01-27', 4270.00, 'confirmed'),
 (5, 13, NULL, '2026-05-05', '2026-05-10', 1300.00, 'confirmed'),
 (10, 30, NULL, '2026-08-12', '2026-08-16', 2600.00, 'confirmed'),
 (2, 10, NULL, '2026-11-03', '2026-11-06',  165.00, 'confirmed'),
 (8, 27, NULL, '2026-09-14', '2026-09-17',  585.00, 'confirmed'),
 (2, NULL, 8,  '2026-11-04', NULL,           205.00, 'confirmed'),
 (3, NULL, 10, '2026-06-11', NULL,           280.00, 'confirmed'),
 (10, NULL, 24,'2026-08-13', NULL,           440.00, 'confirmed'),
 (2, NULL, 23, '2026-05-20', NULL,           650.00, 'pending');
GO


/*==============================================================================
  7. KNOWLEDGE DOCUMENTS   (trust_score persisted from metadata.$.trust)
==============================================================================*/
SET IDENTITY_INSERT dbo.KnowledgeDocuments ON;

INSERT INTO dbo.KnowledgeDocuments
    (doc_id, title, doc_type, source_uri, publisher, language_code, entity_type, entity_id, metadata, published_at)
VALUES
 (1,  N'Kyoto Travel Guide',            N'guide',     N'https://guides.example.com/kyoto',            N'TravelAI Editorial', 'en', N'destination', 1,  N'{"author":"Editorial","trust":0.95}', '2025-06-01'),
 (2,  N'Barcelona City Guide',          N'guide',     N'https://guides.example.com/barcelona',        N'TravelAI Editorial', 'en', N'destination', 2,  N'{"author":"Editorial","trust":0.90}', '2025-05-15'),
 (3,  N'Iceland Ring Road Itinerary',   N'itinerary', N'https://guides.example.com/iceland-ringroad',  N'TravelAI Editorial', 'en', N'destination', 3,  N'{"author":"Editorial","trust":0.88}', '2025-04-20'),
 (4,  N'Queenstown Adventure Guide',    N'guide',     N'https://guides.example.com/queenstown',        N'TravelAI Editorial', 'en', N'destination', 4,  N'{"author":"Editorial","trust":0.86}', '2025-07-02'),
 (5,  N'Santorini Romantic Escapes',    N'guide',     N'https://guides.example.com/santorini',         N'TravelAI Editorial', 'en', N'destination', 5,  N'{"author":"Editorial","trust":0.90}', '2025-03-11'),
 (6,  N'Bali Wellness and Beaches',     N'guide',     N'https://guides.example.com/bali',              N'TravelAI Editorial', 'en', N'destination', 6,  N'{"author":"Editorial","trust":0.87}', '2025-08-01'),
 (7,  N'Zermatt Ski Guide',             N'guide',     N'https://guides.example.com/zermatt',           N'TravelAI Editorial', 'en', N'destination', 7,  N'{"author":"Editorial","trust":0.92}', '2025-11-10'),
 (8,  N'Marrakech Medina Guide',        N'guide',     N'https://guides.example.com/marrakech',         N'TravelAI Editorial', 'en', N'destination', 8,  N'{"author":"Editorial","trust":0.83}', '2025-02-18'),
 (9,  N'Banff National Park Guide',     N'guide',     N'https://guides.example.com/banff',             N'TravelAI Editorial', 'en', N'destination', 9,  N'{"author":"Editorial","trust":0.90}', '2025-06-25'),
 (10, N'Lisbon Neighborhood Guide',     N'guide',     N'https://guides.example.com/lisbon',            N'TravelAI Editorial', 'en', N'destination', 10, N'{"author":"Editorial","trust":0.85}', '2025-05-30'),
 (11, N'Cape Town Highlights',          N'guide',     N'https://guides.example.com/capetown',          N'TravelAI Editorial', 'en', N'destination', 11, N'{"author":"Editorial","trust":0.86}', '2025-09-05'),
 (12, N'Tokyo First-Timer FAQ',         N'faq',       N'https://guides.example.com/tokyo-faq',         N'TravelAI Editorial', 'en', N'destination', 12, N'{"author":"Editorial","trust":0.90}', '2025-07-19'),
 (13, N'Rome Ancient Sites',            N'article',   N'https://guides.example.com/rome-ancient',      N'TravelAI Editorial', 'en', N'destination', 13, N'{"author":"Editorial","trust":0.88}', '2025-04-01'),
 (14, N'Paris Family Travel',           N'guide',     N'https://guides.example.com/paris-family',      N'TravelAI Editorial', 'en', N'destination', 14, N'{"author":"Editorial","trust":0.90}', '2025-06-12'),
 (15, N'Booking and Cancellation Policy', N'policy',  N'https://policies.example.com/booking',         N'TravelAI Legal',     'en', NULL,          NULL, N'{"author":"Legal","trust":0.99}', '2025-01-05'),
 (16, N'Travel Insurance FAQ',          N'faq',       N'https://policies.example.com/insurance',       N'TravelAI Legal',     'en', NULL,          NULL, N'{"author":"Legal","trust":0.97}', '2025-01-05'),
 (17, N'Machu Picchu Trek Guide',       N'guide',     N'https://guides.example.com/machupicchu',       N'TravelAI Editorial', 'en', N'destination', 17, N'{"author":"Editorial","trust":0.89}', '2025-03-22'),
 (18, N'Serengeti Safari Guide',        N'guide',     N'https://guides.example.com/serengeti',         N'TravelAI Editorial', 'en', N'destination', 18, N'{"author":"Editorial","trust":0.90}', '2025-08-14');

SET IDENTITY_INSERT dbo.KnowledgeDocuments OFF;
GO


/*==============================================================================
  8. DOCUMENT CHUNKS   (117 rows; content_vector left NULL for the embed proc)
     chunk_id is IDENTITY (auto). UNIQUE (doc_id, ordinal) enforced by schema.
     metadata.$.topic supports the @topic filter in usp_HybridSearchChunks.
==============================================================================*/

-- Doc 1: Kyoto Travel Guide (8 chunks) -----------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (1, 1, N'Getting There',            N'Kyoto has no major international airport; most visitors fly into Osaka Kansai (KIX) and take the Haruka express train, about 75 minutes, or arrive by shinkansen bullet train from Tokyo in roughly 2 hours 15 minutes.', 52, N'{"topic":"transport","season":"any"}'),
 (1, 2, N'Best Time to Visit',       N'The best time to visit Kyoto is spring (late March to April) for cherry blossoms and autumn (November) for red maple leaves. Summers are hot and humid, while winter is cold but quiet with occasional snow on the temples.', 55, N'{"topic":"seasonality","season":"spring"}'),
 (1, 3, N'Neighborhoods',            N'Gion is the historic geisha district, Higashiyama is full of temples and lanes, Arashiyama offers bamboo groves and river views, and downtown Nakagyo has shopping and dining around Nishiki Market.', 48, N'{"topic":"neighborhoods","season":"any"}'),
 (1, 4, N'Temples and Shrines',      N'Must-see sites include Fushimi Inari with its torii gate tunnels, golden Kinkaku-ji, Kiyomizu-dera''s wooden terrace, and the Zen rock garden at Ryoan-ji. Arrive early to avoid crowds.', 46, N'{"topic":"sights","season":"any"}'),
 (1, 5, N'Food and Dining',          N'Kyoto is known for kaiseki multi-course cuisine, yudofu tofu hot pot, matcha sweets, and Nishiki Market street food. Reserve high-end kaiseki restaurants well in advance.', 44, N'{"topic":"food","season":"any"}'),
 (1, 6, N'Etiquette',                N'Remove shoes when entering temples and ryokan, keep voices low in sacred spaces, and do not photograph geiko or maiko without permission in Gion.', 38, N'{"topic":"etiquette","season":"any"}'),
 (1, 7, N'Day Trips',                N'Easy day trips include Nara''s deer park and Great Buddha, the lakeside town of Otsu, and the sake district of Fushimi, all within an hour by train.', 40, N'{"topic":"day-trips","season":"any"}'),
 (1, 8, N'Getting Around',           N'Kyoto''s buses cover most temples, but the subway and bicycles are faster for central areas. A prepaid ICOCA card works on all transit.', 38, N'{"topic":"transport","season":"any"}');

-- Doc 2: Barcelona City Guide (7 chunks) ---------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (2, 1, N'Getting There',            N'Barcelona El Prat airport is 15 km from the center, connected by the Aerobus, metro line L9, and trains. The city is also a major stop on Spain''s AVE high-speed rail network.', 46, N'{"topic":"transport","season":"any"}'),
 (2, 2, N'Best Time to Visit',       N'Spring and early autumn offer warm weather and thinner crowds. July and August are hot and busy; the beaches fill up and prices peak.', 40, N'{"topic":"seasonality","season":"spring"}'),
 (2, 3, N'Gaudi and Modernism',      N'Antoni Gaudi''s works define the skyline: the Sagrada Familia basilica, Park Guell, Casa Batllo and La Pedrera. Book timed tickets online to skip long lines.', 44, N'{"topic":"sights","season":"any"}'),
 (2, 4, N'The Gothic Quarter',       N'The Barri Gotic is a maze of medieval streets, hidden squares and the Barcelona Cathedral, best explored on foot in the early morning.', 40, N'{"topic":"neighborhoods","season":"any"}'),
 (2, 5, N'Beaches',                  N'Barceloneta and Bogatell beaches are a short metro ride from the center, with chiringuito beach bars and calm summer swimming.', 38, N'{"topic":"beaches","season":"summer"}'),
 (2, 6, N'Food and Tapas',           N'Sample tapas, pintxos and vermouth in the El Born and Gracia districts, and visit La Boqueria market off La Rambla for fresh produce.', 40, N'{"topic":"food","season":"any"}'),
 (2, 7, N'Safety and Tips',          N'Barcelona is generally safe but pickpocketing is common on La Rambla and the metro; keep valuables secure in crowds.', 36, N'{"topic":"safety","season":"any"}');

-- Doc 3: Iceland Ring Road Itinerary (7 chunks) --------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (3, 1, N'Overview',                 N'The Ring Road (Route 1) circles Iceland for about 1,332 km. A comfortable self-drive loop takes 7 to 10 days, longer if you detour to the Westfjords.', 46, N'{"topic":"itinerary","season":"summer"}'),
 (3, 2, N'When to Go',               N'Summer offers midnight sun and open highland roads; winter brings northern lights but icy driving and shorter days. Rent a 4x4 outside summer.', 42, N'{"topic":"seasonality","season":"summer"}'),
 (3, 3, N'The Golden Circle',        N'Near Reykjavik, the Golden Circle links Thingvellir National Park, the Geysir hot springs and the two-tiered Gullfoss waterfall.', 38, N'{"topic":"sights","season":"any"}'),
 (3, 4, N'South Coast',              N'The south coast features Seljalandsfoss and Skogafoss waterfalls, the black-sand Reynisfjara beach, and the Jokulsarlon glacier lagoon.', 40, N'{"topic":"sights","season":"any"}'),
 (3, 5, N'North and Myvatn',         N'The north offers the Godafoss waterfall, the geothermal Myvatn area, and whale watching from Husavik.', 34, N'{"topic":"sights","season":"any"}'),
 (3, 6, N'Driving Tips',             N'Fuel up whenever possible, watch for single-lane bridges and sheep on the road, and check road.is for conditions before setting out.', 40, N'{"topic":"transport","season":"any"}'),
 (3, 7, N'Northern Lights',          N'Aurora season runs roughly September to April. Chase clear, dark skies away from towns and check aurora forecasts for activity levels.', 38, N'{"topic":"seasonality","season":"winter"}');

-- Doc 4: Queenstown Adventure Guide (6 chunks) ---------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (4, 1, N'Getting There',            N'Queenstown airport receives direct flights from Auckland, Christchurch and eastern Australia. The town center is a 10-minute drive away.', 38, N'{"topic":"transport","season":"any"}'),
 (4, 2, N'Adrenaline Activities',    N'Queenstown is the birthplace of commercial bungy jumping; try the Kawarau Bridge or the higher Nevis, plus jet boating, skydiving and canyon swings.', 44, N'{"topic":"adventure","season":"summer"}'),
 (4, 3, N'Winter Skiing',            N'From June to September, Coronet Peak and the Remarkables offer skiing and snowboarding within 30 minutes of town.', 38, N'{"topic":"skiing","season":"winter"}'),
 (4, 4, N'Milford Sound',            N'A long but rewarding day trip leads to Milford Sound in Fiordland, where cruises pass waterfalls and sheer cliffs.', 38, N'{"topic":"sights","season":"any"}'),
 (4, 5, N'Family Options',           N'Families enjoy the Skyline Gondola and luge, the lakeside walks, and gentle cruises on the historic steamship TSS Earnslaw.', 38, N'{"topic":"family","season":"any"}'),
 (4, 6, N'Where to Stay',            N'Stay central for nightlife and dining, or across the lake at Kelvin Heights for quiet family resorts with pools and shuttles.', 40, N'{"topic":"lodging","season":"any"}');

-- Doc 5: Santorini Romantic Escapes (6 chunks) ---------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (5, 1, N'Why Santorini',            N'Santorini is one of the world''s most romantic destinations, with whitewashed villages perched on a volcanic caldera and legendary sunsets.', 40, N'{"topic":"romance","season":"summer"}'),
 (5, 2, N'Best Villages',            N'Oia is famous for its sunset and luxury cave suites, Imerovigli is quieter and upscale, and Fira is the lively capital with nightlife.', 42, N'{"topic":"neighborhoods","season":"any"}'),
 (5, 3, N'Sunset Spots',             N'The Oia castle is the classic sunset viewpoint but gets crowded; a caldera sailing cruise offers a calmer, romantic alternative.', 40, N'{"topic":"romance","season":"summer"}'),
 (5, 4, N'Beaches',                  N'Santorini''s volcanic beaches include the Red Beach, the Black Beach at Perissa, and Kamari with its dark sand and tavernas.', 40, N'{"topic":"beaches","season":"summer"}'),
 (5, 5, N'Wine and Food',            N'The island''s volcanic soil produces crisp Assyrtiko white wine; visit a caldera-view winery and try fresh seafood and fava dip.', 40, N'{"topic":"food","season":"any"}'),
 (5, 6, N'When to Visit',            N'Late spring and early autumn are ideal for warm weather without peak-summer crowds and prices. August is the busiest month.', 38, N'{"topic":"seasonality","season":"summer"}');

-- Doc 6: Bali Wellness and Beaches (7 chunks) ----------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (6, 1, N'Regions',                  N'Ubud is Bali''s cultural and wellness heart inland, while Seminyak, Canggu and Uluwatu on the south coast draw surfers and beach lovers.', 42, N'{"topic":"neighborhoods","season":"any"}'),
 (6, 2, N'Best Season',              N'The dry season from April to October is best for sunshine and surfing; the wet season is greener, quieter and cheaper.', 40, N'{"topic":"seasonality","season":"dry season"}'),
 (6, 3, N'Wellness and Yoga',        N'Ubud is renowned for yoga retreats, spa treatments and healthy cafes set among the rice terraces.', 34, N'{"topic":"wellness","season":"any"}'),
 (6, 4, N'Surfing',                  N'Beginners learn on the gentle beach breaks of Kuta and Seminyak, while experienced surfers head to the reef breaks of Uluwatu.', 40, N'{"topic":"adventure","season":"dry season"}'),
 (6, 5, N'Temples',                  N'Visit the sea temple of Tanah Lot, the clifftop Uluwatu temple at sunset, and the water temple of Tirta Empul for a purification ritual.', 42, N'{"topic":"sights","season":"any"}'),
 (6, 6, N'Rice Terraces',            N'The Tegallalang and Jatiluwih rice terraces showcase Bali''s traditional subak irrigation and make for scenic morning walks.', 38, N'{"topic":"sights","season":"any"}'),
 (6, 7, N'Etiquette',                N'Wear a sarong at temples, use your right hand to give and receive, and step around the small daily canang sari offerings on the ground.', 42, N'{"topic":"etiquette","season":"any"}');

-- Doc 7: Zermatt Ski Guide (7 chunks) ------------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (7, 1, N'Getting There',            N'Zermatt is car-free; drive or take the train to Tasch and transfer to the Zermatt shuttle train for the final leg into the resort.', 42, N'{"topic":"transport","season":"winter"}'),
 (7, 2, N'The Ski Area',             N'Zermatt offers over 360 km of interconnected pistes linked to Cervinia in Italy, suitable for beginners through experts.', 38, N'{"topic":"skiing","season":"winter"}'),
 (7, 3, N'Summer Skiing',            N'Thanks to the glacier, Zermatt is one of the few resorts offering summer skiing on the Theodul glacier.', 34, N'{"topic":"skiing","season":"summer"}'),
 (7, 4, N'Family Skiing',            N'The Sunnegga and Wolli kids'' areas offer gentle nursery slopes and ski school, and many hotels provide a pool and kids club for downtime.', 44, N'{"topic":"family","season":"winter"}'),
 (7, 5, N'Non-Ski Activities',       N'Ride the Gornergrat railway or the Matterhorn Glacier Paradise cable car for panoramic views, or walk the winter hiking trails.', 40, N'{"topic":"sights","season":"winter"}'),
 (7, 6, N'Après-Ski',                N'Zermatt has a lively après-ski scene of mountain bars and fine dining, with fondue and raclette a local staple.', 38, N'{"topic":"food","season":"winter"}'),
 (7, 7, N'Where to Stay',            N'Choose ski-in ski-out resorts near the lifts for convenience, or self-catering chalets in Winkelmatten for a quieter, family stay.', 40, N'{"topic":"lodging","season":"winter"}');

-- Doc 8: Marrakech Medina Guide (6 chunks) -------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (8, 1, N'The Medina',               N'Marrakech''s walled medina is a labyrinth of souks selling spices, lanterns, leather and textiles. Expect to haggle and get pleasantly lost.', 42, N'{"topic":"neighborhoods","season":"any"}'),
 (8, 2, N'Jemaa el-Fnaa',            N'The main square comes alive at night with food stalls, musicians and storytellers; sample grilled meats and fresh orange juice.', 40, N'{"topic":"food","season":"any"}'),
 (8, 3, N'Palaces and Gardens',      N'Visit the Bahia Palace, the Saadian Tombs and the tranquil Majorelle Garden once owned by Yves Saint Laurent.', 38, N'{"topic":"sights","season":"any"}'),
 (8, 4, N'Staying in a Riad',        N'Traditional riads offer courtyard calm and rooftop terraces hidden behind plain medina walls; many include a small pool or hammam.', 42, N'{"topic":"lodging","season":"any"}'),
 (8, 5, N'Best Season',              N'Spring and autumn are pleasant; summer is very hot, and desert excursions are best in the cooler months.', 36, N'{"topic":"seasonality","season":"spring"}'),
 (8, 6, N'Etiquette',               N'Dress modestly, ask before photographing people, and agree taxi fares or use the meter before you set off.', 36, N'{"topic":"etiquette","season":"any"}');

-- Doc 9: Banff National Park Guide (6 chunks) ----------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (9, 1, N'Park Basics',              N'Banff is Canada''s oldest national park in the Alberta Rockies. A Parks Canada pass is required and can be bought online or at the gate.', 44, N'{"topic":"logistics","season":"any"}'),
 (9, 2, N'Lakes',                    N'Lake Louise and Moraine Lake glow turquoise in summer from glacial rock flour; arrive at dawn or use the shuttle as parking fills fast.', 44, N'{"topic":"sights","season":"summer"}'),
 (9, 3, N'Hiking',                   N'Popular trails include Johnston Canyon, Plain of Six Glaciers and Sulphur Mountain, which is also reachable by gondola.', 38, N'{"topic":"adventure","season":"summer"}'),
 (9, 4, N'Winter',                   N'In winter, ski at Sunshine Village and Lake Louise resort, walk the frozen canyon ice, or skate on Lake Louise.', 40, N'{"topic":"skiing","season":"winter"}'),
 (9, 5, N'Wildlife',                 N'Elk, bighorn sheep, and occasionally bears are seen along the Bow Valley Parkway; keep a safe distance and carry bear spray on trails.', 42, N'{"topic":"wildlife","season":"summer"}'),
 (9, 6, N'Family Tips',              N'Family-friendly options include the Banff Gondola, canoeing on Lake Louise, and easy lakeshore walks suitable for all ages.', 38, N'{"topic":"family","season":"any"}');

-- Doc 10: Lisbon Neighborhood Guide (6 chunks) ---------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (10, 1, N'Alfama',                  N'Alfama is Lisbon''s oldest district, a warren of steep alleys, fado houses and viewpoints, best reached on the vintage tram 28.', 42, N'{"topic":"neighborhoods","season":"any"}'),
 (10, 2, N'Belem',                   N'Belem is home to the Jeronimos Monastery, the Belem Tower, and the original pasteis de nata custard tarts.', 38, N'{"topic":"sights","season":"any"}'),
 (10, 3, N'Baixa and Chiado',        N'The downtown Baixa grid and elegant Chiado offer grand squares, shopping and the Santa Justa lift.', 34, N'{"topic":"neighborhoods","season":"any"}'),
 (10, 4, N'Food',                    N'Beyond custard tarts, try grilled sardines, bacalhau salt cod dishes and a glass of ginjinha cherry liqueur.', 38, N'{"topic":"food","season":"any"}'),
 (10, 5, N'Day Trip to Sintra',      N'Sintra, 40 minutes by train, dazzles with the colorful Pena Palace, Quinta da Regaleira and forested hills.', 38, N'{"topic":"day-trips","season":"any"}'),
 (10, 6, N'Getting Around',          N'Lisbon is hilly; use trams, funiculars and the metro, and wear comfortable shoes for the cobblestone streets.', 36, N'{"topic":"transport","season":"any"}');

-- Doc 11: Cape Town Highlights (6 chunks) --------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (11, 1, N'Table Mountain',          N'Table Mountain dominates the city; ride the rotating cable car or hike Platteklip Gorge for sweeping views, weather permitting.', 40, N'{"topic":"sights","season":"summer"}'),
 (11, 2, N'Cape Peninsula',          N'Drive to the Cape of Good Hope and Cape Point, stopping at the Boulders Beach African penguin colony along the way.', 40, N'{"topic":"sights","season":"any"}'),
 (11, 3, N'Winelands',               N'The nearby Stellenbosch and Franschhoek valleys offer world-class wine tasting and Cape Dutch architecture.', 34, N'{"topic":"food","season":"any"}'),
 (11, 4, N'Beaches',                 N'Camps Bay and Clifton offer white sand and sunsets, though the Atlantic water stays cold year round.', 36, N'{"topic":"beaches","season":"summer"}'),
 (11, 5, N'Best Season',             N'The dry summer from November to March is ideal for beaches and hiking; winter is greener but wetter and windier.', 40, N'{"topic":"seasonality","season":"summer"}'),
 (11, 6, N'Safety',                  N'Use ride-hailing at night, avoid displaying valuables, and heed local advice about which areas to avoid after dark.', 38, N'{"topic":"safety","season":"any"}');

-- Doc 12: Tokyo First-Timer FAQ (7 chunks) -------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (12, 1, N'Airports',                N'Tokyo has two airports: Narita, about 60 km east, and Haneda, closer to the city. Both connect by train and limousine bus.', 42, N'{"topic":"transport","season":"any"}'),
 (12, 2, N'Getting Around',          N'The JR Yamanote loop line and the metro cover the city efficiently; a Suica or Pasmo IC card works across all transit.', 42, N'{"topic":"transport","season":"any"}'),
 (12, 3, N'When to Visit',           N'Spring cherry blossoms and autumn foliage are the most popular seasons; summers are hot and humid, winters mild and dry.', 40, N'{"topic":"seasonality","season":"spring"}'),
 (12, 4, N'Neighborhoods',           N'Shibuya and Shinjuku are for nightlife and shopping, Asakusa and Ueno for tradition, and Akihabara for electronics and anime.', 40, N'{"topic":"neighborhoods","season":"any"}'),
 (12, 5, N'Cash or Card',            N'Cards are widely accepted but carry some cash for small shops and shrines; convenience-store ATMs accept foreign cards.', 40, N'{"topic":"logistics","season":"any"}'),
 (12, 6, N'Etiquette',               N'Do not eat while walking, stay quiet on trains, and stand on the correct side of the escalator, which varies by city.', 42, N'{"topic":"etiquette","season":"any"}'),
 (12, 7, N'Day Trips',               N'Popular day trips include Nikko''s shrines, Kamakura''s Great Buddha, Hakone''s hot springs, and views of Mount Fuji.', 38, N'{"topic":"day-trips","season":"any"}');

-- Doc 13: Rome Ancient Sites (6 chunks) ----------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (13, 1, N'The Colosseum',           N'The Colosseum is Rome''s iconic amphitheater; book a combined ticket with the Roman Forum and Palatine Hill, ideally with skip-the-line access.', 44, N'{"topic":"sights","season":"any"}'),
 (13, 2, N'Roman Forum',             N'The Forum was the political and social heart of ancient Rome; wander the ruins of temples, basilicas and the Via Sacra.', 40, N'{"topic":"sights","season":"any"}'),
 (13, 3, N'Pantheon',                N'The remarkably preserved Pantheon features the world''s largest unreinforced concrete dome and a central oculus open to the sky.', 40, N'{"topic":"sights","season":"any"}'),
 (13, 4, N'Vatican',                 N'Vatican City holds St Peter''s Basilica and the Vatican Museums with the Sistine Chapel; dress modestly and book ahead.', 40, N'{"topic":"sights","season":"any"}'),
 (13, 5, N'Best Time',               N'Spring and autumn bring mild weather and manageable crowds; summer is hot and packed, and August sees many closures.', 40, N'{"topic":"seasonality","season":"spring"}'),
 (13, 6, N'Getting Around',          N'Rome''s historic center is walkable; the metro is limited by archaeology, so buses and taxis fill the gaps.', 36, N'{"topic":"transport","season":"any"}');

-- Doc 14: Paris Family Travel (6 chunks) ---------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (14, 1, N'Family Highlights',       N'Paris is very family-friendly, with the Eiffel Tower, boat trips on the Seine, and the science museum at Cite des Enfants.', 42, N'{"topic":"family","season":"any"}'),
 (14, 2, N'Parks',                   N'The Luxembourg Gardens and Jardin des Plantes offer playgrounds, puppet shows, pony rides and space to run.', 38, N'{"topic":"family","season":"any"}'),
 (14, 3, N'Disneyland Paris',        N'Disneyland Paris is a 40-minute RER train ride east of the city and makes an easy full-day family excursion.', 38, N'{"topic":"family","season":"any"}'),
 (14, 4, N'Museums for Kids',        N'Many museums, including the Louvre, offer family trails and are free for children; visit early to avoid queues.', 38, N'{"topic":"sights","season":"any"}'),
 (14, 5, N'Getting Around',          N'The metro is fast but has many stairs; strollers may prefer buses, and older children enjoy the Batobus river shuttle.', 40, N'{"topic":"transport","season":"any"}'),
 (14, 6, N'Where to Stay',           N'Family apartments with connecting rooms and kitchens in Le Marais or the 7th give space and central access to sights.', 40, N'{"topic":"lodging","season":"any"}');

-- Doc 15: Booking and Cancellation Policy (6 chunks) ---------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (15, 1, N'Reservations',            N'A booking is confirmed once payment or a valid card guarantee is received and you have an email confirmation number.', 38, N'{"topic":"policy","season":"any"}'),
 (15, 2, N'Free Cancellation',       N'Most properties offer free cancellation up to 48 hours before check-in; the exact window is shown on the rate at booking.', 40, N'{"topic":"policy","season":"any"}'),
 (15, 3, N'Late Cancellation',       N'Cancellations inside the free window are charged the first night; no-shows may be charged the full stay.', 38, N'{"topic":"policy","season":"any"}'),
 (15, 4, N'Refunds',                 N'Eligible refunds are returned to the original payment method within 5 to 10 business days of cancellation.', 36, N'{"topic":"policy","season":"any"}'),
 (15, 5, N'Modifications',           N'Date or occupancy changes are subject to availability and any rate difference; contact support before the cancellation window closes.', 40, N'{"topic":"policy","season":"any"}'),
 (15, 6, N'Activities',              N'Tours and activities may have stricter, non-refundable policies due to operator terms; check each activity''s conditions.', 38, N'{"topic":"policy","season":"any"}');

-- Doc 16: Travel Insurance FAQ (6 chunks) --------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (16, 1, N'Do I Need It',            N'Travel insurance is optional but strongly recommended to cover trip cancellation, medical emergencies and lost baggage.', 38, N'{"topic":"insurance","season":"any"}'),
 (16, 2, N'Medical Cover',           N'Medical coverage pays for emergency treatment abroad and, if needed, evacuation; check that your activities are included.', 40, N'{"topic":"insurance","season":"any"}'),
 (16, 3, N'Cancellation Cover',      N'Trip cancellation reimburses prepaid, non-refundable costs if you must cancel for a covered reason such as illness.', 40, N'{"topic":"insurance","season":"any"}'),
 (16, 4, N'Adventure Sports',        N'Activities like bungy, skiing and high-altitude trekking often require an add-on; declare them when you buy the policy.', 42, N'{"topic":"insurance","season":"any"}'),
 (16, 5, N'Claims',                  N'Keep receipts, police reports and medical records; most insurers require claims within a set number of days of the incident.', 42, N'{"topic":"insurance","season":"any"}'),
 (16, 6, N'When to Buy',             N'Buy insurance soon after booking so cancellation cover applies from the earliest date and pre-existing waivers may qualify.', 40, N'{"topic":"insurance","season":"any"}');

-- Doc 17: Machu Picchu Trek Guide (7 chunks) -----------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (17, 1, N'Overview',                N'Machu Picchu sits at 2,430 m in the Andes above the Sacred Valley, reached by the classic Inca Trail trek or by train from Cusco.', 44, N'{"topic":"overview","season":"dry season"}'),
 (17, 2, N'The Inca Trail',          N'The classic Inca Trail is a four-day guided trek over high passes ending at the Sun Gate; permits are limited and sell out months ahead.', 46, N'{"topic":"adventure","season":"dry season"}'),
 (17, 3, N'Altitude',                N'Spend two or three days acclimatizing in Cusco or the Sacred Valley before trekking to reduce altitude sickness risk.', 40, N'{"topic":"health","season":"any"}'),
 (17, 4, N'By Train',                N'Non-trekkers take a scenic train from Ollantaytambo to Aguas Calientes, then a shuttle bus up to the citadel.', 40, N'{"topic":"transport","season":"any"}'),
 (17, 5, N'Best Season',             N'The dry season from May to September offers the clearest weather; the trail closes each February for maintenance.', 40, N'{"topic":"seasonality","season":"dry season"}'),
 (17, 6, N'Tickets',                 N'Entry is by timed ticket on set circuits; book official tickets early and bring your passport, which is stamped on site.', 42, N'{"topic":"logistics","season":"any"}'),
 (17, 7, N'What to Pack',            N'Bring layers, rain gear, sturdy boots, sun protection and cash for the bus; large backpacks are not allowed inside.', 40, N'{"topic":"logistics","season":"any"}');

-- Doc 18: Serengeti Safari Guide (7 chunks) ------------------------------------
INSERT INTO dbo.DocumentChunks (doc_id, ordinal, section_path, content, token_count, metadata) VALUES
 (18, 1, N'Overview',                N'The Serengeti in Tanzania is a vast savanna famous for the Big Five and the annual Great Migration of wildebeest and zebra.', 42, N'{"topic":"overview","season":"dry season"}'),
 (18, 2, N'The Great Migration',     N'The migration circles the ecosystem year round; dramatic river crossings typically occur in the northern Serengeti from July to October.', 44, N'{"topic":"wildlife","season":"dry season"}'),
 (18, 3, N'Best Season',             N'The dry season from June to October concentrates wildlife around water and offers the best game viewing and clear roads.', 42, N'{"topic":"seasonality","season":"dry season"}'),
 (18, 4, N'Game Drives',             N'Morning and late-afternoon game drives in open 4x4 vehicles maximize sightings; a knowledgeable guide is essential.', 40, N'{"topic":"wildlife","season":"any"}'),
 (18, 5, N'Getting There',           N'Fly into Kilimanjaro, then take a light aircraft to a Serengeti airstrip near your camp to save long drive times.', 42, N'{"topic":"transport","season":"any"}'),
 (18, 6, N'Where to Stay',           N'Options range from permanent lodges to mobile tented camps that follow the migration; book premium camps far in advance.', 42, N'{"topic":"lodging","season":"any"}'),
 (18, 7, N'What to Pack',            N'Pack neutral clothing, a hat, binoculars, a long camera lens and layers for chilly early-morning drives.', 40, N'{"topic":"logistics","season":"any"}');
GO


/*==============================================================================
  9. VERIFICATION  (row counts + confirm all vectors are NULL, ready to embed)
==============================================================================*/
SELECT 'Destinations'       AS table_name, COUNT(*) AS row_count FROM dbo.Destinations
UNION ALL SELECT 'Properties',        COUNT(*) FROM dbo.Properties
UNION ALL SELECT 'Activities',        COUNT(*) FROM dbo.Activities
UNION ALL SELECT 'Travelers',         COUNT(*) FROM dbo.Travelers
UNION ALL SELECT 'Reviews',           COUNT(*) FROM dbo.Reviews
UNION ALL SELECT 'Bookings',          COUNT(*) FROM dbo.Bookings
UNION ALL SELECT 'KnowledgeDocuments',COUNT(*) FROM dbo.KnowledgeDocuments
UNION ALL SELECT 'DocumentChunks',    COUNT(*) FROM dbo.DocumentChunks;

-- Should show 117 chunks, all content_vector NULL (embed procs will populate).
SELECT
    total_chunks   = COUNT(*),
    unembedded     = SUM(CASE WHEN content_vector IS NULL THEN 1 ELSE 0 END)
FROM dbo.DocumentChunks;

PRINT 'Seed data loaded. Next: run the Bedrock embedding procs:';
PRINT '  EXEC dbo.usp_EmbedDocumentChunks @batch_size = 200;  -- repeat until it returns 0';
PRINT '  EXEC dbo.usp_EmbedProperties     @batch_size = 200;  -- repeat until it returns 0';
GO
