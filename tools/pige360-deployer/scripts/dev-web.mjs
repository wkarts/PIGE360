#!/usr/bin/env node
import { spawn } from "node:child_process";

const args = process.argv.slice(2);
const lan = args.includes("--lan");
const host = process.env.VITE_DEV_HOST || process.env.PIGE360_DEPLOYER_WEB_HOST || "0.0.0.0";
const port = process.env.VITE_DEV_PORT || process.env.PIGE360_DEPLOYER_WEB_PORT || process.env.PORT || "61002";
const child = spawn(process.platform === "win32" ? "npx.cmd" : "npx", ["vite", "--host", host, "--port", port], { stdio: "inherit", env: { ...process.env, VITE_DEV_HOST: host, VITE_DEV_PORT: port } });
child.on("exit", code => process.exit(code ?? 0));
