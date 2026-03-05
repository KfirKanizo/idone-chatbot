from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue
from app.config import settings
from loguru import logger


COLLECTION_NAME = "documents"


class VectorService:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                grpc_port=settings.qdrant_grpc_port,
            )
        return self._client

    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if COLLECTION_NAME not in collection_names:
                # Use 1024 for Cohere embeddings
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=1024,  # Cohere embed-english-v3.0 produces 1024 dimensions
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {COLLECTION_NAME} with 1024-dim vectors")
            else:
                logger.debug(f"Qdrant collection {COLLECTION_NAME} already exists")
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")

    def insert_vectors(
        self,
        tenant_id: str,
        document_id: str,
        chunks: List[str],
        vectors: List[List[float]]
    ) -> bool:
        try:
            if vectors:
                logger.info(f"Inserting {len(vectors)} vectors, dimension: {len(vectors[0]) if vectors else 'unknown'}")
            
            # Build points with proper format for qdrant-client 1.7.x
            points = []
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                points.append({
                    "id": f"{document_id}_{i}",
                    "vector": vector,
                    "payload": {
                        "tenant_id": tenant_id,
                        "document_id": document_id,
                        "chunk_index": i,
                        "text": chunk
                    }
                })
            
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points
            )
            
            logger.info(f"Inserted {len(points)} vectors for document {document_id}")
            return True
        except Exception as e:
            logger.error(f"Error inserting vectors: {e}")
            return False

    def search(
        self,
        tenant_id: str,
        query_vector: List[float],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        try:
            search_result = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=limit,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=tenant_id)
                        )
                    ]
                )
            )
            
            results = [
                {
                    "text": hit.payload.get("text", ""),
                    "document_id": hit.payload.get("document_id"),
                    "score": hit.score
                }
                for hit in search_result
            ]
            
            logger.debug(f"Found {len(results)} results for tenant {tenant_id}")
            return results
        except Exception as e:
            logger.error(f"Error searching vectors: {e}")
            return []

    def delete_by_document_id(self, tenant_id: str, document_id: str) -> bool:
        try:
            self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        ),
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=tenant_id)
                        )
                    ]
                )
            )
            logger.info(f"Deleted vectors for document {document_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors: {e}")
            return False

    def delete_by_tenant_id(self, tenant_id: str) -> bool:
        try:
            self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=tenant_id)
                        )
                    ]
                )
            )
            logger.warning(f"Deleted all vectors for tenant {tenant_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting tenant vectors: {e}")
            return False

    def get_collection_info(self) -> Dict[str, Any]:
        try:
            info = self.client.get_collection(collection_name=COLLECTION_NAME)
            return {
                "name": COLLECTION_NAME,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": str(info.status)
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}


vector_service = VectorService()
