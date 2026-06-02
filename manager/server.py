import asyncio
import json
import sys

from config import MANAGER_HOST, MANAGER_PORT, CONSISTENCY_MODE
import replicator


async def handle_client(reader, writer):
    addr = writer.get_extra_info("peername")
    print(f"[manager] connection from {addr}")

    try:
        # --- read the JSON header up to the \n\n delimiter ---
        header_buf = bytearray()
        while True:
            byte = await reader.read(1)
            if not byte:
                print(f"[manager] {addr} disconnected before header complete")
                writer.close()
                return
            header_buf.extend(byte)
            if header_buf[-2:] == b"\n\n":
                break

        header_str = header_buf[:-2].decode("utf-8").strip()
        header = json.loads(header_str)

        file_id = header.get("id", "unknown")
        filename = header.get("filename", "unnamed")
        payload_size = int(header.get("payloadSize", 0))

        print(f"[manager] upload id={file_id} file=\"{filename}\" payload={payload_size} bytes")

        # --- read exactly payloadSize bytes of encrypted payload ---
        payload = bytearray()
        while len(payload) < payload_size:
            chunk = await reader.read(payload_size - len(payload))
            if not chunk:
                print(f"[manager] {addr} disconnected after {len(payload)}/{payload_size} payload bytes")
                writer.close()
                return
            payload.extend(chunk)

        # reconstruct the full packet to forward to java nodes as-is
        packet_bytes = header_buf + bytes(payload)

        # --- replicate based on consistency mode ---
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
            response = {
                "status": "ok",
                "mode": "eventual",
            }

        response_bytes = (json.dumps(response) + "\n").encode("utf-8")
        writer.write(response_bytes)
        await writer.drain()
        print(f"[manager] responded to {addr}: {response}")

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
