import asyncio
import time
import json
import os
import threading

from config import STORAGE_NODES, STATE_FILE

# shared state -- written by the replicator, read by the dashboard
_lock = threading.Lock()
_state = {
    "node_health": {str(port): "unknown" for _, port in STORAGE_NODES},
    "replication_log": [],
    "metadata": {},
}


def get_state():
    with _lock:
        return json.loads(json.dumps(_state))


def _flush_state():
    """persist state to disk so the streamlit dashboard can read it"""
    with _lock:
        snapshot = json.dumps(_state, indent=2, default=str)
    try:
        with open(STATE_FILE, "w") as f:
            f.write(snapshot)
    except Exception:
        pass


def _update_node_health(port, status):
    with _lock:
        _state["node_health"][str(port)] = status
    _flush_state()


def _append_log(entry):
    with _lock:
        _state["replication_log"].append(entry)
        # keep last 100 entries
        if len(_state["replication_log"]) > 100:
            _state["replication_log"] = _state["replication_log"][-100:]
    _flush_state()


def _update_metadata(file_id, filename, node_port, status):
    with _lock:
        if file_id not in _state["metadata"]:
            _state["metadata"][file_id] = {
                "filename": filename,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "nodes": {},
            }
        _state["metadata"][file_id]["nodes"][str(node_port)] = status
    _flush_state()


async def _send_to_node(host, port, packet_bytes, file_id, filename):
    """open a TCP connection to a single java node and send the full packet"""
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(packet_bytes)
        await writer.drain()

        # read the ack line from the java daemon
        ack_line = await asyncio.wait_for(reader.readline(), timeout=30.0)
        ack_str = ack_line.decode("utf-8").strip()
        writer.close()
        await writer.wait_closed()

        ack = json.loads(ack_str)
        success = ack.get("status") == "saved"
        _update_node_health(port, "up")
        _update_metadata(file_id, filename, port, "saved" if success else "error")
        _append_log({
            "time": time.strftime("%H:%M:%S"),
            "file_id": file_id,
            "filename": filename,
            "node": port,
            "status": "saved" if success else "error",
        })
        return success, port, ack_str
    except Exception as e:
        _update_node_health(port, "down")
        _update_metadata(file_id, filename, port, "failed")
        _append_log({
            "time": time.strftime("%H:%M:%S"),
            "file_id": file_id,
            "filename": filename,
            "node": port,
            "status": f"failed: {e}",
        })
        return False, port, str(e)


async def replicate_strong(packet_bytes, file_id, filename):
    """
    send the packet to all storage nodes concurrently.
    wait for every node to respond before returning.
    """
    tasks = [
        _send_to_node(host, port, packet_bytes, file_id, filename)
        for host, port in STORAGE_NODES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    succeeded = 0
    details = []
    for r in results:
        if isinstance(r, Exception):
            details.append({"success": False, "error": str(r)})
        else:
            ok, port, msg = r
            details.append({"success": ok, "node": port, "message": msg})
            if ok:
                succeeded += 1

    return succeeded, details


async def replicate_eventual(packet_bytes, file_id, filename):
    """
    fire-and-forget: schedule replication tasks in the background.
    returns immediately so the caller can ack the client right away.
    """
    for host, port in STORAGE_NODES:
        asyncio.create_task(
            _send_to_node(host, port, packet_bytes, file_id, filename)
        )
