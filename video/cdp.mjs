// Minimal Chrome DevTools Protocol driver: launch headless Chrome, open a page, send commands.
import { spawn } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

export async function launch({ width = 1920, height = 1080, scale = 1, port = 9333 } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'svchrome-'))
  const proc = spawn(CHROME, [
    '--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`,
    `--window-size=${width},${height}`, '--hide-scrollbars', '--mute-audio', '--no-first-run',
    '--no-default-browser-check', '--force-color-profile=srgb', '--disable-gpu-vsync',
  ], { stdio: 'ignore' })
  let ver
  for (let i = 0; i < 100; i++) {
    try { ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); break } catch { await new Promise((r) => setTimeout(r, 100)) }
  }
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json()
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  let id = 0
  const pending = new Map()
  const listeners = []
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data)
    if (m.id && pending.has(m.id)) {
      const { res, rej } = pending.get(m.id)
      pending.delete(m.id)
      m.error ? rej(new Error(m.error.message)) : res(m.result)
    } else if (m.method) listeners.forEach((f) => f(m))
  })
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })) })
  const waitFor = (method) => new Promise((res) => { const f = (m) => { if (m.method === method) { listeners.splice(listeners.indexOf(f), 1); res(m.params) } }; listeners.push(f) })
  await send('Page.enable')
  await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile: false })
  const page = {
    send, waitFor,
    async goto(url) { const l = waitFor('Page.loadEventFired'); await send('Page.navigate', { url }); await l },
    async eval(expr) {
      const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text)
      return r.result.value
    },
    async shot(file, opts = {}) {
      const r = await send('Page.captureScreenshot', { format: opts.format ?? 'png', quality: opts.quality, optimizeForSpeed: true, captureBeyondViewport: false })
      const buf = Buffer.from(r.data, 'base64')
      if (file) (await import('node:fs')).writeFileSync(file, buf)
      return buf
    },
    async close() { try { ws.close() } catch {} proc.kill('SIGKILL') },
  }
  return page
}
