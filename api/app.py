import os
import ipaddress
from collections import defaultdict

import pymysql
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="hwmonit_api", version="1.0.0")


def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "hwmonit_db"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "hwmonit"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def validate_ip(ip: str) -> str:
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"IP inválido: {ip}") from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/discovery/ports")
def discovery_ports(ip: str = Query(..., description="IP da OLT")):
    olt_ip = validate_ip(ip)

    sql = """
        SELECT DISTINCT port
        FROM ont_status
        WHERE ip = %s
          AND port IS NOT NULL
          AND port <> ''
        ORDER BY port
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (olt_ip,))
                rows = cursor.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar banco: {exc}") from exc

    data = []
    for row in rows:
        port = row["port"].strip()
        parts = port.split("/")

        frame = parts[0] if len(parts) > 0 else ""
        slot = parts[1] if len(parts) > 1 else ""
        pon = parts[2] if len(parts) > 2 else ""

        data.append(
            {
                "{#PORT}": port,
                "{#FRAME}": frame,
                "{#SLOT}": slot,
                "{#PON}": pon,
            }
        )

    return JSONResponse(content={"data": data})


@app.get("/api/v1/summary/olt")
def olt_summary(ip: str = Query(..., description="IP da OLT")):
    olt_ip = validate_ip(ip)

    sql = """
        SELECT
            port,
            run_state,
            last_down_cause,
            rx_power_dbm
        FROM ont_status
        WHERE ip = %s
          AND port IS NOT NULL
          AND port <> ''
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (olt_ip,))
                rows = cursor.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar banco: {exc}") from exc

    slot_stats = defaultdict(lambda: {
        "slot_path": "",
        "frame": "",
        "slot": "",
        "ont_total": 0,
        "ont_online": 0,
        "ont_offline": 0,
        "ont_loss": 0,
        "dbm_sum": 0.0,
        "dbm_count": 0,
    })

    pon_stats = defaultdict(lambda: {
        "port": "",
        "frame": "",
        "slot": "",
        "pon": "",
        "ont_total": 0,
        "ont_online": 0,
        "ont_offline": 0,
        "ont_loss": 0,
        "dbm_sum": 0.0,
        "dbm_count": 0,
    })

    for row in rows:
        port = (row.get("port") or "").strip()
        if not port:
            continue

        parts = port.split("/")
        if len(parts) < 3:
            continue

        frame = parts[0]
        slot = parts[1]
        pon = parts[2]
        slot_path = f"{frame}/{slot}"

        run_state = (row.get("run_state") or "").strip().lower()
        last_down_cause = (row.get("last_down_cause") or "").upper()
        rx_power_dbm = row.get("rx_power_dbm")

        is_online = run_state == "online"
        is_offline = run_state == "offline"
        is_loss = is_offline and ("LOS" in last_down_cause)

        # agrega por slot
        s = slot_stats[slot_path]
        s["slot_path"] = slot_path
        s["frame"] = frame
        s["slot"] = slot
        s["ont_total"] += 1

        if is_online:
            s["ont_online"] += 1
        if is_offline:
            s["ont_offline"] += 1
        if is_loss:
            s["ont_loss"] += 1

        if rx_power_dbm is not None:
            s["dbm_sum"] += float(rx_power_dbm)
            s["dbm_count"] += 1

        # agrega por pon
        p = pon_stats[port]
        p["port"] = port
        p["frame"] = frame
        p["slot"] = slot
        p["pon"] = pon
        p["ont_total"] += 1

        if is_online:
            p["ont_online"] += 1
        if is_offline:
            p["ont_offline"] += 1
        if is_loss:
            p["ont_loss"] += 1

        if rx_power_dbm is not None:
            p["dbm_sum"] += float(rx_power_dbm)
            p["dbm_count"] += 1

    def sort_key_slot(item):
        frame = int(item["frame"]) if str(item["frame"]).isdigit() else 0
        slot = int(item["slot"]) if str(item["slot"]).isdigit() else 0
        return (frame, slot)

    def sort_key_pon(item):
        frame = int(item["frame"]) if str(item["frame"]).isdigit() else 0
        slot = int(item["slot"]) if str(item["slot"]).isdigit() else 0
        pon = int(item["pon"]) if str(item["pon"]).isdigit() else 0
        return (frame, slot, pon)

    slots = []
    for item in sorted(slot_stats.values(), key=sort_key_slot):
        avg_dbm = None
        if item["dbm_count"] > 0:
            avg_dbm = round(item["dbm_sum"] / item["dbm_count"], 2)

        slots.append({
            "slot_path": item["slot_path"],
            "frame": item["frame"],
            "slot": item["slot"],
            "ont_total": item["ont_total"],
            "ont_online": item["ont_online"],
            "ont_offline": item["ont_offline"],
            "ont_loss": item["ont_loss"],
            "avg_dbm": avg_dbm,
        })

    pons = []
    for item in sorted(pon_stats.values(), key=sort_key_pon):
        avg_dbm = None
        if item["dbm_count"] > 0:
            avg_dbm = round(item["dbm_sum"] / item["dbm_count"], 2)

        pons.append({
            "port": item["port"],
            "frame": item["frame"],
            "slot": item["slot"],
            "pon": item["pon"],
            "ont_total": item["ont_total"],
            "ont_online": item["ont_online"],
            "ont_offline": item["ont_offline"],
            "ont_loss": item["ont_loss"],
            "avg_dbm": avg_dbm,
        })

    return JSONResponse(content={
        "ip": olt_ip,
        "slots": slots,
        "pons": pons,
    })

@app.get("/api/v1/worst-power")
def worst_power_onts(
    ip: str = Query(..., description="IP da OLT"),
    limit: int = Query(10, ge=1, le=100, description="Quantidade de ONTs retornadas"),
):
    olt_ip = validate_ip(ip)

    sql = """
        SELECT
            sn,
            port,
            CAST(rx_power_dbm AS DECIMAL(10,2)) AS rx_power_dbm
        FROM ont_status
        WHERE ip = %s
          AND sn IS NOT NULL
          AND sn <> ''
          AND port IS NOT NULL
          AND port <> ''
          AND rx_power_dbm IS NOT NULL
          AND rx_power_dbm <> ''
          AND rx_power_dbm <> '-'
          AND rx_power_dbm REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
        ORDER BY CAST(rx_power_dbm AS DECIMAL(10,2)) ASC
        LIMIT %s
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (olt_ip, limit))
                rows = cursor.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar banco: {exc}") from exc

    data = []
    for row in rows:
        data.append(
            {
                "serial": row["sn"],
                "port": row["port"],
                "dbm": float(row["rx_power_dbm"]),
            }
        )

    return JSONResponse(
        content={
            "ip": olt_ip,
            "total": len(data),
            "onts": data,
        }
    )