/** The socket is a live feed, not a log (#151).
 *
 * `watchSession` reconnects on close, which was the easy half. The hard
 * half is that a reconnect is not a catch-up: whatever the engine sent
 * while the socket was down is gone, including the `decode_complete` or
 * `error` that ended the session. Without a read of `decode/status` on
 * connect, the window shows "listening" for a decode the engine finished
 * -- a session that looks healthy while nothing is happening, which is the
 * 2026-08-19 stall wearing different clothes.
 *
 * These tests are about the seam, not the React state: that `onOpen` fires
 * on the first connect and again on every reconnect, because that is the
 * contract App.tsx's `resync` depends on.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { decodeStatus, watchSession } from "./core";

/** Enough of a WebSocket to drop and come back. */
class FakeSocket {
  static live: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeSocket.live.push(this);
  }

  /** The browser calls this once the handshake finishes. */
  connect() {
    this.onopen?.();
  }

  deliver(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  drop() {
    this.onclose?.();
  }

  close() {
    this.closed = true;
  }

  static last() {
    return FakeSocket.live[FakeSocket.live.length - 1];
  }
}

describe("a session socket that drops", () => {
  beforeEach(() => {
    FakeSocket.live = [];
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("asks what it missed, every time it comes back", () => {
    const opened = vi.fn();
    const close = watchSession("abc", () => undefined, opened);

    FakeSocket.last().connect();
    expect(opened).toHaveBeenCalledTimes(1);

    // The engine finishes the decode while the socket is down. That event
    // is not redelivered -- which is the entire reason onOpen exists.
    FakeSocket.last().drop();
    vi.advanceTimersByTime(1000);
    expect(FakeSocket.live).toHaveLength(2);

    FakeSocket.last().connect();
    expect(opened).toHaveBeenCalledTimes(2);

    close();
  });

  it("stops reconnecting once the caller lets go", () => {
    const opened = vi.fn();
    const close = watchSession("abc", () => undefined, opened);

    FakeSocket.last().connect();
    close();
    FakeSocket.last().drop();
    vi.advanceTimersByTime(5000);

    // One socket, ever. A closer that does not actually close leaks a
    // reconnect loop per session for the life of the window.
    expect(FakeSocket.live).toHaveLength(1);
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it("survives a malformed frame without taking the session down", () => {
    const events: unknown[] = [];
    const close = watchSession("abc", (event) => events.push(event));

    FakeSocket.last().connect();
    FakeSocket.last().onmessage?.({ data: "not json" });
    FakeSocket.last().deliver({ event_type: "audio_levels", left_db: -42 });

    expect(events).toEqual([{ event_type: "audio_levels", left_db: -42 }]);
    close();
  });
});

describe("the status the window reconciles against", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads the session's terminal state and its picture", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              session_id: "abc",
              state: "completed",
              mode: "MartinM1",
              image_id: "img-1",
              error: null,
              progress_percent: 100,
              scanlines_received: 256,
              total_scanlines: 256,
              vis_detected: true,
            }),
        } as Response),
      ),
    );

    await expect(decodeStatus("abc")).resolves.toMatchObject({
      state: "completed",
      image_id: "img-1",
    });
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/decode/status/abc");
  });
});
