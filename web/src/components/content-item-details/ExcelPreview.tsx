import { useState, useEffect } from "react";
import * as XLSX from "xlsx";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { reportClientError } from "@/lib/report-client-error";

interface ExcelPreviewProps {
  url: string;
  onError: (error: boolean) => void;
}

interface ExcelSheetPreview {
  name: string;
  rows: string[][];
}

const cellToText = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "";
  }
  if (value instanceof Date) {
    return value.toLocaleString();
  }
  return String(value);
};

const columnLabel = (index: number): string => {
  let label = "";
  let value = index + 1;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
};

export const ExcelPreview = ({ url, onError }: ExcelPreviewProps) => {
  const [sheets, setSheets] = useState<ExcelSheetPreview[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSheet, setActiveSheet] = useState<string>("");

  useEffect(() => {
    const loadExcel = async () => {
      try {
        setLoading(true);
        const response = await fetch(url);
        if (!response.ok) throw new Error("Failed to fetch file");

        const arrayBuffer = await response.arrayBuffer();
        const workbook = XLSX.read(arrayBuffer, { type: "array" });

        const sheetData = workbook.SheetNames.map((name) => {
          const worksheet = workbook.Sheets[name];
          const rawRows = XLSX.utils.sheet_to_json<unknown[]>(worksheet, {
            header: 1,
            raw: false,
            blankrows: false,
            defval: "",
          });
          const columnCount = Math.max(0, ...rawRows.map((row) => row.length));
          const rows = rawRows.map((row) =>
            Array.from({ length: columnCount }, (_, index) => cellToText(row[index])),
          );
          return { name, rows };
        });

        setSheets(sheetData);
        if (sheetData.length > 0) {
          setActiveSheet(sheetData[0].name);
        }
      } catch (error) {
        reportClientError(error, undefined, { routeName: "preview:excel" });
        onError(true);
      } finally {
        setLoading(false);
      }
    };

    loadExcel();
  }, [url, onError]);

  if (loading) return <Skeleton className="w-full h-full" />;
  if (sheets.length === 0) return null;

  return (
    <div className="flex flex-col h-full w-full bg-background overflow-hidden">
      <Tabs value={activeSheet} onValueChange={setActiveSheet} className="flex flex-col h-full">
        <div className="border-b px-4 bg-muted/20">
          <TabsList className="h-10 bg-transparent p-0 gap-4">
            {sheets.map((sheet) => (
              <TabsTrigger
                key={sheet.name}
                value={sheet.name}
                className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent shadow-none"
              >
                {sheet.name}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        {sheets.map((sheet) => (
          <TabsContent key={sheet.name} value={sheet.name} className="flex-1 m-0 overflow-hidden">
            <div className="h-full w-full overflow-auto">
              <div className="p-4 excel-table-container">
                <table>
                  <thead>
                    <tr>
                      <th className="excel-row-header" aria-label="Row" />
                      {(sheet.rows[0] ?? []).map((_, columnIndex) => (
                        <th key={columnIndex}>{columnLabel(columnIndex)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sheet.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        <th className="excel-row-header" scope="row">
                          {rowIndex + 1}
                        </th>
                        {row.map((cell, columnIndex) => (
                          <td key={columnIndex}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </TabsContent>
        ))}
      </Tabs>

      <style>{`
                .excel-table-container table {
                    border-collapse: collapse;
                    width: max-content;
                    min-width: 100%;
                    font-size: 12px;
                    color: hsl(var(--foreground));
                    font-family: ui-sans-serif, system-ui, sans-serif;
                }
                .excel-table-container th {
                    background-color: hsl(var(--muted));
                    font-weight: 600;
                    color: hsl(var(--muted-foreground));
                    position: sticky;
                    top: 0;
                    z-index: 1;
                }
                .excel-table-container .excel-row-header {
                    left: 0;
                    min-width: 44px;
                    text-align: right;
                    z-index: 2;
                }
                .excel-table-container thead .excel-row-header {
                    z-index: 3;
                }
                .excel-table-container th, .excel-table-container td {
                    border: 1px solid hsl(var(--border));
                    padding: 4px 8px;
                    text-align: left;
                    min-width: 60px;
                    white-space: nowrap;
                }
                .excel-table-container tr:nth-child(even) {
                    background-color: hsl(var(--muted) / 0.5);
                }
                .excel-table-container tr:hover td {
                    background-color: hsl(var(--accent));
                }
            `}</style>
    </div>
  );
};
