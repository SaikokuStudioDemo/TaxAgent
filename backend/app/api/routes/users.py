from fastapi import APIRouter, Depends, HTTPException, status
from app.models.user import CorporateUserCreate, CorporateUserInDB
from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_corporate_user(
    payload: CorporateUserCreate,
    # In a real app, the frontend sends the Firebase Token in the Authorization header
    # and this dependency validates it and extracts the Firebase UID.
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint to save a newly registered Corporate or Tax Firm entity.
    """
    db = get_database()
    firebase_uid = current_user.get("uid")
    
    if not firebase_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    # Check if a corporate record with this Firebase UID already exists
    existing = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if existing:
        raise HTTPException(status_code=400, detail="User profile already exists in DB")

    # Construct the DB record matching the Pydantic schema
    db_record = CorporateUserInDB(
        firebase_uid=firebase_uid,
        corporateType=payload.corporateType,
        companyUrl=payload.companyUrl,
        maIntent=payload.maIntent,
        planId=payload.planId,
        selectedOptions=payload.selectedOptions,
        monthlyFee=payload.monthlyFee,
        sales_agent_id=payload.sales_agent_id,
        referrer_id=payload.referrer_id,
        advising_tax_firm_id=payload.advising_tax_firm_id
    )

    # Insert into MongoDB（戻り値から _id を取得）
    result = await db["corporates"].insert_one(db_record.model_dump())
    corporate_id = str(result.inserted_id)
    print(f">>> REGISTERED CORPORATE: UID={firebase_uid}, TYPE={payload.corporateType}")

    # company_profiles のデフォルトレコードを自動生成
    await db["company_profiles"].insert_one({
        "corporate_id": corporate_id,
        "profile_name": "メインプロファイル",
        "company_name": payload.companyName or "",
        "phone": payload.phone or None,
        "address": payload.address or None,
        "registration_number": payload.registrationNumber or None,
        "is_default": True,
        "created_at": datetime.utcnow()
    })
    print(f">>> CREATED DEFAULT COMPANY_PROFILE: CORPORATE_ID={corporate_id}")

    # ─── Stripe Customer 作成（失敗してもロールバックしない） ──────────
    # ③④ Pydantic モデルのフィールドに直接アクセス
    # email は CorporateUserCreate に存在しないため空文字
    from app.services.stripe_service import create_stripe_customer
    billing_type = (
        "tax_firm_covered" if payload.advising_tax_firm_id else "self_pay"
    )
    stripe_customer_id = await create_stripe_customer(
        firebase_uid=firebase_uid,
        email="",
        name=payload.companyName or "",
    )
    if stripe_customer_id:
        await db["corporates"].update_one(
            {"firebase_uid": firebase_uid},
            {"$set": {
                "stripe_customer_id": stripe_customer_id,
                "billing_type": billing_type,
            }},
        )
        print(f">>> STRIPE CUSTOMER CREATED: {stripe_customer_id}")

    return {"message": "Corporate profile successfully linked to Firebase Auth.", "data": db_record.model_dump()}

@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def register_employee(
    payload: list[dict], # Receive a list of employees for batch registration
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint to save employee records for a parent corporate/tax firm entity.
    """
    db = get_database()
    parent_uid = current_user.get("uid")
    
    if not parent_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    # Use the shared internal sync function
    return await _sync_employees_internal(parent_uid, payload)

async def _sync_employees_internal(parent_uid: str, payload: list[dict]):
    """
    Shared logic to create or update an employee in Firebase Auth, Firestore, and MongoDB.
    Checks if the user exists first. If new, creates them and sends a password reset email.
    """
    db = get_database()
    from app.models.user import EmployeeUserInDB
    from firebase_admin import auth, firestore
    from app.core.config import settings
    import httpx

    # Resolve corporate_id (ObjectId string) from the parent's firebase_uid
    parent_corp = await db["corporates"].find_one({"firebase_uid": parent_uid}, {"_id": 1})
    if not parent_corp:
        raise HTTPException(status_code=404, detail="Parent corporate not found")
    corporate_id = str(parent_corp["_id"])

    fs_db = firestore.client()
    processed = []

    for emp_data in payload:
        emp_email = emp_data["email"]
        
        try:
            # Check if user already exists
            try:
                firebase_user = auth.get_user_by_email(emp_email)
                emp_uid = firebase_user.uid
                is_new_user = False
            except auth.UserNotFoundError:
                # Create NEW USER
                firebase_user = auth.create_user(
                    email=emp_email,
                    display_name=emp_data["name"]
                )
                emp_uid = firebase_user.uid
                is_new_user = True

            # Save/Update PII in Firestore
            fs_db.collection("employees").document(emp_uid).set({
                "name": emp_data["name"],
                "email": emp_email,
                "corporate_id": corporate_id,
                "updatedAt": firestore.SERVER_TIMESTAMP
            }, merge=True)

            # Save/Update operational data in MongoDB
            permissions = emp_data.get("permissions", {})
            if isinstance(permissions, str):
                import json
                try:
                    permissions = json.loads(permissions)
                except Exception as e:
                    logger.warning(
                        f"[users] permissions JSON パース失敗、デフォルト値を使用: {e}"
                    )
                    permissions = {}

            await db["employees"].update_one(
                {"firebase_uid": emp_uid},
                {"$set": {
                    "corporate_id": corporate_id,
                    "role": emp_data.get("role", "staff"),
                    "permissions": permissions,
                    "usageFee": emp_data.get("usageFee", 0),
                    "departmentId": emp_data.get("departmentId", ""),
                    "groupId": emp_data.get("groupId", ""),
                    # also save name and email to MongoDB for dev fallback
                    "name": emp_data.get("name", ""),
                    "email": emp_data.get("email", ""),
                }},
                upsert=True
            )

            if is_new_user:
                # Trigger reset email natively
                api_key = settings.FIREBASE_API_KEY
                if api_key:
                    reset_url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"
                    reset_payload = {
                        "requestType": "PASSWORD_RESET",
                        "email": emp_email
                    }
                    async with httpx.AsyncClient() as client:
                        res = await client.post(reset_url, json=reset_payload)
                        if res.status_code == 200:
                            print(f">>> INVITATION EMAIL successfully triggered for {emp_email}")
            
            processed.append({"email": emp_email, "uid": emp_uid, "status": "synced" if not is_new_user else "invited"})

        except Exception as e:
            print(f"Failed to process employee {emp_email}: {e}")
            processed.append({"email": emp_email, "status": "failed", "error": str(e)})

    print(f">>> SYNC EMPLOYEES: PARENT={parent_uid}, COUNT={len(processed)}")
    return {"message": f"Processed {len(processed)} employees.", "data": processed}

@router.get("/employees", status_code=status.HTTP_200_OK)
async def get_employees(
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint to retrieve the list of employees for a corporate/tax firm entity.
    """
    db = get_database()
    firebase_uid = current_user.get("uid")
    
    if not firebase_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    # Resolve corporate_id to query colleagues
    from bson import ObjectId as BsonObjectId
    calling_employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if calling_employee and calling_employee.get("corporate_id"):
        corporate_id = calling_employee.get("corporate_id")
    else:
        corp = await db["corporates"].find_one({"firebase_uid": firebase_uid}, {"_id": 1})
        if not corp:
            return []
        corporate_id = str(corp["_id"])

    # Fetch employees from MongoDB matching the corporate_id
    cursor = db["employees"].find({"corporate_id": corporate_id})
    employees = await cursor.to_list(length=1000)
    
    emp_data = []
    if employees:
        from firebase_admin import firestore
        fs_db = firestore.client()
        emp_uids = [e["firebase_uid"] for e in employees]
        refs = [fs_db.collection("employees").document(uid) for uid in emp_uids]
        emp_docs = fs_db.get_all(refs)
        
        emp_pii_map = {}
        for doc in emp_docs:
            if doc.exists:
                emp_pii_map[doc.id] = doc.to_dict()
                
        for e in employees:
            e["_id"] = str(e["_id"])
            pii = emp_pii_map.get(e["firebase_uid"], {})
            # Firestore PII takes precedence; fall back to MongoDB fields (e.g. seed data)
            e["name"] = pii.get("name") or e.get("name", "")
            e["email"] = pii.get("email") or e.get("email", "")
            emp_data.append(e)

    return emp_data

@router.patch("/employees/{employee_id}", status_code=status.HTTP_200_OK)
async def update_employee(
    employee_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an employee's operational fields (role, permissions, usageFee) in MongoDB only.
    Does not touch Firebase Auth or Firestore PII.
    """
    from bson import ObjectId as BsonObjectId
    db = get_database()
    caller_uid = current_user.get("uid")

    if not caller_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    # Resolve corporate_id and verify caller has admin/manager role
    caller_emp = await db["employees"].find_one({"firebase_uid": caller_uid})
    if caller_emp and caller_emp.get("corporate_id"):
        corporate_id = caller_emp.get("corporate_id")
        # Employees must have admin or manager role to update other employees
        caller_role = caller_emp.get("role", "staff")
        if caller_role not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="従業員情報の更新には管理者または管理職の権限が必要です。")
    else:
        # Corporate entity itself (owner) can always update employees
        corp = await db["corporates"].find_one({"firebase_uid": caller_uid}, {"_id": 1})
        corporate_id = str(corp["_id"]) if corp else None
        if not corp:
            raise HTTPException(status_code=403, detail="アクセス権限がありません。")

    # Verify the target employee belongs to this corporate
    try:
        oid = BsonObjectId(employee_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid employee ID format")

    target = await db["employees"].find_one({"_id": oid, "corporate_id": corporate_id})
    if not target:
        raise HTTPException(status_code=404, detail="Employee not found or access denied")

    # Only allow updating safe operational fields
    allowed = {"role", "permissions", "usageFee", "departmentId", "groupId", "bank_display_name"}
    update_data = {k: v for k, v in payload.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    await db["employees"].update_one({"_id": oid}, {"$set": update_data})
    return {"status": "updated", "employee_id": employee_id}


@router.delete("/employees/{employee_id}", status_code=status.HTTP_200_OK)
async def delete_employee(
    employee_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint to completely remove an employee from Firebase Auth, Firestore, and MongoDB.
    Only the parent entity (or authorized proxy) should be able to do this.
    """
    db = get_database()
    parent_firebase_uid = current_user.get("uid")
    
    if not parent_firebase_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    # Resolve corporate_id for ownership check
    from bson import ObjectId as BsonObjectId
    current_employee = await db["employees"].find_one({"firebase_uid": parent_firebase_uid})
    if current_employee and current_employee.get("corporate_id"):
        corporate_id = current_employee.get("corporate_id")
    else:
        corp = await db["corporates"].find_one({"firebase_uid": parent_firebase_uid}, {"_id": 1})
        corporate_id = str(corp["_id"]) if corp else None

    # 1. Verify the employee belongs to this corporate (ObjectId only)
    try:
        from bson import ObjectId as EmpObjectId
        emp_oid = EmpObjectId(employee_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid employee ID format")

    target_emp = await db["employees"].find_one({
        "_id": emp_oid,
        "corporate_id": corporate_id
    })
    
    if not target_emp:
        raise HTTPException(status_code=404, detail="Employee not found or access denied")

    target_uid = target_emp["firebase_uid"]

    # 2. Delete from Firebase Auth
    from firebase_admin import auth, firestore
    try:
        auth.delete_user(target_uid)
    except auth.UserNotFoundError:
        pass # Already gone from Auth, proceed with DB cleanup
    except Exception as e:
        print(f"Failed to delete Firebase Auth user: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove user authentication")

    # 3. Delete from Firestore PII
    fs_db = firestore.client()
    try:
        fs_db.collection("employees").document(target_uid).delete()
    except Exception as e:
        print(f"Failed to delete Firestore PII: {e}")

    # 4. Delete from MongoDB
    await db["employees"].delete_one({"firebase_uid": target_uid})

    return {"message": "User successfully deleted"}

@router.get("/me", status_code=status.HTTP_200_OK)
async def get_my_profile(
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint to retrieve the current user's profile from MongoDB using their Firebase UID.
    This is useful for the frontend to determine where to redirect the user after login.
    """
    db = get_database()
    firebase_uid = current_user.get("uid")
    
    if not firebase_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    # Check corporates collection (for Founders / Admins)
    corporate = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if corporate:
        corporate["_id"] = str(corporate["_id"]) # Serialize ObjectId
        
        from firebase_admin import firestore
        fs_db = firestore.client()
        doc = fs_db.collection("corporates").document(firebase_uid).get()
        if doc.exists:
            pii_data = doc.to_dict()
            corporate["companyName"] = pii_data.get("companyName", "Unknown Company")
            corporate["address"] = pii_data.get("address", "")
            corporate["loginEmail"] = pii_data.get("loginEmail", "")
            
        print(f">>> GET /ME: FOUND ADMIN UID={firebase_uid}, TYPE={corporate.get('corporateType')}")
        return {"type": corporate.get("corporateType"), "data": corporate}

    # Check employees collection (for Staff)
    employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if employee:
        employee["_id"] = str(employee["_id"])
        
        # We might need to know parent's corporateType to route correctly too
        from bson import ObjectId as BsonObjectId
        corp_id = employee.get("corporate_id")
        parent = await db["corporates"].find_one({"_id": BsonObjectId(corp_id)}) if corp_id else None
        parent_type = parent.get("corporateType") if parent else "corporate"
        
        from firebase_admin import firestore
        fs_db = firestore.client()
        doc = fs_db.collection("employees").document(firebase_uid).get()
        if doc.exists:
            pii_data = doc.to_dict()
            employee["name"] = pii_data.get("name", "Unknown User")
            employee["email"] = pii_data.get("email", "")

        # Inject parent data for dashboards to read directly
        if parent:
            employee["planId"] = parent.get("planId")
            employee["monthlyFee"] = parent.get("monthlyFee")
            parent_doc = fs_db.collection("corporates").document(parent.get("firebase_uid")).get()
            if parent_doc.exists:
                employee["companyName"] = parent_doc.to_dict().get("companyName", "")
            
        print(f">>> GET /ME: FOUND EMPLOYEE UID={firebase_uid}, PARENT_TYPE={parent_type}")
        return {"type": "employee", "parent_type": parent_type, "data": employee}

    print(f">>> GET /ME: USER NOT FOUND IN DB UID={firebase_uid}")
    raise HTTPException(status_code=404, detail="User profile not found in database")

@router.get("/clients", status_code=status.HTTP_200_OK)
async def get_clients(
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint for Tax Firms to list all their affiliated corporates.
    It queries MongoDB for operational data (plan, status) and Firestore for PII (CompanyName).
    """
    db = get_database()
    firebase_uid = current_user.get("uid")

    if not firebase_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    # Resolve effective firebase_uid (for employees, resolve via corporate_id → parent corporate)
    from bson import ObjectId as BsonObjectId
    effective_uid = firebase_uid
    calling_emp = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if calling_emp and calling_emp.get("corporate_id"):
        parent_corp = await db["corporates"].find_one(
            {"_id": BsonObjectId(calling_emp["corporate_id"])}, {"firebase_uid": 1}
        )
        if parent_corp:
            effective_uid = parent_corp["firebase_uid"]

    # 1. Fetch matching clients from MongoDB
    clients_cursor = db["corporates"].find({
        "corporateType": "corporate",
        "advising_tax_firm_id": effective_uid
    })
    
    clients = await clients_cursor.to_list(length=1000)
    
    if not clients:
        return {"data": []}

    # Extract all client UIDs to fetch names from Firestore
    client_uids = [c["firebase_uid"] for c in clients]

    # 2. Fetch PII (companyName) from Firestore
    from firebase_admin import firestore
    fs_db = firestore.client()
    
    name_map = {}
    
    chunk_size = 100
    for i in range(0, len(client_uids), chunk_size):
        chunk = client_uids[i:i + chunk_size]
        refs = [fs_db.collection("corporates").document(uid) for uid in chunk]
        
        # get_all handles batch fetching efficiently
        docs = fs_db.get_all(refs)
        for doc in docs:
            if doc.exists:
                data = doc.to_dict()
                name_map[doc.id] = data.get("companyName", "Unknown Company")
            
    # 3. Combine MongoDB data with Firestore names and aggregate usage fees
    enriched_clients = []
    
    # 3.1 Fetch all employees for these clients to aggregate usage fees
    # Map: corporate ObjectId string → firebase_uid (for fee_map key lookup)
    corp_id_to_uid = {str(c["_id"]): c["firebase_uid"] for c in clients}
    client_corporate_ids = list(corp_id_to_uid.keys())
    employees_cursor = db["employees"].find({"corporate_id": {"$in": client_corporate_ids}})
    all_employees = await employees_cursor.to_list(length=10000)

    fee_map = {uid: 0 for uid in client_uids}
    user_count_map = {uid: 0 for uid in client_uids}

    for emp in all_employees:
        p_uid = corp_id_to_uid.get(emp.get("corporate_id"))
        if p_uid and p_uid in fee_map:
            fee_map[p_uid] += emp.get("usageFee", 0)
            user_count_map[p_uid] += 1

    # ③ billing_settings を一括取得（Firestore 取得後・enriched_clients ループ前）
    billing_uids = [c["firebase_uid"] for c in clients]
    billing_cursor = db["billing_settings"].find({
        "tax_firm_id": effective_uid,
        "target_corporate_id": {"$in": billing_uids},
    })
    billing_docs = await billing_cursor.to_list(length=1000)
    billing_map = {b["target_corporate_id"]: b for b in billing_docs}

    for c in clients:
        c["_id"] = str(c["_id"])
        uid = c["firebase_uid"]
        c["companyName"] = name_map.get(uid, "Unknown Company")

        # Add real aggregated stats
        c["totalUsageFee"] = fee_map.get(uid, 0)
        c["employeeCount"] = user_count_map.get(uid, 0)

        # Add some mock stats for the UI until real tables exist
        c["approvalRate"] = 100
        c["appCount"] = 0
        c["approvalCount"] = 0
        c["status"] = "Onboarding"
        c["maStatus"] = c.get("maIntent", "none")
        c["assignee"] = "未設定"
        c["monthlyFee"] = c.get("monthlyFee", 0)

        # billing_settings から月額合計を計算（totalUsageFee と別フィールドで返す）
        billing = billing_map.get(uid)
        if billing and billing.get("is_active"):
            corp_price = billing.get("corporate_unit_price", 0)
            user_price = billing.get("user_unit_price", 0)
            emp_count = c.get("employeeCount", 0)
            c["monthlyBillingTotal"] = corp_price + user_price * emp_count
            c["billingIsActive"] = True
        else:
            c["monthlyBillingTotal"] = 0
            c["billingIsActive"] = False

        enriched_clients.append(c)

    return {"data": enriched_clients}

@router.put("/clients/{client_id}", status_code=status.HTTP_200_OK)
async def update_client(
    client_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint for Tax Firms to update affiliated corporate info.
    Updates MongoDB and Firestore.
    """
    from bson import ObjectId
    db = get_database()
    firebase_uid = current_user.get("uid")
    
    # Resolve effective firebase_uid
    from bson import ObjectId as BsonObjectId
    effective_uid = firebase_uid
    calling_emp = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if calling_emp and calling_emp.get("corporate_id"):
        parent_corp = await db["corporates"].find_one(
            {"_id": BsonObjectId(calling_emp["corporate_id"])}, {"firebase_uid": 1}
        )
        if parent_corp:
            effective_uid = parent_corp["firebase_uid"]

    try:
        obj_id = ObjectId(client_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid client ID format")

    # Verify ownership
    target_corporate = await db["corporates"].find_one({
        "_id": obj_id,
        "corporateType": "corporate",
        "advising_tax_firm_id": effective_uid
    })

    if not target_corporate:
        raise HTTPException(status_code=404, detail="Client not found or access denied")

    target_uid = target_corporate["firebase_uid"]

    # Update MongoDB
    update_data = {}
    if "companyUrl" in payload: update_data["companyUrl"] = payload["companyUrl"]
    if "maIntent" in payload: update_data["maIntent"] = payload["maIntent"]
    
    if update_data:
        await db["corporates"].update_one(
            {"_id": obj_id},
            {"$set": update_data}
        )

    # Update Firestore
    fs_update = {}
    if "companyName" in payload: fs_update["companyName"] = payload["companyName"]
    if "companyUrl" in payload: fs_update["companyUrl"] = payload["companyUrl"]
    if "address" in payload: fs_update["address"] = payload["address"]
    if "maIntent" in payload: fs_update["maIntent"] = payload["maIntent"]
    if "phone" in payload: fs_update["phone"] = payload["phone"]
    if "registrationNumber" in payload: fs_update["registrationNumber"] = payload["registrationNumber"]

    if fs_update:
        from firebase_admin import firestore
        fs_db = firestore.client()
        try:
            fs_db.collection("corporates").document(target_uid).update(fs_update)
        except Exception as e:
            print(f"Failed to update Firestore for client {client_id}: {e}")

    return {"message": "Client updated successfully"}

@router.get("/clients/{client_id}", status_code=status.HTTP_200_OK)
async def get_client_detail(
    client_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint for Tax Firms to get the details of a specific client, including their employees.
    """
    db = get_database()
    firebase_uid = current_user.get("uid")

    if not firebase_uid:
        raise HTTPException(status_code=400, detail="Invalid auth token format")

    from bson import ObjectId
    try:
        obj_id = ObjectId(client_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid client ID format")

    # Resolve effective firebase_uid
    from bson import ObjectId as BsonObjectId
    effective_uid = firebase_uid
    calling_emp = await db["employees"].find_one({"firebase_uid": firebase_uid})
    if calling_emp and calling_emp.get("corporate_id"):
        parent_corp = await db["corporates"].find_one(
            {"_id": BsonObjectId(calling_emp["corporate_id"])}, {"firebase_uid": 1}
        )
        if parent_corp:
            effective_uid = parent_corp["firebase_uid"]

    # 1. Fetch matching client from MongoDB by ObjectID
    client_doc = await db["corporates"].find_one({
        "_id": obj_id,
        "corporateType": "corporate",
        "advising_tax_firm_id": effective_uid
    })

    if not client_doc:
        raise HTTPException(status_code=404, detail="Client not found or access denied")

    client_corporate_id = str(client_doc["_id"])
    client_uid = client_doc["firebase_uid"]
    client_doc["_id"] = client_corporate_id

    # 2. Fetch PII from Firestore
    from firebase_admin import firestore
    fs_db = firestore.client()
    
    fs_doc = fs_db.collection("corporates").document(client_uid).get()
    if fs_doc.exists:
        pii = fs_doc.to_dict()
        client_doc["companyName"] = pii.get("companyName", "")
        # fallback to mongo if firestore is missing the url/intent
        client_doc["companyUrl"] = pii.get("companyUrl", client_doc.get("companyUrl", ""))
        client_doc["address"] = pii.get("address", "")
        client_doc["maIntent"] = pii.get("maIntent", client_doc.get("maIntent", ""))
        client_doc["loginEmail"] = pii.get("loginEmail", "")
        client_doc["phone"] = pii.get("phone", None)
        client_doc["registrationNumber"] = pii.get("registrationNumber", None)
        
    # 3. Fetch Employees for this client
    employees_cursor = db["employees"].find({"corporate_id": client_corporate_id})
    employees = await employees_cursor.to_list(length=100)
    emp_data = []
    
    if employees:
        emp_uids = [e["firebase_uid"] for e in employees]
        refs = [fs_db.collection("employees").document(uid) for uid in emp_uids]
        emp_docs = fs_db.get_all(refs)
        
        emp_pii_map = {}
        for doc in emp_docs:
            if doc.exists:
                emp_pii_map[doc.id] = doc.to_dict()
                
        for e in employees:
            e["_id"] = str(e["_id"])
            pii = emp_pii_map.get(e["firebase_uid"], {})
            # Firestore PII takes precedence; fall back to MongoDB fields (e.g. seed data)
            e["name"] = pii.get("name") or e.get("name", "")
            e["email"] = pii.get("email") or e.get("email", "")
            emp_data.append(e)

    return {
        "data": {
            "client": client_doc,
            "employees": emp_data
        }
    }

@router.put("/clients/{client_id}/employees", status_code=status.HTTP_200_OK)
async def sync_client_employees(
    client_id: str,
    payload: list[dict],
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint for Tax Firms to sync (create/update) employees for a client during edit mode.
    """
    try:
        from bson import ObjectId
        db = get_database()
        firebase_uid = current_user.get("uid")

        if not firebase_uid:
            raise HTTPException(status_code=400, detail="Invalid auth token format")

        try:
            obj_id = ObjectId(client_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid client ID format")

        from bson import ObjectId as BsonObjectId
        effective_uid = firebase_uid
        calling_emp = await db["employees"].find_one({"firebase_uid": firebase_uid})
        if calling_emp and calling_emp.get("corporate_id"):
            parent_corp = await db["corporates"].find_one(
                {"_id": BsonObjectId(calling_emp["corporate_id"])}, {"firebase_uid": 1}
            )
            if parent_corp:
                effective_uid = parent_corp["firebase_uid"]

        client_doc = await db["corporates"].find_one({
            "_id": obj_id,
            "advising_tax_firm_id": effective_uid
        })

        if not client_doc:
            raise HTTPException(status_code=404, detail="Client not found or access denied")

        parent_uid = client_doc["firebase_uid"]

        return await _sync_employees_internal(parent_uid, payload)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"DEBUG SYNC EXCEPTION: {error_trace}")
        raise HTTPException(status_code=500, detail=str(error_trace))


# ─────────────────────────────────────────────────────────────────────────────
# Task#30追加：解約エンドポイント
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/cancel", summary="サービスを解約する")
async def cancel_service(
    current_user: dict = Depends(get_current_user),
):
    """
    サービスを解約する。
    法人オーナー・admin 従業員の両方が実行可能。
    resolve_corporate_id で両者を統一的に処理する。

    - Stripe Subscription をキャンセル
    - corporates.is_active = False
    - corporates.cancelled_at を記録
    - データは論理削除しない（is_deleted はセットしない）
    - 税理士法人が解約した場合は配下法人も is_active=False にする
    """
    firebase_uid = current_user.get("uid")
    db = get_database()

    # ② resolve_corporate_id でオーナー・admin 従業員を統一処理
    corporate_id, _ = await resolve_corporate_id(firebase_uid)

    # ロールチェック：admin のみ解約可能
    # 法人オーナー（corporates に firebase_uid が存在）は常に admin 扱い
    # 従業員（employees に存在）は role=admin のみ許可
    caller_corp = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if not caller_corp:
        caller_emp = await db["employees"].find_one({"firebase_uid": firebase_uid})
        if not caller_emp or caller_emp.get("role") != "admin":
            raise HTTPException(status_code=403, detail="解約は管理者のみ実行できます")

    corporate = await db["corporates"].find_one({"_id": ObjectId(corporate_id)})
    if not corporate:
        raise HTTPException(status_code=404, detail="法人情報が見つかりません")

    if not corporate.get("is_active", False):
        raise HTTPException(status_code=400, detail="既に解約済みです")

    # Stripe Subscription のキャンセル（subscription_id がある場合のみ）
    # ⑤ 例外が発生しても解約処理を止めない（ログのみ）
    stripe_sub_id = corporate.get("stripe_subscription_id")
    if stripe_sub_id:
        from app.services.stripe_service import cancel_subscription
        import logging as _logging
        try:
            await cancel_subscription(stripe_sub_id)
        except Exception as e:
            _logging.getLogger(__name__).error(
                f"[Cancel] Stripe キャンセル失敗（処理は続行） sub={stripe_sub_id}: {e}"
            )

    now = datetime.utcnow()

    # 自法人を is_active=False に更新
    await db["corporates"].update_one(
        {"_id": ObjectId(corporate_id)},
        {
            "$set": {
                "is_active": False,
                "stripe_subscription_id": None,
                "cancelled_at": now,
                "updated_at": now,
            }
        },
    )

    # 税理士法人の場合は配下法人も is_active=False にする
    # advising_tax_firm_id は firebase_uid（corporates の _id ではない）で保存されている
    corp_firebase_uid = corporate.get("firebase_uid", "")
    if corporate.get("corporateType") == "tax_firm" and corp_firebase_uid:
        await db["corporates"].update_many(
            {"advising_tax_firm_id": corp_firebase_uid},
            {
                "$set": {
                    "is_active": False,
                    "cancelled_at": now,
                    "updated_at": now,
                }
            },
        )

    return {
        "status": "cancelled",
        "cancelled_at": now.isoformat(),
    }
