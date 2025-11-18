import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId
from typing import List, Optional

from database import db, create_document, get_documents
from schemas import Todo

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Todo API is running"}

@app.get("/schema")
def get_schema():
    # Return the available schemas for the database viewer
    return {
        "collections": [
            {
                "name": "todo",
                "schema": Todo.model_json_schema(),
            }
        ]
    }

# --------- Todo Endpoints ---------
class TodoCreate(BaseModel):
    title: str
    completed: bool = False
    notes: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[str] = None  # ISO string

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    completed: Optional[bool] = None
    notes: Optional[str] = None
    priority: Optional[int] = None
    due_date: Optional[str] = None


def todo_collection():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return db["todo"]

@app.get("/api/todos", response_model=List[dict])
def list_todos():
    docs = get_documents("todo", {})
    # Convert ObjectId to string
    for d in docs:
        d["id"] = str(d.pop("_id", ""))
        # Convert datetimes to isoformat strings
        for key in ["created_at", "updated_at", "due_date"]:
            if key in d and hasattr(d[key], "isoformat"):
                d[key] = d[key].isoformat()
    return docs

@app.post("/api/todos", status_code=201)
def create_todo(payload: TodoCreate):
    todo = Todo(
        title=payload.title,
        completed=payload.completed,
        notes=payload.notes,
        priority=payload.priority,
        # due_date omitted or parsed later
    )
    inserted_id = create_document("todo", todo)
    return {"id": inserted_id}

@app.patch("/api/todos/{todo_id}")
def update_todo(todo_id: str, payload: TodoUpdate):
    col = todo_collection()
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")

    update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        return {"updated": False}

    update_data["updated_at"] = __import__("datetime").datetime.utcnow()
    res = col.update_one({"_id": oid}, {"$set": update_data})
    return {"matched": res.matched_count, "modified": res.modified_count}

@app.delete("/api/todos/{todo_id}")
def delete_todo(todo_id: str):
    col = todo_collection()
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID")
    res = col.delete_one({"_id": oid})
    return {"deleted": res.deleted_count}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
