import fs from "node:fs";
import path from "node:path";

export async function fetchTableRows(config, table, { limit = 5, orderColumn = null } = {}) {
  const query = new URLSearchParams();
  query.set("select", "*");
  query.set("limit", String(limit));
  if (orderColumn) {
    query.set("order", `${orderColumn}.desc`);
  }

  const response = await fetch(`${config.supabaseUrl}/rest/v1/${table}?${query.toString()}`, {
    headers: restHeaders(config),
  });

  if (!response.ok) {
    throw new Error(`${table} sample query failed: ${response.status} ${await response.text()}`);
  }

  return response.json();
}

export async function fetchTableCount(config, table) {
  const response = await fetch(`${config.supabaseUrl}/rest/v1/${table}?select=*`, {
    method: "HEAD",
    headers: {
      ...restHeaders(config),
      Prefer: "count=exact",
    },
  });

  if (!response.ok) {
    throw new Error(`${table} count query failed: ${response.status} ${await response.text()}`);
  }

  const contentRange = response.headers.get("content-range");
  if (!contentRange || !contentRange.includes("/")) {
    return null;
  }

  const total = contentRange.split("/")[1];
  return total === "*" ? null : Number(total);
}

export function buildTableSummary(table, rows) {
  const fieldStats = new Map();

  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!fieldStats.has(key)) {
        fieldStats.set(key, { nonNull: 0, sampleValues: [] });
      }
      const stat = fieldStats.get(key);
      const value = row[key];
      if (value !== null && value !== undefined && value !== "") {
        stat.nonNull += 1;
        if (stat.sampleValues.length < 3) {
          stat.sampleValues.push(value);
        }
      }
    }
  }

  const fields = [...fieldStats.entries()]
    .map(([name, stat]) => ({
      name,
      non_null_ratio: rows.length ? Number((stat.nonNull / rows.length).toFixed(2)) : 0,
      sample_values: stat.sampleValues,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));

  return {
    table,
    sampled_row_count: rows.length,
    fields,
  };
}

export function writeReport(labRoot, report) {
  const outputDir = path.join(labRoot, "output");
  fs.mkdirSync(outputDir, { recursive: true });
  const fileName = `inspect-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  const filePath = path.join(outputDir, fileName);
  fs.writeFileSync(filePath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return filePath;
}

function restHeaders(config) {
  return {
    apikey: config.supabaseKey,
    Authorization: `Bearer ${config.supabaseKey}`,
    Accept: "application/json",
    "Accept-Profile": config.schema,
  };
}
