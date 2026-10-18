"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import ai, auth, datasets, graph, records, train

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(records.router)
api_router.include_router(graph.router)
api_router.include_router(datasets.router)
api_router.include_router(train.router)
api_router.include_router(ai.router)
