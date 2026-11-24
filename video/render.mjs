// Render scenes.html frame by frame (deterministic time), pipe JPEGs to ffmpeg, then lay the narration on top.
//   node render.mjs              # out/sandesh-final.mp4
//   ONLY=12.5,40 node render.mjs # stills at those times
//   DECK=1 node render.mjs       # every scene's final state -> out/deck/*.jpg + out/sandesh-final-deck.pdf
import { spawn } from 'node:child_process'
import { writeFileSync, mkdirSync } from 'node:fs'
import { launch } from './cdp.mjs'

const FPS = Number(process.env.FPS ?? 30)
const only = process.env.ONLY
mkdirSync('out', { recursive: true })
const page = await launch({ width: 1920, height: 1080, scale: 1 })
await page.goto('file://' + process.cwd() + '/scenes.html')
console.log('fonts loaded', await page.eval('window.ready'))
const total = await page.eval('window.TOTAL')
const scenes = await page.eval('window.SCENES')
const overlays = await page.eval('window.OVERLAYS ?? []')
writeFileSync('out/scenes.json', JSON.stringify({ total, scenes }, null, 1))
console.log('total', total.toFixed(2), 's')

if (process.env.DECK) {
  mkdirSync('out/deck', { recursive: true })
  const ids = await page.eval('window.DECK')
  for (const [i, id] of ids.entries()) {
    await page.eval(`still(${JSON.stringify(id)})`)
    await page.shot(`out/deck/${String(i + 1).padStart(2, '0')}-${id}.jpg`, { format: 'jpeg', quality: 92 })
  }
  const imgs = ids.map((id, i) => `<img src="deck/${String(i + 1).padStart(2, '0')}-${id}.jpg">`).join('')
  writeFileSync('out/deck.html', `<!doctype html><style>@page{size:1920px 1080px;margin:0}html,body{margin:0}img{display:block;width:1920px;height:1080px;break-after:page}</style>${imgs}`)
  await page.goto('file://' + process.cwd() + '/out/deck.html')
  const pdf = await page.send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true, marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0 })
  writeFileSync('out/sandesh-final-deck.pdf', Buffer.from(pdf.data, 'base64'))
  console.log('deck', ids.length, 'slides -> out/sandesh-final-deck.pdf')
  await page.close(); process.exit(0)
}

if (only) {
  for (const t of only.split(',').map(Number)) {
    await page.eval(`render(${t})`)
    await page.shot(`out/still-${t}.png`)
  }
  await page.close(); process.exit(0)
}

const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', 'out/video-only.mp4'], { stdio: ['pipe', 'inherit', 'inherit'] })
const n = Math.ceil(total * FPS)
const t0 = Date.now()
for (let i = 0; i < n; i++) {
  await page.eval(`render(${(i / FPS).toFixed(4)})`)
  const buf = await page.shot(null, { format: 'jpeg', quality: 94 })
  if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r))
  if (i % 600 === 0) console.log(`frame ${i}/${n}  ${((Date.now() - t0) / 1000).toFixed(0)}s`)
}
ff.stdin.end()
await new Promise((r) => ff.on('close', r))
await page.close()

// Real video clips (the phone screen recording): masked to rounded corners and laid over the frames at their start time.
let video = 'out/video-only.mp4'
if (overlays.length) {
  const args = ['-y', '-loglevel', 'error', '-i', video], f = []
  let prev = '[0:v]'
  overlays.forEach((o, i) => {
    args.push('-i', o.clip, '-loop', '1', '-framerate', String(FPS), '-t', String(o.dur), '-i', o.mask)
    f.push(`[${2 * i + 2}:v]format=gray[m${i}]`, `[${2 * i + 1}:v]format=yuva420p[c${i}]`, `[c${i}][m${i}]alphamerge,setpts=PTS-STARTPTS+${o.start.toFixed(4)}/TB[o${i}]`,
      `${prev}[o${i}]overlay=x=${o.x}:y=${o.y}:eof_action=pass[v${i}]`)
    prev = `[v${i}]`
  })
  args.push('-filter_complex', f.join(';'), '-map', prev, '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', 'out/video-ov.mp4')
  await new Promise((res, rej) => {
    const p = spawn('ffmpeg', args, { stdio: 'inherit' })
    p.on('close', (c) => (c ? rej(new Error('overlay failed')) : res()))
  })
  video = 'out/video-ov.mp4'
  console.log('overlaid', overlays.length, 'clip(s)', ((Date.now() - t0) / 1000).toFixed(0), 's')
}

// Narration: each scene's wav starts at its audioAt.
const inputs = [], filters = []
scenes.forEach((s, i) => {
  inputs.push('-i', `audio/${s.id}.wav`)
  const ms = Math.round(s.audioAt * 1000)
  filters.push(`[${i}:a]aresample=48000,adelay=${ms}|${ms}[a${i}]`)
})
const mix = scenes.map((_, i) => `[a${i}]`).join('') + `amix=inputs=${scenes.length}:normalize=0,apad,atrim=0:${total.toFixed(3)},loudnorm=I=-16:TP=-1.5:LRA=11[out]`
await new Promise((res, rej) => {
  const p = spawn('ffmpeg', ['-y', '-loglevel', 'error', ...inputs, '-filter_complex', [...filters, mix].join(';'), '-map', '[out]', '-ac', '2', '-c:a', 'pcm_s16le', 'out/narration.wav'], { stdio: 'inherit' })
  p.on('close', (c) => (c ? rej(new Error('audio mix failed')) : res()))
})
await new Promise((res, rej) => {
  const p = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-i', video, '-i', 'out/narration.wav', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', 'out/sandesh-final.mp4'], { stdio: 'inherit' })
  p.on('close', (c) => (c ? rej(new Error('mux failed')) : res()))
})
console.log('done out/sandesh-final.mp4', ((Date.now() - t0) / 1000).toFixed(0), 's')
