from __future__ import annotations

from typing import Callable

from fastapi import APIRouter
from fastapi.datastructures import DefaultPlaceholder
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute, APIWebSocketRoute


def _v1_path(path: str) -> str:
    if path.startswith("/api/"):
        return path[4:]
    if path == "/api":
        return "/"
    return path


def bridge_fastapi_routes(
    source_app,
    versioned_router: APIRouter,
    compatibility_router: APIRouter,
    include_path: Callable[[str], bool],
) -> None:
    seen_versioned: set[tuple[str, tuple[str, ...]]] = set()
    seen_compat: set[tuple[str, tuple[str, ...]]] = set()

    for route in source_app.routes:
        if isinstance(route, APIRoute):
            if not include_path(route.path):
                continue

            response_class = route.response_class
            if isinstance(response_class, DefaultPlaceholder):
                response_class = response_class.value
            if not response_class:
                response_class = getattr(source_app, "default_response_class", None) or JSONResponse
            methods = sorted(list(route.methods or []))
            methods_key = tuple(methods)
            compat_key = (route.path, methods_key)
            v1_key = (_v1_path(route.path), methods_key)

            if compat_key not in seen_compat:
                compatibility_router.add_api_route(
                    route.path,
                    route.endpoint,
                    methods=methods,
                    name=f"legacy_{route.name}",
                    response_model=route.response_model,
                    status_code=route.status_code,
                    responses=route.responses,
                    response_class=response_class,
                    response_model_exclude_unset=route.response_model_exclude_unset,
                    response_model_exclude_defaults=route.response_model_exclude_defaults,
                    response_model_exclude_none=route.response_model_exclude_none,
                    include_in_schema=False,
                )
                seen_compat.add(compat_key)

            if v1_key not in seen_versioned:
                versioned_router.add_api_route(
                    _v1_path(route.path),
                    route.endpoint,
                    methods=methods,
                    name=f"v1_{route.name}",
                    response_model=route.response_model,
                    status_code=route.status_code,
                    responses=route.responses,
                    response_class=response_class,
                    response_model_exclude_unset=route.response_model_exclude_unset,
                    response_model_exclude_defaults=route.response_model_exclude_defaults,
                    response_model_exclude_none=route.response_model_exclude_none,
                    tags=route.tags,
                    summary=route.summary,
                    description=route.description,
                    deprecated=route.deprecated,
                )
                seen_versioned.add(v1_key)

        if isinstance(route, APIWebSocketRoute):
            if not include_path(route.path):
                continue
            compatibility_router.add_api_websocket_route(route.path, route.endpoint)
            versioned_router.add_api_websocket_route(_v1_path(route.path), route.endpoint)
