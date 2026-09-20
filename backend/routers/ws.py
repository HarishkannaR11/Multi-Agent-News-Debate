from datetime import date as date_cls

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..graph.graph import build_graph
from ..graph.state import DebateState

router = APIRouter()


@router.websocket("/ws/debate/{debate_id}")
async def debate_ws(websocket: WebSocket, debate_id: str):
    await websocket.accept()
    graph = build_graph()
    initial_state: DebateState = {
        "topic": "",
        "date": date_cls.today().isoformat(),
        "news_context": "",
        "round": 1,
        "arguments": {},
        "rebuttals": {},
        "guardrail_input_pass": False,
        "guardrail_output_pass": False,
        "verdict": "",
        "bias_scores": {},
        "status": "fetching",
    }
    try:
        async for event in graph.astream(initial_state):
            node_name = list(event.keys())[0]
            payload = event[node_name]
            await websocket.send_json({
                "node": node_name,
                "status": payload.get("status"),
                "data": payload.get("arguments", {}),
                "verdict": payload.get("verdict", ""),
                "bias_scores": payload.get("bias_scores", {}),
            })
    except WebSocketDisconnect:
        pass
