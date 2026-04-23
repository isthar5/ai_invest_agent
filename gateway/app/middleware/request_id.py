from uuid import uuid4

async def request_id_middleware(request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response