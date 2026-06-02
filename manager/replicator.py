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


def get_file_list():
    """return the metadata directory for the download list"""
    with _lock:
        meta = _state.get("metadata", {})
    files = []
    for fid, info in meta.items():
        nodes = info.get("nodes", {})
        saved_nodes = [p for p, s in nodes.items() if s == "saved"]
        if saved_nodes:
            files.append({
                "id": fid,
                "filename": info.get("filename", "?"),
                "timestamp": info.get("timestamp", "?"),
                "nodes": saved_nodes,
            })
    return files


async def fetch_from_node(filename, file_id):
    """
    connect to an available java node and request a file download.
    returns the raw encrypted payload bytes, or raises on failure.
    """
    with _lock:
        health = dict(_state.get("node_health", {}))

    # pick the first node that is "up", fall back to any node
    target = None
    for host, port in STORAGE_NODES:
        if health.get(str(port)) == "up":
            target = (host, port)
            break
    if target is None:
        target = STORAGE_NODES[0]

    host, port = target

    # build a download request packet
    header = json.dumps({
        "type": "download",
        "filename": filename,
        "id": file_id,
        "payloadSize": 0,
    })
    request = (header + "\n\n").encode("utf-8")

    reader, writer = await asyncio.open_connection(host, port)
    writer.write(request)
    await writer.drain()

    # read the response header up to \n\n
    resp_buf = bytearray()
    while True:
        byte = await reader.read(1)
        if not byte:
            writer.close()
            raise Exception(f"node {port} closed connection before response header")
        resp_buf.extend(byte)
        if resp_buf[-2:] == b"\n\n":
            break

    resp_header_str = resp_buf[:-2].decode("utf-8").strip()
    resp_header = json.loads(resp_header_str)

    if resp_header.get("status") == "error":
        writer.close()
        raise Exception(resp_header.get("reason", "unknown error from node"))

    payload_size = int(resp_header.get("payloadSize", 0))

    # read the encrypted payload
    payload = bytearray()
    while len(payload) < payload_size:
        chunk = await reader.read(payload_size - len(payload))
        if not chunk:
            break
        payload.extend(chunk)

    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass

    _update_node_health(port, "up")

    return bytes(payload)
