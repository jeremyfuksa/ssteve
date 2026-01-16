#!/usr/bin/env python3
"""
WebSocket test client for SSTeVe API.

Tests the WebSocket decode and transmit endpoints by:
1. Starting a decode/transmit session via REST API
2. Connecting to the WebSocket
3. Receiving and logging events
4. Verifying session_resume and buffered events

Usage:
    python test_websocket.py decode
    python test_websocket.py transmit --image path/to/image.jpg
"""

import asyncio
import json
import sys
from typing import Optional
from uuid import UUID

import aiohttp


BASE_URL = "http://localhost:8000/api/v1"
WS_URL = "ws://localhost:8000/api/v1"


async def test_decode_websocket(mode: str = "ScottieS1"):
    """Test decode WebSocket endpoint."""
    print("=" * 60)
    print("Testing Decode WebSocket")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # Step 1: Start decode session
        print("\n1. Starting decode session...")
        async with session.post(
            f"{BASE_URL}/decode/start",
            json={
                "mode": mode,
                "auto_detect": False,
                "timeout_seconds": 120,
                "save_image": True,
            }
        ) as resp:
            if resp.status != 201:
                print(f"❌ Failed to start decode: {resp.status}")
                text = await resp.text()
                print(f"   Response: {text}")
                return

            data = await resp.json()
            session_id = data["session_id"]
            print(f"✓ Decode session started: {session_id}")
            print(f"  State: {data['state']}")
            print(f"  WebSocket URL: {data['websocket_url']}")

        # Step 2: Connect to WebSocket
        print(f"\n2. Connecting to WebSocket...")
        ws_url = f"{WS_URL}/ws/decode/{session_id}"

        try:
            async with session.ws_connect(ws_url) as ws:
                print(f"✓ WebSocket connected")

                # Step 3: Receive events
                print(f"\n3. Receiving events (Ctrl+C to stop)...")
                event_count = 0

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(msg.data)
                        event_count += 1

                        event_type = event.get("event", "unknown")
                        print(f"\n[Event {event_count}] {event_type}")

                        if event_type == "session_resume":
                            print(f"  State: {event.get('state')}")
                            print(f"  Metadata: {json.dumps(event.get('metadata', {}), indent=4)}")

                        elif event_type == "vis_detected":
                            print(f"  Mode: {event.get('mode')}")
                            print(f"  Confidence: {event.get('confidence'):.2%}")

                        elif event_type == "scanline_update":
                            line = event.get('line', 0)
                            total = event.get('total', 256)
                            progress = event.get('progress', 0)
                            quality = event.get('signal_quality', 0)
                            print(f"  Progress: {progress:.1f}% ({line}/{total})")
                            print(f"  Signal Quality: {quality:.2f}")

                        elif event_type == "decode_complete":
                            print(f"  Filepath: {event.get('filepath')}")
                            print(f"  Duration: {event.get('timestamp')}s")
                            print("\n✓ Decode completed!")
                            break

                        elif event_type == "error":
                            print(f"  Error Code: {event.get('error_code')}")
                            print(f"  Message: {event.get('message')}")
                            print("\n❌ Decode failed!")
                            break

                        elif event_type == "pong":
                            print(f"  (keepalive)")

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"❌ WebSocket error: {ws.exception()}")
                        break

        except Exception as e:
            print(f"\n❌ WebSocket connection failed: {e}")
            return

        # Step 4: Verify session status
        print(f"\n4. Checking final session status...")
        async with session.get(f"{BASE_URL}/decode/status/{session_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"✓ Final state: {data['state']}")
                print(f"  Progress: {data.get('progress_percent', 0):.1f}%")
                if data.get('image_id'):
                    print(f"  Image ID: {data['image_id']}")
            else:
                print(f"❌ Failed to get status: {resp.status}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


async def test_transmit_websocket(image_path: str, mode: str = "ScottieS1"):
    """Test transmit WebSocket endpoint."""
    print("=" * 60)
    print("Testing Transmit WebSocket")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # Step 1: Start transmit session
        print("\n1. Starting transmit session...")
        async with session.post(
            f"{BASE_URL}/transmit",
            json={
                "image_path": image_path,
                "mode": mode,
                "vox_enabled": True,
                "include_vis": True,
            }
        ) as resp:
            if resp.status != 201:
                print(f"❌ Failed to start transmit: {resp.status}")
                text = await resp.text()
                print(f"   Response: {text}")
                return

            data = await resp.json()
            tx_id = data["tx_id"]
            print(f"✓ Transmit session started: {tx_id}")
            print(f"  State: {data['state']}")
            print(f"  Estimated Duration: {data['estimated_duration_seconds']:.1f}s")
            print(f"  WebSocket URL: {data['websocket_url']}")

        # Step 2: Connect to WebSocket
        print(f"\n2. Connecting to WebSocket...")
        ws_url = f"{WS_URL}/ws/transmit/{tx_id}"

        try:
            async with session.ws_connect(ws_url) as ws:
                print(f"✓ WebSocket connected")

                # Step 3: Receive events
                print(f"\n3. Receiving events (Ctrl+C to stop)...")
                event_count = 0

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(msg.data)
                        event_count += 1

                        event_type = event.get("event", "unknown")
                        print(f"\n[Event {event_count}] {event_type}")

                        if event_type == "session_resume":
                            print(f"  State: {event.get('state')}")
                            print(f"  Metadata: {json.dumps(event.get('metadata', {}), indent=4)}")

                        elif event_type == "tx_progress":
                            progress = event.get('progress', 0)
                            remaining = event.get('time_remaining_sec', 0)
                            scanline = event.get('current_scanline', 0)
                            print(f"  Progress: {progress:.1f}%")
                            print(f"  Time Remaining: {remaining:.1f}s")
                            print(f"  Current Scanline: {scanline}")

                        elif event_type == "tx_complete":
                            print(f"  Duration: {event.get('timestamp')}s")
                            print("\n✓ Transmit completed!")
                            break

                        elif event_type == "error":
                            print(f"  Error Code: {event.get('error_code')}")
                            print(f"  Message: {event.get('message')}")
                            print("\n❌ Transmit failed!")
                            break

                        elif event_type == "pong":
                            print(f"  (keepalive)")

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"❌ WebSocket error: {ws.exception()}")
                        break

        except Exception as e:
            print(f"\n❌ WebSocket connection failed: {e}")
            return

        # Step 4: Verify session status
        print(f"\n4. Checking final session status...")
        async with session.get(f"{BASE_URL}/transmit/status/{tx_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"✓ Final state: {data['state']}")
                print(f"  Progress: {data.get('progress_percent', 0):.1f}%")
            else:
                print(f"❌ Failed to get status: {resp.status}")

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


async def test_reconnection(session_id: str):
    """Test WebSocket reconnection and buffered events."""
    print("=" * 60)
    print("Testing WebSocket Reconnection")
    print("=" * 60)

    print("\nThis test simulates disconnect/reconnect to verify:")
    print("  1. Events are buffered during disconnect")
    print("  2. Buffered events are replayed on reconnect")
    print("  3. session_resume event includes current state")

    async with aiohttp.ClientSession() as session:
        ws_url = f"{WS_URL}/ws/decode/{session_id}"

        # First connection
        print("\n1. First connection...")
        async with session.ws_connect(ws_url) as ws:
            print("✓ Connected")

            # Receive first few events
            for i in range(3):
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    event = json.loads(msg.data)
                    print(f"  Event: {event.get('event')}")

            print("\n2. Disconnecting...")

        # Wait a bit
        await asyncio.sleep(2)

        # Second connection (reconnect)
        print("\n3. Reconnecting...")
        async with session.ws_connect(ws_url) as ws:
            print("✓ Reconnected")

            # Should receive buffered events first
            print("\n4. Receiving buffered events...")
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                event = json.loads(msg.data)
                print(f"  First event: {event.get('event')}")

                if event.get('event') == 'session_resume':
                    print(f"  ✓ Got session_resume event")
                    print(f"    State: {event.get('state')}")

    print("\n" + "=" * 60)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_websocket.py decode")
        print("  python test_websocket.py transmit --image path/to/image.jpg")
        print("  python test_websocket.py reconnect <session_id>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "decode":
        asyncio.run(test_decode_websocket())

    elif command == "transmit":
        if len(sys.argv) < 4 or sys.argv[2] != "--image":
            print("Error: transmit requires --image argument")
            print("Usage: python test_websocket.py transmit --image path/to/image.jpg")
            sys.exit(1)

        image_path = sys.argv[3]
        asyncio.run(test_transmit_websocket(image_path))

    elif command == "reconnect":
        if len(sys.argv) < 3:
            print("Error: reconnect requires session_id")
            print("Usage: python test_websocket.py reconnect <session_id>")
            sys.exit(1)

        session_id = sys.argv[2]
        asyncio.run(test_reconnection(session_id))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
