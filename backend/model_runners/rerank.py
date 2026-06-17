import argparse
import contextlib
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local cross-encoder rerank and emit ranked chunk ids.")
    parser.add_argument("--model-dir", default="")
    parser.add_argument("--model-name", default="BAAI/bge-reranker-v2-m3")
    args = parser.parse_args()

    request = json.loads(sys.stdin.read())
    chunks = request.get("chunks", [])
    output_k = int(request.get("outputK") or len(chunks))
    if not chunks:
        print(json.dumps({"rankedChunkIds": []}))
        return

    model_ref = _model_ref(args.model_dir, args.model_name)
    pairs = [[str(request.get("query", "")), str(chunk.get("text", ""))] for chunk in chunks]
    with contextlib.redirect_stdout(sys.stderr):
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(model_ref, device="cpu")
        scores = model.predict(pairs)
    ranked = sorted(
        zip(chunks, [float(score) for score in scores], strict=False),
        key=lambda item: item[1],
        reverse=True,
    )
    print(json.dumps({"rankedChunkIds": [str(chunk["chunkId"]) for chunk, _ in ranked[:output_k]]}))


def _model_ref(model_dir: str, model_name: str) -> str:
    path = Path(model_dir) if model_dir else None
    if path and path.exists() and any(path.iterdir()):
        return str(path)
    return model_name


if __name__ == "__main__":
    main()
