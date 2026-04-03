"""Minimal demo API gateway service.

This entrypoint satisfies the demo deployment Docker image contract and exposes
an HTTP health endpoint for orchestrators.
"""

from aiohttp import web


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "healthy", "service": "api-gateway"})


async def root(_request: web.Request) -> web.Response:
    return web.json_response({"message": "Demo API gateway is running"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=8080)
