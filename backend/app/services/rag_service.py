from typing import List, Dict, Any, Optional
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_groq import ChatGroq
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from sqlalchemy import select, asc
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.services.vector_service import vector_service
from app.models import ChatHistory
from loguru import logger
import hashlib


class RAGService:
    def __init__(self):
        self.embeddings = HuggingFaceInferenceAPIEmbeddings(
            model_name="BAAI/bge-large-en-v1.5",
            api_key=settings.huggingface_api_key
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks for embedding"""
        chunks = self.text_splitter.split_text(text)
        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        try:
            import json
            embeddings = self.embeddings.embed_documents(texts)
            logger.info(f"Embeddings response type: {type(embeddings)}, len: {len(embeddings) if embeddings else 0}")
            if embeddings:
                logger.info(f"First embedding type: {type(embeddings[0])}, value preview: {str(embeddings[0])[:100]}")
            return embeddings
        except Exception as e:
            import traceback
            logger.error(f"Error generating embeddings: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def generate_query_embedding(self, query: str) -> List[float]:
        """Generate embedding for a query"""
        try:
            embedding = self.embeddings.embed_query(query)
            logger.info(f"Generated query embedding, dim: {len(embedding) if embedding else 'none'}")
            return embedding
        except Exception as e:
            logger.error(f"Error generating query embedding: {type(e).__name__}: {e}")
            raise

    async def ingest_document(
        self,
        tenant_id: str,
        document_id: str,
        text: str,
        filename: str
    ) -> Dict[str, Any]:
        """Ingest a document: chunk, embed, and store in vector DB"""
        try:
            chunks = self.chunk_text(text)
            
            if not chunks:
                return {
                    "success": False,
                    "chunks_created": 0,
                    "message": "No text content to ingest"
                }
            
            vectors = await self.generate_embeddings(chunks)
            
            success = vector_service.insert_vectors(
                tenant_id=tenant_id,
                document_id=document_id,
                chunks=chunks,
                vectors=vectors
            )
            
            if success:
                logger.info(f"Successfully ingested document {filename} for tenant {tenant_id}")
                return {
                    "success": True,
                    "chunks_created": len(chunks),
                    "message": f"Document ingested successfully with {len(chunks)} chunks"
                }
            else:
                return {
                    "success": False,
                    "chunks_created": 0,
                    "message": "Failed to store vectors in database"
                }
                
        except Exception as e:
            logger.error(f"Error ingesting document: {e}")
            return {
                "success": False,
                "chunks_created": 0,
                "message": str(e)
            }

    async def retrieve_context(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant context from vector DB with tenant isolation"""
        try:
            query_embedding = await self.generate_query_embedding(query)
            
            results = vector_service.search(
                tenant_id=tenant_id,
                query_vector=query_embedding,
                limit=top_k
            )
            
            logger.info(f"Retrieved {len(results)} context chunks for query")
            return results
            
        except Exception as e:
            logger.error(f"Error retrieving context: {e}")
            return []

    async def get_chat_history(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        limit: int = 5
    ) -> List[ChatHistory]:
        """Retrieve chat history for a specific user within a tenant with strict isolation"""
        try:
            result = await db.execute(
                select(ChatHistory)
                .where(ChatHistory.tenant_id == tenant_id)
                .where(ChatHistory.user_id == user_id)
                .order_by(asc(ChatHistory.created_at))
                .limit(limit * 2)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error retrieving chat history: {e}")
            return []

    def build_conversation_history(
        self,
        chat_history: List[ChatHistory]
    ) -> List:
        """Build LangChain message list from chat history in chronological order"""
        messages = []
        for chat in chat_history:
            messages.append(HumanMessage(content=chat.message))
            messages.append(AIMessage(content=chat.response))
        return messages

    def build_context_string(self, context_results: List[Dict[str, Any]]) -> str:
        """Build context string from retrieval results"""
        if not context_results:
            return ""
        
        context_parts = []
        for i, result in enumerate(context_results, 1):
            context_parts.append(f"[Context {i}]: {result['text']}")
        
        return "\n\n".join(context_parts)

    async def generate_response(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        user_message: str,
        system_prompt: str,
        llm_model: str,
        temperature: float,
        max_tokens: int,
        history_limit: int = 5
    ) -> Dict[str, Any]:
        """Generate LLM response with RAG context and conversation history"""
        try:
            context_results = await self.retrieve_context(tenant_id, user_message)
            context_string = self.build_context_string(context_results)
            
            messages = []
            
            messages.append(SystemMessage(content=system_prompt))
            
            if context_string:
                messages.append(SystemMessage(
                    content=f"Context Information:\n{context_string}\n\nUse this context to answer the user's question when relevant."
                ))
            
            chat_history = await self.get_chat_history(db, tenant_id, user_id, history_limit)
            if chat_history:
                history_messages = self.build_conversation_history(chat_history)
                messages.extend(history_messages)
                logger.info(f"Injected {len(chat_history)} past interactions into prompt for user {user_id}")
            
            messages.append(HumanMessage(content=user_message))
            
            llm = ChatGroq(
                model=settings.groq_model,
                temperature=temperature,
                max_tokens=max_tokens,
                groq_api_key=settings.groq_api_key
            )
            
            response = llm.invoke(messages)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            return {
                "response": response_text,
                "context_used": [r['text'] for r in context_results],
                "context_scores": [r['score'] for r in context_results],
                "history_used": len(chat_history) if chat_history else 0
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                "response": "I apologize, but I encountered an error processing your request.",
                "context_used": [],
                "context_scores": []
            }


rag_service = RAGService()
