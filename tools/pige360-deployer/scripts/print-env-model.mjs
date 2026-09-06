#!/usr/bin/env node
import fs from "node:fs";
const file = new URL("../.env.model", import.meta.url);
console.log(fs.readFileSync(file, "utf8"));
