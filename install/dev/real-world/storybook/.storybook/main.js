import fs from "node:fs"

export default {
    stories: ["../src/**/*.stories.jsx"],
    framework: {
        name: "@storybook/react-vite",
        options: {},
    },
    viteFinal(config) {
        return {
            ...config,
            plugins: [
                ...(config.plugins || []),
                {
                    name: "lpm-smoke-middleware",
                    configureServer(server) {
                        server.middlewares.use((request, response, next) => {
                            if (request.url === "/lpm-smoke") {
                                response.setHeader("content-type", "text/plain")
                                response.end("LPM Storybook smoke fixture")
                                return
                            }

                            if (request.url === "/lpm-bin-realpath") {
                                response.setHeader("content-type", "application/json")
                                response.end(
                                    JSON.stringify({
                                        argv1: process.argv[1],
                                        realpath: fs.realpathSync(process.argv[1]),
                                    }),
                                )
                                return
                            }

                            next()
                        })
                    },
                },
            ],
        }
    },
}
