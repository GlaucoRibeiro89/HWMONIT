#!/usr/bin/python3
# -*- coding: utf8 -*-

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import mysql.connector
from mysql.connector import MySQLConnection
from netmiko import ConnectHandler


# CONFIG MYSQL
mysqlConfig = {
    "ip": os.getenv("DB_HOST", "mysql"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "db": os.getenv("DB_NAME", "hwmonit"),
    "user": os.getenv("DB_USER", "hwmonit"),
    "pw": os.getenv("DB_PASSWORD", "hwmonit123"),
}

EMPTY_PON_SENTINEL_ONT_ID = int(os.getenv("EMPTY_PON_SENTINEL_ONT_ID", "65535"))

DB_RETRY_ATTEMPTS = int(os.getenv("DB_RETRY_ATTEMPTS", "4"))
DB_RETRY_BASE_SECONDS = float(os.getenv("DB_RETRY_BASE_SECONDS", "2"))
DB_LOCK_WAIT_TIMEOUT = int(os.getenv("DB_LOCK_WAIT_TIMEOUT", "60"))
DB_NAMED_LOCK_TIMEOUT = int(os.getenv("DB_NAMED_LOCK_TIMEOUT", "20"))
DB_UPSERT_CHUNK_SIZE = int(os.getenv("DB_UPSERT_CHUNK_SIZE", "500"))

OLT_READ_TIMEOUT = float(os.getenv("OLT_READ_TIMEOUT", "120"))
OLT_LAST_READ = float(os.getenv("OLT_LAST_READ", "2"))
OLT_CMD_RETRIES = int(os.getenv("OLT_CMD_RETRIES", "3"))
OLT_CMD_RETRY_SLEEP = float(os.getenv("OLT_CMD_RETRY_SLEEP", "2"))
OLT_CONNECT_RETRIES = int(os.getenv("OLT_CONNECT_RETRIES", "2"))
OLT_CONNECT_RETRY_SLEEP = float(os.getenv("OLT_CONNECT_RETRY_SLEEP", "3"))
OLT_SESSION_LOG_DIR = os.getenv("OLT_SESSION_LOG_DIR", "").strip()


def get_db() -> MySQLConnection:
    return mysql.connector.connect(
        host=mysqlConfig["ip"],
        port=mysqlConfig["port"],
        user=mysqlConfig["user"],
        password=mysqlConfig["pw"],
        database=mysqlConfig["db"],
        autocommit=False,
    )


def log_event(message: str, **fields) -> None:
    payload = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "service": "collector",
        "message": message,
    }
    payload.update(fields)
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def build_session_log_path(olt_ip: str) -> Optional[str]:
    if not OLT_SESSION_LOG_DIR:
        return None

    os.makedirs(OLT_SESSION_LOG_DIR, exist_ok=True)
    safe_ip = olt_ip.replace(".", "_").replace(":", "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(OLT_SESSION_LOG_DIR, f"collector_{safe_ip}_{stamp}.log")


def build_device(olt_ip: str) -> Dict[str, Any]:
    olt_port = int(os.getenv("OLT_PORT", "22"))
    olt_user = os.getenv("OLT_USER")
    olt_pass = os.getenv("OLT_PASS")

    missing = []
    if not olt_ip:
        missing.append("ip")
    if not olt_user:
        missing.append("OLT_USER")
    if not olt_pass:
        missing.append("OLT_PASS")

    if missing:
        raise ValueError(f"Variáveis obrigatórias ausentes: {', '.join(missing)}")

    device = {
        "device_type": "huawei_smartax",
        "ip": olt_ip,
        "port": olt_port,
        "username": olt_user,
        "password": olt_pass,
        "conn_timeout": int(os.getenv("OLT_CONN_TIMEOUT", "20")),
        "banner_timeout": int(os.getenv("OLT_BANNER_TIMEOUT", "20")),
        "auth_timeout": int(os.getenv("OLT_AUTH_TIMEOUT", "20")),
        "global_delay_factor": float(os.getenv("OLT_GLOBAL_DELAY_FACTOR", "1.5")),
        "fast_cli": False,
    }

    session_log = build_session_log_path(olt_ip)
    if session_log:
        device["session_log"] = session_log

    return device


def normalize_value(value: Any) -> Optional[str]:
    if value is None:
        return None

    value = str(value).strip()

    if value in ("", "-", "--", "N/A", "NULL", "-/-"):
        return None

    return value


def to_float_or_none(value: Any) -> Optional[float]:
    value = normalize_value(value)
    if value is None:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def to_int_or_none(value: Any) -> Optional[int]:
    value = normalize_value(value)
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def parse_dt_br(value: Any) -> Optional[datetime]:
    value = normalize_value(value)
    if value is None:
        return None

    try:
        return datetime.strptime(value, "%d-%m-%Y %H:%M:%S")
    except Exception:
        return None


def chunked(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    if size <= 0:
        size = 500

    for i in range(0, len(items), size):
        yield items[i:i + size]


def is_retryable_mysql_error(exc: Exception) -> bool:
    if isinstance(exc, mysql.connector.Error):
        if exc.errno in (1205, 1213):
            return True

    error_text = str(exc).lower()
    return (
        "lock wait timeout exceeded" in error_text
        or "deadlock found when trying to get lock" in error_text
    )


def run_db_with_retry(operation_name: str, callback):
    last_exc = None

    for attempt in range(1, DB_RETRY_ATTEMPTS + 1):
        try:
            return callback()
        except Exception as exc:
            last_exc = exc

            if not is_retryable_mysql_error(exc) or attempt >= DB_RETRY_ATTEMPTS:
                raise

            sleep_seconds = round(DB_RETRY_BASE_SECONDS * attempt, 2)
            log_event(
                "db_retry",
                operation=operation_name,
                attempt=attempt,
                sleep_seconds=sleep_seconds,
                error=str(exc),
            )
            time.sleep(sleep_seconds)

    if last_exc:
        raise last_exc

    raise RuntimeError(f"Falha inesperada em operação de banco: {operation_name}")


def execute_cli(conn, cmd: str) -> str:
    last_exc = None

    for attempt in range(1, OLT_CMD_RETRIES + 1):
        try:
            output = conn.send_command_timing(
                cmd,
                read_timeout=OLT_READ_TIMEOUT,
                last_read=OLT_LAST_READ,
                strip_prompt=False,
                strip_command=False,
                cmd_verify=False,
            )
            return str(output or "")
        except Exception as exc:
            last_exc = exc
            log_event(
                "olt_command_retry",
                ip=getattr(conn, "host", "unknown"),
                command=cmd,
                attempt=attempt,
                error=str(exc),
            )

            if attempt >= OLT_CMD_RETRIES:
                raise

            try:
                conn.clear_buffer()
            except Exception:
                pass

            time.sleep(OLT_CMD_RETRY_SLEEP * attempt)

    if last_exc:
        raise last_exc

    raise RuntimeError(f"Falha inesperada ao executar comando: {cmd}")


def connect_olt(ip: str):
    last_exc = None

    for attempt in range(1, OLT_CONNECT_RETRIES + 1):
        conn = None
        try:
            device = build_device(ip)
            conn = ConnectHandler(**device)
            conn.enable()
            return conn
        except Exception as exc:
            last_exc = exc
            log_event(
                "olt_connect_retry",
                ip=ip,
                attempt=attempt,
                error=str(exc),
            )

            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

            if attempt >= OLT_CONNECT_RETRIES:
                raise

            time.sleep(OLT_CONNECT_RETRY_SLEEP * attempt)

    if last_exc:
        raise last_exc

    raise RuntimeError(f"Falha inesperada ao conectar na OLT {ip}")


def GetBoards(conn) -> List[str]:
    boards = []
    cmd = "display board 0"

    result = execute_cli(conn, cmd)

    for line in result.splitlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue

        partials = line.split()

        if len(partials) < 3:
            continue

        slot = partials[0]
        board = partials[1]
        status = partials[2]

        if (
            "MPLB" not in board
            and "MPLA" not in board
            and "PILA" not in board
            and status == "Normal"
        ):
            boards.append(slot)

    time.sleep(1)
    return boards


def parse_ont_summary(result: str, slot: str, pon: int) -> List[Dict[str, Any]]:
    state_map = {}
    detail_map = {}
    section = None

    for raw_line in result.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("----"):
            continue

        if line.startswith("ONT") and "Run" in line and "State" not in line:
            section = "state_header"
            continue

        if section == "state_header" and line.startswith("ID"):
            section = "state"
            continue

        if line.startswith("ONT") and "SN" in line and "Rx/Tx" in line:
            section = "detail_header"
            continue

        if section == "detail_header" and line.startswith("ID"):
            section = "detail"
            continue

        if section == "state" and line and line[0].isdigit():
            parts = line.split(None, 6)

            if len(parts) >= 7:
                ont_id = int(parts[0])
                run_state = normalize_value(parts[1])
                last_uptime = normalize_value(f"{parts[2]} {parts[3]}")
                last_downtime = normalize_value(f"{parts[4]} {parts[5]}")
                last_down_cause = normalize_value(parts[6])

                state_map[ont_id] = {
                    "run_state": run_state,
                    "last_uptime": last_uptime,
                    "last_downtime": last_downtime,
                    "last_down_cause": last_down_cause,
                }

            continue

        if section == "detail" and line and line[0].isdigit():
            parts = line.split(None, 5)

            if len(parts) >= 5:
                ont_id = int(parts[0])
                sn = normalize_value(parts[1])
                ont_type = normalize_value(parts[2])
                distance = normalize_value(parts[3])
                rx_tx_power = normalize_value(parts[4])
                description = normalize_value(parts[5]) if len(parts) >= 6 else None

                rx_power = None
                tx_power = None

                if rx_tx_power and "/" in rx_tx_power:
                    rx_power, tx_power = rx_tx_power.split("/", 1)

                rx_power = normalize_value(rx_power)
                tx_power = normalize_value(tx_power)

                detail_map[ont_id] = {
                    "sn": sn,
                    "ont_type": ont_type,
                    "distance_m": distance,
                    "rx_power_dbm": rx_power,
                    "tx_power_dbm": tx_power,
                    "description": description,
                }

            continue

    ont_list = []
    all_ids = sorted(set(state_map.keys()) | set(detail_map.keys()))

    for ont_id in all_ids:
        state_info = state_map.get(ont_id, {})
        detail_info = detail_map.get(ont_id, {})

        ont_list.append({
            "slot": slot,
            "pon": pon,
            "port": f"0/{slot}/{pon}",
            "ont_id": ont_id,
            "sn": detail_info.get("sn"),
            "run_state": state_info.get("run_state"),
            "last_down_cause": state_info.get("last_down_cause"),
            "last_uptime": state_info.get("last_uptime"),
            "last_downtime": state_info.get("last_downtime"),
            "rx_power_dbm": detail_info.get("rx_power_dbm"),
            "tx_power_dbm": detail_info.get("tx_power_dbm"),
            "distance_m": detail_info.get("distance_m"),
            "ont_type": detail_info.get("ont_type"),
            "description": detail_info.get("description"),
        })

    return ont_list


def build_empty_pon_record(slot: str, pon: int) -> Dict[str, Any]:
    return {
        "slot": slot,
        "pon": pon,
        "port": f"0/{slot}/{pon}",
        "ont_id": EMPTY_PON_SENTINEL_ONT_ID,
        "sn": None,
        "run_state": "empty",
        "last_down_cause": None,
        "last_uptime": None,
        "last_downtime": None,
        "rx_power_dbm": None,
        "tx_power_dbm": None,
        "distance_m": None,
        "ont_type": None,
        "description": "EMPTY_PON_SENTINEL",
    }


def build_db_rows(olt_ip: str, ponInfo: List[Dict[str, Any]]) -> Tuple[List[Tuple[Any, ...]], set]:
    rows = []
    found_keys = set()

    for item in ponInfo:
        slot = int(item["slot"])
        pon = int(item["pon"])
        ont_id = int(item["ont_id"])

        found_keys.add((slot, pon, ont_id))

        rows.append((
            olt_ip,
            slot,
            pon,
            ont_id,
            item.get("port"),
            item.get("sn"),
            item.get("run_state"),
            item.get("last_down_cause"),
            parse_dt_br(item.get("last_uptime")),
            parse_dt_br(item.get("last_downtime")),
            to_float_or_none(item.get("rx_power_dbm")),
            to_float_or_none(item.get("tx_power_dbm")),
            to_int_or_none(item.get("distance_m")),
            item.get("ont_type"),
            item.get("description"),
        ))

    rows.sort(key=lambda x: (x[1], x[2], x[3]))
    return rows, found_keys


def SavePonInfo(olt_ip: str, ponInfo: List[Dict[str, Any]]) -> Dict[str, int]:
    if not ponInfo:
        raise Exception("Coleta retornou vazia. Sincronização cancelada para evitar sobrescrita indevida.")

    rows, found_keys = build_db_rows(olt_ip, ponInfo)

    sql_upsert = """
    INSERT INTO ont_status (
        ip, slot, pon, ont_id, port, sn, run_state, last_down_cause,
        last_uptime, last_downtime, rx_power_dbm, tx_power_dbm,
        distance_m, ont_type, description
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s
    )
    ON DUPLICATE KEY UPDATE
        port = VALUES(port),
        sn = VALUES(sn),
        run_state = VALUES(run_state),
        last_down_cause = VALUES(last_down_cause),
        last_uptime = VALUES(last_uptime),
        last_downtime = VALUES(last_downtime),
        rx_power_dbm = VALUES(rx_power_dbm),
        tx_power_dbm = VALUES(tx_power_dbm),
        distance_m = VALUES(distance_m),
        ont_type = VALUES(ont_type),
        description = VALUES(description),
        updated_at = CURRENT_TIMESTAMP
    """

    lock_name = f"hwmonit:ont_status:{olt_ip}"

    def _save_operation() -> Dict[str, int]:
        conn_db = get_db()
        cursor = conn_db.cursor()
        lock_acquired = False

        try:
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute("SET SESSION innodb_lock_wait_timeout = %s", (DB_LOCK_WAIT_TIMEOUT,))
            cursor.execute("SELECT GET_LOCK(%s, %s)", (lock_name, DB_NAMED_LOCK_TIMEOUT))
            lock_result = cursor.fetchone()
            lock_acquired = bool(lock_result and lock_result[0] == 1)

            if not lock_acquired:
                raise RuntimeError(f"Não foi possível obter lock de sincronização para a OLT {olt_ip}")

            conn_db.start_transaction()

            for row_chunk in chunked(rows, DB_UPSERT_CHUNK_SIZE):
                cursor.executemany(sql_upsert, row_chunk)

            conn_db.commit()

            return {
                "received": len(found_keys),
                "removed": 0,
            }

        except Exception:
            conn_db.rollback()
            raise
        finally:
            if lock_acquired:
                try:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
                except Exception:
                    pass

            cursor.close()
            conn_db.close()

    return run_db_with_retry("SavePonInfo", _save_operation)


def GetPonInfo(conn, slots: List[str]) -> List[Dict[str, Any]]:
    ponInfo = []

    sleep_pons = float(os.getenv("SLEEP_PONS", "0"))
    sleep_boards = float(os.getenv("SLEEP_BOARDS", "0"))

    for slot in slots:
        for pon in range(0, 16):
            cmd = f"display ont info summary 0/{slot}/{pon} | no-more"
            result = execute_cli(conn, cmd)

            parsed = parse_ont_summary(result, slot, pon)
            if parsed:
                ponInfo.extend(parsed)
            else:
                ponInfo.append(build_empty_pon_record(slot, pon))

            if sleep_pons > 0:
                time.sleep(sleep_pons)

        if sleep_boards > 0:
            time.sleep(sleep_boards)

    return ponInfo


def ensure_state_row(ip: str) -> None:
    def _operation() -> None:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO olt_collect_state (ip, status, is_locked)
                VALUES (%s, 'idle', 0)
                ON DUPLICATE KEY UPDATE ip = VALUES(ip)
                """,
                (ip,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    run_db_with_retry("ensure_state_row", _operation)


def enqueue_collect(ip: str, lease_minutes: int = 10) -> str:
    ensure_state_row(ip)
    token = str(uuid.uuid4())

    def _operation() -> str:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE olt_collect_state
                   SET is_locked = 1,
                       status = 'running',
                       lock_token = %s,
                       lock_expires_at = DATE_ADD(NOW(3), INTERVAL %s MINUTE),
                       last_started_at = NOW(3),
                       last_finished_at = NULL,
                       last_error = NULL
                 WHERE ip = %s
                   AND (
                        is_locked = 0
                        OR lock_expires_at IS NULL
                        OR lock_expires_at < NOW(3)
                   )
                """,
                (token, lease_minutes, ip),
            )
            conn.commit()

            if cur.rowcount != 1:
                raise RuntimeError(f"Já existe coleta em execução para a OLT {ip}")

            return token
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    return run_db_with_retry("enqueue_collect", _operation)


def finish_success(ip: str, token: str, duration_seconds: float) -> None:
    def _operation() -> None:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE olt_collect_state
                   SET status = 'success',
                       last_duration_seconds = %s,
                       is_locked = 0,
                       lock_token = NULL,
                       lock_expires_at = NULL,
                       last_finished_at = NOW(3),
                       last_error = NULL
                 WHERE ip = %s
                   AND lock_token = %s
                """,
                (round(duration_seconds, 2), ip, token),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    run_db_with_retry("finish_success", _operation)


def finish_error(ip: str, token: str, duration_seconds: float, error: str) -> None:
    def _operation() -> None:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE olt_collect_state
                   SET status = 'error',
                       last_duration_seconds = %s,
                       is_locked = 0,
                       lock_token = NULL,
                       lock_expires_at = NULL,
                       last_finished_at = NOW(3),
                       last_error = %s
                 WHERE ip = %s
                   AND lock_token = %s
                """,
                (round(duration_seconds, 2), str(error)[:1000], ip, token),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    run_db_with_retry("finish_error", _operation)


def get_collect_state(ip: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT
                ip,
                status,
                last_duration_seconds,
                is_locked,
                lock_token,
                lock_expires_at,
                last_started_at,
                last_finished_at,
                last_error,
                created_at,
                updated_at
            FROM olt_collect_state
            WHERE ip = %s
            """,
            (ip,),
        )
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def _do_collect(ip: str) -> Dict[str, Any]:
    start = time.perf_counter()
    conn = None

    try:
        conn = connect_olt(ip)

        boards = GetBoards(conn)
        pon_info = GetPonInfo(conn, boards)
        save_result = SavePonInfo(ip, pon_info)

        duration = time.perf_counter() - start

        result = {
            "success": True,
            "ip": ip,
            "boards": boards,
            "boards_count": len(boards),
            "processed": len(pon_info),
            "received": save_result["received"],
            "removed": save_result["removed"],
            "duration_seconds": round(duration, 2),
        }

        log_event("collection_finished", **result)
        return result

    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


def run_collection_job(ip: str, token: str) -> None:
    start = time.perf_counter()

    try:
        result = _do_collect(ip)
        duration = time.perf_counter() - start
        finish_success(ip, token, duration)

        log_event(
            "collection_state_updated",
            ip=ip,
            token=token,
            status="success",
            duration_seconds=round(duration, 2),
            processed=result.get("processed"),
            received=result.get("received"),
            removed=result.get("removed"),
        )

    except Exception as e:
        duration = time.perf_counter() - start
        finish_error(ip, token, duration, str(e))

        log_event(
            "collection_failed",
            ip=ip,
            token=token,
            status="error",
            duration_seconds=round(duration, 2),
            error=str(e),
        )


def collect_olt(ip: str) -> Dict[str, Any]:
    """
    Execução síncrona.
    Útil para teste manual ou uso fora do BackgroundTasks.
    """
    token = enqueue_collect(ip)

    start = time.perf_counter()
    try:
        result = _do_collect(ip)
        duration = time.perf_counter() - start
        finish_success(ip, token, duration)

        log_event(
            "collection_state_updated",
            ip=ip,
            token=token,
            status="success",
            duration_seconds=round(duration, 2),
            processed=result.get("processed"),
            received=result.get("received"),
            removed=result.get("removed"),
        )

        return result

    except Exception as e:
        duration = time.perf_counter() - start
        finish_error(ip, token, duration, str(e))

        log_event(
            "collection_failed",
            ip=ip,
            token=token,
            status="error",
            duration_seconds=round(duration, 2),
            error=str(e),
        )

        raise
