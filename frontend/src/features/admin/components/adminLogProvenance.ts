import type { AdminOperationalLog } from "../types/adminTypes";

export type AdminLogProvenanceRow = [label: string, value: string];

export function adminLogProvenanceRows(event: AdminOperationalLog): AdminLogProvenanceRow[] {
  const type = event.executorType;
  const effectiveProvider = event.effectiveProvider ?? event.provider;
  const effectiveModel = event.effectiveModel ?? event.model;
  const rows: Array<[string, string | null]> = [["Executor", executorLabel(type)]];

  if (type === "vector_store") {
    rows.push(["Vector Store", effectiveProvider], ["Collection", event.resource]);
  } else if (type === "embedding") {
    rows.push(["Embedding Provider", effectiveProvider], ["Embedding Model", effectiveModel]);
  } else if (type === "rule") {
    rows.push(["Rule Engine", effectiveProvider], ["Rule", event.resource]);
  } else if (type === "cache") {
    const served = event.details.served === true;
    if (served && event.originProvider) {
      rows.push(
        ["Answer Provider", event.originProvider],
        ["Answer Model", event.originModel],
        ["Cache Store", effectiveProvider],
        ["Cache", event.resource]
      );
    } else {
      rows.push(["Cache Store", effectiveProvider], ["Cache", event.resource]);
    }
  } else if (type === "worker") {
    rows.push(["Worker / Queue", effectiveProvider], ["Resource", event.resource]);
  } else if (type === "asr") {
    rows.push(["ASR Provider", effectiveProvider], ["ASR Model", effectiveModel]);
  } else if (type === "diarization") {
    rows.push(["Diarization Provider", effectiveProvider], ["Diarization Model", effectiveModel]);
  } else if (type === "audio_processing") {
    rows.push(["Implementation", effectiveProvider], ["Version", event.version]);
  } else if (type === "local") {
    rows.push(["Implementation", effectiveProvider], ["Component", event.resource]);
  } else if (type === "guardrail") {
    rows.push(["Guardrail Provider", effectiveProvider], ["Guardrail Model", effectiveModel]);
  } else if (type === "llm") {
    rows.push(["LLM Provider", effectiveProvider], ["LLM Model", effectiveModel]);
  } else {
    rows.push(["Provider", effectiveProvider], ["Model", effectiveModel], ["Resource", event.resource]);
  }

  if (event.version && type !== "audio_processing") rows.push(["Version", event.version]);
  if (event.operation) rows.push(["Operation", event.operation]);
  if (event.fallbackUsed === true) rows.push(["Fallback", "Used"]);

  return rows.filter((row): row is AdminLogProvenanceRow => typeof row[1] === "string" && Boolean(row[1]));
}

export function adminLogProvenanceSummary(event: AdminOperationalLog): AdminLogProvenanceRow[] {
  return adminLogProvenanceRows(event).filter(([label]) => label !== "Executor" && label !== "Operation").slice(0, 3);
}

function executorLabel(type: string | null): string | null {
  if (!type) return null;
  const labels: Record<string, string> = {
    llm: "LLM",
    embedding: "Embedding",
    vector_store: "Vector store",
    guardrail: "Guardrail",
    rule: "Rule",
    worker: "Worker",
    cache: "Cache",
    asr: "Speech recognition",
    diarization: "Speaker diarization",
    audio_processing: "Audio processing",
    pipeline: "Pipeline",
    local: "Local logic"
  };
  return labels[type] ?? type;
}
