import json

from fastapi import WebSocket, WebSocketDisconnect

from app.multi_agent.runtime import run_multi_agent


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        data = await websocket.receive_text()
        request = json.loads(data)
        query = request.get("query", "")
        session_id = request.get("session_id", "default")

        await websocket.send_json({"type": "status", "value": "connecting"})

        async def stream_callback(chunk_type: str, content):
            await websocket.send_json({"type": chunk_type, "value": content})

        result = await run_multi_agent(
            query=query,
            session_id=session_id,
            stream_callback=stream_callback,
        )

        if result.get("error"):
            await websocket.send_json({"type": "error", "value": result["error"]})

        await websocket.send_json(
            {
                "type": "done",
                "value": {
                    "success": result.get("success", False),
                    "session_id": session_id,
                },
            }
        )
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({"type": "error", "value": str(e)})
