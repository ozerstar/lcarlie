SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';

SELECT '[1,2,3]'::vector <-> '[3,2,1]'::vector AS l2_distance;

SELECT count(*) AS semantic_rows
FROM ai_semantic.memory_embedding;
