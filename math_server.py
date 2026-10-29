from mcp.server.fastmcp import FastMCP

server = FastMCP("mini-math")

@server.tool()
def multiply(a: int, b: int) -> int:
    """计算两个整数的乘积。"""
    return a * b

if __name__ == "__main__":
    server.run(transport="stdio")
