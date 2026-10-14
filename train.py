#!/usr/bin/env python3
"""Train Bible NLP classifiers from the existing KJV study CSVs.

SWORD remains the reading text. These models only classify a pasted line:
  - testament: OT vs NT
  - book: one of 66 books
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
MINI = Path(
    "/Users/ebrown63/Desktop/Computer Science Projects/rightAI/"
    "Bible-NLP-and-ML-using-Python/Bible-Verse-Prediction-Machine-Learning-App/"
    "data/kjvmindata.csv"
)
NLP = Path(
    "/Users/ebrown63/Desktop/Computer Science Projects/projectFile1/kjv_final1.csv"
)


def load_frame() -> pd.DataFrame:
    mini = pd.read_csv(MINI)
    nlp = pd.read_csv(NLP)
    # kjvmindata label 0 = OT, 1 = NT (original notebook split at verse 23145)
    df = mini[["id", "book", "chapter", "verse", "text", "label"]].copy()
    extra = nlp[
        ["id", "verse_length", "verse_polarity", "verse_subjectivity", "named_entities"]
    ]
    df = df.merge(extra, on="id", how="left")
    df["text"] = df["text"].fillna("").astype(str)
    df["testament"] = df["label"].map({0.0: "OT", 1.0: "NT", 0: "OT", 1: "NT"})
    # fallback if label missing
    ot_books = set(df.loc[df["testament"] == "OT", "book"].dropna().unique())
    mask = df["testament"].isna()
    df.loc[mask, "testament"] = df.loc[mask, "book"].map(
        lambda b: "OT" if b in ot_books else "NT"
    )
    return df


def make_text_clf() -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=2,
                    max_features=40000,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=400,
                    class_weight="balanced",
                ),
            ),
        ]
    )


def train_one(df: pd.DataFrame, ycol: str, name: str) -> dict:
    X = df["text"]
    y = df[ycol].astype(str)
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    pipe = make_text_clf()
    pipe.fit(Xtr, ytr)
    pred = pipe.predict(Xte)
    acc = float(accuracy_score(yte, pred))
    MODELS.mkdir(exist_ok=True)
    joblib.dump(pipe, MODELS / f"{name}.joblib")
    report = classification_report(yte, pred, output_dict=True, zero_division=0)
    print(f"{name} accuracy={acc:.4f} n_train={len(Xtr)} n_test={len(Xte)}")
    return {"name": name, "accuracy": acc, "n_train": len(Xtr), "n_test": len(Xte), "macro_f1": report["macro avg"]["f1-score"]}


def main() -> None:
    df = load_frame()
    print(f"rows={len(df)} books={df['book'].nunique()} testaments={df['testament'].value_counts().to_dict()}")
    metrics = {
        "testament": train_one(df, "testament", "testament"),
        "book": train_one(df, "book", "book"),
        "source_mini": str(MINI),
        "source_nlp": str(NLP),
        "note": "Canonical verse text is SWORD. This model is study-only (paste a line, guess book/testament).",
    }
    (MODELS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"wrote {MODELS}")


if __name__ == "__main__":
    main()
