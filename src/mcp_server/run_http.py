import uvicorn
from fastapi.staticfiles import StaticFiles
from mcp_server.server import mcp
import os

# 尝试获取 underlying FastAPI app
# FastMCP 可能将 app 存储在 internal attributes 中
app = None
if hasattr(mcp, "_fastapi_app"):
    app = mcp._fastapi_app
elif hasattr(mcp, "fastapi_app"):
    app = mcp.fastapi_app
elif hasattr(mcp, "_app"):
    app = mcp._app

if app:
    # 挂载图片缓存目录
    # 假设运行目录在项目根目录
    cache_dir = os.path.join("output", "cache", "images")
    if os.path.exists(cache_dir):
        app.mount("/images", StaticFiles(directory=cache_dir), name="images")
        print(f"挂载静态目录: /images -> {cache_dir}")
    else:
        print(f"缓存目录不存在，跳过挂载: {cache_dir}")
else:
    print("Warning: Could not find FastAPI app in mcp object")

if __name__ == "__main__":
    # 直接运行
    if app:
        print("Starting custom MCP server with static files...")
        uvicorn.run(app, host="0.0.0.0", port=3333)
    else:
        # Fallback to mcp.run if app extraction failed
        print("Fallback to standard mcp.run...")
        mcp.run(transport="sse")
