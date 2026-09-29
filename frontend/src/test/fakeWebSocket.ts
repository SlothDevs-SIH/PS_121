/** A WebSocket stand-in for jsdom: tests find the socket by URL and drive it. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  readyState = 0
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  static find(part: string): FakeWebSocket | undefined {
    return [...FakeWebSocket.instances].reverse().find((s) => s.url.includes(part))
  }

  static reset() {
    FakeWebSocket.instances = []
  }

  open() {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }

  send() {}

  receive(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  close(code = 1000) {
    if (this.readyState === 3) return
    this.readyState = 3
    this.onclose?.(new CloseEvent('close', { code }))
  }
}
