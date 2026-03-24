import os
import requests


class ZabbixClient:
    def __init__(self):
        self.url = os.getenv("ZABBIX_URL")
        self.token = os.getenv("ZABBIX_API_TOKEN")
        self.timeout = int(os.getenv("ZABBIX_TIMEOUT", "30"))

        if not self.url:
            raise ValueError("ZABBIX_URL não definido")
        if not self.token:
            raise ValueError("ZABBIX_API_TOKEN não definido")

    def _call(self, method: str, params: dict):
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }

        resp = requests.post(
            self.url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()

        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"Erro Zabbix API: {data['error']}")

        return data["result"]

    def get_olt_hosts(self):
        params = {
            "output": ["hostid", "host", "name", "status"],
            "selectInterfaces": ["ip", "dns", "useip", "type", "main"],
            "filter": {
                "status": 0
            }
        }

        group_id = os.getenv("ZABBIX_OLT_GROUP_ID")
        if group_id:
            params["groupids"] = [group_id]

        results = self._call("host.get", params)

        hosts = []
        for host in results:
            ip = None
            for iface in host.get("interfaces", []):
                if iface.get("main") == "1" and iface.get("useip") == "1" and iface.get("ip"):
                    ip = iface["ip"]
                    break

            if not ip:
                for iface in host.get("interfaces", []):
                    if iface.get("ip"):
                        ip = iface["ip"]
                        break

            if ip:
                hosts.append({
                    "hostid": host["hostid"],
                    "host": host["host"],
                    "name": host["name"],
                    "ip": ip,
                })

        return hosts