import { describe, expect, it } from "vitest";

import { parseSse, type SseMessage } from "./sse";

const encoder = new TextEncoder();

function streamOf(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

function split(bytes: Uint8Array, size: number): Uint8Array[] {
  const out: Uint8Array[] = [];
  for (let i = 0; i < bytes.length; i += size) out.push(bytes.slice(i, i + size));
  return out;
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SseMessage[]> {
  const out: SseMessage[] = [];
  for await (const message of parseSse(stream)) out.push(message);
  return out;
}

const SAMPLE =
  'event: sources\ndata: {"a":1}\n\nevent: token\ndata: {"text":"¿Qué es un semáforo? ñ"}\n\n' +
  'event: done\ndata: {"ok":true}\n\n';

describe("parseSse", () => {
  it("parses complete events", async () => {
    const messages = await collect(streamOf([encoder.encode(SAMPLE)]));
    expect(messages.map((m) => m.event)).toEqual(["sources", "token", "done"]);
    expect(JSON.parse(messages[1]!.data)).toEqual({ text: "¿Qué es un semáforo? ñ" });
  });

  it.each([1, 2, 3, 5, 7, 13])("gives the same result whatever the chunk size (%i bytes)", async (size) => {
    const bytes = encoder.encode(SAMPLE);
    const whole = await collect(streamOf([bytes]));
    const chunked = await collect(streamOf(split(bytes, size)));
    expect(chunked).toEqual(whole);
  });

  it("does not corrupt multi-byte characters split across chunks", async () => {
    const bytes = encoder.encode('event: token\ndata: {"text":"¿ñ—é?"}\n\n');
    const messages = await collect(streamOf(split(bytes, 1)));
    expect(JSON.parse(messages[0]!.data)).toEqual({ text: "¿ñ—é?" });
  });

  it("accepts CRLF line endings", async () => {
    const messages = await collect(streamOf([encoder.encode("event: a\r\ndata: 1\r\n\r\n")]));
    expect(messages).toEqual([{ event: "a", data: "1" }]);
  });

  it("joins several data lines with a newline", async () => {
    const messages = await collect(streamOf([encoder.encode("event: a\ndata: uno\ndata: dos\n\n")]));
    expect(messages[0]!.data).toBe("uno\ndos");
  });

  it("ignores comments and unknown fields", async () => {
    const messages = await collect(
      streamOf([encoder.encode(": latido\nid: 7\nretry: 100\nevent: a\ndata: x\n\n")]),
    );
    expect(messages).toEqual([{ event: "a", data: "x" }]);
  });

  it("defaults the event name to 'message'", async () => {
    const messages = await collect(streamOf([encoder.encode("data: x\n\n")]));
    expect(messages[0]!.event).toBe("message");
  });

  it("delivers a last event even if the stream ends without a blank line", async () => {
    const messages = await collect(streamOf([encoder.encode("event: done\ndata: {}")]));
    expect(messages).toEqual([{ event: "done", data: "{}" }]);
  });

  it("yields nothing for an empty stream", async () => {
    expect(await collect(streamOf([]))).toEqual([]);
  });
});
