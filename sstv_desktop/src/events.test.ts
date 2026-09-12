/** Every event is accounted for, and an unknown one says so (#145).
 *
 * The union used to end in `| { event_type: string }` -- a member matching
 * every frame. TypeScript therefore read the `default`-less switch as
 * exhaustive, so the compiler saw nothing wrong while seven of the
 * engine's twelve event types fell on the floor. A literal
 * `"__unknown__"` discriminant is what makes the gap expressible.
 *
 * These tests are about the labelling seam, because that is what decides
 * whether a frame reaches a `case` at all.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { watchApp, watchSession, type AppEvent, type SessionEvent } from "./core";

class FakeSocket {
  static live: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    FakeSocket.live.push(this);
  }

  deliver(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  close() {}

  static last() {
    return FakeSocket.live[FakeSocket.live.length - 1];
  }
}

beforeEach(() => {
  FakeSocket.live = [];
  vi.stubGlobal("WebSocket", FakeSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the session socket", () => {
  /** Every event type the engine broadcasts to a session, from
   *  api/models.py, plus library_updated which goes to both sockets. */
  const CARRIED = [
    "audio_levels",
    "vis_detected",
    "scanline_update",
    "decode_complete",
    "error",
    "tx_progress",
    "transmit_complete",
    "library_updated",
  ];

  it.each(CARRIED)("keeps %s as itself", (eventType) => {
    const seen: SessionEvent[] = [];
    const close = watchSession("abc", (event) => seen.push(event));

    FakeSocket.last().deliver({ event_type: eventType });

    expect(seen).toHaveLength(1);
    expect(seen[0].event_type).toBe(eventType);
    close();
  });

  it("labels an event this build has never heard of", () => {
    // A newer engine. The window must be able to tell "I don't handle
    // this" from "I handled it by doing nothing" -- the first is a gap,
    // the second is a decision.
    const seen: SessionEvent[] = [];
    const close = watchSession("abc", (event) => seen.push(event));

    FakeSocket.last().deliver({ event_type: "doppler_lock", hz: 12 });

    expect(seen[0].event_type).toBe("__unknown__");
    expect(seen[0]).toMatchObject({
      raw: { event_type: "doppler_lock", hz: 12 },
    });
    close();
  });

  it("does not pass a spectrum frame off as a session event", () => {
    // spectrum_update belongs to the app channel. If it ever arrives here
    // it is unknown, not silently accepted.
    const seen: SessionEvent[] = [];
    const close = watchSession("abc", (event) => seen.push(event));

    FakeSocket.last().deliver({ event_type: "spectrum_update" });

    expect(seen[0].event_type).toBe("__unknown__");
    close();
  });
});

describe("the app channel", () => {
  const CARRIED = [
    "spectrum_update",
    "device_changed",
    "monitor_state",
    "library_updated",
  ];

  it.each(CARRIED)("keeps %s as itself", (eventType) => {
    const seen: AppEvent[] = [];
    const close = watchApp((event) => seen.push(event));

    FakeSocket.last().deliver({ event_type: eventType });

    expect(seen[0].event_type).toBe(eventType);
    close();
  });

  it("labels a session event arriving on the wrong socket", () => {
    const seen: AppEvent[] = [];
    const close = watchApp((event) => seen.push(event));

    FakeSocket.last().deliver({ event_type: "scanline_update" });

    expect(seen[0].event_type).toBe("__unknown__");
    close();
  });

  it("survives a frame with no event_type at all", () => {
    const seen: AppEvent[] = [];
    const close = watchApp((event) => seen.push(event));

    FakeSocket.last().deliver({ hello: true });

    expect(seen[0].event_type).toBe("__unknown__");
    close();
  });
});
