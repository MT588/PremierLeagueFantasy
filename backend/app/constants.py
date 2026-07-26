"""Constants shared by the API and the ML package.

MODEL_VERSION lives here rather than in ml.train_v2 so the API can read it
without importing LightGBM/pandas/scikit-learn — that keeps the serverless
deployment bundle small enough to fit Vercel's size limit.
"""

MODEL_VERSION = "lgbm-v2"
