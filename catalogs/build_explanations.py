"""Build data/explanations.json from catalogs/explanations_src.yaml (sources = ordered union of cited source keys)."""
import os, sys, yaml
from config import *
from common import write_json

def build():
    y = yaml.safe_load(open(os.path.join(AMNA, "explanations_src.yaml"), encoding="utf-8"))
    src = y["sources"]
    errors = []

    def entry(path, e):
        texts, keys = [], []
        for i, s in enumerate(e["sentences"]):
            if s["f"] and not s["s"]:
                errors.append(f"{path} sentence {i+1}: factual but no source: {s['t']}")
            for k in s["s"]:
                if k not in src:
                    errors.append(f"{path}: unknown source key {k}")
                elif k not in keys:
                    keys.append(k)
            texts.append(s["t"].strip())
        return {"title": e["title"], "text": " ".join(texts),
                "sources": [{"label": src[k]["label"], "url": src[k]["url"]} for k in keys if k in src]}

    out = {
        "types": {k: entry(f"types.{k}", y["types"][k]) for k in ALLOWED_TYPES},
        "verdicts": {k: entry(f"verdicts.{k}", y["verdicts"][k]) for k in VERDICTS},
        "targets": {k: entry(f"targets.{k}", y["targets"][k]) for k in TARGETS},
        "about": {k: entry(f"about.{k}", y["about"][k]) for k in ("how_it_works", "limits")},
    }
    for sect, keys in (("types", ALLOWED_TYPES), ("verdicts", VERDICTS), ("targets", list(TARGETS))):
        extra = set(y[sect]) - set(keys)
        if extra:
            errors.append(f"{sect}: unexpected keys {extra}")
    if errors:
        print("\n".join(errors)); sys.exit(1)
    write_json(os.path.join(DATA, "explanations.json"), out)
    print("wrote data/explanations.json:", {k: len(v) for k, v in out.items()})
    for sect in ("types", "targets", "about"):
        for k, v in out[sect].items():
            nsent = v["text"].count(". ") + 1
            print(f"  {sect}.{k}: ~{nsent} sentences, {len(v['sources'])} sources")

if __name__ == "__main__":
    build()
