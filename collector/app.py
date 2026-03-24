#!/usr/bin/python3
# -*- coding: utf8 -*-

from fastapi import FastAPI, HTTPException, BackgroundTasks, Response, status
from pydantic import BaseModel, IPvAnyAddress
from collector.collector_service import (
    enqueue_collect,
    get_collect_state,
    run_collection_job,
)

app = FastAPI(
    title="HWMonit Collector",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class CollectRequest(BaseModel):
    ip: IPvAnyAddress


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/state/{ip}")
def state(ip: str):
    result = get_collect_state(ip)
    if not result:
        raise HTTPException(status_code=404, detail="OLT não encontrada no estado de coleta")
    return result


@app.post("/collect", status_code=status.HTTP_202_ACCEPTED)
def collect(payload: CollectRequest, background_tasks: BackgroundTasks):
    ip = str(payload.ip)

    try:
        token = enqueue_collect(ip)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    background_tasks.add_task(run_collection_job, ip, token)

    return {
        "success": True,
        "message": "Coleta aceita para execução em segundo plano",
        "ip": ip,
        "status": "accepted",
    }
