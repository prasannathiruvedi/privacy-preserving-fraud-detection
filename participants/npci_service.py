from fastapi import FastAPI
import json

with open("../data/npci.json", "r") as file:
    data=json.load(file)

app = FastAPI()

@app.get("/features/{txn_id}")
def get_features(txn_id: str):
    if txn_id in data:
        return data[txn_id]
    else:
        return {"error": "Transaction ID not found"}