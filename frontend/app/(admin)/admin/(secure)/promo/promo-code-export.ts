import type {
  BulkGenerateResponse,
  CodeModalState,
  PromoCodeCsvRow,
  PromoItem,
} from "./promo-types";

function toPromoCodeCsvRow(item: PromoItem, fallbackCode: string | undefined): PromoCodeCsvRow {
  return {
    code: item.raw_code ?? fallbackCode ?? item.code,
    campaign_name: item.campaign_name,
    discount_type: item.discount_type,
    discount_value: item.discount_value,
    valid_until: item.valid_until,
  };
}

export function createSingleCodeModalState(item: PromoItem): CodeModalState {
  return {
    title: "Code sichern",
    campaignName: item.campaign_name,
    codes: item.raw_code ? [item.raw_code] : [],
    csvRows: item.raw_code ? [toPromoCodeCsvRow(item, item.raw_code)] : [],
  };
}

export function createBulkCodeModalState(
  campaignName: string,
  data: BulkGenerateResponse,
): CodeModalState {
  return {
    title: `${data.generated} Codes wurden erzeugt`,
    campaignName,
    codes: data.codes,
    csvRows: data.items.map((item, index) => toPromoCodeCsvRow(item, data.codes[index])),
  };
}

export async function copyPromoCodes(value: string) {
  await navigator.clipboard.writeText(value);
}

export function downloadPromoCodesCsv(rows: PromoCodeCsvRow[]) {
  const csvRows = [
    "code,campaign_name,discount_type,discount_value,valid_until",
    ...rows.map((row) =>
      [
        row.code,
        row.campaign_name,
        row.discount_type ?? "",
        row.discount_value ?? "",
        row.valid_until ?? "",
      ].join(","),
    ),
  ];

  const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "promo-codes.csv";
  link.click();
  URL.revokeObjectURL(url);
}
