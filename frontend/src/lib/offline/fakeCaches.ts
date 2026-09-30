/**
 * Test double for Cache Storage (jsdom has none): enough of `caches` for the pack manager
 * and the service worker fallback. Keys are absolute URLs; `match` ignores Vary like the
 * real call with { ignoreVary: true }. Used by the offline unit tests only.
 */
class FakeCache {
  readonly entries = new Map<string, Response>()

  private static url(req: RequestInfo | URL): string {
    return typeof req === 'string' ? req : req instanceof URL ? req.href : req.url
  }

  async match(req: RequestInfo | URL): Promise<Response | undefined> {
    return this.entries.get(FakeCache.url(req))?.clone()
  }

  async put(req: RequestInfo | URL, res: Response): Promise<void> {
    // A real Cache stores the body; read it now so the stored copy can be cloned freely.
    const body = await res.arrayBuffer()
    this.entries.set(
      FakeCache.url(req),
      new Response(body, { status: res.status, headers: res.headers }),
    )
  }

  async delete(req: RequestInfo | URL): Promise<boolean> {
    return this.entries.delete(FakeCache.url(req))
  }

  async keys(): Promise<Request[]> {
    return [...this.entries.keys()].map((k) => new Request(k))
  }
}

export class FakeCacheStorage {
  readonly stores = new Map<string, FakeCache>()
  /** When set, every put fails like a full disk (QuotaExceededError). */
  failPuts = false

  async open(name: string): Promise<Cache> {
    let cache = this.stores.get(name)
    if (!cache) {
      cache = new FakeCache()
      this.stores.set(name, cache)
    }
    if (this.failPuts) {
      cache.put = async () => {
        throw new DOMException('quota', 'QuotaExceededError')
      }
    }
    return cache as unknown as Cache
  }

  async has(name: string): Promise<boolean> {
    return this.stores.has(name)
  }

  async delete(name: string): Promise<boolean> {
    return this.stores.delete(name)
  }

  async keys(): Promise<string[]> {
    return [...this.stores.keys()]
  }

  async match(req: RequestInfo | URL): Promise<Response | undefined> {
    for (const c of this.stores.values()) {
      const hit = await c.match(req)
      if (hit) return hit
    }
    return undefined
  }

  asCacheStorage(): CacheStorage {
    return this as unknown as CacheStorage
  }
}

/**
 * Makes jsdom look like a browser that can keep well packs (Cache Storage + a service
 * worker container). Call the returned function to undo it.
 */
export function installPackSupport(): { storage: FakeCacheStorage; uninstall: () => void } {
  const storage = new FakeCacheStorage()
  Object.defineProperty(globalThis, 'caches', {
    value: storage.asCacheStorage(),
    configurable: true,
    writable: true,
  })
  Object.defineProperty(navigator, 'serviceWorker', { value: {}, configurable: true })
  return {
    storage,
    uninstall: () => {
      delete (globalThis as { caches?: unknown }).caches
      delete (navigator as { serviceWorker?: unknown }).serviceWorker
    },
  }
}
