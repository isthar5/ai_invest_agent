from app.core.config import ROUTES

def match_route(path: str):
    for route in ROUTES:
        if path.startswith(route["path"]):
            return route["target"] + path
    return None