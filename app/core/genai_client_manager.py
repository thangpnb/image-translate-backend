import asyncio
from typing import Dict
from google.genai import Client
from loguru import logger


class GenAIClientManager:
    """
    Centralized Google GenAI client manager with connection reuse.
    Maintains a pool of clients per API key to avoid creating new clients for each request.
    This improves performance by reusing connections and internal resources.
    """
    
    def __init__(self):
        self._clients: Dict[str, Client] = {}
        self._lock = asyncio.Lock()
    
    async def get_client(self, api_key: str) -> Client:
        """
        Get or create a GenAI client for the given API key.
        Reuses existing clients to leverage internal connection pooling.
        
        Args:
            api_key: The API key to create/get client for
            
        Returns:
            Client: A Google GenAI client instance
        """
        if api_key not in self._clients:
            async with self._lock:
                if api_key not in self._clients:
                    # Create client - GenAI SDK handles internal connection pooling
                    self._clients[api_key] = Client(api_key=api_key)
                    logger.debug(f"Created new GenAI client for key: {api_key[:8]}...")
        
        return self._clients[api_key]
    
    async def remove_client(self, api_key: str):
        """
        Remove a client from the pool (e.g., when an API key is invalidated).
        
        Args:
            api_key: The API key whose client should be removed
        """
        async with self._lock:
            if api_key in self._clients:
                del self._clients[api_key]
                logger.debug(f"Removed GenAI client for key: {api_key[:8]}...")
    
    async def close_all(self):
        """Close all clients and cleanup connections."""
        async with self._lock:
            client_count = len(self._clients)
            self._clients.clear()
            logger.info(f"Closed {client_count} GenAI clients")
    
    def get_client_count(self) -> int:
        """Get the number of active clients in the pool."""
        return len(self._clients)
    
    def get_client_keys(self) -> list[str]:
        """Get list of API key prefixes for active clients (for debugging)."""
        return [f"{key[:8]}..." for key in self._clients.keys()]
    
    async def health_check(self) -> bool:
        """Check if the client manager is healthy."""
        try:
            return True  # Always healthy if initialized
        except Exception as e:
            logger.error(f"GenAI client manager health check failed: {e}")
            return False


# Global GenAI client manager instance
genai_client_manager = GenAIClientManager()


async def get_genai_client(api_key: str) -> Client:
    """
    Get a GenAI client for the given API key.
    Uses the global client manager to reuse connections and avoid creating new clients.
    
    Args:
        api_key: The API key to get client for
        
    Returns:
        Client: A Google GenAI client instance
    """
    return await genai_client_manager.get_client(api_key)


async def remove_genai_client(api_key: str):
    """
    Remove a GenAI client from the pool.
    Useful when an API key becomes invalid or rate-limited.
    
    Args:
        api_key: The API key whose client should be removed
    """
    await genai_client_manager.remove_client(api_key)