import os
import time
import requests
import mysql.connector

from orchestrator.zabbix_client import ZabbixClient


DB_HOST = os.getenv("DB_HOST", "hwmonit_db")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "hwmonit")
DB_USER = os.getenv("DB_USER", "hwmonit")
DB_PASS = os.getenv("DB_PASSWORD", "hwmonit123")

COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://hwmonit-collector:8000")
ORCHESTRATOR_LOOP_SECONDS = int(os.getenv("ORCHESTRATOR_LOOP_SECONDS", "15"))
SYNC_ZABBIX_EVERY_SECONDS = int(os.getenv("SYNC_ZABBIX_EVERY_SECONDS", "300"))
REQUEST_TIMEOUT = int(os.getenv("COLLECTOR_TIMEOUT", "15"))


def get_db():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
    )


def ensure_olt_state(ip: str):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO olt_collect_state (ip, status, is_locked)
            VALUES (%s, 'idle', 0)
            ON DUPLICATE KEY UPDATE ip = VALUES(ip)
        """, (ip,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def sync_olts_from_zabbix():
    client = ZabbixClient()
    hosts = client.get_olt_hosts()

    synced = 0
    for host in hosts:
        ensure_olt_state(host["ip"])
        synced += 1

    print(f"[sync] OLTs sincronizadas do Zabbix: {synced}")
    return synced


def get_due_olts(limit: int = 20):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"""
            SELECT
                ip,
                status,
                last_duration_seconds,
                is_locked,
                last_started_at,
                last_finished_at,
                lock_expires_at
            FROM olt_collect_state
            WHERE
                (
                    is_locked = 0
                    OR lock_expires_at IS NULL
                    OR lock_expires_at < NOW(3)
                )
                AND
                (
                    last_finished_at IS NULL
                    OR TIMESTAMPDIFF(
                        SECOND,
                        last_finished_at,
                        NOW(3)
                    ) >= (60 + COALESCE(last_duration_seconds, 0))
                )
            ORDER BY
                COALESCE(last_finished_at, '2000-01-01 00:00:00') ASC
            LIMIT %s
        """, (limit,))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def trigger_collect(ip: str):
    url = f"{COLLECTOR_URL}/collect"

    resp = requests.post(
        url,
        json={"ip": ip},
        timeout=REQUEST_TIMEOUT,
    )

    if resp.status_code == 202:
        print(f"[collect] aceito: {ip}")
        return True

    if resp.status_code == 409:
        print(f"[collect] já em execução: {ip}")
        return False

    print(f"[collect] erro {ip}: {resp.status_code} - {resp.text}")
    return False


def main():
    last_sync = 0

    while True:
        try:
            now = time.time()

            if now - last_sync >= SYNC_ZABBIX_EVERY_SECONDS:
                sync_olts_from_zabbix()
                last_sync = now

            due_olts = get_due_olts()

            for row in due_olts:
                trigger_collect(row["ip"])

        except Exception as e:
            print(f"[orchestrator] erro: {e}")

        time.sleep(ORCHESTRATOR_LOOP_SECONDS)


if __name__ == "__main__":
    main()
import os
import time
import requests
import mysql.connector

from orchestrator.zabbix_client import ZabbixClient


DB_HOST = os.getenv("DB_HOST", "hwmonit_db")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "hwmonit")
DB_USER = os.getenv("DB_USER", "hwmonit")
DB_PASS = os.getenv("DB_PASS", "hwmonit123")

COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://hwmonit-collector:8000")
ORCHESTRATOR_LOOP_SECONDS = int(os.getenv("ORCHESTRATOR_LOOP_SECONDS", "15"))
SYNC_ZABBIX_EVERY_SECONDS = int(os.getenv("SYNC_ZABBIX_EVERY_SECONDS", "300"))
REQUEST_TIMEOUT = int(os.getenv("COLLECTOR_TIMEOUT", "15"))


def get_db():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
    )


def ensure_olt_state(ip: str):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO olt_collect_state (ip, status, is_locked)
            VALUES (%s, 'idle', 0)
            ON DUPLICATE KEY UPDATE ip = VALUES(ip)
        """, (ip,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


def sync_olts_from_zabbix():
    client = ZabbixClient()
    hosts = client.get_olt_hosts()

    synced = 0
    for host in hosts:
        ensure_olt_state(host["ip"])
        synced += 1

    print(f"[sync] OLTs sincronizadas do Zabbix: {synced}")
    return synced


def get_due_olts(limit: int = 20):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"""
            SELECT
                ip,
                status,
                last_duration_seconds,
                is_locked,
                last_started_at,
                last_finished_at,
                lock_expires_at
            FROM olt_collect_state
            WHERE
                (
                    is_locked = 0
                    OR lock_expires_at IS NULL
                    OR lock_expires_at < NOW(3)
                )
                AND
                (
                    last_finished_at IS NULL
                    OR TIMESTAMPDIFF(
                        SECOND,
                        last_finished_at,
                        NOW(3)
                    ) >= (60 + COALESCE(last_duration_seconds, 0))
                )
            ORDER BY
                COALESCE(last_finished_at, '2000-01-01 00:00:00') ASC
            LIMIT %s
        """, (limit,))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def trigger_collect(ip: str):
    url = f"{COLLECTOR_URL}/collect"

    resp = requests.post(
        url,
        json={"ip": ip},
        timeout=REQUEST_TIMEOUT,
    )

    if resp.status_code == 202:
        print(f"[collect] aceito: {ip}")
        return True

    if resp.status_code == 409:
        print(f"[collect] já em execução: {ip}")
        return False

    print(f"[collect] erro {ip}: {resp.status_code} - {resp.text}")
    return False


def main():
    last_sync = 0

    while True:
        try:
            now = time.time()

            if now - last_sync >= SYNC_ZABBIX_EVERY_SECONDS:
                sync_olts_from_zabbix()
                last_sync = now

            due_olts = get_due_olts()

            for row in due_olts:
                trigger_collect(row["ip"])

        except Exception as e:
            print(f"[orchestrator] erro: {e}")

        time.sleep(ORCHESTRATOR_LOOP_SECONDS)


if __name__ == "__main__":
    main()