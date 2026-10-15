"""FalkorDB connection singleton supporting Local & FalkorDB Cloud."""

from typing import Optional
from falkordb import FalkorDB, Graph
from config import get_settings


class FalkorDBConnection:
    _instance: Optional["FalkorDBConnection"] = None
    _client: Optional[FalkorDB] = None

    def __new__(cls) -> "FalkorDBConnection":
        if cls._instance is None:
            cls._instance = super(FalkorDBConnection, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "FalkorDBConnection":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_client(self) -> FalkorDB:
        if self._client is None:
            settings = get_settings()
            connection_kwargs = {
                "host": settings.FALKORDB_HOST,
                "port": settings.FALKORDB_PORT,
            }
            if settings.FALKORDB_USERNAME:
                connection_kwargs["username"] = settings.FALKORDB_USERNAME
            if settings.FALKORDB_PASSWORD:
                connection_kwargs["password"] = settings.FALKORDB_PASSWORD

            self._client = FalkorDB(**connection_kwargs)
        return self._client

    def get_graph(self, graph_name: Optional[str] = None) -> Graph:
        settings = get_settings()
        target_name = graph_name or settings.FALKORDB_GRAPH_NAME
        client = self.get_client()
        return client.select_graph(target_name)

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.connection.close()
            except Exception:
                pass
            self._client = None


def get_db() -> FalkorDB:
    """Return the FalkorDB client singleton."""
    return FalkorDBConnection.get_instance().get_client()


def get_graph(graph_name: Optional[str] = None) -> Graph:
    """Return a selected Graph from the FalkorDB client singleton."""
    return FalkorDBConnection.get_instance().get_graph(graph_name)
