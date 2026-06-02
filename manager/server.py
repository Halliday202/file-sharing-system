import asyncio
import json
import sys

from config import MANAGER_HOST, MANAGER_PORT, CONSISTENCY_MODE
import replicator


async def read_header(reader):
    """read bytes until the \\n\\n delimiter, return (header_buf, parsed_header)"""
    header_buf = bytearray()
    while True:
        byte = await reader.read(1)
        if not byte:
            return None, None
        header_buf.extend(byte)
        if header_buf[-2:] == b"\n\n":
            break
    header_str = header_buf[:-2].decode("utf-8").strip()
    return header_buf, json.loads(header_str)


async def read_payload(reader, payload_size):
    """read exactly payload_size bytes from the stream"""
    payload = bytearray()
    while len(payload) < payload_size:
        chunk = await reader.read(payload_size - len(payload))
        if not chunk:
            return None
        payload.extend(chunk)
    return bytes(payload)


async def handle_upload(reader, writer, header, header_buf):
    addr = writer.get_extra_info("peername")
    file_id = header.get("id", "unknown")
    filename = header.get("filename", "unnamed")
    payload_size = int(header.get("payloadSize", 0))

    print(f"[manager] upload id={file_id} file=\"{filename}\" payload={payload_size} bytes")

    payload = await read_payload(reader, payload_size)
    if payload is None:
        print(f"[manager] {addr} disconnected during payload")
        return

    packet_bytes = header_buf + payload

    mode = CONSISTENCY_MODE
    if mode == "strong":
        succeeded, details = await replicator.replicate_strong(
            packet_bytes, file_id, filename
        )
        response = {
            "status": "ok" if succeeded == len(details) else "partial",
            "mode": "strong",
            "replicas": succeeded,
            "total_nodes": len(details),
        }
    else:
        await replicator.replicate_eventual(packet_bytes, file_id, filename)
        response = {"status": "ok", "mode": "eventual"}

    writer.write((json.dumps(response) + "\n").encode("utf-8"))
    await writer.drain()
    print(f"[manager] responded to {addr}: {response}")


async def handle_list(writer):
    files = replicator.get_file_list()
    response = {"status": "ok", "files": files}
    writer.write((json.dumps(response) + "\n").encode("utf-8"))
    await writer.drain()
    print(f"[manager] list response: {len(files)} files")


async def handle_download(writer, header):
    filename = header.get("filename", "")
    file_id = header.get("id", "")
    print(f"[manager] download request for \"{filename}\" id={file_id}")

    try:
        encrypted_payload = await replicator.fetch_from_node(filename, file_id)

        resp_header = json.dumps({
            "status": "ok",
            "type": "download_response",
            "filename": filename,
            "payloadSize": len(encrypted_payload),
        })
        writer.write((resp_header + "\n\n").encode("utf-8"))
        writer.write(encrypted_payload)
        await writer.drain()
        print(f"[manager] sent download: {filename} ({len(encrypted_payload)} bytes encrypted)")
    except Exception as e:
        err = json.dumps({"status": "error", "reason": str(e)}) + "\n"
        writer.write(err.encode("utf-8"))
        await writer.drain()
        print(f"[manager] download error: {e}")


async def handle_client(reader, writer):
    addr = writer.get_extra_info("peername")
    print(f"[manager] connection from {addr}")

    try:
        header_buf, header = await read_header(reader)
        if header is None:
            print(f"[manager] {addr} disconnected before header complete")
            return

        request_type = header.get("type", "upload")

        if request_type == "upload":
            await handle_upload(reader, writer, header, header_buf)
        elif request_type == "list":
            await handle_list(writer)
        elif request_type == "download":
            await handle_download(writer, header)
        else:
            err = json.dumps({"status": "error", "reason": f"unknown type: {request_type}"}) + "\n"
            writer.write(err.encode("utf-8"))
            await writer.drain()

    except Exception as e:
        print(f"[manager] error handling {addr}: {e}")
        try:
            err = json.dumps({"status": "error", "reason": str(e)}) + "\n"
            writer.write(err.encode("utf-8"))
            await writer.drain()
        except Exception:
            pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle_client, MANAGER_HOST, MANAGER_PORT)
    addr = server.sockets[0].getsockname()
    print(f"[manager] listening on {addr[0]}:{addr[1]}")
    print(f"[manager] consistency mode: {CONSISTENCY_MODE}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[manager] shutting down")
        sys.exit(0)
