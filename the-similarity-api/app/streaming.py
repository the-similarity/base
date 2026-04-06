"""WebSocket streaming for real-time search and candle watching.

Two WebSocket endpoints:

1. /ws/search — Stream search progress + results in real time.
   Client sends a SearchRequest JSON, server streams back:
     {"type": "progress", "stage": "prefilter", ...}
     {"type": "progress", "stage": "tier1", ...}
     {"type": "progress", "stage": "tier2", "completed": 5, "total": 20, ...}
     {"type": "result", "matches": [...], "forecast": {...}}
     {"type": "done"}

2. /ws/watch — Watch for pattern matches on a live candle stream.
   Client sends initial config, then pushes candles as they arrive.
   Server re-runs search when enough new bars accumulate.

Concurrency & Async Boundary Lifecycle:
- GIL Dynamics: `the_similarity.search()` leans heavily into compiled C extensions 
  (NumPy, SciPy). Because these drop the Global Interpreter Lock (GIL) during tight 
  computational segments, running concurrent UI requests through a `ThreadPoolExecutor` 
  actually provides true structural hardware parallelization, avoiding dummy context 
  switches.
- Event Loop Blocking: All engine calls MUST explicitly route through `loop.run_in_executor()`. 
  Invoking them directly in the coroutine path will structurally lock the FastAPI 
  uvicorn asynchronous event loop, blocking all other clients.
- Thread-safe Progress Streaming: The background search executors asynchronously emit 
  progress updates. To bridge this back to the main thread's async WebSocket pipeline, 
  `_progress_callback` leverages `loop.call_soon_threadsafe()` to marshal data 
  cleanly into an `asyncio.Queue()`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from the_similarity.config import Config
from the_similarity.core.matcher import ProgressEvent

logger = logging.getLogger(__name__)

# Shared thread pool for CPU-bound search work
_search_executor = ThreadPoolExecutor(max_workers=2)


def _serialize(obj: Any) -> Any:
    """Make objects JSON-serializable."""
    if obj is None:
        return None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


async def _send_json(ws: WebSocket, data: dict) -> bool:
    """Send JSON to WebSocket, return False if connection lost."""
    try:
        await ws.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


async def handle_search_stream(ws: WebSocket) -> None:
    """Handle a streaming search WebSocket connection.

    Protocol:
        1. Client connects
        2. Client sends JSON matching SearchRequest schema
        3. Server streams progress events as JSON
        4. Server sends final results
        5. Connection remains open for additional searches
    """
    await ws.accept()

    try:
        while True:
            # Wait for a search request
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                return

            try:
                request = json.loads(raw)
            except json.JSONDecodeError as exc:
                await _send_json(ws, {"type": "error", "message": f"invalid JSON: {exc}"})
                continue

            # Validate required fields
            query_values = request.get("queryValues") or request.get("query_values")
            history_values = request.get("historyValues") or request.get("history_values")
            if not query_values or not history_values:
                await _send_json(ws, {
                    "type": "error",
                    "message": "query_values and history_values are required",
                })
                continue

            # Extract config overrides
            top_k = request.get("topK", request.get("top_k", 20))
            forward_bars = request.get("forwardBars", request.get("forward_bars", 50))
            stride = request.get("stride")
            active_methods = request.get("activeMethods", request.get("active_methods", []))
            weights = request.get("weights", {})
            percentiles = request.get("percentiles", [])

            # Run search in thread pool with progress streaming
            loop = asyncio.get_event_loop()
            progress_queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()

            def _progress_callback(event: ProgressEvent) -> None:
                """Thread-safe callback that puts events on the async queue."""
                loop.call_soon_threadsafe(progress_queue.put_nowait, event)

            def _run_search() -> dict:
                """Execute search in thread pool."""
                import the_similarity

                q = np.asarray(query_values, dtype=np.float64)
                h = np.asarray(history_values, dtype=np.float64)

                search_kwargs: dict[str, Any] = {}
                if stride is not None:
                    search_kwargs["stride"] = stride
                if active_methods:
                    search_kwargs["active_methods"] = active_methods

                results = the_similarity.search(
                    query=q,
                    history=h,
                    top_k=top_k,
                    weights=weights or None,
                    progress_fn=_progress_callback,
                    **search_kwargs,
                )

                forecast = the_similarity.project(
                    matches=results,
                    history=h,
                    forward_bars=forward_bars,
                    percentiles=percentiles or None,
                )

                # Signal completion
                loop.call_soon_threadsafe(progress_queue.put_nowait, None)

                return {
                    "matches": [
                        {
                            "startIdx": m.start_idx,
                            "endIdx": m.end_idx,
                            "startDate": m.start_date,
                            "endDate": m.end_date,
                            "confidenceScore": m.confidence_score,
                            "scoreBreakdown": _serialize(m.score_breakdown),
                            "matchedSeries": _serialize(m.matched_series),
                            "regime": m.regime,
                        }
                        for m in results.matches
                    ],
                    "forecast": {
                        "bars": forecast.bars,
                        "percentiles": forecast.percentiles,
                        "curves": _serialize(forecast.curves),
                    },
                }

            # Start search in background
            search_future = loop.run_in_executor(_search_executor, _run_search)

            # Stream progress events while search runs
            while True:
                event = await progress_queue.get()
                if event is None:
                    break
                ok = await _send_json(ws, {
                    "type": "progress",
                    "stage": event.stage,
                    "completed": event.completed,
                    "total": event.total,
                    "message": event.message,
                    "topScore": event.top_score,
                })
                if not ok:
                    search_future.cancel()
                    return

            # Send final results
            try:
                result = await search_future
            except Exception as exc:
                await _send_json(ws, {"type": "error", "message": str(exc)})
                continue

            await _send_json(ws, {"type": "result", **result})
            await _send_json(ws, {"type": "done"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("search stream error: %s", exc)


async def handle_watch_stream(ws: WebSocket) -> None:
    """Handle a candle-watching WebSocket connection.

    Protocol:
        1. Client connects
        2. Client sends initial config:
           {
             "type": "init",
             "queryValues": [...],      // pattern to watch for
             "historyValues": [...],    // initial history
             "windowSize": 60,
             "threshold": 70.0,         // min confidence to trigger alert
             "recheckBars": 5,          // re-run search every N new bars
             "stride": 3,
           }
        3. Client pushes new candles:
           {"type": "candle", "value": 105.23}
           {"type": "candle", "value": 105.45}
        4. After `recheckBars` new candles, server re-runs search and sends:
           {"type": "scan", "topScore": 82.3, "matches": 5, "alert": true}
           or if above threshold:
           {"type": "alert", "match": {...}, "message": "..."}
        5. Client can update the query:
           {"type": "update_query", "queryValues": [...]}
    """
    await ws.accept()

    state = {
        "query": None,
        "history": None,
        "threshold": 70.0,
        "recheck_bars": 5,
        "stride": 3,
        "new_bar_count": 0,
        "initialized": False,
        "top_k": 5,
    }

    try:
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                return

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError as exc:
                await _send_json(ws, {"type": "error", "message": f"invalid JSON: {exc}"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "init":
                query_vals = msg.get("queryValues") or msg.get("query_values")
                history_vals = msg.get("historyValues") or msg.get("history_values")
                if not query_vals or not history_vals:
                    await _send_json(ws, {
                        "type": "error",
                        "message": "queryValues and historyValues required for init",
                    })
                    continue

                state["query"] = np.asarray(query_vals, dtype=np.float64)
                state["history"] = np.asarray(history_vals, dtype=np.float64)
                state["threshold"] = msg.get("threshold", 70.0)
                state["recheck_bars"] = msg.get("recheckBars", msg.get("recheck_bars", 5))
                state["stride"] = msg.get("stride", 3)
                state["top_k"] = msg.get("topK", msg.get("top_k", 5))
                state["new_bar_count"] = 0
                state["initialized"] = True

                await _send_json(ws, {
                    "type": "initialized",
                    "historyLength": len(state["history"]),
                    "queryLength": len(state["query"]),
                    "threshold": state["threshold"],
                    "recheckBars": state["recheck_bars"],
                })

            elif msg_type == "candle":
                if not state["initialized"]:
                    await _send_json(ws, {"type": "error", "message": "send init first"})
                    continue

                value = msg.get("value")
                if value is None:
                    await _send_json(ws, {"type": "error", "message": "candle needs value"})
                    continue

                # Append to history
                state["history"] = np.append(state["history"], float(value))
                state["new_bar_count"] += 1

                await _send_json(ws, {
                    "type": "ack",
                    "historyLength": len(state["history"]),
                    "newBars": state["new_bar_count"],
                })

                # Check if we should re-scan
                if state["new_bar_count"] >= state["recheck_bars"]:
                    state["new_bar_count"] = 0
                    await _run_watch_scan(ws, state)

            elif msg_type == "update_query":
                query_vals = msg.get("queryValues") or msg.get("query_values")
                if not query_vals:
                    await _send_json(ws, {"type": "error", "message": "queryValues required"})
                    continue
                state["query"] = np.asarray(query_vals, dtype=np.float64)
                await _send_json(ws, {
                    "type": "query_updated",
                    "queryLength": len(state["query"]),
                })

            elif msg_type == "scan":
                # Force an immediate re-scan
                if not state["initialized"]:
                    await _send_json(ws, {"type": "error", "message": "send init first"})
                    continue
                state["new_bar_count"] = 0
                await _run_watch_scan(ws, state)

            else:
                await _send_json(ws, {"type": "error", "message": f"unknown type: {msg_type}"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("watch stream error: %s", exc)


async def _run_watch_scan(ws: WebSocket, state: dict) -> None:
    """Run a search scan and send results over WebSocket."""
    loop = asyncio.get_event_loop()

    def _scan() -> dict:
        import the_similarity

        results = the_similarity.search(
            query=state["query"],
            history=state["history"],
            top_k=state["top_k"],
            stride=state["stride"],
            exclude_self=False,
        )
        best = results.best
        return {
            "top_score": best.confidence_score if best else 0.0,
            "n_matches": len(results.matches),
            "best_match": {
                "startIdx": best.start_idx,
                "endIdx": best.end_idx,
                "confidenceScore": best.confidence_score,
                "regime": best.regime,
                "scoreBreakdown": _serialize(best.score_breakdown),
            } if best else None,
        }

    try:
        result = await loop.run_in_executor(_search_executor, _scan)
    except Exception as exc:
        await _send_json(ws, {"type": "error", "message": f"scan failed: {exc}"})
        return

    is_alert = result["top_score"] >= state["threshold"]
    msg = {
        "type": "alert" if is_alert else "scan",
        "topScore": result["top_score"],
        "matches": result["n_matches"],
        "historyLength": len(state["history"]),
    }
    if is_alert and result["best_match"]:
        msg["match"] = result["best_match"]
        msg["message"] = (
            f"Pattern match detected! Score {result['top_score']:.1f} "
            f"exceeds threshold {state['threshold']:.1f}"
        )

    await _send_json(ws, msg)
