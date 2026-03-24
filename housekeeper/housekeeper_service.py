import os
import time
from datetime import datetime

import pymysql


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "hwmonit_db"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "hwmonit"),
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}

HOUSEKEEPER_INTERVAL_SECONDS = env_int("HOUSEKEEPER_INTERVAL_SECONDS", 300)
OLT_STALE_HOURS = env_int("OLT_STALE_HOURS", 48)
ONT_STALE_MINUTES = env_int("ONT_STALE_MINUTES", 60)


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [housekeeper] {msg}", flush=True)


def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


def release_expired_locks(conn) -> int:
    sql = f"""
        UPDATE olt_collect_state
        SET
            is_locked = 0,
            lock_token = NULL,
            lock_expires_at = NULL,
            status = CASE
                WHEN status = 'running' THEN 'error'
                ELSE status
            END,
            last_error = CASE
                WHEN status = 'running'
                    THEN 'Housekeeper liberou lock expirado automaticamente'
                ELSE last_error
            END,
            updated_at = CURRENT_TIMESTAMP(3)
        WHERE is_locked = 1
          AND lock_expires_at IS NOT NULL
          AND lock_expires_at < NOW(3)
    """
    with conn.cursor() as cursor:
        affected = cursor.execute(sql)
    return affected


def find_stale_olts(conn):
    sql = f"""
        SELECT ip
        FROM olt_collect_state
        WHERE updated_at < (NOW(3) - INTERVAL %s HOUR)
          AND NOT (
              status = 'running'
              AND is_locked = 1
              AND lock_expires_at IS NOT NULL
              AND lock_expires_at >= NOW(3)
          )
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (OLT_STALE_HOURS,))
        return cursor.fetchall()


def delete_onts_by_ips(conn, ips):
    if not ips:
        return 0

    placeholders = ", ".join(["%s"] * len(ips))
    sql = f"DELETE FROM ont_status WHERE ip IN ({placeholders})"

    with conn.cursor() as cursor:
        affected = cursor.execute(sql, ips)

    return affected


def delete_olt_states_by_ips(conn, ips):
    if not ips:
        return 0

    placeholders = ", ".join(["%s"] * len(ips))
    sql = f"DELETE FROM olt_collect_state WHERE ip IN ({placeholders})"

    with conn.cursor() as cursor:
        affected = cursor.execute(sql, ips)

    return affected


def delete_stale_onts(conn) -> int:
    sql = f"""
        DELETE os
        FROM ont_status os
        LEFT JOIN olt_collect_state ocs
            ON ocs.ip = os.ip
        WHERE os.updated_at < (NOW() - INTERVAL %s MINUTE)
          AND NOT (
              ocs.status = 'running'
              AND ocs.is_locked = 1
              AND ocs.lock_expires_at IS NOT NULL
              AND ocs.lock_expires_at >= NOW(3)
          )
    """
    with conn.cursor() as cursor:
        affected = cursor.execute(sql, (ONT_STALE_MINUTES,))
    return affected


def run_once():
    conn = get_db_connection()

    try:
        released_locks = release_expired_locks(conn)

        stale_olts = find_stale_olts(conn)
        stale_ips = [row["ip"] for row in stale_olts]

        deleted_onts_from_stale_olts = delete_onts_by_ips(conn, stale_ips)
        deleted_olts = delete_olt_states_by_ips(conn, stale_ips)

        deleted_stale_onts = delete_stale_onts(conn)

        conn.commit()

        log(
            f"locks_liberados={released_locks} | "
            f"olts_removidas={deleted_olts} | "
            f"onts_removidas_por_olt={deleted_onts_from_stale_olts} | "
            f"onts_removidas_stale={deleted_stale_onts}"
        )

    except Exception as exc:
        conn.rollback()
        log(f"erro: {exc}")
    finally:
        conn.close()


def main():
    log(
        f"iniciado | intervalo={HOUSEKEEPER_INTERVAL_SECONDS}s | "
        f"olt_stale={OLT_STALE_HOURS}h | ont_stale={ONT_STALE_MINUTES}min"
    )

    while True:
        run_once()
        time.sleep(HOUSEKEEPER_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()