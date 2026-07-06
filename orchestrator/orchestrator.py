from fastapi import FastAPI
from pydantic import BaseModel
import requests
from shared.secret_sharing import secret_sharing

app = FastAPI()

class Transaction(BaseModel):
    txn_id: str

# Orchestrator on 8000
# SBI ON PORT 8001
# HDFC ON PORT 8002
# NPCI ON PORT 8003

@app.post("/evaluate")
def evaluate(transaction: Transaction):
    
    #sbi
    sbi = requests.get(f"http://localhost:8001/features/{transaction.txn_id}")
    if(sbi.status_code!=200):
        return "SBI Server Down"
    
    #hdfc
    hdfc = requests.get(f"http://localhost:8002/features/{transaction.txn_id}")
    if(hdfc.status_code!=200):
        return "HDFC Server Down"
    
    #npci
    npci = requests.get(f"http://localhost:8003/features/{transaction.txn_id}")
    if(npci.status_code!=200):
        return "NPCI Server Down"
    
    transaction_details=sbi.json()|hdfc.json()|npci.json()

    #====Under Deliberation=====
    #shares=share_creation(transaction_details)
    #placeholder value 1
    return 1


#def share_creation(transaction_details):
    details_share=dict()
    for key, value in transaction_details.items():
        if isinstance(value, (int,float)):
            details_share[key]=secret_sharing(value)
    
    return details_share