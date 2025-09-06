from utils.env_vars import *
import pymssql
import sys

# Database Creds
db_server = DATABASE_SERVER
db_user = DATABASE_USERNAME
db_pass = DATABASE_PASSWORD
db_name = DATABASE_NAME

table = "agentic_campaign_images"  # or "dbo.agentic_campaign_images"

conn = None
cursor = None

try:
    conn = pymssql.connect(
        server=db_server,
        user=db_user,
        password=db_pass,
        database=db_name,
    )
    cursor = conn.cursor(as_dict=True)
    print("Connected to SQL server")
except Exception as e:
    print("Connection failed:", e)
    sys.exit(1)

# Split schema and table if provided as "schema.table"
if "." in table:
    owner, table_name = table.split(".", 1)
else:
    owner, table_name = "dbo", table

try:
    # Create the table if it doesn't exist
    create_table_query = f"""
    IF OBJECT_ID('{owner}.{table_name}', 'U') IS NULL
    BEGIN
        CREATE TABLE {owner}.{table_name} (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username NVARCHAR(255) NOT NULL,
            campaign_name NVARCHAR(255) NOT NULL,
            post_id NVARCHAR(255) NOT NULL,
            image_base64 NVARCHAR(MAX) NULL,
            image_s3_key NVARCHAR(MAX) NULL,
            prompt_used NVARCHAR(MAX) NULL,
            generation_model NVARCHAR(255) NULL,
            created_at DATETIME DEFAULT GETDATE(),
            CONSTRAINT FK_AgenticCampaign FOREIGN KEY (username, campaign_name)
            REFERENCES dbo.agentic_campaign_planner (username, campaign_name) ON DELETE CASCADE
        );
    END
    """
    cursor.execute(create_table_query)
    conn.commit()
    print(f"Table {owner}.{table_name} created or already exists.")

    # Parameterized call to avoid quoting issues
    cursor.execute(
        "EXEC sp_columns @table_name=%s, @table_owner=%s",
        (table_name, owner),
    )
    columns = cursor.fetchall()

    if not columns:
        print(f"No columns found in table {owner}.{table_name}")
    else:
        print(f"\nColumns in table {owner}.{table_name}:")
        for col in columns:
            column_name = col.get("COLUMN_NAME")
            data_type = col.get("TYPE_NAME")
            print(f"- {column_name} ({data_type})")

except Exception as e:
    print("Failed to create table or retrieve columns:", e)
finally:
    try:
        if cursor is not None:
            cursor.close()
    finally:
        if conn is not None:
            conn.close()



# Updated API Code for Image Upload and Response Modification

Based on the requirements:
- **Upload API**: A new endpoint to upload an image file, convert it to Base64 (as data URL), and associate it with a `post_id` (e.g., "email_week_1_Day_1"). The Base64 will be stored in the database for retrieval.
- **Response Modification**: Update the existing `GET /{username}/{campaign_name}/responses` to inject an `"images"` array into each post's structure (e.g., under "Day_2") with Base64 data URLs.
- **Format**: Ensure the campaign_plan output matches the specified structure, using data URL Base64 (e.g., "data:image/jpg;base64,abcd212==").

I've integrated this with the new `agentic_campaign_images` table from previous updates. Images are stored as Base64 in the DB for simplicity (though in production, store in S3 and reference keys). Unchanged code is omitted for brevity.

***

## 1. Database Schema Update (if not already applied)
Ensure the `agentic_campaign_images` table exists with a new column for Base64:

```sql
-- Add base64 column if not present (update to existing table)
ALTER TABLE agentic_campaign_images ADD COLUMN IF NOT EXISTS image_base64 TEXT;
```

## 2. Updated `operations.py`
Add Base64 handling in insert and list functions.

```python
# ... (Existing code remains)

def insert_campaign_image(
    username: str,
    campaign_name: str,
    post_id: str,
    image_base64: str,  # NEW: Store Base64 directly
    image_s3_key: str = None,  # Optional S3 key
    prompt_used: str = None,
    generation_model: str = None
) -> bool:
    query = text("""
        INSERT INTO agentic_campaign_images (
            username, campaign_name, post_id, 
            image_base64, image_s3_key, prompt_used, generation_model
        )
        VALUES (
            :username, :campaign_name, :post_id,
            :image_base64, :image_s3_key, :prompt_used, :generation_model
        )
        RETURNING id
    """)
    params = {
        "username": username,
        "campaign_name": campaign_name,
        "post_id": post_id,
        "image_base64": image_base64,
        "image_s3_key": image_s3_key,
        "prompt_used": prompt_used,
        "generation_model": generation_model
    }
    result = execute_query(query, params=params, fetch_one=True, commit=True)
    return result is not None

def list_campaign_images(
    username: str,
    campaign_name: str,
    post_id: str = None
) -> list[dict]:
    base_query = """
        SELECT id, post_id, image_base64, image_s3_key, prompt_used, generation_model, created_at
        FROM agentic_campaign_images
        WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
          AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
    """
    if post_id:
        base_query += " AND TRIM(LOWER(post_id)) = TRIM(LOWER(:post_id))"
    
    base_query += " ORDER BY created_at DESC"
    
    query = text(base_query)
    params = {"username": username, "campaign_name": campaign_name}
    if post_id:
        params["post_id"] = post_id
    
    results = execute_query(query, params=params, fetch_all=True) or []
    return [
        {
            "id": row[0],
            "post_id": row[1],
            "image_base64": row[2],  # NEW: Include Base64
            "image_s3_key": row[3],
            "prompt_used": row[4],
            "generation_model": row[5],
            "created_at": row[6]
        }
        for row in results
    ]
```

