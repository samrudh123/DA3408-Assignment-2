import joblib
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

VERSION = "v1"
MODEL_PATH = "model.joblib"

_model = None

app = FastAPI(title="Spam Detection API", version=VERSION)

class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, description="The message to classify")

@app.on_event("startup")
def load_model():
    global _model
    try:
        _model = joblib.load(MODEL_PATH)
    except Exception as e:
        print(f"Error loading model: {e}")
        _model = None

@app.get("/healthz")
def healthz():
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    return {
        "status": "ok",
        "version": VERSION,
    }


@app.post("/predict")
def predict(request: PredictRequest):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    text = request.text
    label = str(_model.predict([text])[0])
    return {"label": label}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
