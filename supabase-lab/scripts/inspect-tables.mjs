import { loadLabEnv } from "./_env.mjs";
import {
  buildTableSummary,
  fetchTableCount,
  fetchTableRows,
  writeReport,
} from "./_supabase.mjs";

async function inspectTarget(config, { label, table, orderColumn }) {
  const [count, rows] = await Promise.all([
    fetchTableCount(config, table),
    fetchTableRows(config, table, {
      limit: config.sampleLimit,
      orderColumn,
    }),
  ]);

  return {
    label,
    table,
    count,
    summary: buildTableSummary(table, rows),
    sample_rows: rows,
  };
}

async function main() {
  const config = loadLabEnv();
  const inspectedAt = new Date().toISOString();

  const targets = await Promise.all([
    inspectTarget(config, {
      label: "camera",
      table: config.cameraTable,
      orderColumn: config.cameraOrderColumn,
    }),
    inspectTarget(config, {
      label: "browser",
      table: config.browserTable,
      orderColumn: config.browserOrderColumn,
    }),
  ]);

  const report = {
    inspected_at: inspectedAt,
    project_url: config.supabaseUrl,
    schema: config.schema,
    sample_limit: config.sampleLimit,
    targets,
  };

  const filePath = writeReport(config.labRoot, report);

  console.log(JSON.stringify(report, null, 2));
  console.log(`\nSaved report to ${filePath}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
