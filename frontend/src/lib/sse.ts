/** Mensaje de un flujo Server-Sent Events. */
export interface SseMessage {
  event: string;
  data: string;
}

const LINE_BREAK = /\r\n|\n|\r/;

/**
 * Lee un flujo SSE (`text/event-stream`) de una respuesta `fetch`. `EventSource` solo sirve para
 * GET y `/ask` es POST, así que se interpreta el protocolo a mano: trozos de cualquier tamaño,
 * caracteres UTF-8 partidos entre trozos, saltos CRLF, comentarios y varias líneas `data`.
 */
export async function* parseSse(stream: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let event = "message";
  let data: string[] = [];

  const dispatch = (): SseMessage | null => {
    const message = data.length > 0 ? { event, data: data.join("\n") } : null;
    event = "message";
    data = [];
    return message;
  };

  const readLine = (line: string): SseMessage | null => {
    if (line === "") return dispatch();
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    return null;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      while (true) {
        const match = LINE_BREAK.exec(buffer);
        if (!match) break;
        // Un "\r" al final del búfer puede ser la mitad de un "\r\n": se espera al siguiente trozo.
        if (match[0] === "\r" && match.index === buffer.length - 1 && !done) break;
        const line = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const message = readLine(line);
        if (message) yield message;
      }
      if (done) break;
    }
    if (buffer.length > 0) {
      const message = readLine(buffer);
      if (message) yield message;
    }
    const last = dispatch();
    if (last) yield last;
  } finally {
    reader.releaseLock();
  }
}
