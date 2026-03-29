import fs from "node:fs";
import path from "node:path";

const LAB_ROOT = path.resolve(process.cwd());
const ENV_PATH = path.join(LAB_ROOT, ".env.local");

function parseEnv(text) {
  const values = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eqIndex = line.indexOf("=");
    if (eqIndex === -1) continue;
    const key = line.slice(0, eqIndex).trim();
    let value = line.slice(eqIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

export function loadLabEnv() {
  if (!fs.existsSync(ENV_PATH)) {
    throw new Error(`Missing ${ENV_PATH}. Copy .env.example to .env.local first.`);
  }

  const parsed = parseEnv(fs.readFileSync(ENV_PATH, "utf8"));
  return {
    supabaseUrl: required(parsed, "SUPABASE_URL"),
    supabaseKey: required(parsed, "SUPABASE_KEY"),
    schema: parsed.SUPABASE_SCHEMA || "public",
    cameraTable: required(parsed, "SUPABASE_CAMERA_TABLE"),
    browserTable: required(parsed, "SUPABASE_BROWSER_TABLE"),
    cameraOrderColumn: parsed.SUPABASE_CAMERA_ORDER_COLUMN || null,
    browserOrderColumn: parsed.SUPABASE_BROWSER_ORDER_COLUMN || null,
    sampleLimit: Math.max(1, Number(parsed.SUPABASE_SAMPLE_LIMIT || 5)),
    labRoot: LAB_ROOT,
  };
}

function required(values, key) {
  const value = values[key];
  if (!value) {
    throw new Error(`Missing required env var: ${key}`);
  }
  return value;
}
