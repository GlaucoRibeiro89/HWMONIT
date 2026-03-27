#!/usr/bin/python3
# -*- coding: utf8 -*-

import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, status
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


def log_json(message: str, **kwargs):
    payload = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "service": "collector-api",
        "message": message,
    }
    payload.update(kwargs)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


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

    log_json(
        "collect_request_received",
        ip=ip,
        endpoint="/collect",
        method="POST",
        status="received",
    )

    try:
        token = enqueue_collect(ip)

        log_json(
            "collect_request_accepted",
            ip=ip,
            endpoint="/collect",
            method="POST",
            status="accepted",
            token=token,
        )

    except RuntimeError as e:
        log_json(
            "collect_request_conflict",
            ip=ip,
            endpoint="/collect",
            method="POST",
            status="conflict",
            error=str(e),
        )
        raise HTTPException(status_code=409, detail=str(e))

    except Exception as e:
        log_json(
            "collect_request_error",
            ip=ip,
            endpoint="/collect",
            method="POST",
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))

    background_tasks.add_task(run_collection_job, ip, token)

    return {
        "success": True,
        "message": "Coleta aceita para execução em segundo plano",
        "ip": ip,
        "status": "accepted",
    }