## 3. Updated `api.py`
- New upload endpoint: Handles file upload, Base64 conversion, and DB insert.
- Modified responses endpoint: Fetches images from DB and injects `"images"` array into the campaign_plan structure.

```python
# ... (Existing imports)

import base64
from fastapi import UploadFile, File

# NEW: Image Upload Endpoint
@router.post("/{username}/{campaign_name}/upload-image/{post_id}")
async def upload_post_image(
    username: str,
    campaign_name: str,
    post_id: str,  # e.g., "email_week_1_Day_1"
    file: UploadFile = File(...),
    prompt_used: Optional[str] = Form(None),
    generation_model: Optional[str] = Form(None)
) -> dict:
    """
    Upload an image for a specific post_id, convert to Base64 data URL, 
    and store in DB. Returns the Base64 for confirmation.
    """
    try:
        # Validate file type
        if not file.content_type.startswith("image/"):
            raise HTTPException(400, "Only image files are allowed.")
        
        # Read file and encode to Base64
        file_data = await file.read()
        normal_base64 = base64.b64encode(file_data).decode("utf-8")
        data_url_base64 = f"data:{file.content_type};base64,{normal_base64}"
        
        # Optional: Upload to S3 and get key (if you want dual storage)
        s3_key = None  # Implement S3 upload if needed, e.g., upload_to_s3(file_data, post_id)
        
        # Insert into DB
        success = insert_campaign_image(
            username=username,
            campaign_name=campaign_name,
            post_id=post_id,
            image_base64=data_url_base64,
            image_s3_key=s3_key,
            prompt_used=prompt_used,
            generation_model=generation_model
        )
        if not success:
            raise HTTPException(500, "Failed to store image metadata.")
        
        return {
            "success": True,
            "message": "Image uploaded and stored successfully",
            "post_id": post_id,
            "image_base64": data_url_base64  # Return for immediate use
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading image: {e}")
        raise HTTPException(500, f"Error uploading image: {str(e)}")

# MODIFIED: Existing Responses Endpoint with Images Injection
@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(username: str, campaign_name: str):
    """Endpoint to retrieve responses with images injected into campaign_plan."""
    try:
        responses = fetch_campaign_responses(username, campaign_name)
        if not responses:
            raise HTTPException(404, f"No campaign found for user '{username}' with campaign '{campaign_name}'")
        
        # Parse JSON fields (existing logic)
        json_fields = [
            "plan_response", "approve_response", "feedback_response",
            "approved_plan_v1", "approved_plan_v2", "approved_plan_v3",
            "human_feedback_v1", "human_feedback_v2", "human_feedback_v3"
        ]
        for key in json_fields:
            if key in responses and responses.get(key):
                try:
                    responses[key] = json.loads(responses[key])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse {key} for '{username}/{campaign_name}'")
                    raise HTTPException(500, f"Failed to parse {key} into JSON.")
        
        # NEW: Fetch all images for this campaign
        images = list_campaign_images(username, campaign_name)
        
        # Group images by post_id (dict: post_id -> list of base64)
        images_by_post = {}
        for img in images:
            pid = img["post_id"]
            if pid not in images_by_post:
                images_by_post[pid] = []
            images_by_post[pid].append(img["image_base64"])  # Add Base64 data URL
        
        # NEW: Inject "images" into each campaign_plan's day structures
        def inject_images(plan_data: dict):
            if "campaign_plan" not in plan_data:
                return
            campaign_plan = plan_data["campaign_plan"]
            for platform, weeks in campaign_plan.items():
                for week_key, days in weeks.items():
                    for day_key, post in days.items():
                        # Construct post_id like "email_week_1_Day_1"
                        post_id = f"{platform.lower()}_{week_key.lower()}_{day_key.replace(' ', '_').lower()}"
                        post["images"] = images_by_post.get(post_id, [])  # Inject array of Base64
        
        # Apply injection to all relevant responses
        for key in json_fields:
            if key in responses and isinstance(responses[key], dict):
                inject_images(responses[key])
        
        return responses
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve responses: {str(e)}")
        raise HTTPException(500, f"Failed to retrieve responses: {str(e)}")
```

***

### Example Output Structure
After modification, a sample day in `campaign_plan` (e.g., from approve_response) would look like:

```json
"Day_2": {
    "task": "Craft unique, inspiring success stories highlighting financial transformation.",
    "content": "**Day 2: InslConfidence",
    "images": [
        "data:image/jpg;base64,abcd212==",
        "data:image/jpg;base64,ibase64"
    ],
    "human_feedback": "",
    "regeneration_count": 0
}
```

### Notes
- **Base64 Handling**: The upload endpoint creates `dataUrlBase64` as specified.
- **S3 Integration**: I kept S3 optional; if you upload to S3, generate the key and pass to `insert_campaign_image`.
- **Security**: Add auth/validation (e.g., check if post_id exists in campaign_plan).
- **Testing**: After uploading, call the responses endpoint to see injected images.

This is the complete update. If more details are needed, provide specifics!

[1](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/42012257/52a15357-a021-46e4-b2d2-810674ad78bd/paste.txt)
