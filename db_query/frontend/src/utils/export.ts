/**
 * Shared query-result export utilities (CSV / JSON).
 *
 * CSV escaping rules intentionally mirror the backend exporter
 * (backend/app/services/exporter.py): quote-minimal, `""` escaping,
 * nulls become empty strings, so a browser export and a server export
 * of the same query produce equivalent files.
 */

export type ExportFormat = "csv" | "json";

export interface ExportableResult {
  columns: Array<{ name: string; dataType: string }>;
  rows: Array<Record<string, any>>;
  rowCount: number;
}

export function timestampedFilename(databaseName: string, extension: string): string {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, -5);
  return `${databaseName}_${timestamp}.${extension}`;
}

export function buildCsvContent(result: ExportableResult): string {
  const headers = result.columns.map((col) => col.name);
  const escape = (value: any): string => {
    if (value === null || value === undefined) return "";
    const stringValue = String(value);
    if (stringValue.includes(",") || stringValue.includes('"') || stringValue.includes("\n")) {
      return `"${stringValue.replace(/"/g, '""')}"`;
    }
    return stringValue;
  };

  const lines = [headers.join(",")];
  result.rows.forEach((row) => {
    lines.push(headers.map((header) => escape(row[header])).join(","));
  });
  return lines.join("\n");
}

export function buildJsonContent(result: ExportableResult): string {
  return JSON.stringify(result.rows, null, 2);
}

export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8;` });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

const MIME_TYPES: Record<ExportFormat, string> = {
  csv: "text/csv",
  json: "application/json",
};

/** Build file content for the given format. */
export function buildContent(result: ExportableResult, format: ExportFormat): string {
  return format === "csv" ? buildCsvContent(result) : buildJsonContent(result);
}

/** Export a query result locally in the browser (no backend round-trip). */
export function exportResultLocally(
  result: ExportableResult,
  format: ExportFormat,
  databaseName: string
): string {
  const filename = timestampedFilename(databaseName, format);
  downloadFile(buildContent(result, format), filename, MIME_TYPES[format]);
  return filename;
}
