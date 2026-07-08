import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient

load_dotenv()

client = QdrantClient(
    host=os.getenv("QDRANT_HOST"),
    port=6333
)

print(client.get_collections())