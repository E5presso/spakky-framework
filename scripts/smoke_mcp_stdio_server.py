"""Small external MCP stdio server used by real-world protocol smoke tests."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("weather-smoke")


@server.tool()
def forecast(city: str) -> str:
    """Return a deterministic weather forecast."""
    return f"sunny in {city}"


@server.tool()
def join(args: list[str]) -> str:
    """Return joined arguments, including the reserved MCP field name case."""
    return ",".join(args)


if __name__ == "__main__":
    server.run("stdio")
