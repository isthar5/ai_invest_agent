from fastembed import TextEmbedding, SparseTextEmbedding
import asyncio

dense_model = TextEmbedding("BAAI/bge-small-zh-v1.5")
sparse_model = SparseTextEmbedding("Qdrant/bm25")

async def embed(query):
    loop = asyncio.get_event_loop()

    dense = await loop.run_in_executor(
        None, lambda: next(dense_model.query_embed(query)).tolist()
    )

    sparse = await loop.run_in_executor(
        None, lambda: next(sparse_model.query_embed(query)).as_object()
    )

    return dense, sparse