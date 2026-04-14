import requests
from typing import Any, Dict, Optional

class GoToolClient:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip('/')
    
    def health(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except:
            return False
    
    def list_tools(self) -> list:
        resp = requests.get(f"{self.base_url}/tools")
        resp.raise_for_status()
        return resp.json()
    
    def call(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/call",
            json={"tool": tool, "params": params},
            timeout=30
        )
        data = resp.json()
        if not data.get("success"):
            raise Exception(data.get("error", "Unknown error"))
        return data["data"]