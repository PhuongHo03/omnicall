import { CheckCircle2, XCircle } from "lucide-react";

import { formatNumber, isRecord, labelize } from "../utils/jsonDisplay";

export function JsonValue({ value, depth }: { value: unknown; depth: number }) {
  if (value === null || value === undefined) {
    return <span className="json-null">null</span>;
  }
  if (typeof value === "boolean") {
    return value
      ? <span className="json-bool json-bool--true"><CheckCircle2 size={12} /> Yes</span>
      : <span className="json-bool json-bool--false"><XCircle size={12} /> No</span>;
  }
  if (typeof value === "number") {
    return <span className="json-number">{formatNumber(value)}</span>;
  }
  if (typeof value === "string") {
    return <JsonString value={value} />;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="json-empty">Empty</span>;
    }
    if (value.every((item) => typeof item !== "object" || item === null)) {
      return (
        <div className="json-tag-list">
          {value.map((item, index) => (
            <span key={index} className="json-tag">{String(item)}</span>
          ))}
        </div>
      );
    }
    return (
      <div className="json-card-list">
        {value.map((item, index) => (
          <div key={index} className="json-card">
            <JsonValue value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return <span className="json-empty">Empty</span>;
    }
    return (
      <dl className={depth > 0 ? "json-map json-map--nested" : "json-map"}>
        {entries.map(([key, entryValue]) => {
          const containsStructuredValue = isRecord(entryValue)
            || (Array.isArray(entryValue) && entryValue.some((item) => isRecord(item)));

          return (
            <div
              key={key}
              className={`json-map__row${containsStructuredValue ? " json-map__row--structured" : ""}`}
            >
              <dt>{labelize(key)}</dt>
              <dd>
                <JsonValue value={entryValue} depth={depth + 1} />
              </dd>
            </div>
          );
        })}
      </dl>
    );
  }
  return <span className="json-scalar">{String(value)}</span>;
}

function JsonString({ value }: { value: string }) {
  const isLongText = value.length > 120 || value.includes("\n");
  if (isLongText) {
    return <span className="json-text-block">{value}</span>;
  }
  return <span className="json-string">{value}</span>;
}
