import yaml

with open("config/gateway.yaml", "r") as f:
    config = yaml.safe_load(f)

ROUTES = config["routes"]
RATE_LIMIT = config["rate_limit"]["default"]
CB_CONFIG = config["circuit_breaker"]
CACHE_CONFIG = config["cache"]