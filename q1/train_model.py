import argparse
import os

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

RANDOM_STATE = 42


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )),
        ("nb", MultinomialNB(alpha=0.1)),
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the spam-detection pipeline.")
    parser.add_argument("--data", help="labeled CSV: text,label")
    parser.add_argument("--out", help="path for the joblib artifact")
    args = parser.parse_args()

    df = pd.read_csv(args.data)
    print(f"Loaded {len(df)} rows from {args.data}")
    print(f"Label distribution:\n{df['label'].value_counts().to_string()}\n")

    final_pipeline = build_pipeline()
    final_pipeline.fit(df["text"], df["label"])
    joblib.dump(final_pipeline, args.out)

    size_kb = os.path.getsize(args.out) / 1024
    print(f"Saved model to {args.out} ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
