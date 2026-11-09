"""
pse_quant/api/routes/stream.py — Real-Time Server-Sent Events (SSE) Endpoints
PSE Quant SaaS (v2 Rebuild) — Lab 11

Exposes real-time event streaming for background task execution, portfolio alerts,
market ticks, and live system telemetry using W3C EventSource.
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Request, Path, Query, status, HTTPException
from starlette.responses import StreamingResponse

from pse_quant.streaming.hub import stream_hub, format_sse_event
from pse_quant.tasks.engine import task_queue
from pse_quant.api.auth import require_admin, get_current_user
from pse_quant.db.models import User

router = APIRouter(prefix="/stream", tags=["streaming"])

SSE_HEADERS = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # Disables Nginx reverse proxy response buffering
}


@router.get(
    "/tasks/{task_id}",
    summary="Real-time SSE stream of background task progress and results",
)
async def stream_task_progress(
    request: Request,
    task_id: str = Path(..., min_length=5, max_length=64),
):
    """
    Subscribes to live progress events for an asynchronous background task.
    Streams step milestones, progress percentages, and final completion payload.
    """
    channel = f"tasks:{task_id}"

    async def _task_stream_generator():
        # First, if the task is already completed or failed in the DB, emit status immediately
        status_info = task_queue.get_task_status(task_id)
        if status_info:
            yield format_sse_event(
                event_type="task_initial",
                data=status_info,
            )
            # If already terminal, we don't need to stay open
            if status_info["status"] in ("completed", "failed", "cancelled"):
                yield format_sse_event(
                    event_type="task_terminal",
                    data=status_info,
                )
                return

        # Stream live events until terminal state or client disconnect
        async for chunk in stream_hub.event_generator(channel=channel, request=request):
            yield chunk
            # Check if this chunk indicated task completion to cleanly terminate the stream
            if '"status": "completed"' in chunk or '"status": "failed"' in chunk or '"status": "cancelled"' in chunk:
                break

    return StreamingResponse(
        _task_stream_generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/alerts",
    summary="Real-time user portfolio and Margin of Safety alert stream",
)
async def stream_user_alerts(
    request: Request,
    user_id: Optional[int] = Query(None, description="Target user ID for alert channel"),
):
    """
    Streams personalized in-app notifications and Margin of Safety breach events.
    Automatically pushes live alerts without requiring client polling.
    """
    channel = f"alerts:user:{user_id}" if user_id else "alerts:public"

    return StreamingResponse(
        stream_hub.event_generator(channel=channel, request=request),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/market",
    summary="Real-time PSE market tick and quote stream",
)
async def stream_market_ticks(request: Request):
    """Streams live stock price movements, volume ticks, and trading halts."""
    return StreamingResponse(
        stream_hub.event_generator(channel="market:ticks", request=request),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/hub/metrics",
    summary="Inspect SSE stream hub subscribers and channel activity",
    dependencies=[Depends(require_admin)],
)
def get_stream_hub_metrics():
    """Returns active subscribers, channel distribution, and total events dispatched."""
    return stream_hub.get_metrics()


@router.post(
    "/publish",
    summary="Publish a message to an SSE channel (Admin / Diagnostic)",
    dependencies=[Depends(require_admin)],
)
def publish_sse_event(
    channel: str = Query(..., description="Target SSE channel e.g. 'market:ticks'"),
    event_type: str = Query("message", description="Event name"),
    data: dict = ...,
):
    """Admin endpoint to broadcast an SSE message to all subscribers of a channel."""
    delivered = stream_hub.broadcast(channel=channel, event_type=event_type, data=data)
    return {
        "status": "success",
        "channel": channel,
        "event_type": event_type,
        "delivered_to_subscribers": delivered,
    }
