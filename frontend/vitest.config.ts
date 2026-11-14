import { defineConfig, mergeConfig, type UserConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default defineConfig(async (env) => {
  const resolved = typeof viteConfig === 'function' ? await viteConfig({ command: 'serve', mode: env.mode }) : viteConfig
  return mergeConfig(resolved as UserConfig, {
    ssr: {
      noExternal: ['frappe-ui'],
    },
    test: {
      environment: 'happy-dom',
      include: ['src/**/*.test.ts'],
      testTimeout: 15000,
      server: {
        deps: {
          inline: ['frappe-ui'],
        },
      },
    },
  })
})
