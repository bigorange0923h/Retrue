/** 按 SSE 帧解析 UTF-8 字节流；处理拆包、多帧、心跳及 CRLF，不进行自动重连。 */
export async function consumeSse(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: string) => boolean,
  onChunk: () => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      onChunk()
      buffer += decoder.decode(value, { stream: true })
      let boundary = /\r?\n\r?\n/.exec(buffer)
      while (boundary) {
        const frame = buffer.slice(0, boundary.index)
        if (frame.length > 1_000_000) throw new Error('进度消息过大')
        buffer = buffer.slice(boundary.index + boundary[0].length)
        let event = 'message'
        const data: string[] = []
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith('event:')) event = line.slice(6).replace(/^ /, '')
          if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
        }
        if (data.length && onEvent(event, data.join('\n'))) return
        boundary = /\r?\n\r?\n/.exec(buffer)
      }
      if (buffer.length > 1_000_000) throw new Error('进度消息过大')
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
