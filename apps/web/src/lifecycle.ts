const HEARTBEAT_MS = 4000

let timer: ReturnType<typeof setInterval> | null = null

function apiUrl(path: string) {
  const base = import.meta.env.VITE_API_BASE ?? ''
  return `${base}${path}`
}

async function ping() {
  try {
    await fetch(apiUrl('/api/heartbeat'), {
      method: 'POST',
      keepalive: true,
    })
  } catch {
    // Server may already be stopping.
  }
}

function notifyLeaving() {
  const url = apiUrl('/api/leaving')
  if (navigator.sendBeacon) {
    navigator.sendBeacon(url)
    return
  }
  void fetch(url, { method: 'POST', keepalive: true })
}

export function startLifecycleGuard() {
  void ping()
  if (timer) clearInterval(timer)
  timer = setInterval(() => {
    void ping()
  }, HEARTBEAT_MS)

  // On close OR refresh: start a short grace period.
  // Refresh resumes heartbeat and cancels shutdown; close does not.
  window.addEventListener('pagehide', notifyLeaving)
  window.addEventListener('beforeunload', notifyLeaving)
}

export function stopLifecycleGuard() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  window.removeEventListener('pagehide', notifyLeaving)
  window.removeEventListener('beforeunload', notifyLeaving)
}
