const fs = require("node:fs")
const HtmlWebpackPlugin = require("html-webpack-plugin")

module.exports = {
    mode: "development",
    entry: "./src/index.js",
    plugins: [
        new HtmlWebpackPlugin({
            templateContent:
                '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>LPM Webpack smoke</title></head><body><main>LPM Webpack dev server smoke fixture</main></body></html>',
        }),
    ],
    devServer: {
        host: "127.0.0.1",
        port: Number(process.env.PORT || 8080),
        allowedHosts: "all",
        setupMiddlewares(middlewares, devServer) {
            devServer.app.get("/lpm-bin-realpath", (_request, response) => {
                response.json({
                    argv1: process.argv[1],
                    realpath: fs.realpathSync(process.argv[1]),
                })
            })
            return middlewares
        },
    },
}
