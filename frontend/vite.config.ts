import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { defineConfig, type Plugin } from 'vite'

const root = path.dirname(fileURLToPath(import.meta.url))

function whatsappUiSrc() {
  const candidates = ['../../whatsapp/ui/src', '../../../whatsapp/ui/src', 'vendor/whatsapp-ui/src'].map(
    (entry) => path.resolve(root, entry),
  )
  return candidates.find((entry) => fs.existsSync(path.join(entry, 'index.ts')))
}

const whatsappUi = whatsappUiSrc()
if (!whatsappUi) {
  throw new Error('WhatsApp UI source is missing. Expected apps/whatsapp/ui or frontend/vendor/whatsapp-ui.')
}

/** Dev-server stand-in for `/api/method/upload_file`, so sample threads can attach a file. */
function sampleMediaUpload(): Plugin {
  return {
    name: 'sample-media-upload',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url?.split('?')[0]
        if (req.method !== 'POST' || url !== '/api/method/upload_file') {
          next()
          return
        }
        const chunks: Buffer[] = []
        req.on('data', (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)))
        req.on('error', () => next())
        req.on('end', () => {
          try {
            const file = readMultipartFile(Buffer.concat(chunks), String(req.headers['content-type'] || ''))
            if (!file) {
              res.statusCode = 400
              res.setHeader('Content-Type', 'application/json')
              res.end(JSON.stringify({ message: 'No file was uploaded.' }))
              return
            }
            const mime = file.mime || 'application/octet-stream'
            const payload = {
              message: {
                file_url: `data:${mime};base64,${file.data.toString('base64')}`,
                file_name: file.name,
                file_size: file.data.length,
              },
            }
            res.statusCode = 200
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(payload))
          } catch {
            res.statusCode = 400
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ message: 'Could not read the upload.' }))
          }
        })
      })
    },
  }
}

function readMultipartFile(body: Buffer, contentType: string) {
  const boundary = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType)?.[1]
    || /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType)?.[2]
  if (!boundary) return null
  const marker = Buffer.from(`--${boundary.trim()}`)
  let start = 0
  while (start < body.length) {
    const at = body.indexOf(marker, start)
    if (at === -1) break
    const next = body.indexOf(marker, at + marker.length)
    if (next === -1) break
    const part = body.subarray(at + marker.length, next)
    const headerEnd = part.indexOf('\r\n\r\n')
    if (headerEnd !== -1) {
      const header = part.subarray(0, headerEnd).toString('utf8')
      if (/filename=/.test(header)) {
        const name = /filename="([^"]*)"/.exec(header)?.[1]
          || /filename=([^;\r\n]+)/.exec(header)?.[1]
          || 'file'
        const mime = /Content-Type:\s*([^\r\n]+)/i.exec(header)?.[1]?.trim()
        let data = part.subarray(headerEnd + 4)
        if (data.subarray(-2).toString() === '\r\n') data = data.subarray(0, -2)
        return { name, mime, data }
      }
    }
    start = next
  }
  return null
}

export default defineConfig(({ command, mode }) => {
  const frappeBuild = command === 'build' && mode === 'frappe'
  return {
    plugins: [
      frappeui({
        frontendRoute: '/nudg',
        lucideIcons: true,
        frappeProxy: { port: 4178 },
        jinjaBootData: frappeBuild,
        buildConfig: frappeBuild
          ? {
              outDir: '../nudg/public/frontend',
              indexHtmlPath: '../nudg/www/nudg.html',
              baseUrl: '/assets/nudg/frontend/',
            }
          : false,
      }),
      vue(),
      sampleMediaUpload(),
    ],
    base: frappeBuild ? '/assets/nudg/frontend/' : '/',
    resolve: {
      alias: {
        '@': path.resolve(root, 'src'),
        '@whatsapp/ui': whatsappUi,
      },
      dedupe: ['vue', 'frappe-ui', 'reka-ui', 'dompurify'],
    },
    server: {
      host: '0.0.0.0',
      port: 4178,
      strictPort: true,
    },
  }
})
