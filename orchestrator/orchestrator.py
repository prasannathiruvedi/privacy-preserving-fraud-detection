from fastapi import FastAPI
from pydantic import BaseModel
import uuid

app = FastAPI()

#====Classes=====
class Session: 
    def __init__(self, txn_id):
        self.sessionID=uuid.uuid4()
        self.txnID=txn_id

class Transaction(BaseModel):
    txn_id:str

#====API Calls=====
@app.post("/evaluate")
def evaluate(txn_details:Transaction):
    evalSession=Session(txn_details.txn_id)
    return evalSession/