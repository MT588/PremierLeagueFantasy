"""Constants shared by the API and the ML package.

MODEL_VERSION lives here rather than in ml.train_v2 so the API can read it
without importing LightGBM/pandas/scikit-learn — that keeps the serverless
deployment bundle small enough to fit Vercel's size limit.

It names the version the API serves. Every generation writes its predictions
under its own version and the queries filter on this, so rolling back is a
one-line change with no data migration; older rows stay in the table.
"""

MODEL_VERSION = "lgbm-v3"

#: Previous generations, still runnable for comparison (ml.train_v2 / ml.train).
V2_VERSION = "lgbm-v2"
