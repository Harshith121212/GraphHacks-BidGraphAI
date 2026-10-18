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
            if settings.FALKORDB_URL:
                self._client = FalkorDB.from_url(settings.FALKORDB_URL)
            else:
                connection_kwargs = {
                    "host": settings.FALKORDB_HOST,
                    "port": settings.FALKORDB_PORT,
                }
                if settings.FALKORDB_USERNAME:
                    connection_kwargs["username"] = settings.FALKORDB_USERNAME
                if settings.FALKORDB_PASSWORD:
                    connection_kwargs["password"] = settings.FALKORDB_PASSWORD

                if settings.FALKORDB_SSL:
                    connection_kwargs["ssl"] = True
                    # Default to strict verification first
                    if getattr(settings, "FALKORDB_SSL_VERIFY", True):
                        strict_kwargs = dict(connection_kwargs)
                        strict_kwargs["ssl_cert_reqs"] = "required"
                        strict_kwargs["ssl_check_hostname"] = True
                        strict_kwargs["socket_connect_timeout"] = 3.0
                        try:
                            candidate_client = FalkorDB(**strict_kwargs)
                            candidate_client.connection.ping()
                            self._client = candidate_client
                            return self._client
                        except Exception as exc:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(
                                "Strict TLS certificate/hostname verification failed for %s (%s). "
                                "Falling back to encrypted TLS without hostname verification as documented in docs/SECURITY.md.",
                                settings.FALKORDB_HOST, exc
                            )
                    connection_kwargs["ssl_cert_reqs"] = None
                    connection_kwargs["ssl_check_hostname"] = False

                self._client = FalkorDB(**connection_kwargs)
        return self._client

    def get_graph(self, graph_name: Optional[str] = None) -> Graph:
        import os
        settings = get_settings()
        target_name = graph_name or os.getenv("FALKORDB_GRAPH_NAME") or settings.FALKORDB_GRAPH_NAME
        client = self.get_client()
        return client.select_graph(target_name)

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.connection.close()
            except Exception:
                pass
            self._client = None

    def reset_client(self) -> None:
        """Force-close and reset the cached client connection (useful when switching hosts)."""
        self.close()


def get_db() -> FalkorDB:
    """Return the FalkorDB client singleton."""
    return FalkorDBConnection.get_instance().get_client()


def get_graph(graph_name: Optional[str] = None) -> Graph:
    """Return a selected Graph from the FalkorDB client singleton."""
    return FalkorDBConnection.get_instance().get_graph(graph_name)


def reset_connection() -> None:
    """Reset the singleton connection to reconnect with updated settings."""
    from config import get_settings
    get_settings.cache_clear()
    FalkorDBConnection.get_instance().reset_client()


def test_connection(
    host: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    ssl: bool = False,
    url: Optional[str] = None,
) -> dict:
    """Test connection to a FalkorDB instance and return status with latency and graphs."""
    import time
    settings = get_settings()
    target_host = host or settings.FALKORDB_HOST
    target_port = port or settings.FALKORDB_PORT
    target_user = username if username is not None else settings.FALKORDB_USERNAME
    target_pass = password if password is not None else settings.FALKORDB_PASSWORD
    target_ssl = ssl if ssl is not None else settings.FALKORDB_SSL
    target_url = url or settings.FALKORDB_URL

    t0 = time.time()
    try:
        if target_url:
            test_client = FalkorDB.from_url(target_url)
        else:
            kwargs = {
                "host": target_host,
                "port": target_port,
            }
            if target_user:
                kwargs["username"] = target_user
            if target_pass:
                kwargs["password"] = target_pass
            if target_ssl:
                kwargs["ssl"] = True
                kwargs["ssl_cert_reqs"] = None
                kwargs["ssl_check_hostname"] = False
            test_client = FalkorDB(**kwargs)

        graphs = test_client.list_graphs()
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        masked_host = target_host[:6] + "***" + target_host[-8:] if len(target_host) > 20 else target_host
        return {
            "status": "connected",
            "host": masked_host,
            "port": target_port,
            "ssl": target_ssl,
            "latency_ms": elapsed_ms,
            "graphs": graphs,
        }
    except Exception as exc:
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        masked_host = target_host[:6] + "***" + target_host[-8:] if len(target_host) > 20 else target_host
        return {
            "status": "error",
            "host": masked_host,
            "port": target_port,
            "ssl": target_ssl,
            "latency_ms": elapsed_ms,
            "error": "Failed to connect to FalkorDB instance",
        }

