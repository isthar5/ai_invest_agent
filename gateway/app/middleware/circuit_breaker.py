import time
from app.core.config import CB_CONFIG

class CircuitBreaker:
    def __init__(self):
        self.state = "CLOSED"
        self.fail_count = 0
        self.last_fail_time = 0

    def allow_request(self):
        if self.state == "OPEN":
            if time.time() - self.last_fail_time > CB_CONFIG["recovery_time"]:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def on_success(self):
        self.fail_count = 0
        self.state = "CLOSED"

    def on_failure(self):
        self.fail_count += 1
        if self.fail_count >= CB_CONFIG["fail_threshold"]:
            self.state = "OPEN"
            self.last_fail_time = time.time()


# ⭐ 核心：按服务维度存储
cb_map = {}

def get_cb(service_key: str):
    if service_key not in cb_map:
        cb_map[service_key] = CircuitBreaker()
    return cb_map[service_key]