// Panda CSS configuration
import { defineConfig } from "@pandacss/dev"

export default defineConfig({
  preflight: true,
  include: ["./components/**/*.{js,jsx}"],
  theme: {
    extend: {},
  },
  outdir: "styled-system",
})
